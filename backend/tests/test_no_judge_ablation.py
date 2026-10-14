"""Unit and ablation tests for T3.10: No-judge multi-agent review configuration.

Verifies that the 'multi_agent_no_judge' configuration:
1. Runs the 3 specialized reviewers (security, performance, maintainability) in parallel fan-out.
2. Runs deterministic finding validation without LLM calls.
3. Completely bypasses the judge node, retaining raw validated findings without deduplication.
4. Generates a composite summary directly from reviewer outputs.
5. Records accurate token, cost, latency, and trace accounting excluding judge overhead.
6. Propagates 'partial' status when a reviewer agent fails.
"""

import json
from datetime import datetime

import pytest

from backend.app.agents.graph import run_review_pipeline
from backend.app.llm.fake import FakeLLMClient
from backend.app.schemas.github import PullRequestMetadata
from backend.app.services.trace_store import build_pipeline_trace_report

SAMPLE_DIFF = """diff --git a/app/auth.py b/app/auth.py
index 1234567..89abcdef 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -10,6 +10,12 @@ def process_login(username, password):
+    # Check credentials
+    query = f"SELECT * FROM users WHERE user = '{username}'"
+    for user in db.execute(query):
+        if not user.is_active:
+            raise Exception("Inactive user")
+    return True
"""


def _sample_metadata() -> PullRequestMetadata:
    return PullRequestMetadata.model_validate(
        {
            "id": 101,
            "number": 43,
            "title": "Add process_login endpoint",
            "body": "Implements basic login processing.",
            "state": "open",
            "owner": "testorg",
            "repo": "testrepo",
            "head_sha": "headsha123",
            "base_sha": "basesha000",
            "head_ref": "feature/login",
            "base_ref": "main",
            "author": "dev-user",
            "created_at": "2026-10-09T00:00:00Z",
            "html_url": "https://github.com/testorg/testrepo/pull/43",
            "diff_url": "https://github.com/testorg/testrepo/pull/43.diff",
        }
    )


@pytest.mark.asyncio
async def test_no_judge_ablation_runs_three_reviewers_and_bypasses_judge() -> None:
    """multi_agent_no_judge fans out to 3 reviewers, validates, and publishes without judge."""
    sec_payload = json.dumps(
        {
            "summary": "Detected critical SQL injection.",
            "findings": [
                {
                    "category": "security",
                    "severity": "critical",
                    "file": "app/auth.py",
                    "line_start": 12,
                    "line_end": 12,
                    "title": "SQL injection via f-string query formatting",
                    "explanation": "Direct interpolation of username into SQL string enables injection.",
                    "evidence": "query = f\"SELECT * FROM users WHERE user = '{username}'\"",
                    "suggested_fix": "db.execute('SELECT * FROM users WHERE user = :u', {'u': username})",
                    "confidence": 0.98,
                }
            ],
        }
    )
    perf_payload = json.dumps(
        {
            "summary": "Detected unbuffered iteration query.",
            "findings": [
                {
                    "category": "performance",
                    "severity": "high",
                    "file": "app/auth.py",
                    "line_start": 13,
                    "line_end": 13,
                    "title": "Unbuffered full table scan loop",
                    "explanation": "Iterating over db.execute without pagination or LIMIT.",
                    "evidence": "for user in db.execute(query):",
                    "suggested_fix": "user = db.execute(query).first()",
                    "confidence": 0.88,
                }
            ],
        }
    )
    maint_payload = json.dumps(
        {
            "summary": "Detected generic Exception antipattern.",
            "findings": [
                {
                    "category": "maintainability",
                    "severity": "low",
                    "file": "app/auth.py",
                    "line_start": 15,
                    "line_end": 15,
                    "title": "Generic Exception raised instead of domain error",
                    "explanation": "Raising bare Exception obscures caller error handling.",
                    "evidence": 'raise Exception("Inactive user")',
                    "suggested_fix": "raise InactiveUserError('Inactive user')",
                    "confidence": 0.82,
                }
            ],
        }
    )

    fake_llm = FakeLLMClient(responses=[sec_payload, perf_payload, maint_payload])

    result = await run_review_pipeline(
        owner="testorg",
        repo="testrepo",
        pull_number=43,
        head_sha="headsha123",
        diff_text=SAMPLE_DIFF,
        metadata=_sample_metadata(),
        config="multi_agent_no_judge",
        dry_run=True,
        llm_client=fake_llm,
    )

    # 1. Pipeline completed cleanly
    assert result["status"] == "completed"
    assert result["error"] is None

    # 2. All 3 reviewer agents executed and populated findings
    assert "security" in result["agent_findings"]
    assert "performance" in result["agent_findings"]
    assert "maintainability" in result["agent_findings"]
    assert len(result["raw_findings"]) == 3

    # 3. Deterministic validation validated all 3 findings
    assert len(result["validated_findings"]) == 3

    # 4. Final findings contain all 3 validated findings directly (bypassing judge)
    assert len(result["final_findings"]) == 3
    final_categories = {f.category for f in result["final_findings"]}
    assert final_categories == {"security", "performance", "maintainability"}

    # 5. Judge was NEVER executed
    trace_nodes = [t["node"] for t in result["traces"]]
    assert "judge" not in trace_nodes
    assert "prepare_context" in trace_nodes
    assert "security" in trace_nodes
    assert "performance" in trace_nodes
    assert "maintainability" in trace_nodes
    assert "validate_findings" in trace_nodes
    assert "publish" in trace_nodes
    assert "judge" not in result["node_latencies"]

    # 6. Composite summary includes all 3 agent summaries
    summary = result.get("summary", "")
    assert "Security" in summary
    assert "Performance" in summary
    assert "Maintainability" in summary

    # 7. Published review reflects the 3 comments
    assert result["published_review"] is not None
    assert result["published_review"].comment_count == 3


@pytest.mark.asyncio
async def test_no_judge_ablation_preserves_duplicates_unlike_judge() -> None:
    """In no-judge ablation, duplicate findings across agents are NOT deduplicated.

    This test confirms the core ablation thesis: the judge removes duplicate findings,
    while multi_agent_no_judge retains all raw validated findings.
    """
    # Both security and maintainability report the exact same issue on line 12
    duplicate_finding = {
        "category": "security",
        "severity": "critical",
        "file": "app/auth.py",
        "line_start": 12,
        "line_end": 12,
        "title": "SQL injection risk",
        "explanation": "Untrusted input in query string",
        "evidence": "query = f\"SELECT * FROM users WHERE user = '{username}'\"",
        "confidence": 0.95,
    }

    sec_res = json.dumps({"summary": "Sec summary", "findings": [duplicate_finding]})
    perf_res = json.dumps({"summary": "Perf summary", "findings": []})
    # Maintainability flags identical line and title
    maint_finding = dict(duplicate_finding)
    maint_finding["category"] = "maintainability"
    maint_res = json.dumps({"summary": "Maint summary", "findings": [maint_finding]})

    # 1. Run multi_agent_no_judge
    llm_no_judge = FakeLLMClient(responses=[sec_res, perf_res, maint_res])
    result_no_judge = await run_review_pipeline(
        owner="testorg",
        repo="testrepo",
        pull_number=43,
        head_sha="headsha123",
        diff_text=SAMPLE_DIFF,
        config="multi_agent_no_judge",
        dry_run=True,
        llm_client=llm_no_judge,
    )

    # In no-judge ablation, both duplicates remain in final_findings
    assert len(result_no_judge["final_findings"]) == 2

    # 2. Run multi_agent_judge with identical responses
    llm_judge = FakeLLMClient(responses=[sec_res, perf_res, maint_res])
    result_judge = await run_review_pipeline(
        owner="testorg",
        repo="testrepo",
        pull_number=43,
        head_sha="headsha123",
        diff_text=SAMPLE_DIFF,
        config="multi_agent_judge",
        dry_run=True,
        llm_client=llm_judge,
    )

    # In judge config, duplicate is deduplicated to 1 finding with corroborated reason
    assert len(result_judge["final_findings"]) == 1
    assert "judge" in [t["node"] for t in result_judge["traces"]]


@pytest.mark.asyncio
async def test_no_judge_ablation_partial_status_on_reviewer_failure() -> None:
    """When a reviewer encounters an error in multi_agent_no_judge, status becomes partial."""
    sec_payload = json.dumps(
        {
            "summary": "Security ok",
            "findings": [
                {
                    "category": "security",
                    "severity": "medium",
                    "file": "app/auth.py",
                    "line_start": 12,
                    "line_end": 12,
                    "title": "Use parameterized queries",
                    "explanation": "Avoid string interpolation",
                    "evidence": "query = f\"SELECT * FROM users WHERE user = '{username}'\"",
                    "confidence": 0.9,
                }
            ],
        }
    )
    # Performance returns malformed non-JSON that cannot be repaired
    perf_payload = "NOT VALID JSON <<<>>> GARBAGE"
    maint_payload = json.dumps({"summary": "Maint clean", "findings": []})

    fake_llm = FakeLLMClient(responses=[sec_payload, perf_payload, maint_payload])

    result = await run_review_pipeline(
        owner="testorg",
        repo="testrepo",
        pull_number=43,
        head_sha="headsha123",
        diff_text=SAMPLE_DIFF,
        config="multi_agent_no_judge",
        dry_run=True,
        llm_client=fake_llm,
    )

    # Status must be 'partial' to honestly reflect that the performance reviewer errored
    assert result["status"] == "partial"
    # Surviving security finding is still published
    assert len(result["final_findings"]) == 1
    assert result["published_review"] is not None
    assert result["published_review"].comment_count == 1

    # Trace report reflects partial status and errored agent
    report = build_pipeline_trace_report(
        dict(result),
        started_at=datetime.utcnow(),
    )
    assert report.status == "partial"
    val_trace = next(t for t in report.nodes if t.node == "validate_findings")
    assert val_trace.is_partial is True
    assert val_trace.errored_agents == ["performance"]


@pytest.mark.asyncio
async def test_no_judge_ablation_cost_and_token_accounting() -> None:
    """multi_agent_no_judge accumulates tokens and costs only from reviewer nodes."""
    res = json.dumps({"summary": "ok", "findings": []})
    fake_llm = FakeLLMClient(responses=[res, res, res], model="gemini-1.5-flash")

    result = await run_review_pipeline(
        owner="testorg",
        repo="testrepo",
        pull_number=43,
        head_sha="headsha123",
        diff_text=SAMPLE_DIFF,
        config="multi_agent_no_judge",
        model="gemini-1.5-flash",
        dry_run=True,
        llm_client=fake_llm,
    )

    assert result["tokens_prompt"] > 0
    assert result["tokens_completion"] > 0
    assert result["cost_usd"] > 0.0

    # Ensure traces contain exactly the 6 expected nodes
    trace_nodes = [t["node"] for t in result["traces"]]
    assert len(trace_nodes) == 6
    assert trace_nodes[0] == "prepare_context"
    assert set(trace_nodes[1:4]) == {"security", "performance", "maintainability"}
    assert trace_nodes[4] == "validate_findings"
    assert trace_nodes[5] == "publish"
    assert "judge" not in trace_nodes
