"""LangGraph state definition for the CodeCourt review pipeline.

Represents all data flowing through the multi-agent execution graph,
including input PR metadata, diffs, parallel agent findings, deterministic validation
results, judge synthesis, token/cost accounting, and per-node execution traces.
"""

import operator
from typing import Annotated, Any, Literal, TypedDict

from backend.app.schemas.diff import ParsedDiff
from backend.app.schemas.finding import (
    FindingValidationResult,
    RawAgentFinding,
    ValidatedFinding,
)
from backend.app.schemas.github import GitHubPublishedReview, PullRequestMetadata

ReviewConfigType = Literal["single_agent", "multi_agent_no_judge", "multi_agent_judge"]
ReviewStatusType = Literal["queued", "running", "completed", "partial", "failed"]


def merge_dict_updates(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Merge dictionary updates across parallel graph nodes."""
    merged = dict(a)
    merged.update(b)
    return merged


def reduce_bool_or(a: bool | None, b: bool | None) -> bool:
    """Logical OR reducer across parallel graph node updates."""
    return bool(a or b)


def reduce_first_string(a: str | None, b: str | None) -> str | None:
    """Reducer retaining first non-empty string across parallel graph node updates."""
    return a or b


class ReviewState(TypedDict, total=False):
    """Unified state schema for the CodeCourt review graph."""

    # 1. Identification and configuration
    review_id: int | None
    owner: str
    repo: str
    pull_number: int
    head_sha: str
    config: ReviewConfigType
    model: str
    dry_run: bool

    # 2. Input artifacts
    metadata: PullRequestMetadata | None
    diff_text: str
    parsed_diff: ParsedDiff | None

    # 3. Agent findings (parallel fan-out reducers)
    agent_findings: Annotated[dict[str, list[RawAgentFinding]], merge_dict_updates]
    agent_summaries: Annotated[dict[str, str], merge_dict_updates]
    raw_findings: Annotated[list[RawAgentFinding], operator.add]

    # 4. Deterministic validation artifacts
    validation_result: FindingValidationResult | None
    validated_findings: list[RawAgentFinding]
    dropped_findings: list[ValidatedFinding]

    # 5. Judge synthesis artifacts
    final_findings: list[RawAgentFinding]
    summary: str

    # 6. Publishing artifacts
    published_review: GitHubPublishedReview | None

    # 7. Metrics & accounting (accumulated across all nodes)
    tokens_prompt: Annotated[int, operator.add]
    tokens_completion: Annotated[int, operator.add]
    cost_usd: Annotated[float, operator.add]
    node_latencies: Annotated[dict[str, float], merge_dict_updates]
    traces: Annotated[list[dict[str, Any]], operator.add]
    max_budget_usd: float | None
    circuit_breaker_tripped: Annotated[bool, reduce_bool_or]
    circuit_breaker_reason: Annotated[str | None, reduce_first_string]

    # 8. Pipeline lifecycle status
    status: ReviewStatusType
    error: str | None


def create_initial_state(
    owner: str,
    repo: str,
    pull_number: int,
    head_sha: str,
    diff_text: str,
    metadata: PullRequestMetadata | None = None,
    config: ReviewConfigType = "single_agent",
    model: str = "fake-llm",
    dry_run: bool = True,
    review_id: int | None = None,
    max_budget_usd: float | None = None,
) -> ReviewState:
    """Create a fully initialized ReviewState for graph execution."""
    return {
        "review_id": review_id,
        "owner": owner,
        "repo": repo,
        "pull_number": pull_number,
        "head_sha": head_sha,
        "config": config,
        "model": model,
        "dry_run": dry_run,
        "metadata": metadata,
        "diff_text": diff_text,
        "parsed_diff": None,
        "agent_findings": {},
        "agent_summaries": {},
        "raw_findings": [],
        "validation_result": None,
        "validated_findings": [],
        "dropped_findings": [],
        "final_findings": [],
        "summary": "",
        "published_review": None,
        "tokens_prompt": 0,
        "tokens_completion": 0,
        "cost_usd": 0.0,
        "node_latencies": {},
        "traces": [],
        "max_budget_usd": max_budget_usd,
        "circuit_breaker_tripped": False,
        "circuit_breaker_reason": None,
        "status": "queued",
        "error": None,
    }
