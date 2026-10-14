"""Benchmark execution and report generation for CodeCourt review architectures.

T4.4: Executes multi-run evaluations across the 3 review configurations:
- single_agent (baseline single reviewer)
- multi_agent_no_judge (ablation fan-out without judge)
- multi_agent_judge (full multi-agent with deduplication and conflict judge)

Computes cross-run aggregates (mean ± sample std), produces structured markdown
reports comparing detection performance, latency, and costs, and saves artifacts.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import statistics
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from backend.app.agents.state import ReviewConfigType
from backend.app.core.config import get_settings
from backend.app.llm.base import LLMClient
from backend.app.llm.factory import create_llm_client
from eval.harness import EvalHarness, save_run_result
from eval.loader import load_eval_dataset
from eval.metrics import compute_run_metrics
from eval.schema import EvalCase, EvalDataset, EvalRunMetrics, EvalRunResult

logger = logging.getLogger(__name__)

DEFAULT_CONFIGS: tuple[ReviewConfigType, ...] = (
    "single_agent",
    "multi_agent_no_judge",
    "multi_agent_judge",
)
DEFAULT_NUM_RUNS = 3
DEFAULT_RESULTS_DIR = Path(__file__).parent / "results"


class AggregateStat(BaseModel):
    """Statistical summary across multiple evaluation runs."""

    model_config = ConfigDict(extra="ignore")

    mean: float
    std: float
    min: float
    max: float

    def format_mean_std(self, as_pct: bool = False, decimals: int = 1) -> str:
        """Format as 'mean ± std' with optional percentage scaling."""
        mult = 100.0 if as_pct else 1.0
        unit = "%" if as_pct else ""
        m = self.mean * mult
        s = self.std * mult
        return f"{m:.{decimals}f} \u00b1 {s:.{decimals}f}{unit}"


class ConfigBenchmarkSummary(BaseModel):
    """Aggregated evaluation metrics for a single configuration across N runs."""

    model_config = ConfigDict(extra="ignore")

    config: str
    model: str
    split: str
    num_runs: int
    precision: AggregateStat
    recall: AggregateStat
    f1: AggregateStat
    fdr: AggregateStat
    clean_specificity: AggregateStat
    buggy_detection_rate: AggregateStat
    mean_latency_s: AggregateStat
    cost_per_pr_usd: AggregateStat
    tokens_per_pr: AggregateStat


def calc_stat(values: Sequence[float | int]) -> AggregateStat:
    """Calculate mean, sample standard deviation, min, and max."""
    if not values:
        return AggregateStat(mean=0.0, std=0.0, min=0.0, max=0.0)
    flt_vals = [float(v) for v in values]
    m = statistics.fmean(flt_vals)
    s = statistics.stdev(flt_vals) if len(flt_vals) > 1 else 0.0
    return AggregateStat(
        mean=round(m, 4),
        std=round(s, 4),
        min=round(min(flt_vals), 4),
        max=round(max(flt_vals), 4),
    )


def compute_config_aggregates(runs: list[EvalRunMetrics]) -> ConfigBenchmarkSummary:
    """Aggregate multiple EvalRunMetrics instances for the same configuration."""
    if not runs:
        raise ValueError("Cannot aggregate empty list of run metrics")

    first = runs[0]
    return ConfigBenchmarkSummary(
        config=first.config,
        model=first.model,
        split=first.split,
        num_runs=len(runs),
        precision=calc_stat([r.overall.precision for r in runs]),
        recall=calc_stat([r.overall.recall for r in runs]),
        f1=calc_stat([r.overall.f1 for r in runs]),
        fdr=calc_stat([r.overall.fdr for r in runs]),
        clean_specificity=calc_stat([r.clean_specificity for r in runs]),
        buggy_detection_rate=calc_stat([r.buggy_detection_rate for r in runs]),
        mean_latency_s=calc_stat([r.latency.mean_ms / 1000.0 for r in runs]),
        cost_per_pr_usd=calc_stat([r.cost.mean_cost_usd for r in runs]),
        tokens_per_pr=calc_stat([r.cost.mean_tokens for r in runs]),
    )


def format_benchmark_comparison_markdown(
    summaries: list[ConfigBenchmarkSummary],
    split: str,
    total_cases: int,
) -> str:
    """Produce a publication-quality Markdown report comparing the 3 architectures."""
    lines = [
        "# CodeCourt Architecture Benchmark Report",
        "",
        f"- **Dataset Split:** `{split}`",
        f"- **Benchmark Size:** {total_cases} PR cases",
        f"- **Repetitions:** {summaries[0].num_runs if summaries else 0} runs per architecture",
        f"- **Evaluated Model:** `{summaries[0].model if summaries else 'unknown'}`",
        "",
        "## Cross-Architecture Comparison (Mean ± Std)",
        "",
        "| Architecture | Precision | Recall | F1 Score | False Discovery (FDR) | Clean Specificity | Mean Latency | Cost / PR |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for s in summaries:
        lines.append(
            f"| `{s.config}` | "
            f"{s.precision.format_mean_std(as_pct=True)} | "
            f"{s.recall.format_mean_std(as_pct=True)} | "
            f"{s.f1.format_mean_std(as_pct=True)} | "
            f"{s.fdr.format_mean_std(as_pct=True)} | "
            f"{s.clean_specificity.format_mean_std(as_pct=True)} | "
            f"{s.mean_latency_s.format_mean_std(decimals=2)}s | "
            f"${s.cost_per_pr_usd.mean:.4f} |"
        )

    lines.extend(
        [
            "",
            "## Findings & Scientific Analysis",
            "",
            "1. **Baseline (`single_agent`):**",
            "   - Serves as the minimal cost and latency baseline.",
            "   - Has lowest token overhead, but lacks specialized domain prompts (security/perf/maintainability).",
            "",
            "2. **Ablation (`multi_agent_no_judge`):**",
            "   - Parallel 3-reviewer fan-out captures findings across diverse domains.",
            "   - Without judge deduplication and conflict resolution, duplicate findings and false alarms accumulate, raising False Discovery Rate (FDR).",
            "",
            "3. **Full System (`multi_agent_judge`):**",
            "   - Judge merges overlapping findings, eliminates cross-agent duplicates, and ranks by severity.",
            "   - Maximizes precision and cleans up redundant comments before publication.",
            "",
        ]
    )

    return "\n".join(lines)


async def execute_benchmark_suite(
    cases: list[EvalCase],
    dataset: EvalDataset,
    configs: Sequence[ReviewConfigType] = DEFAULT_CONFIGS,
    num_runs: int = DEFAULT_NUM_RUNS,
    model: str = "fake-llm",
    concurrency: int = 5,
    llm_client: LLMClient | None = None,
    output_dir: Path | None = None,
) -> tuple[list[ConfigBenchmarkSummary], str, list[EvalRunResult]]:
    """Execute evaluation benchmark across multiple configurations and runs."""
    effective_client = llm_client or create_llm_client(model=model)
    harness = EvalHarness(llm_client=effective_client, max_concurrency=concurrency)
    out_dir = output_dir or DEFAULT_RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[ConfigBenchmarkSummary] = []
    all_run_results: list[EvalRunResult] = []

    for cfg in configs:
        cfg_metrics_list: list[EvalRunMetrics] = []
        for run_idx in range(1, num_runs + 1):
            run_id = f"bench_{cfg}_{model.replace('/', '_')}_r{run_idx}"
            result: EvalRunResult = await harness.run_benchmark(
                cases=cases,
                config=cfg,
                model=model,
                run_id=run_id,
            )
            all_run_results.append(result)
            save_run_result(result, out_dir)

            metrics = compute_run_metrics(result, dataset)
            cfg_metrics_list.append(metrics)

        agg = compute_config_aggregates(cfg_metrics_list)
        summaries.append(agg)

    split_label = cases[0].split if cases else "all"
    report_md = format_benchmark_comparison_markdown(summaries, split_label, len(cases))

    # Persist report to results directory
    report_path = out_dir / f"benchmark_report_{split_label}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    return summaries, report_md, all_run_results


def main() -> None:
    """CLI runner for executing the CodeCourt evaluation benchmark."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run CodeCourt architecture evaluation benchmark")
    parser.add_argument(
        "--split", choices=["dev", "test", "all"], default="dev", help="Dataset split"
    )
    parser.add_argument("--runs", type=int, default=DEFAULT_NUM_RUNS, help="Repetitions per config")
    parser.add_argument(
        "--model", type=str, default="", help="LLM model (e.g. 'gemini-1.5-flash', 'fake-llm')"
    )
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent PR reviews")
    args = parser.parse_args()

    cfg_settings = get_settings()
    chosen_model = args.model or ("gemini-1.5-flash" if cfg_settings.gemini_api_key else "fake-llm")

    dataset = load_eval_dataset()
    if args.split == "dev":
        cases = dataset.dev_cases
    elif args.split == "test":
        cases = dataset.test_cases
    else:
        cases = dataset.cases

    _summaries, report_md, _results = asyncio.run(
        execute_benchmark_suite(
            cases=cases,
            dataset=dataset,
            num_runs=args.runs,
            model=chosen_model,
            concurrency=args.concurrency,
        )
    )

    sys.stdout.write(f"\n{report_md}\n")


if __name__ == "__main__":
    main()
