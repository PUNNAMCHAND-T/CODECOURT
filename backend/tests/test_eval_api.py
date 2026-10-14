"""Tests for evaluation benchmark and failure analysis API endpoints.

T5.4: Verifies GET /api/eval/benchmark, /api/eval/runs, and /api/eval/failure-analysis.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest.mark.asyncio
async def test_get_benchmark_overview_test_split() -> None:
    """Verify GET /api/eval/benchmark returns cross-architecture aggregates for test split."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/eval/benchmark?split=test")

    assert response.status_code == 200
    data = response.json()

    assert data["split"] == "test"
    assert data["total_cases"] == 30
    assert data["num_runs_per_config"] >= 1
    assert len(data["comparisons"]) == 3

    # Check 3 architectures in order
    configs = [c["config"] for c in data["comparisons"]]
    assert configs == ["single_agent", "multi_agent_no_judge", "multi_agent_judge"]

    # Verify metrics structure on judge configuration
    judge_comp = next(c for c in data["comparisons"] if c["config"] == "multi_agent_judge")
    assert "precision" in judge_comp
    assert "recall" in judge_comp
    assert "f1" in judge_comp
    assert "clean_specificity" in judge_comp
    assert "mean_latency_s" in judge_comp
    assert "cost_per_pr_usd" in judge_comp
    assert "formatted" in judge_comp["f1"]

    # Verify runs list and markdown report are populated
    assert len(data["runs"]) >= 3
    assert len(data["report_markdown"]) > 0


@pytest.mark.asyncio
async def test_get_benchmark_overview_dev_split() -> None:
    """Verify GET /api/eval/benchmark returns dev split results."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/eval/benchmark?split=dev")

    assert response.status_code == 200
    data = response.json()
    assert data["split"] == "dev"
    assert data["total_cases"] == 20


@pytest.mark.asyncio
async def test_get_benchmark_invalid_split() -> None:
    """Verify GET /api/eval/benchmark with invalid split returns 422."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/eval/benchmark?split=unknown")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_eval_runs() -> None:
    """Verify GET /api/eval/runs returns list of executed runs."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/eval/runs?split=test")

    assert response.status_code == 200
    runs = response.json()
    assert isinstance(runs, list)
    assert len(runs) >= 3
    first = runs[0]
    assert "run_id" in first
    assert "config" in first
    assert "total_cases" in first
    assert "total_tokens" in first


@pytest.mark.asyncio
async def test_get_failure_analysis() -> None:
    """Verify GET /api/eval/failure-analysis returns failure taxonomy."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/eval/failure-analysis")

    assert response.status_code == 200
    data = response.json()
    assert "total_evaluated_cases" in data
    assert "total_failures" in data
    assert "by_failure_mode" in data
    assert "by_category" in data
    assert "by_language" in data
    assert len(data["report_markdown"]) > 0
