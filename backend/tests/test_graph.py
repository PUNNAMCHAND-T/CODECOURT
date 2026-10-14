"""Unit tests for LangGraph review pipeline state and graph skeleton on FakeLLM."""

import json

import pytest

from backend.app.agents.graph import build_review_graph, run_review_pipeline
from backend.app.agents.state import create_initial_state
from backend.app.llm.fake import FakeLLMClient
from backend.app.schemas.github import PullRequestMetadata

SAMPLE_DIFF = """diff --git a/app/auth.py b/app/auth.py
index 1234567..89abcdef 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -10,4 +10,6 @@ def login(username, password):
+    if not password:
+        raise ValueError('Empty password')
     return True
"""


def _sample_pr_metadata() -> PullRequestMetadata:
    return PullRequestMetadata.model_validate(
        {
            "id": 100,
            "number": 42,
            "title": "Add basic password check",
            "body": "Ensures password is not empty.",
            "state": "open",
            "owner": "octocat",
            "repo": "Hello-World",
            "head_sha": "abc123head",
            "base_sha": "base000000",
            "head_ref": "feature/auth",
            "base_ref": "main",
            "author": "octocat",
            "created_at": "2026-10-08T12:00:00Z",
            "html_url": "https://github.com/octocat/Hello-World/pull/42",
            "diff_url": "https://github.com/octocat/Hello-World/pull/42.diff",
        }
    )


@pytest.mark.asyncio
async def test_single_agent_pipeline_execution_on_fake_llm() -> None:
    canned_single_agent_response = json.dumps(
        {
            "summary": "Detected basic empty password check.",
            "findings": [
                {
                    "category": "security",
                    "severity": "high",
                    "file": "app/auth.py",
                    "line_start": 10,
                    "line_end": 12,
                    "title": "Empty password check should enforce complexity",
                    "explanation": "Checking only for non-empty password permits weak passwords.",
                    "evidence": "if not password:\n    raise ValueError('Empty password')",
                    "suggested_fix": "if len(password) < 8:\n    raise ValueError('Password too short')",
                    "confidence": 0.95,
                }
            ],
        }
    )

    fake_llm = FakeLLMClient(responses=[canned_single_agent_response])

    result = await run_review_pipeline(
        owner="octocat",
        repo="Hello-World",
        pull_number=42,
        head_sha="abc123head",
        diff_text=SAMPLE_DIFF,
        metadata=_sample_pr_metadata(),
        config="single_agent",
        dry_run=True,
        llm_client=fake_llm,
    )

    # Lifecycle status
    assert result["status"] == "completed"
    assert result["error"] is None

    # Context parsed
    assert result["parsed_diff"] is not None
    assert len(result["parsed_diff"].files) == 1

    # Findings
    assert len(result["raw_findings"]) == 1
    assert len(result["validated_findings"]) == 1
    assert len(result["final_findings"]) == 1
    assert result["final_findings"][0].category == "security"

    # Accounting
    assert result["tokens_prompt"] > 0
    assert result["tokens_completion"] > 0

    # Traces contain prepare_context, single_agent, validate_findings, publish
    trace_nodes = [t["node"] for t in result["traces"]]
    assert "prepare_context" in trace_nodes
    assert "single_agent" in trace_nodes
    assert "validate_findings" in trace_nodes
    assert "publish" in trace_nodes
    # Judge was not run in single_agent config
    assert "judge" not in trace_nodes

    # Publication outcome
    assert result["published_review"] is not None
    assert result["published_review"].is_dry_run is True
    assert result["published_review"].comment_count == 1


@pytest.mark.asyncio
async def test_multi_agent_judge_pipeline_execution_on_fake_llm() -> None:
    # 3 canned responses for security, performance, maintainability
    sec_response = json.dumps(
        {
            "summary": "Security review completed.",
            "findings": [
                {
                    "category": "security",
                    "severity": "critical",
                    "file": "app/auth.py",
                    "line_start": 10,
                    "line_end": 12,
                    "title": "Insecure password validation",
                    "explanation": "Weak password check",
                    "evidence": "if not password:",
                    "confidence": 0.99,
                }
            ],
        }
    )
    perf_response = json.dumps(
        {
            "summary": "Performance review completed.",
            "findings": [],
        }
    )
    maint_response = json.dumps(
        {
            "summary": "Maintainability review completed.",
            "findings": [
                {
                    "category": "maintainability",
                    "severity": "low",
                    "file": "app/auth.py",
                    "line_start": 10,
                    "line_end": 12,
                    "title": "Use custom exception",
                    "explanation": "Custom exception is preferred over ValueError",
                    "evidence": "raise ValueError('Empty password')",
                    "confidence": 0.8,
                }
            ],
        }
    )

    fake_llm = FakeLLMClient(responses=[sec_response, perf_response, maint_response])

    result = await run_review_pipeline(
        owner="octocat",
        repo="Hello-World",
        pull_number=42,
        head_sha="abc123head",
        diff_text=SAMPLE_DIFF,
        metadata=_sample_pr_metadata(),
        config="multi_agent_judge",
        dry_run=True,
        llm_client=fake_llm,
    )

    assert result["status"] == "completed"

    # Parallel fan-out collected both findings into raw_findings
    assert len(result["raw_findings"]) == 2
    assert "security" in result["agent_findings"]
    assert "performance" in result["agent_findings"]
    assert "maintainability" in result["agent_findings"]

    # Judge executed and ranked (critical first)
    assert len(result["final_findings"]) == 2
    assert result["final_findings"][0].severity == "critical"
    assert result["final_findings"][1].severity == "low"

    trace_nodes = [t["node"] for t in result["traces"]]
    assert "prepare_context" in trace_nodes
    assert "security" in trace_nodes
    assert "performance" in trace_nodes
    assert "maintainability" in trace_nodes
    assert "validate_findings" in trace_nodes
    assert "judge" in trace_nodes
    assert "publish" in trace_nodes


@pytest.mark.asyncio
async def test_multi_agent_no_judge_pipeline_bypasses_judge() -> None:
    sec_response = json.dumps(
        {
            "summary": "Security review completed.",
            "findings": [],
        }
    )
    perf_response = json.dumps(
        {
            "summary": "Performance review completed.",
            "findings": [],
        }
    )
    maint_response = json.dumps(
        {
            "summary": "Maintainability review completed.",
            "findings": [],
        }
    )

    fake_llm = FakeLLMClient(responses=[sec_response, perf_response, maint_response])

    result = await run_review_pipeline(
        owner="octocat",
        repo="Hello-World",
        pull_number=42,
        head_sha="abc123head",
        diff_text=SAMPLE_DIFF,
        metadata=_sample_pr_metadata(),
        config="multi_agent_no_judge",
        dry_run=True,
        llm_client=fake_llm,
    )

    assert result["status"] == "completed"
    trace_nodes = [t["node"] for t in result["traces"]]
    assert "judge" not in trace_nodes
    assert "publish" in trace_nodes


@pytest.mark.asyncio
async def test_reviewer_node_handles_malformed_json_gracefully() -> None:
    # Malformed output from LLM
    bad_response = "I am not returning valid JSON!"
    fake_llm = FakeLLMClient(responses=[bad_response])

    result = await run_review_pipeline(
        owner="octocat",
        repo="Hello-World",
        pull_number=42,
        head_sha="abc123head",
        diff_text=SAMPLE_DIFF,
        metadata=_sample_pr_metadata(),
        config="single_agent",
        dry_run=True,
        llm_client=fake_llm,
    )

    # Pipeline gracefully handles parsing failure and continues to completion with empty findings
    assert result["status"] == "completed"
    assert len(result["raw_findings"]) == 0
    assert len(result["final_findings"]) == 0

    single_agent_trace = next(t for t in result["traces"] if t["node"] == "single_agent")
    assert single_agent_trace["error"] is not None
    assert "Output parsing error" in single_agent_trace["error"]


def test_create_initial_state_defaults() -> None:
    state = create_initial_state(
        owner="octocat",
        repo="Hello-World",
        pull_number=42,
        head_sha="head123",
        diff_text="diff content",
    )
    assert state["owner"] == "octocat"
    assert state["repo"] == "Hello-World"
    assert state["pull_number"] == 42
    assert state["head_sha"] == "head123"
    assert state["config"] == "single_agent"
    assert state["status"] == "queued"
    assert state["tokens_prompt"] == 0
    assert state["tokens_completion"] == 0
    assert state["cost_usd"] == 0.0
    assert state["raw_findings"] == []


@pytest.mark.asyncio
async def test_graph_records_node_latencies() -> None:
    fake_llm = FakeLLMClient(
        responses=[json.dumps({"summary": "ok", "findings": []})],
        simulated_latency_ms=10,
    )
    result = await run_review_pipeline(
        owner="octocat",
        repo="Hello-World",
        pull_number=42,
        head_sha="abc123head",
        diff_text=SAMPLE_DIFF,
        config="single_agent",
        dry_run=True,
        llm_client=fake_llm,
    )

    latencies = result["node_latencies"]
    assert "prepare_context" in latencies
    assert "single_agent" in latencies
    assert "validate_findings" in latencies
    assert "publish" in latencies
    assert latencies["single_agent"] > 0


def test_build_review_graph_compiles() -> None:
    fake_llm = FakeLLMClient()
    graph = build_review_graph(llm_client=fake_llm)
    assert graph is not None
