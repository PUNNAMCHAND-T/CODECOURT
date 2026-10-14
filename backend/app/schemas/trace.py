"""Pydantic schemas for structured per-node execution trace storage.

T3.9: Defines NodeTrace (one per graph node execution) and PipelineTraceReport
(the complete trace for a full review pipeline run), enabling structured
observability, cost attribution, and latency profiling.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NodeTrace(BaseModel):
    """Structured trace record for a single graph node execution.

    Captures timing, token accounting, findings stats, error state,
    and any node-specific metadata (e.g. repair flags, conflict maps).
    """

    model_config = ConfigDict(extra="allow")

    node: str = Field(..., description="Name of the graph node (e.g. 'security', 'judge')")
    latency_seconds: float = Field(..., ge=0.0, description="Wall-clock execution time in seconds")

    # Token and cost accounting (only set for LLM-calling nodes)
    tokens_prompt: int = Field(default=0, ge=0, description="Number of prompt tokens consumed")
    tokens_completion: int = Field(
        default=0, ge=0, description="Number of completion tokens generated"
    )
    cost_usd: float = Field(default=0.0, ge=0.0, description="Estimated USD cost for this node")

    # Finding stats (set for reviewer nodes)
    findings_count: int = Field(default=0, ge=0, description="Number of findings produced")

    # Robustness flags (T3.8)
    repair_attempted: bool = Field(
        default=False, description="Whether JSON repair was attempted on malformed LLM output"
    )
    capped: bool = Field(
        default=False,
        description="Whether findings were capped at MAX_FINDINGS_PER_AGENT",
    )

    # Validation node fields
    total_evaluated: int | None = Field(default=None, description="Total findings evaluated")
    accepted_count: int | None = Field(default=None, description="Findings accepted by validator")
    dropped_count: int | None = Field(default=None, description="Findings dropped by validator")
    repaired_count: int | None = Field(default=None, description="Findings repaired by validator")
    per_agent_counts: dict[str, int] | None = Field(
        default=None, description="Per-agent finding counts at validation time"
    )
    errored_agents: list[str] | None = Field(
        default=None, description="Agent names that recorded errors before validation"
    )
    is_partial: bool | None = Field(
        default=None, description="Whether pipeline is running in partial mode"
    )

    # Judge node fields (T3.7)
    input_findings_count: int | None = Field(default=None, description="Findings input to judge")
    deduped_findings_count: int | None = Field(
        default=None, description="Findings after judge deduplication"
    )
    conflict_count: int | None = Field(
        default=None, description="Cross-agent conflicts detected by judge"
    )
    conflict_map: list[dict[str, Any]] | None = Field(
        default=None, description="Structured cross-agent conflict details"
    )
    decision_reasons: dict[str, str] | None = Field(
        default=None, description="Per-finding decision reason from judge"
    )

    # Publish node fields
    is_dry_run: bool | None = Field(default=None)
    published_state: str | None = Field(default=None)
    comments_count: int | None = Field(default=None)

    # Error field (None means success)
    error: str | None = Field(default=None, description="Error message if the node failed")


class PipelineTraceReport(BaseModel):
    """Complete structured trace for a single review pipeline run.

    Aggregates all NodeTrace records, total cost/token accounting, and
    final pipeline status for observability and cost attribution.
    """

    model_config = ConfigDict(extra="ignore")

    review_id: int | None = Field(default=None)
    owner: str = Field(default="")
    repo: str = Field(default="")
    pull_number: int = Field(default=0)
    head_sha: str = Field(default="")
    config: str = Field(default="single_agent")

    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = Field(default=None)

    status: str = Field(default="queued")
    error: str | None = Field(default=None)

    nodes: list[NodeTrace] = Field(
        default_factory=list, description="Ordered list of per-node trace records"
    )

    # Aggregate accounting
    total_tokens_prompt: int = Field(default=0, ge=0)
    total_tokens_completion: int = Field(default=0, ge=0)
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    total_latency_seconds: float = Field(default=0.0, ge=0.0)

    # Finding summary
    total_raw_findings: int = Field(default=0, ge=0)
    total_validated_findings: int = Field(default=0, ge=0)
    total_final_findings: int = Field(default=0, ge=0)
    total_dropped_findings: int = Field(default=0, ge=0)
