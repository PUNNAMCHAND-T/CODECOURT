"""Unit tests for multi-run benchmark orchestrator and comparison reporting.

T4.4: Tests statistical aggregation, formatting, multi-run variance math,
and end-to-end execution of the architecture benchmark suite.
"""

from pathlib import Path

import pytest
from eval.metrics import compute_run_metrics
from eval.run_benchmark import (
    calc_stat,
    compute_config_aggregates,
    execute_benchmark_suite,
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

from backend.app.llm.fake import FakeLLMClient


def _make_sample_case(case_id: str, has_bug: bool) -> EvalCase:
    gt = (
        GroundTruthFinding(
            file="app/calc.py",
            line_start=10,
            line_end=15,
            category="correctness",
            severity="high",
            title="Bug",
            description="Bug desc",
            evidence_snippet="x = 1 / 0",
        )
        if has_bug
        else None
    )
    return EvalCase(
        id=case_id,
        split="dev",
        language="python",
        category="correctness" if has_bug else "clean",
        has_bug=has_bug,
        pr_title=f"PR {case_id}",
        pr_description="PR desc",
        filename="app/calc.py",
        diff_text="",
        ground_truth=gt,
    )


def test_calc_stat_and_formatting() -> None:
    """Verify statistical calculations (mean, std, min, max) and string formatters."""
    # Empty
    empty_stat = calc_stat([])
    assert empty_stat.mean == 0.0 and empty_stat.std == 0.0

    # Single value
    single_stat = calc_stat([0.85])
    assert single_stat.mean == 0.85 and single_stat.std == 0.0
    assert single_stat.format_mean_std(as_pct=True) == "85.0 ± 0.0%"

    # Multiple values
    multi_stat = calc_stat([0.80, 0.90])
    assert multi_stat.mean == 0.85
    assert round(multi_stat.std, 3) == 0.071
    assert "85.0 ± 7.1%" in multi_stat.format_mean_std(as_pct=True)
    assert "0.85 ± 0.07" in multi_stat.format_mean_std(as_pct=False, decimals=2)


def test_compute_config_aggregates() -> None:
    """Verify aggregation of multiple run metrics for the same architecture."""
    case = _make_sample_case("case_1", has_bug=True)
    dataset = EvalDataset(cases=[case])

    # Run 1: 1 TP, 0 FP (precision 1.0)
    res_1 = EvalCaseResult(
        case_id="case_1",
        split="dev",
        language="python",
        category="correctness",
        has_bug=True,
        config="single_agent",
        model="fake-llm",
        status="completed",
        latency_ms=1000,
        tokens_total=100,
        cost_usd=0.0001,
        findings=[
            EvalCaseFinding(
                category="correctness",
                severity="high",
                file="app/calc.py",
                line_start=10,
                line_end=15,
                title="Bug",
            )
        ],
    )
    # Run 2: 0 TP, 1 FP (precision 0.0)
    res_2 = EvalCaseResult(
        case_id="case_1",
        split="dev",
        language="python",
        category="correctness",
        has_bug=True,
        config="single_agent",
        model="fake-llm",
        status="completed",
        latency_ms=1200,
        tokens_total=120,
        cost_usd=0.00015,
        findings=[
            EvalCaseFinding(
                category="correctness",
                severity="high",
                file="app/calc.py",
                line_start=99,
                line_end=100,
                title="Wrong line",
            )
        ],
    )

    sum_1 = EvalRunSummary(
        run_id="r1",
        config="single_agent",
        model="fake-llm",
        split="dev",
        total_cases=1,
        completed_cases=1,
        partial_cases=0,
        failed_cases=0,
        total_findings=1,
        total_tokens=100,
        total_cost_usd=0.0001,
        duration_seconds=1.0,
        created_at="2026-10-09T00:00:00Z",
    )
    sum_2 = EvalRunSummary(
        run_id="r2",
        config="single_agent",
        model="fake-llm",
        split="dev",
        total_cases=1,
        completed_cases=1,
        partial_cases=0,
        failed_cases=0,
        total_findings=1,
        total_tokens=120,
        total_cost_usd=0.00015,
        duration_seconds=1.2,
        created_at="2026-10-09T00:00:00Z",
    )

    m1 = compute_run_metrics(EvalRunResult(summary=sum_1, case_results=[res_1]), dataset)
    m2 = compute_run_metrics(EvalRunResult(summary=sum_2, case_results=[res_2]), dataset)

    agg = compute_config_aggregates([m1, m2])
    assert agg.config == "single_agent"
    assert agg.num_runs == 2
    assert agg.precision.mean == 0.5
    assert agg.precision.min == 0.0
    assert agg.precision.max == 1.0


def test_compute_config_aggregates_empty_raises() -> None:
    """Verify ValueError when attempting to aggregate an empty run list."""
    with pytest.raises(ValueError, match="Cannot aggregate empty list"):
        compute_config_aggregates([])


@pytest.mark.asyncio
async def test_execute_benchmark_suite_integration(tmp_path: Path) -> None:
    """Verify execution of the benchmark suite across multiple configs with FakeLLM."""
    case_bug = _make_sample_case("case_b", has_bug=True)
    case_clean = _make_sample_case("case_c", has_bug=False)
    cases = [case_bug, case_clean]
    dataset = EvalDataset(cases=cases)

    fake_client = FakeLLMClient(default_response='{"findings": []}')

    summaries, report_md, run_results = await execute_benchmark_suite(
        cases=cases,
        dataset=dataset,
        configs=("single_agent", "multi_agent_judge"),
        num_runs=1,
        model="fake-llm",
        concurrency=2,
        llm_client=fake_client,
        output_dir=tmp_path,
    )

    # 2 configs x 1 run = 2 summaries and 2 saved results
    assert len(summaries) == 2
    assert len(run_results) == 2
    assert {s.config for s in summaries} == {"single_agent", "multi_agent_judge"}

    # Assert persistence to disk
    report_file = tmp_path / "benchmark_report_dev.md"
    assert report_file.exists()
    assert "# CodeCourt Architecture Benchmark Report" in report_md
    assert "| `single_agent` |" in report_md
    assert "| `multi_agent_judge` |" in report_md
