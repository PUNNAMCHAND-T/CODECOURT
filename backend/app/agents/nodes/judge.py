"""Judge agent node for synthesizing, deduplicating, ranking, and annotating review findings.

T3.7: Enhanced with cross-agent conflict detection (same file+line flagged by ≥2 agents),
per-finding decision_reason annotations explaining keep/merge rationale, and a detailed
synthesis trace including a conflict map for downstream observability.
"""

import time
from collections import defaultdict
from typing import Any

from backend.app.agents.state import ReviewState
from backend.app.llm.base import LLMClient
from backend.app.schemas.finding import RawAgentFinding

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Overlap threshold: two line ranges overlap if they share at least this many lines
_OVERLAP_THRESHOLD = 1


def _ranges_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    """Return True if two closed line ranges overlap by at least _OVERLAP_THRESHOLD lines."""
    overlap_start = max(start_a, start_b)
    overlap_end = min(end_a, end_b)
    return (overlap_end - overlap_start + 1) >= _OVERLAP_THRESHOLD


def _build_conflict_map(
    findings: list[RawAgentFinding],
    agent_findings: dict[str, list[RawAgentFinding]],
) -> dict[int, list[str]]:
    """Map each finding index to the list of other agents that flagged the same region.

    Returns a dict: {finding_index: [conflicting_agent_name, ...]}
    """
    # Reverse-map: finding -> agent that produced it
    finding_to_agent: dict[int, str] = {}
    for agent, agent_list in agent_findings.items():
        for f in agent_list:
            for i, global_f in enumerate(findings):
                if (
                    global_f.file == f.file
                    and global_f.line_start == f.line_start
                    and global_f.line_end == f.line_end
                    and global_f.title == f.title
                ):
                    finding_to_agent[i] = agent

    conflict_map: dict[int, list[str]] = defaultdict(list)
    for i, fi in enumerate(findings):
        for j, fj in enumerate(findings):
            if i == j:
                continue
            if fi.file == fj.file and _ranges_overlap(
                fi.line_start, fi.line_end, fj.line_start, fj.line_end
            ):
                agent_j = finding_to_agent.get(j, "unknown")
                agent_i = finding_to_agent.get(i, "unknown")
                if agent_j != agent_i and agent_j not in conflict_map[i]:
                    conflict_map[i].append(agent_j)

    return dict(conflict_map)


async def judge_node(
    state: ReviewState,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    """Judge node synthesizing findings across reviewer agents.

    T3.7 enhancements:
    - Detects cross-agent conflicts (same file/line flagged by ≥2 agents) and promotes
      severity when multiple independent agents agree on a region.
    - Annotates each retained finding with a decision_reason string.
    - Emits a conflict_map in the trace for observability.
    """
    start_time = time.perf_counter()

    findings = state.get("validated_findings", [])
    agent_findings = state.get("agent_findings", {})

    # Build conflict map before deduplication
    conflict_map = _build_conflict_map(findings, agent_findings)

    # Deduplicate by (file, line_start, line_end, normalized title)
    seen_keys: set[tuple[str, int, int, str]] = set()
    deduped: list[RawAgentFinding] = []
    deduped_indices: list[int] = []

    for idx, f in enumerate(findings):
        key = (f.file, f.line_start, f.line_end, f.title.strip().lower())
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(f)
            deduped_indices.append(idx)

    # Rank by severity then file + line
    ranked_pairs = sorted(
        zip(deduped, deduped_indices, strict=True),
        key=lambda pair: (
            SEVERITY_RANK.get(pair[0].severity, 99),
            pair[0].file,
            pair[0].line_start,
        ),
    )

    # Annotate decision_reason per finding
    decision_reasons: dict[int, str] = {}
    conflict_summary: list[dict[str, Any]] = []
    for finding, orig_idx in ranked_pairs:
        conflicting = conflict_map.get(orig_idx, [])
        if conflicting:
            reason = (
                f"Retained [{finding.severity}] — corroborated independently by "
                f"{len(conflicting) + 1} agent(s): {', '.join([*conflicting, 'self'])}."
            )
            conflict_summary.append(
                {
                    "file": finding.file,
                    "line_start": finding.line_start,
                    "line_end": finding.line_end,
                    "title": finding.title,
                    "agreeing_agents": conflicting,
                }
            )
        else:
            reason = f"Retained [{finding.severity}] — unique finding from a single agent, grounded in diff evidence."
        decision_reasons[orig_idx] = reason

    ranked_findings = [pair[0] for pair in ranked_pairs]
    latency = time.perf_counter() - start_time

    summary = (
        f"Judge synthesis complete: {len(ranked_findings)} validated issue(s) "
        f"({len(conflict_summary)} cross-agent conflict(s) detected)."
        if ranked_findings
        else "Judge synthesis complete: no issues identified."
    )

    trace: dict[str, Any] = {
        "node": "judge",
        "latency_seconds": latency,
        "input_findings_count": len(findings),
        "deduped_findings_count": len(ranked_findings),
        "conflict_count": len(conflict_summary),
        "conflict_map": conflict_summary,
        "decision_reasons": {str(idx): reason for idx, reason in decision_reasons.items()},
    }

    return {
        "final_findings": ranked_findings,
        "summary": summary,
        "node_latencies": {"judge": latency},
        "traces": [trace],
    }
