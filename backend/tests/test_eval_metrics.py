"""Unit tests for deterministic evaluation metrics and finding matching.

T4.3: Tests candidate-to-ground-truth matching, line overlap calculations,
confusion scoring, latency percentiles, and markdown report formatting.
"""

from eval.metrics import (
    calculate_line_overlap,
    compute_percentile,
    compute_run_metrics,
    compute_scores,
    evaluate_case,
    is_finding_match,
    normalize_path,
)
from eval.reporting import format_comparison_table, format_metrics_markdown
from eval.schema import (
    EvalCase,
    EvalCaseFinding,
    EvalCaseResult,
    EvalDataset,
    EvalRunResult,
    EvalRunSummary,
    GroundTruthFinding,
    MatchingConfig,
)


def _make_gt(
    file: str = "app/auth.py", s: int = 20, e: int = 25, cat: str = "security"
) -> GroundTruthFinding:
    return GroundTruthFinding(
        file=file,
        line_start=s,
        line_end=e,
        category=cat,
        severity="high",  # type: ignore[arg-type]
        title="Vulnerability",
        description="Desc",
        evidence_snippet="code snippet",
    )


def _make_case(
    cid: str, has_bug: bool, gt: GroundTruthFinding | None = None, cat: str = "security"
) -> EvalCase:
    return EvalCase(
        id=cid,
        split="dev",
        language="python",
        category=cat,
        has_bug=has_bug,  # type: ignore[arg-type]
        pr_title=f"PR {cid}",
        pr_description="Desc",
        filename=gt.file if gt else "app/main.py",
        diff_text="",
        ground_truth=gt,
    )


def _make_finding(file: str, s: int, e: int, cat: str = "security") -> EvalCaseFinding:
    return EvalCaseFinding(
        category=cat,
        severity="high",
        file=file,
        line_start=s,
        line_end=e,
        title="Finding",
    )


def test_normalize_path() -> None:
    """Verify path normalization across OS separators and relative prefixes."""
    assert normalize_path("./backend/app/main.py") == "backend/app/main.py"
    assert normalize_path("backend\\app\\main.py") == "backend/app/main.py"
    assert normalize_path("/src/index.ts") == "src/index.ts"
    assert normalize_path("   service/worker.py   ") == "service/worker.py"


def test_calculate_line_overlap() -> None:
    """Verify closed interval line intersection and IoU calculation."""
    # Exact match: [10, 15] and [10, 15] -> 6 lines, IoU 1.0
    inter, iou = calculate_line_overlap(10, 15, 10, 15)
    assert inter == 6 and iou == 1.0

    # Partial overlap: [10, 15] and [12, 17] -> inter [12, 15] = 4 lines, union 8
    inter, iou = calculate_line_overlap(10, 15, 12, 17)
    assert inter == 4 and round(iou, 2) == 0.50

    # Disjoint intervals: [10, 15] and [20, 25] -> 0
    inter, iou = calculate_line_overlap(10, 15, 20, 25)
    assert inter == 0 and iou == 0.0

    # Line tolerance expanding ground truth
    inter, iou = calculate_line_overlap(10, 12, 15, 18, line_tolerance=3)
    assert inter > 0 and iou > 0.0


def test_is_finding_match_criteria() -> None:
    """Verify matching behavior with category constraints and IoU thresholds."""
    gt = _make_gt()

    # 1. Matching candidate
    match_cand = _make_finding("./app/auth.py", 20, 24, "security")
    is_match, iou = is_finding_match(match_cand, gt, MatchingConfig())
    assert is_match is True and iou > 0.0

    # 2. File mismatch
    diff_file = _make_finding("app/users.py", 20, 25, "security")
    assert is_finding_match(diff_file, gt, MatchingConfig())[0] is False

    # 3. Category mismatch with strict_category=True vs False
    diff_cat = _make_finding("app/auth.py", 20, 25, "performance")
    assert is_finding_match(diff_cat, gt, MatchingConfig(strict_category=True))[0] is False
    assert is_finding_match(diff_cat, gt, MatchingConfig(strict_category=False))[0] is True

    # 4. High IoU threshold (1 line overlap out of 16 union lines -> IoU = 0.0625)
    cand_small_overlap = _make_finding("app/auth.py", 25, 35, "security")
    assert is_finding_match(cand_small_overlap, gt, MatchingConfig(iou_threshold=0.5))[0] is False


def test_compute_percentile() -> None:
    """Verify linear interpolation percentile helper."""
    assert compute_percentile([], 50.0) == 0.0
    assert compute_percentile([42], 90.0) == 42.0

    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert compute_percentile(values, 0.0) == 10.0
    assert compute_percentile(values, 50.0) == 30.0
    assert compute_percentile(values, 100.0) == 50.0


def test_compute_scores() -> None:
    """Verify precision, recall, F1, and FDR math."""
    s0 = compute_scores(0, 0, 0)
    assert (s0.precision, s0.recall, s0.f1, s0.fdr) == (0.0, 0.0, 0.0, 0.0)

    s_perf = compute_scores(10, 0, 0)
    assert (s_perf.precision, s_perf.recall, s_perf.f1, s_perf.fdr) == (1.0, 1.0, 1.0, 0.0)

    s_mix = compute_scores(8, 2, 2)
    assert (s_mix.precision, s_mix.recall, s_mix.f1, s_mix.fdr) == (0.8, 0.8, 0.8, 0.2)


def test_evaluate_case_scenarios() -> None:
    """Test evaluation outcomes on clean PRs and buggy PRs."""
    cfg = MatchingConfig()

    # 1. Clean PR with 0 findings -> Pass (TP=0, FP=0, FN=0)
    clean_case = _make_case("c1", has_bug=False, cat="clean")
    res_clean_pass = EvalCaseResult(
        case_id="c1",
        split="dev",
        language="python",
        category="clean",
        has_bug=False,
        config="single_agent",
        model="fake-llm",
        status="completed",
        findings=[],
    )
    detail = evaluate_case(clean_case, res_clean_pass, cfg)
    assert detail.tp == 0 and detail.fp == 0 and detail.fn == 0

    # 2. Clean PR with 2 hallucinated findings -> Fail (FP=2)
    res_clean_fail = EvalCaseResult(
        case_id="c1",
        split="dev",
        language="python",
        category="clean",
        has_bug=False,
        config="single_agent",
        model="fake-llm",
        status="completed",
        findings=[_make_finding("app/main.py", 1, 2), _make_finding("app/main.py", 3, 4)],
    )
    detail_fail = evaluate_case(clean_case, res_clean_fail, cfg)
    assert detail_fail.tp == 0 and detail_fail.fp == 2 and detail_fail.fn == 0

    # 3. Buggy PR with 1 match + 1 extra finding -> TP=1, FP=1, FN=0
    gt = _make_gt(file="app/db.py", s=10, e=15, cat="performance")
    buggy_case = _make_case("b1", has_bug=True, gt=gt, cat="performance")
    res_buggy = EvalCaseResult(
        case_id="b1",
        split="dev",
        language="python",
        category="performance",
        has_bug=True,
        config="single_agent",
        model="fake-llm",
        status="completed",
        findings=[
            _make_finding("app/db.py", 10, 14, "performance"),
            _make_finding("app/db.py", 1, 2, "maintainability"),
        ],
    )
    detail_bug = evaluate_case(buggy_case, res_buggy, cfg)
    assert (
        detail_bug.tp == 1
        and detail_bug.fp == 1
        and detail_bug.fn == 0
        and detail_bug.matched_ground_truth is True
    )


def test_compute_run_metrics_end_to_end() -> None:
    """Verify run-level aggregation across clean and buggy cases."""
    gt = _make_gt(file="app/calc.py", s=5, e=8, cat="correctness")
    case_buggy = _make_case("case_bug", has_bug=True, gt=gt, cat="correctness")
    case_clean = _make_case("case_clean", has_bug=False, cat="clean")
    dataset = EvalDataset(cases=[case_buggy, case_clean])

    case_res_1 = EvalCaseResult(
        case_id="case_bug",
        split="dev",
        language="python",
        category="correctness",
        has_bug=True,
        config="multi_agent_judge",
        model="fake-llm",
        status="completed",
        latency_ms=1200,
        tokens_prompt=400,
        tokens_completion=100,
        tokens_total=500,
        cost_usd=0.0005,
        findings=[_make_finding("app/calc.py", 5, 8, "correctness")],
    )
    case_res_2 = EvalCaseResult(
        case_id="case_clean",
        split="dev",
        language="python",
        category="clean",
        has_bug=False,
        config="multi_agent_judge",
        model="fake-llm",
        status="completed",
        latency_ms=800,
        tokens_prompt=300,
        tokens_completion=50,
        tokens_total=350,
        cost_usd=0.0003,
        findings=[],
    )

    summary = EvalRunSummary(
        run_id="run_test_001",
        config="multi_agent_judge",
        model="fake-llm",
        split="dev",
        total_cases=2,
        completed_cases=2,
        partial_cases=0,
        failed_cases=0,
        total_findings=1,
        total_tokens=850,
        total_cost_usd=0.0008,
        duration_seconds=2.0,
        created_at="2026-10-09T00:00:00Z",
    )
    run_result = EvalRunResult(summary=summary, case_results=[case_res_1, case_res_2])

    metrics = compute_run_metrics(run_result, dataset)

    assert metrics.total_cases == 2 and metrics.completed_cases == 2
    assert (metrics.overall.tp, metrics.overall.fp, metrics.overall.fn) == (1, 0, 0)
    assert metrics.overall.precision == 1.0 and metrics.overall.recall == 1.0
    assert (
        metrics.clean_cases_total == 1
        and metrics.clean_cases_passed == 1
        and metrics.clean_specificity == 1.0
    )
    assert (
        metrics.buggy_cases_total == 1
        and metrics.buggy_cases_detected == 1
        and metrics.buggy_detection_rate == 1.0
    )
    assert "correctness" in metrics.by_category
    assert metrics.latency.min_ms == 800 and metrics.latency.max_ms == 1200

    # Markdown format and comparison table generation
    md = format_metrics_markdown(metrics)
    assert "# Evaluation Report: `run_test_001`" in md
    assert "Precision" in md and "100.0%" in md

    table = format_comparison_table([metrics])
    assert "| `multi_agent_judge` | `fake-llm` |" in table
