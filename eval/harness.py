"""Evaluation harness for running CodeCourt review configurations against benchmark cases.

T4.2: Coordinates execution of benchmark PR cases across the three review configurations:
- single_agent (baseline)
- multi_agent_no_judge (ablation)
- multi_agent_judge (full multi-agent)

Collects case-level and run-level metrics (status, tokens, cost, latency, findings),
enforces bounded concurrency, and handles failures cleanly without crashing.
"""

import asyncio
import json
import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from backend.app.agents.graph import run_review_pipeline
from backend.app.agents.state import ReviewConfigType, ReviewState
from backend.app.llm.base import LLMClient
from backend.app.schemas.github import PullRequestMetadata
from backend.app.services.github_client import GitHubClient
from eval.schema import (
    EvalCase,
    EvalCaseFinding,
    EvalCaseResult,
    EvalRunResult,
    EvalRunSummary,
)

logger = logging.getLogger(__name__)

DEFAULT_RESULTS_DIR = Path(__file__).parent / "results"
DEFAULT_CONCURRENCY = 5


def _synthesize_pr_metadata(case: EvalCase) -> PullRequestMetadata:
    """Create standardized PullRequestMetadata for an evaluation case."""
    return PullRequestMetadata.model_validate(
        {
            "id": 9999,
            "number": 1,
            "title": case.pr_title,
            "body": case.pr_description,
            "state": "open",
            "owner": "eval-org",
            "repo": f"bench-{case.language}",
            "head_sha": "evalheadsha123",
            "base_sha": "evalbasesha000",
            "head_ref": f"eval/{case.id}",
            "base_ref": "main",
            "author": "eval-bot",
            "created_at": "2026-10-09T00:00:00Z",
            "html_url": f"https://github.com/eval-org/bench-{case.language}/pull/1",
            "diff_url": f"https://github.com/eval-org/bench-{case.language}/pull/1.diff",
        }
    )


class EvalHarness:
    """Benchmark runner executing PR cases through CodeCourt review pipelines."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        github_client: GitHubClient | None = None,
        max_concurrency: int = DEFAULT_CONCURRENCY,
        dry_run: bool = True,
    ) -> None:
        self.llm_client = llm_client
        self.github_client = github_client
        self.max_concurrency = max(1, max_concurrency)
        self.dry_run = dry_run

    async def run_case(
        self,
        case: EvalCase,
        config: ReviewConfigType = "single_agent",
        model: str = "fake-llm",
    ) -> EvalCaseResult:
        """Run a single evaluation case through the specified review pipeline."""
        start_time = time.perf_counter()
        metadata = _synthesize_pr_metadata(case)

        try:
            state: ReviewState = await run_review_pipeline(
                owner=metadata.owner,
                repo=metadata.repo,
                pull_number=metadata.number,
                head_sha=metadata.head_sha,
                diff_text=case.diff_text,
                metadata=metadata,
                config=config,
                model=model,
                dry_run=self.dry_run,
                llm_client=self.llm_client,
                github_client=self.github_client,
            )

            latency_ms = int((time.perf_counter() - start_time) * 1000)
            final_findings = state.get("final_findings", [])

            mapped_findings = [
                EvalCaseFinding(
                    category=f.category,
                    severity=f.severity,
                    file=f.file,
                    line_start=f.line_start,
                    line_end=f.line_end,
                    title=f.title,
                    explanation=f.explanation,
                    confidence=f.confidence,
                )
                for f in final_findings
            ]

            prompt_tok = state.get("tokens_prompt", 0)
            comp_tok = state.get("tokens_completion", 0)
            traces = state.get("traces", [])

            return EvalCaseResult(
                case_id=case.id,
                split=case.split,
                language=case.language,
                category=case.category,
                has_bug=case.has_bug,
                config=config,
                model=model,
                status=state.get("status", "completed"),
                error=state.get("error"),
                latency_ms=latency_ms,
                tokens_prompt=prompt_tok,
                tokens_completion=comp_tok,
                tokens_total=prompt_tok + comp_tok,
                cost_usd=round(state.get("cost_usd", 0.0), 6),
                findings=mapped_findings,
                summary=state.get("summary", ""),
                trace_node_count=len(traces),
            )

        except Exception as exc:
            logger.exception("Eval case %s failed with unexpected exception", case.id)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return EvalCaseResult(
                case_id=case.id,
                split=case.split,
                language=case.language,
                category=case.category,
                has_bug=case.has_bug,
                config=config,
                model=model,
                status="failed",
                error=str(exc),
                latency_ms=latency_ms,
            )

    async def run_benchmark(
        self,
        cases: Sequence[EvalCase],
        config: ReviewConfigType = "single_agent",
        model: str = "fake-llm",
        split_label: str = "custom",
        run_id: str | None = None,
    ) -> EvalRunResult:
        """Execute a batch of evaluation cases with bounded concurrency."""
        start_time = time.perf_counter()
        effective_run_id = run_id or f"run_{config}_{model.replace('/', '_')}_{int(time.time())}"
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _bounded_run(case: EvalCase) -> EvalCaseResult:
            async with semaphore:
                return await self.run_case(case, config=config, model=model)

        tasks = [_bounded_run(case) for case in cases]
        case_results = await asyncio.gather(*tasks)

        total_duration = time.perf_counter() - start_time

        # Aggregate summary metrics
        total_cases = len(case_results)
        completed_cases = sum(1 for r in case_results if r.status == "completed")
        partial_cases = sum(1 for r in case_results if r.status == "partial")
        failed_cases = sum(1 for r in case_results if r.status == "failed")
        total_findings = sum(len(r.findings) for r in case_results)
        total_tokens = sum(r.tokens_total for r in case_results)
        total_cost = sum(r.cost_usd for r in case_results)

        summary = EvalRunSummary(
            run_id=effective_run_id,
            config=config,
            model=model,
            split=split_label,
            total_cases=total_cases,
            completed_cases=completed_cases,
            partial_cases=partial_cases,
            failed_cases=failed_cases,
            total_findings=total_findings,
            total_tokens=total_tokens,
            total_cost_usd=round(total_cost, 6),
            duration_seconds=round(total_duration, 3),
            created_at=datetime.now(UTC).isoformat(),
        )

        return EvalRunResult(summary=summary, case_results=list(case_results))


def save_run_result(result: EvalRunResult, output_dir: Path | None = None) -> Path:
    """Save an EvalRunResult container to JSON on disk."""
    target_dir = output_dir or DEFAULT_RESULTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{result.summary.run_id}.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(), f, indent=2)

    return file_path


def load_run_result(file_path: Path) -> EvalRunResult:
    """Load an EvalRunResult container from JSON on disk."""
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    return EvalRunResult.model_validate(data)
