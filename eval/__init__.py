"""CodeCourt evaluation framework package."""

from eval.loader import (
    load_eval_dataset,
    load_from_json,
    validate_dataset_integrity,
)
from eval.metrics import (
    calculate_line_overlap,
    compute_percentile,
    compute_run_metrics,
    compute_scores,
    evaluate_case,
    is_finding_match,
    normalize_path,
)
from eval.schema import (
    CaseMatchDetail,
    CostMetrics,
    EvalCase,
    EvalCaseFinding,
    EvalCaseResult,
    EvalDataset,
    EvalRunMetrics,
    EvalRunResult,
    EvalRunSummary,
    GroundTruthFinding,
    LatencyMetrics,
    MatchingConfig,
    MetricScores,
)

__all__ = [
    "CaseMatchDetail",
    "CostMetrics",
    "EvalCase",
    "EvalCaseFinding",
    "EvalCaseResult",
    "EvalDataset",
    "EvalRunMetrics",
    "EvalRunResult",
    "EvalRunSummary",
    "GroundTruthFinding",
    "LatencyMetrics",
    "MatchingConfig",
    "MetricScores",
    "calculate_line_overlap",
    "compute_percentile",
    "compute_run_metrics",
    "compute_scores",
    "evaluate_case",
    "is_finding_match",
    "load_eval_dataset",
    "load_from_json",
    "normalize_path",
    "validate_dataset_integrity",
]
