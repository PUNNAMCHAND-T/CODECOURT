"""Trace storage service for per-node execution observability.

T3.9: Converts raw trace dicts accumulated in ReviewState into structured
NodeTrace Pydantic models and builds a complete PipelineTraceReport that
can be serialized to JSON for storage, debugging, or cost attribution.
"""

import logging
from datetime import datetime
from typing import Any

from backend.app.schemas.trace import NodeTrace, PipelineTraceReport

logger = logging.getLogger(__name__)


def _coerce_node_trace(raw: dict[str, Any]) -> NodeTrace:
    """Coerce a raw trace dict (as emitted by graph nodes) into a NodeTrace model.

    Unknown keys are preserved via extra="allow" on NodeTrace, so node-specific
    fields added in the future are not silently dropped.
    """
    try:
        return NodeTrace.model_validate(raw)
    except Exception as exc:
        logger.warning(
            "Failed to validate NodeTrace for node '%s': %s — using partial trace",
            raw.get("node", "unknown"),
            exc,
        )
        # Fallback: return a minimal trace with only node + latency
        try:
            fallback_latency = float(raw.get("latency_seconds", 0.0))
        except (TypeError, ValueError):
            fallback_latency = 0.0
        return NodeTrace(
            node=str(raw.get("node", "unknown")),
            latency_seconds=fallback_latency,
            error=f"Trace validation error: {exc}",
        )


def build_pipeline_trace_report(
    state: dict[str, Any],
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> PipelineTraceReport:
    """Build a complete PipelineTraceReport from a finished ReviewState.

    Args:
        state: The final ReviewState dict after graph execution.
        started_at: Optional pipeline start timestamp.
        finished_at: Optional pipeline finish timestamp (defaults to utcnow).

    Returns:
        A fully populated PipelineTraceReport with all NodeTrace records
        and aggregate cost/token/finding accounting.
    """
    raw_traces: list[dict[str, Any]] = state.get("traces", [])
    node_traces = [_coerce_node_trace(t) for t in raw_traces]

    # Aggregate accounting
    total_tokens_prompt = state.get("tokens_prompt", 0) or 0
    total_tokens_completion = state.get("tokens_completion", 0) or 0
    total_cost_usd = state.get("cost_usd", 0.0) or 0.0
    total_latency = sum(t.latency_seconds for t in node_traces)

    # Finding counts
    raw_findings = state.get("raw_findings", []) or []
    validated_findings = state.get("validated_findings", []) or []
    final_findings = state.get("final_findings", []) or []
    dropped_findings = state.get("dropped_findings", []) or []

    return PipelineTraceReport(
        review_id=state.get("review_id"),
        owner=state.get("owner", ""),
        repo=state.get("repo", ""),
        pull_number=state.get("pull_number", 0),
        head_sha=state.get("head_sha", ""),
        config=state.get("config", "single_agent"),
        started_at=started_at or datetime.utcnow(),
        finished_at=finished_at or datetime.utcnow(),
        status=state.get("status", "completed"),
        error=state.get("error"),
        nodes=node_traces,
        total_tokens_prompt=total_tokens_prompt,
        total_tokens_completion=total_tokens_completion,
        total_cost_usd=total_cost_usd,
        total_latency_seconds=total_latency,
        total_raw_findings=len(raw_findings),
        total_validated_findings=len(validated_findings),
        total_final_findings=len(final_findings),
        total_dropped_findings=len(dropped_findings),
    )


def serialize_trace_report(report: PipelineTraceReport) -> str:
    """Serialize a PipelineTraceReport to a JSON string.

    Args:
        report: A fully constructed PipelineTraceReport.

    Returns:
        JSON string representation suitable for storage or logging.
    """
    return report.model_dump_json(indent=2)
