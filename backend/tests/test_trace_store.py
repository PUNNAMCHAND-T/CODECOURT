"""Tests for T3.6-T3.9: validate_findings partial status, judge conflict detection,
reviewer output repair/cap, NodeTrace schema, and PipelineTraceReport trace store.
"""

import json
from datetime import datetime

import pytest

from backend.app.agents.nodes.judge import _build_conflict_map, _ranges_overlap
from backend.app.agents.nodes.reviewers import MAX_FINDINGS_PER_AGENT, _attempt_json_repair
from backend.app.agents.nodes.validate_findings import (
    _MULTI_AGENT_REVIEWERS,
    validate_findings_node,
)
from backend.app.agents.state import create_initial_state
from backend.app.llm.fake import FakeLLMClient
from backend.app.schemas.finding import AgentReviewOutput, RawAgentFinding
from backend.app.schemas.trace import NodeTrace
from backend.app.services.trace_store import (
    _coerce_node_trace,
    build_pipeline_trace_report,
    serialize_trace_report,
)

# ---------------------------------------------------------------------------
# T3.6 — validate_findings partial status
# ---------------------------------------------------------------------------


def _make_finding(
    file: str = "app/foo.py",
    line_start: int = 1,
    line_end: int = 5,
    category: str = "security",
    severity: str = "high",
    title: str = "Test finding",
) -> RawAgentFinding:
    return RawAgentFinding(
        category=category,
        severity=severity,
        file=file,
        line_start=line_start,
        line_end=line_end,
        title=title,
        explanation="Detailed explanation of the issue.",
        evidence="quoted code snippet",
        suggested_fix="fix suggestion",
        confidence=0.9,
    )


def test_validate_findings_node_per_agent_counts_in_trace() -> None:
    finding = _make_finding()
    state = create_initial_state(owner="o", repo="r", pull_number=1, head_sha="abc", diff_text="")
    state["agent_findings"] = {"security": [finding], "performance": []}
    state["raw_findings"] = [finding]
    state["config"] = "multi_agent_no_judge"

    result = validate_findings_node(state)
    trace = result["traces"][0]

    assert trace["per_agent_counts"] == {"security": 1, "performance": 0}
    assert trace["errored_agents"] == []
    assert trace["is_partial"] is False


def test_validate_findings_node_partial_status_when_agent_errored() -> None:
    state = create_initial_state(owner="o", repo="r", pull_number=1, head_sha="abc", diff_text="")
    state["config"] = "multi_agent_no_judge"
    state["agent_findings"] = {"security": [], "performance": []}
    state["raw_findings"] = []
    # Simulate a security agent error in the accumulated traces
    state["traces"] = [
        {
            "node": "security",
            "latency_seconds": 0.5,
            "findings_count": 0,
            "error": "LLM API timeout",
            "repair_attempted": False,
            "capped": False,
            "tokens_prompt": 0,
            "tokens_completion": 0,
            "cost_usd": 0.0,
        }
    ]

    result = validate_findings_node(state)
    trace = result["traces"][0]

    assert trace["errored_agents"] == ["security"]
    assert trace["is_partial"] is True
    assert result["status"] == "partial"


def test_validate_findings_node_no_partial_for_single_agent() -> None:
    """Single-agent config should never trigger partial status."""
    state = create_initial_state(owner="o", repo="r", pull_number=1, head_sha="abc", diff_text="")
    state["config"] = "single_agent"
    state["agent_findings"] = {}
    state["raw_findings"] = []
    state["traces"] = [{"node": "single_agent", "latency_seconds": 0.1, "error": "Some error"}]

    result = validate_findings_node(state)
    trace = result["traces"][0]
    assert trace["is_partial"] is False
    assert result["status"] == "running"


def test_multi_agent_reviewers_constant() -> None:
    assert "security" in _MULTI_AGENT_REVIEWERS
    assert "performance" in _MULTI_AGENT_REVIEWERS
    assert "maintainability" in _MULTI_AGENT_REVIEWERS
    assert "single_agent" not in _MULTI_AGENT_REVIEWERS


# ---------------------------------------------------------------------------
# T3.7 — judge conflict detection and decision reasons
# ---------------------------------------------------------------------------


def test_ranges_overlap_basic() -> None:
    assert _ranges_overlap(1, 5, 3, 8) is True  # overlap at 3-5
    assert _ranges_overlap(1, 5, 6, 10) is False  # adjacent but no overlap
    assert _ranges_overlap(1, 10, 10, 15) is True  # single line overlap
    assert _ranges_overlap(5, 5, 5, 5) is True  # same line


def test_build_conflict_map_detects_cross_agent_overlap() -> None:
    f_sec = _make_finding(
        file="app/auth.py", line_start=10, line_end=20, category="security", title="SQL injection"
    )
    f_perf = _make_finding(
        file="app/auth.py",
        line_start=15,
        line_end=25,
        category="performance",
        title="N+1 in auth query",
    )

    findings = [f_sec, f_perf]
    agent_findings = {"security": [f_sec], "performance": [f_perf]}

    conflict_map = _build_conflict_map(findings, agent_findings)

    # Both findings overlap at lines 15-20, so each should see the other agent
    assert 0 in conflict_map or 1 in conflict_map  # at least one conflict detected


def test_build_conflict_map_no_conflict_different_files() -> None:
    f_a = _make_finding(
        file="app/auth.py", line_start=1, line_end=5, category="security", title="Auth bypass"
    )
    f_b = _make_finding(
        file="app/db.py", line_start=1, line_end=5, category="performance", title="Slow query"
    )

    findings = [f_a, f_b]
    agent_findings = {"security": [f_a], "performance": [f_b]}

    conflict_map = _build_conflict_map(findings, agent_findings)
    # Different files — no conflicts
    assert conflict_map.get(0, []) == []
    assert conflict_map.get(1, []) == []


@pytest.mark.asyncio
async def test_judge_node_conflict_in_trace() -> None:
    from backend.app.agents.nodes.judge import judge_node

    f_sec = _make_finding(
        file="app/auth.py",
        line_start=10,
        line_end=20,
        category="security",
        title="SQL injection risk",
    )
    f_perf = _make_finding(
        file="app/auth.py",
        line_start=15,
        line_end=25,
        category="performance",
        title="N+1 in overlapping region",
    )

    state = create_initial_state(owner="o", repo="r", pull_number=1, head_sha="abc", diff_text="")
    state["validated_findings"] = [f_sec, f_perf]
    state["agent_findings"] = {"security": [f_sec], "performance": [f_perf]}

    result = await judge_node(state)
    trace = result["traces"][0]

    assert "conflict_count" in trace
    assert "conflict_map" in trace
    assert "decision_reasons" in trace
    assert len(result["final_findings"]) == 2  # both unique titles, no dedup


@pytest.mark.asyncio
async def test_judge_node_deduplicates_exact_duplicates() -> None:
    from backend.app.agents.nodes.judge import judge_node

    f1 = _make_finding(file="app/foo.py", line_start=5, line_end=10, title="Exact dupe")
    f2 = _make_finding(file="app/foo.py", line_start=5, line_end=10, title="Exact dupe")

    state = create_initial_state(owner="o", repo="r", pull_number=1, head_sha="abc", diff_text="")
    state["validated_findings"] = [f1, f2]
    state["agent_findings"] = {"security": [f1], "performance": [f2]}

    result = await judge_node(state)
    assert len(result["final_findings"]) == 1  # deduped to one


@pytest.mark.asyncio
async def test_judge_node_ranks_critical_before_low() -> None:
    from backend.app.agents.nodes.judge import judge_node

    f_low = _make_finding(
        file="app/a.py", line_start=1, line_end=2, severity="low", title="Low issue"
    )
    f_crit = _make_finding(
        file="app/a.py", line_start=3, line_end=4, severity="critical", title="Critical issue"
    )

    state = create_initial_state(owner="o", repo="r", pull_number=1, head_sha="abc", diff_text="")
    state["validated_findings"] = [f_low, f_crit]
    state["agent_findings"] = {}

    result = await judge_node(state)
    assert result["final_findings"][0].severity == "critical"
    assert result["final_findings"][1].severity == "low"


# ---------------------------------------------------------------------------
# T3.8 — JSON repair and findings cap
# ---------------------------------------------------------------------------


def test_attempt_json_repair_valid_json() -> None:
    valid = json.dumps({"summary": "ok", "findings": []})
    result = _attempt_json_repair(valid)
    assert result is not None
    assert isinstance(result, AgentReviewOutput)
    assert result.findings == []


def test_attempt_json_repair_embedded_json() -> None:
    """Repair should extract the JSON object from surrounding text."""
    finding_obj = {
        "category": "security",
        "severity": "high",
        "file": "app/auth.py",
        "line_start": 1,
        "line_end": 3,
        "title": "SQL injection",
        "explanation": "Unsanitized user input used in SQL query.",
        "evidence": "cursor.execute(query % user_input)",
        "suggested_fix": "Use parameterized queries.",
        "confidence": 0.9,
    }
    embedded = (
        "Here is my review:\n"
        + json.dumps({"summary": "One finding.", "findings": [finding_obj]})
        + "\nDone."
    )
    result = _attempt_json_repair(embedded)
    assert result is not None
    assert len(result.findings) == 1
    assert result.findings[0].severity == "high"


def test_attempt_json_repair_returns_none_for_garbage() -> None:
    result = _attempt_json_repair("This is completely plain text with no JSON at all.")
    assert result is None


@pytest.mark.asyncio
async def test_reviewer_caps_findings_at_max() -> None:
    from backend.app.agents.nodes.reviewers import security_reviewer_node

    finding_template = {
        "category": "security",
        "severity": "low",
        "file": "app/foo.py",
        "line_start": 1,
        "line_end": 2,
        "title": "Minor issue",
        "explanation": "Some explanation.",
        "evidence": "code",
        "suggested_fix": "fix",
        "confidence": 0.5,
    }
    # Produce MAX_FINDINGS_PER_AGENT + 5 findings
    many_findings = [
        dict(finding_template, title=f"Minor issue #{i}", line_start=i, line_end=i + 1)
        for i in range(1, MAX_FINDINGS_PER_AGENT + 6)
    ]
    canned = json.dumps({"summary": "Many findings.", "findings": many_findings})

    fake_llm = FakeLLMClient(responses=[canned])
    state = create_initial_state(
        owner="o", repo="r", pull_number=1, head_sha="abc", diff_text="diff"
    )

    result = await security_reviewer_node(state, fake_llm)

    assert len(result["agent_findings"]["security"]) == MAX_FINDINGS_PER_AGENT
    trace = result["traces"][0]
    assert trace["capped"] is True
    assert trace["findings_count"] == MAX_FINDINGS_PER_AGENT


# ---------------------------------------------------------------------------
# T3.9 — NodeTrace schema and PipelineTraceReport
# ---------------------------------------------------------------------------


def test_node_trace_basic_validation() -> None:
    trace = NodeTrace(node="security", latency_seconds=0.42)
    assert trace.node == "security"
    assert trace.latency_seconds == 0.42
    assert trace.error is None
    assert trace.repair_attempted is False
    assert trace.capped is False


def test_node_trace_extra_fields_preserved() -> None:
    """extra='allow' means unknown fields from new nodes are not dropped."""
    trace = NodeTrace.model_validate(
        {
            "node": "future_node",
            "latency_seconds": 0.1,
            "some_new_field": "hello",
        }
    )
    assert trace.some_new_field == "hello"


def test_coerce_node_trace_valid() -> None:
    raw = {
        "node": "judge",
        "latency_seconds": 0.15,
        "input_findings_count": 3,
        "deduped_findings_count": 2,
        "conflict_count": 1,
    }
    trace = _coerce_node_trace(raw)
    assert trace.node == "judge"
    assert trace.input_findings_count == 3


def test_coerce_node_trace_invalid_graceful_fallback() -> None:
    """Malformed trace dict should not raise; fallback partial trace returned."""
    raw = {"node": "broken", "latency_seconds": "not_a_number"}
    trace = _coerce_node_trace(raw)
    assert trace.node == "broken"
    assert trace.error is not None
    assert "Trace validation error" in trace.error


def test_build_pipeline_trace_report_basic() -> None:
    state = {
        "owner": "octocat",
        "repo": "Hello-World",
        "pull_number": 42,
        "head_sha": "abc123",
        "config": "multi_agent_judge",
        "status": "completed",
        "error": None,
        "tokens_prompt": 500,
        "tokens_completion": 200,
        "cost_usd": 0.0012,
        "raw_findings": [_make_finding()],
        "validated_findings": [_make_finding()],
        "final_findings": [_make_finding()],
        "dropped_findings": [],
        "traces": [
            {"node": "prepare_context", "latency_seconds": 0.01, "files_count": 2},
            {"node": "security", "latency_seconds": 1.2, "findings_count": 1, "error": None},
            {"node": "judge", "latency_seconds": 0.05, "deduped_findings_count": 1},
            {"node": "publish", "latency_seconds": 0.3, "is_dry_run": True},
        ],
    }

    report = build_pipeline_trace_report(state)
    assert report.owner == "octocat"
    assert report.total_tokens_prompt == 500
    assert report.total_cost_usd == 0.0012
    assert len(report.nodes) == 4
    assert report.total_raw_findings == 1
    assert report.total_final_findings == 1
    assert report.total_dropped_findings == 0


def test_serialize_trace_report_is_valid_json() -> None:
    state = {
        "owner": "o",
        "repo": "r",
        "pull_number": 1,
        "head_sha": "abc",
        "config": "single_agent",
        "status": "completed",
        "error": None,
        "tokens_prompt": 100,
        "tokens_completion": 50,
        "cost_usd": 0.0001,
        "raw_findings": [],
        "validated_findings": [],
        "final_findings": [],
        "dropped_findings": [],
        "traces": [{"node": "single_agent", "latency_seconds": 0.5}],
    }
    report = build_pipeline_trace_report(state)
    json_str = serialize_trace_report(report)
    parsed = json.loads(json_str)
    assert parsed["owner"] == "o"
    assert isinstance(parsed["nodes"], list)
    assert len(parsed["nodes"]) == 1


def test_pipeline_trace_report_aggregate_latency() -> None:
    state = {
        "owner": "o",
        "repo": "r",
        "pull_number": 1,
        "head_sha": "abc",
        "config": "single_agent",
        "status": "completed",
        "error": None,
        "tokens_prompt": 0,
        "tokens_completion": 0,
        "cost_usd": 0.0,
        "raw_findings": [],
        "validated_findings": [],
        "final_findings": [],
        "dropped_findings": [],
        "traces": [
            {"node": "prepare_context", "latency_seconds": 0.1},
            {"node": "single_agent", "latency_seconds": 2.5},
            {"node": "validate_findings", "latency_seconds": 0.05},
            {"node": "publish", "latency_seconds": 0.3},
        ],
    }
    report = build_pipeline_trace_report(state, started_at=datetime(2026, 10, 9, 0, 0, 0))
    assert abs(report.total_latency_seconds - 2.95) < 0.001
