"""Failure analysis engine for CodeCourt evaluation benchmarks.

T4.5: Classifies failure modes: clean false alarms, missed bugs, line drifts,
category mismatches, duplicate noise, and ungrounded findings.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from eval.loader import load_eval_dataset
from eval.metrics import calculate_line_overlap, is_finding_match, normalize_path
from eval.reporting import format_failure_analysis_markdown as _format_failure_md
from eval.schema import (
    EvalCase,
    EvalCaseFinding,
    EvalCaseResult,
    EvalDataset,
    EvalRunResult,
    MatchingConfig,
)

FailureModeType = Literal[
    "clean_pr_false_alarm",
    "missed_injected_bug",
    "wrong_line_drift",
    "category_mismatch",
    "extra_duplicate_noise",
    "ungrounded_extra_finding",
]

FAILURE_DESCRIPTIONS: dict[str, str] = {
    "clean_pr_false_alarm": "Hallucinated finding on clean PR",
    "missed_injected_bug": "False negative (missed defect)",
    "wrong_line_drift": "Correct defect, inaccurate line interval",
    "category_mismatch": "Correct line, wrong category taxonomy",
    "extra_duplicate_noise": "Unmerged duplicate finding (unjudged ablation)",
    "ungrounded_extra_finding": "Spurious comment on harmless code",
}


class FailureRecord(BaseModel):
    """Detailed record of an individual evaluation failure."""

    model_config = ConfigDict(extra="ignore")

    case_id: str
    config: str
    model: str
    split: str
    failure_mode: FailureModeType
    language: str
    category: str
    file: str
    expected_lines: str | None = None
    reported_lines: str | None = None
    description: str


class FailureAnalysisReport(BaseModel):
    """Aggregated taxonomy and breakdown of evaluation failures."""

    model_config = ConfigDict(extra="ignore")

    total_cases_evaluated: int = 0
    total_failures: int = 0
    by_failure_mode: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    by_language: dict[str, int] = Field(default_factory=dict)
    by_config: dict[str, int] = Field(default_factory=dict)
    failures: list[FailureRecord] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


def _rec(
    c: EvalCase,
    r: EvalCaseResult,
    m: FailureModeType,
    cat: str,
    desc: str,
    exp: str | None = None,
    rep: str | None = None,
) -> FailureRecord:
    return FailureRecord(
        case_id=c.id,
        config=r.config,
        model=r.model,
        split=c.split,
        failure_mode=m,
        language=c.language,
        category=cat,
        file=c.filename,
        expected_lines=exp,
        reported_lines=rep,
        description=desc,
    )


def analyze_case_failures(
    case: EvalCase,
    result: EvalCaseResult,
    config: MatchingConfig | None = None,
) -> list[FailureRecord]:
    """Diagnose and classify all failure modes observed in a single PR evaluation."""
    cfg = config or MatchingConfig()
    failures: list[FailureRecord] = []

    if not case.has_bug or case.ground_truth is None:
        for f in result.findings:
            failures.append(
                _rec(
                    case,
                    result,
                    "clean_pr_false_alarm",
                    f.category,
                    f"Hallucinated '{f.title}'",
                    rep=f"{f.line_start}-{f.line_end}",
                )
            )
        return failures

    gt = case.ground_truth
    matched_finding: EvalCaseFinding | None = None
    near_matches: list[tuple[EvalCaseFinding, FailureModeType]] = []

    for f in result.findings:
        is_match, _ = is_finding_match(f, gt, cfg)
        if is_match:
            if matched_finding is None:
                matched_finding = f
            else:
                failures.append(
                    _rec(
                        case,
                        result,
                        "extra_duplicate_noise",
                        f.category,
                        f"Duplicate '{f.title}'",
                        f"{gt.line_start}-{gt.line_end}",
                        f"{f.line_start}-{f.line_end}",
                    )
                )
        else:
            same_file = normalize_path(f.file) == normalize_path(gt.file)
            inter, _ = calculate_line_overlap(
                f.line_start, f.line_end, gt.line_start, gt.line_end, line_tolerance=3
            )
            if same_file and inter > 0:
                mode: FailureModeType = (
                    "wrong_line_drift"
                    if f.category.lower() == gt.category.lower()
                    else "category_mismatch"
                )
                near_matches.append((f, mode))
            else:
                failures.append(
                    _rec(
                        case,
                        result,
                        "ungrounded_extra_finding",
                        f.category,
                        f"Ungrounded '{f.title}'",
                        rep=f"{f.line_start}-{f.line_end}",
                    )
                )

    if matched_finding is None:
        if near_matches:
            near_f, mode = near_matches[0]
            failures.append(
                _rec(
                    case,
                    result,
                    mode,
                    near_f.category,
                    f"Near-miss defect: {near_f.title}",
                    f"{gt.line_start}-{gt.line_end}",
                    f"{near_f.line_start}-{near_f.line_end}",
                )
            )
        else:
            failures.append(
                _rec(
                    case,
                    result,
                    "missed_injected_bug",
                    gt.category,
                    f"Missed defect '{gt.title}'",
                    f"{gt.line_start}-{gt.line_end}",
                )
            )

    return failures


def analyze_multi_run_failures(
    run_results: list[EvalRunResult],
    dataset: EvalDataset,
    config: MatchingConfig | None = None,
) -> FailureAnalysisReport:
    """Analyze and aggregate failures across multiple evaluation run results."""
    cfg = config or MatchingConfig()
    case_map = {c.id: c for c in dataset.cases}
    failures: list[FailureRecord] = []
    total = 0

    for run in run_results:
        for cr in run.case_results:
            case = case_map.get(cr.case_id)
            if case:
                total += 1
                failures.extend(analyze_case_failures(case, cr, cfg))

    def _count(field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in failures:
            val = getattr(f, field)
            counts[val] = counts.get(val, 0) + 1
        return counts

    return FailureAnalysisReport(
        total_cases_evaluated=total,
        total_failures=len(failures),
        by_failure_mode=_count("failure_mode"),
        by_category=_count("category"),
        by_language=_count("language"),
        by_config=_count("config"),
        failures=failures,
    )


def format_failure_analysis_markdown(report: FailureAnalysisReport) -> str:
    """Format failure analysis findings into an informative Markdown report."""
    return _format_failure_md(report.model_dump(), FAILURE_DESCRIPTIONS)


def main() -> None:
    """CLI entrypoint for running failure analysis across evaluation runs."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="CodeCourt Benchmark Failure Analysis")
    parser.add_argument(
        "--results-dir", type=str, default="eval/results", help="Directory with EvalRunResult JSONs"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="eval/results/FAILURE_ANALYSIS.md",
        help="Output markdown path",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    json_files = list(results_dir.glob("bench_*.json"))
    if not json_files:
        sys.stdout.write(f"No benchmark run files found in {results_dir}\n")
        return

    runs = [
        EvalRunResult.model_validate(json.loads(f.read_text(encoding="utf-8"))) for f in json_files
    ]
    report = analyze_multi_run_failures(runs, load_eval_dataset())
    md = format_failure_analysis_markdown(report)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    sys.stdout.write(f"\n{md}\n")


if __name__ == "__main__":
    main()
