"""Tests for optional Langfuse / OpenTelemetry observability tracing.

PROJECT.md §6 & §7: Phase 6 Hardening - T6.3 Optional Langfuse verification.
Verifies no-op fallback when disabled/unconfigured, active trace recording
with structured reports, and total crash resilience against network failures.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.app.agents.graph import run_review_pipeline
from backend.app.core.config import Settings
from backend.app.llm.fake import FakeLLMClient
from backend.app.schemas.trace import NodeTrace, PipelineTraceReport
from backend.app.services.tracing import (
    BaseTracer,
    LangfuseTracer,
    NoopTracer,
    get_tracer,
    reset_tracer,
    set_tracer,
)


@pytest.fixture(autouse=True)
def cleanup_tracer() -> Any:
    """Ensure global tracer is reset before and after every test."""
    reset_tracer()
    yield
    reset_tracer()


def test_default_settings_produces_noop_tracer() -> None:
    """Verify that default settings produce a NoopTracer with all calls safe."""
    cfg = Settings(langfuse_enabled=False)
    tracer = get_tracer(cfg)

    assert isinstance(tracer, NoopTracer)
    assert not tracer.is_enabled()
    assert tracer.trace_pipeline({}) is None
    assert tracer.trace_llm_generation(model="test", prompt="p", response="r") is None
    # Verify flush and shutdown execute silently
    tracer.flush()
    tracer.shutdown()


def test_settings_with_enabled_but_missing_keys_returns_noop() -> None:
    """Verify that enabling Langfuse without keys safely returns NoopTracer."""
    cfg = Settings(langfuse_enabled=True, langfuse_public_key="", langfuse_secret_key="")
    tracer = get_tracer(cfg)

    assert isinstance(tracer, NoopTracer)
    assert not tracer.is_enabled()


def test_langfuse_tracer_active_with_mock_client() -> None:
    """Verify LangfuseTracer builds root chain and child spans from trace report."""
    mock_client = MagicMock()
    mock_root = MagicMock()
    mock_root.id = "trace-root-123"
    mock_child = MagicMock()
    mock_child.id = "span-child-456"

    mock_client.start_observation.return_value = mock_root
    mock_root.start_observation.return_value = mock_child

    tracer = LangfuseTracer(
        public_key="pk-test",
        secret_key="sk-test",
        client=mock_client,
    )
    assert tracer.is_enabled()

    state = {
        "owner": "testorg",
        "repo": "testrepo",
        "pull_number": 10,
        "config": "multi_agent_judge",
        "status": "completed",
        "cost_usd": 0.042,
        "tokens_prompt": 1200,
        "tokens_completion": 400,
        "circuit_breaker_tripped": False,
        "final_findings": [{"title": "Issue 1"}],
    }

    report = PipelineTraceReport(
        owner="testorg",
        repo="testrepo",
        pull_number=10,
        config="multi_agent_judge",
        nodes=[
            NodeTrace(
                node="security_reviewer",
                latency_seconds=1.2,
                tokens_prompt=600,
                tokens_completion=200,
                cost_usd=0.02,
                findings_count=1,
            ),
            NodeTrace(
                node="validate_findings",
                latency_seconds=0.1,
                tokens_prompt=0,
                tokens_completion=0,
                cost_usd=0.0,
            ),
        ],
    )

    trace_id = tracer.trace_pipeline(state, trace_report=report)
    assert trace_id == "trace-root-123"

    # Verify root chain observation
    mock_client.start_observation.assert_called_once()
    root_call = mock_client.start_observation.call_args[1]
    assert root_call["name"] == "review_pipeline:multi_agent_judge"
    assert root_call["as_type"] == "chain"
    assert root_call["usage_details"]["total"] == 1600
    assert root_call["cost_details"]["total"] == 0.042

    # Verify child node observations
    assert mock_root.start_observation.call_count == 2
    child_call_sec = mock_root.start_observation.call_args_list[0][1]
    assert child_call_sec["name"] == "security_reviewer"
    assert child_call_sec["as_type"] == "agent"
    assert child_call_sec["usage_details"]["input"] == 600

    child_call_val = mock_root.start_observation.call_args_list[1][1]
    assert child_call_val["name"] == "validate_findings"
    assert child_call_val["as_type"] == "span"

    assert mock_root.end.called
    assert mock_client.flush.called


def test_langfuse_tracer_resilience_on_start_observation_error() -> None:
    """Verify that network or API exceptions during tracing do not propagate."""
    mock_client = MagicMock()
    mock_client.start_observation.side_effect = ConnectionError("Langfuse collector offline")

    tracer = LangfuseTracer(
        public_key="pk-test",
        secret_key="sk-test",
        client=mock_client,
    )

    # Must return None and not raise ConnectionError
    trace_id = tracer.trace_pipeline({"owner": "o", "repo": "r"})
    assert trace_id is None


def test_langfuse_tracer_resilience_on_flush_and_shutdown_error() -> None:
    """Verify flush and shutdown exceptions are caught and suppressed."""
    mock_client = MagicMock()
    mock_client.flush.side_effect = TimeoutError("Timed out flushing traces")
    mock_client.shutdown.side_effect = RuntimeError("Failed to terminate worker thread")

    tracer = LangfuseTracer(
        public_key="pk-test",
        secret_key="sk-test",
        client=mock_client,
    )

    # Neither call should raise
    tracer.flush()
    tracer.shutdown()


def test_trace_llm_generation_success_and_resilience() -> None:
    """Verify trace_llm_generation records generation spans and handles errors."""
    mock_client = MagicMock()
    mock_gen = MagicMock()
    mock_gen.id = "gen-789"
    mock_client.start_observation.return_value = mock_gen

    tracer = LangfuseTracer(
        public_key="pk-test",
        secret_key="sk-test",
        client=mock_client,
    )

    res_id = tracer.trace_llm_generation(
        model="gemini-1.5-flash",
        prompt="Review this code",
        response="No issues found",
        cost_usd=0.001,
        prompt_tokens=100,
        completion_tokens=25,
        metadata={"reviewer": "security"},
    )
    assert res_id == "gen-789"
    assert mock_gen.end.called

    # Test error resilience
    mock_client.start_observation.side_effect = Exception("LLM tracing failed")
    assert tracer.trace_llm_generation(model="m", prompt="p", response="r") is None


@pytest.mark.asyncio
async def test_pipeline_run_integration_with_active_tracer() -> None:
    """Verify run_review_pipeline notifies active tracer upon completion."""
    mock_tracer = MagicMock(spec=BaseTracer)
    mock_tracer.is_enabled.return_value = True

    set_tracer(mock_tracer)

    fake_llm = FakeLLMClient(
        responses=['{"summary": "Traced review", "findings": []}'],
        model="fake-llm",
    )

    diff = "--- a/file.py\n+++ b/file.py\n@@ -1,1 +1,1 @@\n-old\n+new\n"
    result = await run_review_pipeline(
        owner="octocat",
        repo="Hello-World",
        pull_number=42,
        head_sha="6dcb09b5b57875f334f61aebed695e2e4193db5e",
        diff_text=diff,
        config="single_agent",
        dry_run=True,
        llm_client=fake_llm,
    )

    assert result["status"] == "completed"
    assert mock_tracer.trace_pipeline.called
    call_state, call_kwargs = mock_tracer.trace_pipeline.call_args
    assert call_state[0]["owner"] == "octocat"
    assert call_kwargs["trace_report"] is not None


@pytest.mark.asyncio
async def test_pipeline_run_integration_unaffected_when_tracer_raises() -> None:
    """Verify PR review pipeline succeeds completely even if tracer throws unexpected error."""
    mock_tracer = MagicMock(spec=BaseTracer)
    mock_tracer.is_enabled.return_value = True
    mock_tracer.trace_pipeline.side_effect = RuntimeError("Fatal tracer crash")

    set_tracer(mock_tracer)

    fake_llm = FakeLLMClient(
        responses=['{"summary": "Resilient review", "findings": []}'],
        model="fake-llm",
    )

    diff = "--- a/file.py\n+++ b/file.py\n@@ -1,1 +1,1 @@\n-old\n+new\n"
    result = await run_review_pipeline(
        owner="octocat",
        repo="Hello-World",
        pull_number=42,
        head_sha="6dcb09b5b57875f334f61aebed695e2e4193db5e",
        diff_text=diff,
        config="single_agent",
        dry_run=True,
        llm_client=fake_llm,
    )

    # Execution MUST NOT be aborted by tracer crash
    assert result["status"] == "completed"
    assert "summary" in result
