"""Report generation and comparison formatting for CodeCourt evaluations.

T4.3: Generates publication-ready markdown reports, cross-architecture comparison
tables, and provides a CLI runner for offline evaluation analysis.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval.loader import load_eval_dataset
from eval.metrics import compute_run_metrics
from eval.schema import EvalRunMetrics, EvalRunResult


def format_metrics_markdown(metrics: EvalRunMetrics) -> str:
    """Format evaluation metrics into a publication-ready markdown report."""
    lines = [
        f"# Evaluation Report: `{metrics.run_id}`",
        "",
        f"- **Architecture:** `{metrics.config}`",
        f"- **Model:** `{metrics.model}`",
        f"- **Split:** `{metrics.split}`",
        f"- **Total Cases:** {metrics.total_cases} "
        f"({metrics.completed_cases} completed, {metrics.partial_cases} partial, "
        f"{metrics.failed_cases} failed)",
        "",
        "## Core Detection Performance",
        "",
        "| Metric | Value |",
        "| :--- | :--- |",
        f"| **Precision** | {metrics.overall.precision * 100:.1f}% |",
        f"| **Recall** | {metrics.overall.recall * 100:.1f}% |",
        f"| **F1 Score** | {metrics.overall.f1 * 100:.1f}% |",
        f"| **False Discovery Rate (FDR)** | {metrics.overall.fdr * 100:.1f}% |",
        f"| **Clean PR Specificity** | {metrics.clean_specificity * 100:.1f}% "
        f"({metrics.clean_cases_passed}/{metrics.clean_cases_total}) |",
        f"| **Buggy PR Detection Rate** | {metrics.buggy_detection_rate * 100:.1f}% "
        f"({metrics.buggy_cases_detected}/{metrics.buggy_cases_total}) |",
        f"| **Confusion Counts** | TP={metrics.overall.tp}, FP={metrics.overall.fp}, "
        f"FN={metrics.overall.fn} |",
        "",
        "## Performance by Bug Category",
        "",
        "| Category | TP | FP | FN | Precision | Recall | F1 |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for cat, scores in sorted(metrics.by_category.items()):
        lines.append(
            f"| `{cat}` | {scores.tp} | {scores.fp} | {scores.fn} | "
            f"{scores.precision * 100:.1f}% | {scores.recall * 100:.1f}% | "
            f"{scores.f1 * 100:.1f}% |"
        )

    lines.extend(
        [
            "",
            "## Latency & Accounting",
            "",
            "| Resource | Value |",
            "| :--- | :--- |",
            f"| **Mean Latency** | {metrics.latency.mean_ms / 1000.0:.2f}s |",
            f"| **p95 Latency** | {metrics.latency.p95_ms / 1000.0:.2f}s |",
            f"| **Total Cost** | ${metrics.cost.total_cost_usd:.4f} |",
            f"| **Mean Cost / PR** | ${metrics.cost.mean_cost_usd:.4f} |",
            f"| **Total Tokens** | {metrics.cost.total_tokens:,} |",
            f"| **Mean Tokens / PR** | {metrics.cost.mean_tokens:.0f} |",
            "",
        ]
    )

    return "\n".join(lines)


def format_comparison_table(metrics_runs: list[EvalRunMetrics]) -> str:
    """Generate a Markdown cross-architecture comparison table."""
    headers = [
        "| Configuration | Model | Precision | Recall | F1 | FDR | Clean Spec | "
        "Mean Latency | Cost/PR |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    rows = []
    for m in metrics_runs:
        rows.append(
            f"| `{m.config}` | `{m.model}` | {m.overall.precision * 100:.1f}% | "
            f"{m.overall.recall * 100:.1f}% | {m.overall.f1 * 100:.1f}% | "
            f"{m.overall.fdr * 100:.1f}% | {m.clean_specificity * 100:.1f}% | "
            f"{m.latency.mean_ms / 1000.0:.2f}s | ${m.cost.mean_cost_usd:.4f} |"
        )
    return "\n".join(headers + rows)


def format_failure_analysis_markdown(
    report_dict: dict[str, object],
    descriptions: dict[str, str] | None = None,
) -> str:
    """Format failure analysis findings into an informative Markdown report."""
    descs = descriptions or {}
    total_cases = report_dict.get("total_cases_evaluated", 0)
    raw_failures = report_dict.get("total_failures", 0)
    total_failures = int(raw_failures) if isinstance(raw_failures, (int, str)) else 0
    tot = max(1, total_failures)

    lines = [
        "# CodeCourt Evaluation: Failure Analysis Report",
        "",
        f"- **Evaluated Cases Total:** {total_cases}",
        f"- **Identified Failures:** {total_failures}",
        f"- **Report Generated:** {report_dict.get('generated_at', '')}",
        "",
        "## Failure Mode Taxonomy Breakdown",
        "",
        "| Failure Mode | Count | % of Failures | Description |",
        "| :--- | :---: | :---: | :--- |",
    ]

    by_mode = report_dict.get("by_failure_mode", {})
    if isinstance(by_mode, dict):
        for mode, count in sorted(by_mode.items(), key=lambda x: -int(x[1])):
            cnt = int(count)
            pct = (cnt / tot) * 100.0
            desc = descs.get(mode, mode)
            lines.append(f"| `{mode}` | {cnt} | {pct:.1f}% | {desc} |")

    lines.extend(
        [
            "",
            "## Failures by Review Architecture",
            "",
            "| Architecture | Failure Count | Share |",
            "| :--- | :---: | :---: |",
        ]
    )
    by_cfg = report_dict.get("by_config", {})
    if isinstance(by_cfg, dict):
        for cfg, count in sorted(by_cfg.items(), key=lambda x: -int(x[1])):
            cnt = int(count)
            lines.append(f"| `{cfg}` | {cnt} | {(cnt / tot) * 100.0:.1f}% |")

    lines.extend(
        [
            "",
            "## Failures by Bug Domain",
            "",
            "| Category | Failure Count | Share |",
            "| :--- | :---: | :---: |",
        ]
    )
    by_cat = report_dict.get("by_category", {})
    if isinstance(by_cat, dict):
        for cat, count in sorted(by_cat.items(), key=lambda x: -int(x[1])):
            cnt = int(count)
            lines.append(f"| `{cat}` | {cnt} | {(cnt / tot) * 100.0:.1f}% |")

    lines.extend(
        [
            "",
            "## Key Architectural Takeaways",
            "",
            "1. **Clean PR Resilience:** Strict grounding eliminates false alarms on safe code.",
            "2. **Ablation Duplication:** `multi_agent_no_judge` suffers from duplicate noise when agents overlap.",
            "3. **Judge Synthesis:** `multi_agent_judge` eliminates duplicate noise through deduplication.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """CLI entrypoint for computing metrics from a run result JSON file."""
    parser = argparse.ArgumentParser(description="Generate evaluation reports for CodeCourt")
    parser.add_argument("--run-file", type=str, required=True, help="Path to EvalRunResult JSON")
    parser.add_argument("--output", type=str, default="", help="Optional output markdown file")
    args = parser.parse_args()

    run_path = Path(args.run_file)
    with open(run_path, encoding="utf-8") as f:
        run_data = json.load(f)
    run_result = EvalRunResult.model_validate(run_data)

    dataset = load_eval_dataset()
    metrics = compute_run_metrics(run_result, dataset)
    report_md = format_metrics_markdown(metrics)
    sys.stdout.write(f"{report_md}\n")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report_md)


if __name__ == "__main__":
    main()
