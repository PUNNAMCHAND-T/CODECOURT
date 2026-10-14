"""Deterministic finding validator node for the review graph.

T3.6: Enhanced with per-agent breakdown in trace, partial-status propagation,
and agent-error-awareness so a failed reviewer does not silently collapse the pipeline.
"""

import time
from typing import Any

from backend.app.agents.state import ReviewState
from backend.app.services.diff_parser import parse_unified_diff
from backend.app.services.finding_validator import validate_findings

# Multi-agent reviewer node names expected in a fan-out configuration
_MULTI_AGENT_REVIEWERS = frozenset({"security", "performance", "maintainability"})


def validate_findings_node(state: ReviewState) -> dict[str, Any]:
    """Execute deterministic validation on all collected agent findings without LLM calls.

    Enhancements (T3.6):
    - Records per-agent finding counts in the trace for observability.
    - Detects agents that produced errors (via node traces) and marks overall
      pipeline status as 'partial' rather than allowing silent data loss.
    - Preserves an explicit summary entry for each contributing agent.
    """
    start_time = time.perf_counter()

    raw_findings = state.get("raw_findings", [])
    agent_findings = state.get("agent_findings", {})
    config = state.get("config", "single_agent")

    parsed_diff = state.get("parsed_diff")
    if parsed_diff is None:
        diff_text = state.get("diff_text", "")
        parsed_diff = parse_unified_diff(diff_text)

    result = validate_findings(raw_findings, parsed_diff)
    latency = time.perf_counter() - start_time

    # Per-agent finding counts for observability
    per_agent_counts: dict[str, int] = {
        agent: len(findings) for agent, findings in agent_findings.items()
    }

    # Partial-status detection: an agent errored or circuit breaker tripped
    node_traces: list[dict[str, Any]] = state.get("traces", [])
    errored_agents: list[str] = [
        t["node"]
        for t in node_traces
        if t.get("error") is not None and t.get("node") in _MULTI_AGENT_REVIEWERS
    ]
    cb_tripped = bool(
        state.get("circuit_breaker_tripped")
        or any(t.get("circuit_breaker_tripped") for t in node_traces)
    )

    is_partial = (bool(errored_agents) and config != "single_agent") or cb_tripped

    trace: dict[str, Any] = {
        "node": "validate_findings",
        "latency_seconds": latency,
        "total_evaluated": result.total_evaluated,
        "accepted_count": len(result.accepted),
        "dropped_count": len(result.dropped),
        "repaired_count": result.repaired_count,
        "per_agent_counts": per_agent_counts,
        "errored_agents": errored_agents,
        "circuit_breaker_tripped": cb_tripped,
        "is_partial": is_partial,
    }

    updates: dict[str, Any] = {
        "validation_result": result,
        "validated_findings": result.accepted,
        "dropped_findings": result.dropped,
        "final_findings": result.accepted,  # default before judge override
        "status": "partial" if is_partial else "running",
        "node_latencies": {"validate_findings": latency},
        "traces": [trace],
    }
    if cb_tripped:
        updates["circuit_breaker_tripped"] = True

    # Build composite summary from all agent summaries
    if not state.get("summary"):
        agent_summaries = state.get("agent_summaries", {})
        if agent_summaries:
            summary_parts = [f"**{k.capitalize()}**: {v}" for k, v in agent_summaries.items() if v]
            if errored_agents:
                summary_parts.append(
                    f"Warning: Agents with errors (partial results): {', '.join(errored_agents)}"
                )
            if cb_tripped:
                cb_reason = state.get("circuit_breaker_reason") or "budget limit exceeded"
                summary_parts.append(
                    f"Notice: Circuit breaker halted further execution ({cb_reason}). Review is partial."
                )
            updates["summary"] = "\n\n".join(summary_parts)
        else:
            base_sum = (
                f"Validated {len(result.accepted)} finding(s) "
                f"({result.repaired_count} repaired, {len(result.dropped)} dropped)."
            )
            if cb_tripped:
                cb_reason = state.get("circuit_breaker_reason") or "budget limit exceeded"
                base_sum += f" Circuit breaker halted further execution ({cb_reason})."
            updates["summary"] = base_sum

    return updates
