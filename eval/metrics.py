"""Metrics calculation and deterministic finding matching for CodeCourt evaluations.

T4.3: Implements deterministic candidate-to-ground-truth matching:
- File equality with path normalization
- Line interval overlap (closed-interval intersection and IoU threshold)
- Precision, Recall, F1, and False Discovery Rate (FDR)
- Clean PR pass rate (specificity) and Buggy PR hit rate
- Latency percentiles (mean, p50, p95) and token/cost accounting
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence

from eval.schema import (
    CaseMatchDetail,
    CostMetrics,
    EvalCase,
    EvalCaseFinding,
    EvalCaseResult,
    EvalDataset,
    EvalRunMetrics,
    EvalRunResult,
    GroundTruthFinding,
    LatencyMetrics,
    MatchingConfig,
    MetricScores,
)


def normalize_path(path: str) -> str:
    """Normalize file path for cross-platform and format-agnostic matching."""
    cleaned = path.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.lstrip("/")


def calculate_line_overlap(
    cand_start: int,
    cand_end: int,
    gt_start: int,
    gt_end: int,
    line_tolerance: int = 0,
) -> tuple[int, float]:
    """Calculate line intersection and IoU between candidate and ground truth intervals.

    Returns:
        (intersection_lines, intersection_over_union)
    """
    eff_gt_start = max(1, gt_start - line_tolerance)
    eff_gt_end = gt_end + line_tolerance

    inter_start = max(cand_start, eff_gt_start)
    inter_end = min(cand_end, eff_gt_end)
    intersection = max(0, inter_end - inter_start + 1)

    cand_len = max(0, cand_end - cand_start + 1)
    gt_len = max(0, eff_gt_end - eff_gt_start + 1)
    union = (cand_len + gt_len) - intersection

    iou = (intersection / union) if union > 0 else 0.0
    return intersection, iou


def is_finding_match(
    finding: EvalCaseFinding,
    gt: GroundTruthFinding,
    config: MatchingConfig,
) -> tuple[bool, float]:
    """Determine whether a candidate finding matches a pre-labeled ground truth finding."""
    if normalize_path(finding.file) != normalize_path(gt.file):
        return False, 0.0

    if config.strict_category and finding.category.strip().lower() != gt.category.strip().lower():
        return False, 0.0

    intersection, iou = calculate_line_overlap(
        finding.line_start,
        finding.line_end,
        gt.line_start,
        gt.line_end,
        line_tolerance=config.line_tolerance,
    )

    if config.iou_threshold > 0.0:
        is_match = (intersection > 0) and (iou >= config.iou_threshold)
    else:
        is_match = intersection > 0

    return is_match, iou


def compute_percentile(values: Sequence[float | int], p: float) -> float:
    """Compute the p-th percentile (0.0 to 100.0) with linear interpolation."""
    if not values:
        return 0.0
    sorted_v = sorted(float(v) for v in values)
    if len(sorted_v) == 1:
        return sorted_v[0]
    rank = (len(sorted_v) - 1) * (max(0.0, min(100.0, p)) / 100.0)
    low_idx = int(rank)
    high_idx = min(low_idx + 1, len(sorted_v) - 1)
    weight = rank - low_idx
    return sorted_v[low_idx] * (1.0 - weight) + sorted_v[high_idx] * weight


def compute_scores(tp: int, fp: int, fn: int) -> MetricScores:
    """Calculate standard information retrieval scores from confusion counts."""
    precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    fdr = (fp / (tp + fp)) if (tp + fp) > 0 else 0.0

    return MetricScores(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        fdr=round(fdr, 4),
    )


def evaluate_case(
    case: EvalCase,
    result: EvalCaseResult,
    config: MatchingConfig,
) -> CaseMatchDetail:
    """Evaluate candidate findings for a single benchmark case against ground truth."""
    cand_count = len(result.findings)

    # 1. Clean PR (expected 0 findings)
    if not case.has_bug or case.ground_truth is None:
        return CaseMatchDetail(
            case_id=case.id,
            split=case.split,
            has_bug=False,
            category=case.category,
            status=result.status,
            tp=0,
            fp=cand_count,
            fn=0,
            matched_ground_truth=False,
            candidate_findings_count=cand_count,
        )

    # 2. Buggy PR (expected 1 matching finding)
    gt = case.ground_truth
    matched = False
    best_iou = -1.0

    for finding in result.findings:
        is_match, iou = is_finding_match(finding, gt, config)
        if is_match and iou > best_iou:
            matched = True
            best_iou = iou

    if matched:
        tp = 1
        fn = 0
        fp = max(0, cand_count - 1)  # Extra candidate findings are duplicates or false alarms
    else:
        tp = 0
        fn = 1
        fp = cand_count

    return CaseMatchDetail(
        case_id=case.id,
        split=case.split,
        has_bug=True,
        category=case.category,
        status=result.status,
        tp=tp,
        fp=fp,
        fn=fn,
        matched_ground_truth=matched,
        candidate_findings_count=cand_count,
    )


def compute_run_metrics(
    run_result: EvalRunResult,
    dataset: EvalDataset,
    config: MatchingConfig | None = None,
) -> EvalRunMetrics:
    """Compute comprehensive evaluation metrics for an evaluation run result."""
    effective_config = config or MatchingConfig()
    details: list[CaseMatchDetail] = []
    case_map = {c.id: c for c in dataset.cases}

    for case_res in run_result.case_results:
        case = case_map.get(case_res.case_id)
        if case is None:
            continue
        details.append(evaluate_case(case, case_res, effective_config))

    # Confusion counts
    tot_tp = sum(d.tp for d in details)
    tot_fp = sum(d.fp for d in details)
    tot_fn = sum(d.fn for d in details)
    overall_scores = compute_scores(tot_tp, tot_fp, tot_fn)

    # Clean & buggy counts
    clean_cases = [d for d in details if not d.has_bug]
    clean_total = len(clean_cases)
    clean_passed = sum(1 for d in clean_cases if d.candidate_findings_count == 0)
    clean_spec = (clean_passed / clean_total) if clean_total > 0 else 1.0

    buggy_cases = [d for d in details if d.has_bug]
    buggy_total = len(buggy_cases)
    buggy_detected = sum(1 for d in buggy_cases if d.matched_ground_truth)
    buggy_rate = (buggy_detected / buggy_total) if buggy_total > 0 else 0.0

    # Per-category scores
    categories = sorted({d.category for d in details if d.category != "clean"})
    by_category: dict[str, MetricScores] = {}
    for cat in categories:
        cat_details = [d for d in details if d.category == cat]
        cat_tp = sum(d.tp for d in cat_details)
        cat_fp = sum(d.fp for d in cat_details)
        cat_fn = sum(d.fn for d in cat_details)
        by_category[cat] = compute_scores(cat_tp, cat_fp, cat_fn)

    # Latency percentiles
    latencies = [r.latency_ms for r in run_result.case_results]
    mean_lat = statistics.fmean(latencies) if latencies else 0.0
    latency_metrics = LatencyMetrics(
        mean_ms=round(mean_lat, 1),
        median_ms=round(compute_percentile(latencies, 50.0), 1),
        p95_ms=round(compute_percentile(latencies, 95.0), 1),
        min_ms=min(latencies) if latencies else 0,
        max_ms=max(latencies) if latencies else 0,
    )

    # Cost metrics
    n_cases = len(run_result.case_results) or 1
    cost_metrics = CostMetrics(
        total_cost_usd=round(run_result.summary.total_cost_usd, 6),
        mean_cost_usd=round(run_result.summary.total_cost_usd / n_cases, 6),
        total_tokens=run_result.summary.total_tokens,
        mean_tokens=round(run_result.summary.total_tokens / n_cases, 1),
        tokens_prompt=sum(r.tokens_prompt for r in run_result.case_results),
        tokens_completion=sum(r.tokens_completion for r in run_result.case_results),
    )

    return EvalRunMetrics(
        run_id=run_result.summary.run_id,
        config=run_result.summary.config,
        model=run_result.summary.model,
        split=run_result.summary.split,
        total_cases=len(details),
        completed_cases=run_result.summary.completed_cases,
        partial_cases=run_result.summary.partial_cases,
        failed_cases=run_result.summary.failed_cases,
        clean_cases_total=clean_total,
        clean_cases_passed=clean_passed,
        clean_specificity=round(clean_spec, 4),
        buggy_cases_total=buggy_total,
        buggy_cases_detected=buggy_detected,
        buggy_detection_rate=round(buggy_rate, 4),
        overall=overall_scores,
        by_category=by_category,
        latency=latency_metrics,
        cost=cost_metrics,
        matching_config=effective_config,
        case_details=details,
    )
