"""Unit tests for evaluation failure analysis engine.

T4.5: Tests classification of failure modes: clean false alarms, missed bugs,
line coordinate drifts, category mismatches, duplicate noise, and spurious findings.
"""

from eval.failure_analysis import (
    analyze_case_failures,
    analyze_multi_run_failures,
    format_failure_analysis_markdown,
)
from eval.schema import (
    EvalCase,
    EvalCaseFinding,
    EvalCaseResult,
    EvalDataset,
    EvalRunResult,
    EvalRunSummary,
    GroundTruthFinding,
)


def _make_gt(
    file: str = "app/db.py", s: int = 10, e: int = 15, cat: str = "security"
) -> GroundTruthFinding:
    return GroundTruthFinding(
        file=file,
        line_start=s,
        line_end=e,
        category=cat,
        severity="high",  # type: ignore[arg-type]
        title="SQL Injection",
        description="Raw SQL format",
        evidence_snippet="f'SELECT {user}'",
    )


def _make_case(cid: str, has_bug: bool, gt: GroundTruthFinding | None = None) -> EvalCase:
    return EvalCase(
        id=cid,
        split="dev",
        language="python",
        category=gt.category if gt else "clean",  # type: ignore[arg-type]
        has_bug=has_bug,
        pr_title=f"PR {cid}",
        pr_description="Desc",
        filename=gt.file if gt else "app/main.py",
        diff_text="",
        ground_truth=gt,
    )


def _make_res(cid: str, findings: list[EvalCaseFinding]) -> EvalCaseResult:
    return EvalCaseResult(
        case_id=cid,
        split="dev",
        language="python",
        category="security" if findings else "clean",
        has_bug=True,
        config="multi_agent_judge",
        model="fake-llm",
        status="completed",
        findings=findings,
    )


def test_clean_pr_false_alarm_classification() -> None:
    """Verify that any finding emitted on a clean PR is classified as a false alarm."""
    case = _make_case("c1", has_bug=False)
    finding = EvalCaseFinding(
        category="security",
        severity="low",
        file="app/main.py",
        line_start=1,
        line_end=2,
        title="Spurious",
    )
    res = _make_res("c1", [finding])

    failures = analyze_case_failures(case, res)
    assert len(failures) == 1
    assert failures[0].failure_mode == "clean_pr_false_alarm"
    assert "Hallucinated 'Spurious'" in failures[0].description


def test_missed_injected_bug_classification() -> None:
    """Verify that zero findings on a buggy PR is classified as a missed bug."""
    gt = _make_gt()
    case = _make_case("b1", has_bug=True, gt=gt)
    res = _make_res("b1", [])

    failures = analyze_case_failures(case, res)
    assert len(failures) == 1
    assert failures[0].failure_mode == "missed_injected_bug"
    assert "Missed defect 'SQL Injection'" in failures[0].description


def test_wrong_line_drift_classification() -> None:
    """Verify near-miss line coordinate drift detection within tolerance."""
    gt = _make_gt(s=10, e=15)
    case = _make_case("b2", has_bug=True, gt=gt)
    # Drifted finding at lines 17-18 (close to 15, within line tolerance 3)
    drifted = EvalCaseFinding(
        category="security",
        severity="high",
        file="app/db.py",
        line_start=17,
        line_end=18,
        title="SQL issue",
    )
    res = _make_res("b2", [drifted])

    failures = analyze_case_failures(case, res)
    assert len(failures) == 1
    assert failures[0].failure_mode == "wrong_line_drift"
    assert "Near-miss defect" in failures[0].description


def test_category_mismatch_classification() -> None:
    """Verify correct line interval with misclassified domain taxonomy."""
    gt = _make_gt(cat="security", s=10, e=15)
    case = _make_case("b3", has_bug=True, gt=gt)
    # Misclassified as maintainability
    mismatched = EvalCaseFinding(
        category="maintainability",
        severity="medium",
        file="app/db.py",
        line_start=10,
        line_end=15,
        title="Bad style",
    )
    res = _make_res("b3", [mismatched])

    failures = analyze_case_failures(case, res)
    assert len(failures) == 1
    assert failures[0].failure_mode == "category_mismatch"


def test_duplicate_noise_and_ungrounded_extra() -> None:
    """Verify duplicate unmerged findings and ungrounded extras on buggy PRs."""
    gt = _make_gt(s=10, e=15)
    case = _make_case("b4", has_bug=True, gt=gt)

    f_match1 = EvalCaseFinding(
        category="security",
        severity="high",
        file="app/db.py",
        line_start=10,
        line_end=15,
        title="Match 1",
    )
    f_match2 = EvalCaseFinding(
        category="security",
        severity="high",
        file="app/db.py",
        line_start=10,
        line_end=14,
        title="Match 2 duplicate",
    )
    f_extra = EvalCaseFinding(
        category="performance",
        severity="low",
        file="app/other.py",
        line_start=1,
        line_end=2,
        title="Extra ungrounded",
    )

    res = _make_res("b4", [f_match1, f_match2, f_extra])
    failures = analyze_case_failures(case, res)

    modes = {f.failure_mode for f in failures}
    assert "extra_duplicate_noise" in modes
    assert "ungrounded_extra_finding" in modes


def test_analyze_multi_run_failures_and_markdown() -> None:
    """Verify multi-run failure report aggregation and markdown rendering."""
    gt = _make_gt()
    case_b = _make_case("case_b", has_bug=True, gt=gt)
    case_c = _make_case("case_c", has_bug=False)
    dataset = EvalDataset(cases=[case_b, case_c])

    res_b = _make_res("case_b", [])  # Missed bug
    res_c = EvalCaseResult(
        case_id="case_c",
        split="dev",
        language="python",
        category="clean",
        has_bug=False,
        config="single_agent",
        model="fake-llm",
        status="completed",
        findings=[
            EvalCaseFinding(
                category="maintainability",
                severity="low",
                file="app/main.py",
                line_start=1,
                line_end=2,
                title="Hallucination",
            )
        ],
    )

    summary = EvalRunSummary(
        run_id="r1",
        config="single_agent",
        model="fake-llm",
        split="dev",
        total_cases=2,
        completed_cases=2,
        partial_cases=0,
        failed_cases=0,
        total_findings=1,
        total_tokens=100,
        total_cost_usd=0.0001,
        duration_seconds=1.0,
        created_at="2026-10-09T00:00:00Z",
    )
    run_result = EvalRunResult(summary=summary, case_results=[res_b, res_c])

    report = analyze_multi_run_failures([run_result], dataset)
    assert report.total_cases_evaluated == 2
    assert report.total_failures == 2
    assert report.by_failure_mode["missed_injected_bug"] == 1
    assert report.by_failure_mode["clean_pr_false_alarm"] == 1

    md = format_failure_analysis_markdown(report)
    assert "# CodeCourt Evaluation: Failure Analysis Report" in md
    assert "| `missed_injected_bug` |" in md
    assert "| `clean_pr_false_alarm` |" in md
