"""Unit tests for T4.2: Evaluation benchmark harness.

Verifies:
1. Single case execution with positive findings and token/latency accounting.
2. Clean case execution with zero findings.
3. Resilience to pipeline exceptions (gracefully records status='failed' without aborting).
4. Batch benchmark execution with bounded concurrency and summary aggregation.
5. Support for all three review configurations (single_agent, multi_agent_no_judge, multi_agent_judge).
6. Result serialization and deserialization roundtrip.
"""

import json
from pathlib import Path

import pytest
from eval.harness import EvalHarness, load_run_result, save_run_result
from eval.loader import get_all_cases

from backend.app.llm.fake import FakeLLMClient


@pytest.fixture
def sample_cases():
    """Retrieve sample cases from the benchmark suite."""
    all_cases = get_all_cases()
    sqli_case = next(c for c in all_cases if c.id == "dev_01_py_sec_sqli")
    clean_case = next(c for c in all_cases if c.id == "dev_15_py_clean_email_validator")
    n_plus_one_case = next(c for c in all_cases if c.id == "dev_06_py_perf_n_plus_one")
    return sqli_case, clean_case, n_plus_one_case


@pytest.mark.asyncio
async def test_harness_runs_single_case_with_findings(sample_cases) -> None:
    """Harness runs a buggy case and correctly maps findings and accounting."""
    sqli_case, _, _ = sample_cases

    canned_res = json.dumps(
        {
            "summary": "Detected critical SQL injection.",
            "findings": [
                {
                    "category": "security",
                    "severity": "critical",
                    "file": "app/auth.py",
                    "line_start": 11,
                    "line_end": 12,
                    "title": "SQL injection via formatted query",
                    "explanation": "Untrusted input in query string",
                    "evidence": "query = f\"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'\"",
                    "suggested_fix": "db.execute('SELECT * FROM users WHERE username = :u', {'u': username})",
                    "confidence": 0.99,
                }
            ],
        }
    )

    fake_llm = FakeLLMClient(responses=[canned_res], model="gemini-1.5-flash")
    harness = EvalHarness(llm_client=fake_llm)

    result = await harness.run_case(sqli_case, config="single_agent", model="gemini-1.5-flash")

    assert result.case_id == "dev_01_py_sec_sqli"
    assert result.split == "dev"
    assert result.status == "completed"
    assert result.error is None
    assert len(result.findings) == 1
    assert result.findings[0].category == "security"
    assert result.findings[0].severity == "critical"
    assert result.tokens_total > 0
    assert result.cost_usd > 0.0
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_harness_runs_clean_case_zero_findings(sample_cases) -> None:
    """Harness runs a clean case with zero findings."""
    _, clean_case, _ = sample_cases

    canned_res = json.dumps({"summary": "Code looks good and clean.", "findings": []})
    fake_llm = FakeLLMClient(responses=[canned_res])
    harness = EvalHarness(llm_client=fake_llm)

    result = await harness.run_case(clean_case, config="single_agent")

    assert result.case_id == "dev_15_py_clean_email_validator"
    assert result.has_bug is False
    assert result.status == "completed"
    assert len(result.findings) == 0


@pytest.mark.asyncio
async def test_harness_handles_unexpected_pipeline_exception(sample_cases) -> None:
    """Harness catches internal exceptions and records status='failed' cleanly."""
    from unittest.mock import patch

    sqli_case, _, _ = sample_cases
    harness = EvalHarness()

    with patch(
        "eval.harness.run_review_pipeline",
        side_effect=RuntimeError("Simulated pipeline crash"),
    ):
        result = await harness.run_case(sqli_case, config="single_agent")

    assert result.case_id == "dev_01_py_sec_sqli"
    assert result.status == "failed"
    assert result.error is not None
    assert "Simulated pipeline crash" in result.error
    assert len(result.findings) == 0


@pytest.mark.asyncio
async def test_harness_benchmark_batch_execution(sample_cases) -> None:
    """Harness runs a batch of cases concurrently and aggregates run summary."""
    sqli_case, clean_case, n_plus_one_case = sample_cases
    cases = [sqli_case, clean_case, n_plus_one_case]

    res = json.dumps({"summary": "Review complete.", "findings": []})
    fake_llm = FakeLLMClient(responses=[res, res, res])
    harness = EvalHarness(llm_client=fake_llm, max_concurrency=2)

    run_result = await harness.run_benchmark(
        cases=cases,
        config="single_agent",
        model="fake-llm",
        split_label="dev_subset",
        run_id="test_run_001",
    )

    summary = run_result.summary
    assert summary.run_id == "test_run_001"
    assert summary.total_cases == 3
    assert summary.completed_cases == 3
    assert summary.failed_cases == 0
    assert summary.split == "dev_subset"
    assert len(run_result.case_results) == 3


@pytest.mark.asyncio
async def test_harness_supports_all_three_configurations(sample_cases) -> None:
    """Harness supports single_agent, multi_agent_no_judge, and multi_agent_judge."""
    sqli_case, _, _ = sample_cases
    res = json.dumps({"summary": "ok", "findings": []})

    # Test single_agent
    fake_single = FakeLLMClient(responses=[res])
    harness_single = EvalHarness(llm_client=fake_single)
    res_single = await harness_single.run_case(sqli_case, config="single_agent")
    assert res_single.config == "single_agent"

    # Test multi_agent_no_judge (3 reviewers)
    fake_no_judge = FakeLLMClient(responses=[res, res, res])
    harness_no_judge = EvalHarness(llm_client=fake_no_judge)
    res_no_judge = await harness_no_judge.run_case(sqli_case, config="multi_agent_no_judge")
    assert res_no_judge.config == "multi_agent_no_judge"

    # Test multi_agent_judge (3 reviewers)
    fake_judge = FakeLLMClient(responses=[res, res, res])
    harness_judge = EvalHarness(llm_client=fake_judge)
    res_judge = await harness_judge.run_case(sqli_case, config="multi_agent_judge")
    assert res_judge.config == "multi_agent_judge"


@pytest.mark.asyncio
async def test_harness_save_and_load_run_result(sample_cases, tmp_path: Path) -> None:
    """Save and reload an EvalRunResult container from JSON."""
    sqli_case, clean_case, _ = sample_cases
    res = json.dumps({"summary": "ok", "findings": []})
    fake_llm = FakeLLMClient(responses=[res, res])
    harness = EvalHarness(llm_client=fake_llm)

    run_result = await harness.run_benchmark(
        cases=[sqli_case, clean_case],
        config="single_agent",
        run_id="persistence_test_run",
    )

    saved_file = save_run_result(run_result, output_dir=tmp_path)
    assert saved_file.exists()

    loaded = load_run_result(saved_file)
    assert loaded.summary.run_id == "persistence_test_run"
    assert loaded.summary.total_cases == 2
    assert len(loaded.case_results) == 2
    assert loaded.case_results[0].case_id == sqli_case.id
