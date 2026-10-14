"""LangGraph compilation and execution pipeline for CodeCourt pull request reviews.

Coordinates prepare_context, parallel reviewer agents (or baseline single-agent),
deterministic finding validation, judge synthesis, and review publication.
"""

import logging
from datetime import datetime
from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.app.agents.nodes.judge import judge_node
from backend.app.agents.nodes.prepare_context import prepare_context_node
from backend.app.agents.nodes.publish import publish_node
from backend.app.agents.nodes.reviewers import (
    maintainability_reviewer_node,
    performance_reviewer_node,
    security_reviewer_node,
    single_agent_reviewer_node,
)
from backend.app.agents.nodes.validate_findings import validate_findings_node
from backend.app.agents.state import (
    ReviewConfigType,
    ReviewState,
    create_initial_state,
)
from backend.app.core.config import get_settings
from backend.app.llm.base import LLMClient
from backend.app.llm.factory import create_llm_client
from backend.app.schemas.github import PullRequestMetadata
from backend.app.schemas.trace import PipelineTraceReport
from backend.app.services.github_client import GitHubClient
from backend.app.services.trace_store import build_pipeline_trace_report, serialize_trace_report
from backend.app.services.tracing import get_tracer

logger = logging.getLogger(__name__)


def build_review_graph(
    llm_client: LLMClient | None = None,
    github_client: GitHubClient | None = None,
) -> CompiledStateGraph[ReviewState, Any, Any, Any]:
    """Construct and compile the LangGraph workflow for pull request reviews.

    Supports three evaluation configurations (PROJECT.md §4):
    - 'single_agent': prepare -> single_agent -> validate -> publish
    - 'multi_agent_no_judge': prepare -> [sec, perf, maint] -> validate -> publish
    - 'multi_agent_judge': prepare -> [sec, perf, maint] -> validate -> judge -> publish
    """
    client = llm_client or create_llm_client()
    workflow = StateGraph(ReviewState)

    # 1. Register graph nodes
    workflow.add_node("prepare_context", prepare_context_node)

    async def _single_agent_wrapper(state: ReviewState) -> dict[str, Any]:
        return await single_agent_reviewer_node(state, client)

    async def _security_wrapper(state: ReviewState) -> dict[str, Any]:
        return await security_reviewer_node(state, client)

    async def _performance_wrapper(state: ReviewState) -> dict[str, Any]:
        return await performance_reviewer_node(state, client)

    async def _maintainability_wrapper(state: ReviewState) -> dict[str, Any]:
        return await maintainability_reviewer_node(state, client)

    workflow.add_node("single_agent_reviewer", _single_agent_wrapper)
    workflow.add_node("security_reviewer", _security_wrapper)
    workflow.add_node("performance_reviewer", _performance_wrapper)
    workflow.add_node("maintainability_reviewer", _maintainability_wrapper)

    workflow.add_node("validate_findings", validate_findings_node)

    async def _judge_wrapper(state: ReviewState) -> dict[str, Any]:
        return await judge_node(state, client)

    workflow.add_node("judge", _judge_wrapper)

    async def _publish_wrapper(state: ReviewState) -> dict[str, Any]:
        return await publish_node(state, github_client)

    workflow.add_node("publish", _publish_wrapper)

    # 2. Wire graph edges
    workflow.add_edge(START, "prepare_context")

    # Conditional fan-out after context preparation
    def _route_after_prepare(state: ReviewState) -> list[str]:
        cfg = state.get("config", "single_agent")
        if cfg == "single_agent":
            return ["single_agent_reviewer"]
        return ["security_reviewer", "performance_reviewer", "maintainability_reviewer"]

    workflow.add_conditional_edges(
        "prepare_context",
        _route_after_prepare,
        [
            "single_agent_reviewer",
            "security_reviewer",
            "performance_reviewer",
            "maintainability_reviewer",
        ],
    )

    # Reviewer nodes fan into validate_findings
    workflow.add_edge("single_agent_reviewer", "validate_findings")
    workflow.add_edge("security_reviewer", "validate_findings")
    workflow.add_edge("performance_reviewer", "validate_findings")
    workflow.add_edge("maintainability_reviewer", "validate_findings")

    # Conditional routing after validation (judge vs direct publish)
    def _route_after_validation(state: ReviewState) -> str:
        cfg = state.get("config", "single_agent")
        if cfg == "multi_agent_judge":
            return "judge"
        return "publish"

    workflow.add_conditional_edges(
        "validate_findings",
        _route_after_validation,
        {"judge": "judge", "publish": "publish"},
    )

    workflow.add_edge("judge", "publish")
    workflow.add_edge("publish", END)

    return workflow.compile()


async def run_review_pipeline(
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
    llm_client: LLMClient | None = None,
    github_client: GitHubClient | None = None,
    max_budget_usd: float | None = None,
) -> ReviewState:
    """Execute the full review pipeline graph for a pull request.

    T3.9 & T6.2: Records pipeline start time, enforces per-review budget ceiling
    via circuit breaker, and builds a structured PipelineTraceReport.
    """
    started_at = datetime.utcnow()
    cfg = get_settings()
    effective_max_budget = (
        max_budget_usd if max_budget_usd is not None else cfg.max_review_budget_usd
    )

    initial_state = create_initial_state(
        owner=owner,
        repo=repo,
        pull_number=pull_number,
        head_sha=head_sha,
        diff_text=diff_text,
        metadata=metadata,
        config=config,
        model=model,
        dry_run=dry_run,
        review_id=review_id,
        max_budget_usd=effective_max_budget,
    )

    graph = build_review_graph(
        llm_client=llm_client,
        github_client=github_client,
    )

    result_state = await graph.ainvoke(initial_state)
    finished_at = datetime.utcnow()
    result_state = cast(ReviewState, result_state)

    # T3.9: Build and log the structured pipeline trace report
    trace_report: PipelineTraceReport | None = None
    try:
        trace_report = build_pipeline_trace_report(
            state=dict(result_state),
            started_at=started_at,
            finished_at=finished_at,
        )
        logger.info(
            "Pipeline trace | pr=%s/%s#%d | nodes=%d | cost=$%.6f | status=%s",
            owner,
            repo,
            pull_number,
            len(trace_report.nodes),
            trace_report.total_cost_usd,
            trace_report.status,
        )
        logger.debug("Full pipeline trace:\n%s", serialize_trace_report(trace_report))
    except Exception as trace_exc:
        logger.warning("Failed to build pipeline trace report: %s", trace_exc)

    # T6.3: Optional Langfuse / OpenTelemetry observability trace export
    try:
        tracer = get_tracer()
        if tracer.is_enabled():
            tracer.trace_pipeline(dict(result_state), trace_report=trace_report)
    except Exception as obs_exc:
        logger.warning("Failed to export Langfuse pipeline trace: %s", obs_exc)

    return result_state
