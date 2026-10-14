"""Background review execution service.

Fetches PR diff, executes the LangGraph review pipeline, and persists
findings, traces, and accounting metrics to the database.
"""

import logging
from datetime import datetime

from backend.app.agents.graph import run_review_pipeline
from backend.app.core.config import get_settings
from backend.app.core.database import async_session_factory
from backend.app.llm.factory import create_llm_client
from backend.app.repositories.finding import FindingRepository
from backend.app.repositories.review import ReviewRepository
from backend.app.schemas.finding import FindingCreate
from backend.app.services.github_client import GitHubClient

logger = logging.getLogger(__name__)


async def execute_review(review_id: int) -> None:
    """Execute the multi-agent review pipeline for a queued review record.

    Transitions review status: queued -> running -> completed (or partial/failed).
    """
    settings = get_settings()
    started_at = datetime.utcnow()

    async with async_session_factory() as session:
        review_repo = ReviewRepository(session)
        review = await review_repo.get_by_id(review_id)
        if review is None:
            logger.error("execute_review: Review id %d not found", review_id)
            return

        pr = review.pull_request
        repo = pr.repository

        # Mark as running
        review.status = "running"
        review.started_at = started_at
        await session.commit()

        owner = repo.owner
        repo_name = repo.name
        pr_number = pr.number
        head_sha = pr.head_sha
        model = review.model

        config_data = review.config or {}
        config_type = "multi_agent_judge"
        if isinstance(config_data, dict):
            config_type = config_data.get("system", "multi_agent_judge")
        elif isinstance(config_data, str):
            config_type = config_data

        # Ensure config_type is a valid literal
        if config_type not in {"single_agent", "multi_agent_no_judge", "multi_agent_judge"}:
            config_type = "multi_agent_judge"

        logger.info(
            "Executing review %d for %s/%s PR #%d (model=%s, config=%s)",
            review_id,
            owner,
            repo_name,
            pr_number,
            model,
            config_type,
        )

        async with GitHubClient(token=settings.github_token) as github_client:
            try:
                # 1. Fetch PR diff
                diff_text = await github_client.get_pull_request_diff(
                    owner=owner,
                    repo=repo_name,
                    pull_number=pr_number,
                )
                if not diff_text or not diff_text.strip():
                    logger.warning("Empty diff for review %d", review_id)
                    diff_text = ""

                # 2. Fetch metadata
                pr_meta = await github_client.get_pull_request(
                    owner=owner,
                    repo=repo_name,
                    pull_number=pr_number,
                )

                # 3. Create LLM client
                llm_client = create_llm_client(settings=settings, model=model)

                # 4. Run pipeline
                state = await run_review_pipeline(
                    owner=owner,
                    repo=repo_name,
                    pull_number=pr_number,
                    head_sha=head_sha,
                    diff_text=diff_text,
                    metadata=pr_meta,
                    config=config_type,  # type: ignore[arg-type]
                    model=model,
                    dry_run=True,
                    review_id=review_id,
                    llm_client=llm_client,
                    github_client=github_client,
                )

                # 5. Persist findings
                finding_repo = FindingRepository(session)
                findings_to_create: list[FindingCreate] = []

                for f in state.get("final_findings", []):
                    agent_name = getattr(f, "agent", None) or "judge"
                    findings_to_create.append(
                        FindingCreate(
                            review_id=review_id,
                            agent=agent_name,
                            category=f.category,
                            severity=f.severity,
                            file=f.file,
                            line_start=f.line_start,
                            line_end=f.line_end,
                            title=f.title,
                            explanation=f.explanation,
                            evidence=f.evidence,
                            suggested_fix=f.suggested_fix,
                            confidence=f.confidence,
                            status="active",
                            merged_from=getattr(f, "merged_from", None),
                            decision_reason=getattr(f, "decision_reason", None),
                        )
                    )

                for df in state.get("dropped_findings", []):
                    findings_to_create.append(
                        FindingCreate(
                            review_id=review_id,
                            agent=getattr(df.finding, "agent", "validator"),
                            category=df.finding.category,
                            severity=df.finding.severity,
                            file=df.finding.file,
                            line_start=df.finding.line_start,
                            line_end=df.finding.line_end,
                            title=df.finding.title,
                            explanation=df.finding.explanation,
                            evidence=df.finding.evidence,
                            suggested_fix=df.finding.suggested_fix,
                            confidence=df.finding.confidence,
                            status="dropped",
                            drop_reason=getattr(df, "drop_reason", "Filtered out"),
                        )
                    )

                if findings_to_create:
                    await finding_repo.create_findings_batch(findings_to_create)

                # 6. Update review record
                finished_at = datetime.utcnow()
                prompt_tokens = state.get("tokens_prompt", 0)
                comp_tokens = state.get("tokens_completion", 0)
                tot_tokens = prompt_tokens + comp_tokens

                review.status = state.get("status", "completed")
                review.tokens_prompt = prompt_tokens
                review.tokens_completion = comp_tokens
                review.tokens_total = tot_tokens
                review.cost_usd = state.get("cost_usd", 0.0)
                review.latency_ms = int((finished_at - started_at).total_seconds() * 1000)
                review.completed_at = finished_at

                existing_config = dict(review.config or {})
                if "traces" in state:
                    existing_config["traces"] = state["traces"]
                review.config = existing_config

                await session.commit()
                logger.info(
                    "Review %d completed successfully (findings=%d, cost=$%.4f)",
                    review_id,
                    len(findings_to_create),
                    review.cost_usd,
                )

            except Exception as exc:
                logger.exception("Failed executing review %d: %s", review_id, exc)
                review.status = "failed"
                review.error_message = str(exc)
                review.completed_at = datetime.utcnow()
                await session.commit()
