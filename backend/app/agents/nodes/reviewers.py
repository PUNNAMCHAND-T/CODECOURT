import logging
import time
from typing import Any

from backend.app.agents.prompts.delimiters import wrap_untrusted_diff
from backend.app.agents.prompts.maintainability_v1 import build_maintainability_agent_prompt
from backend.app.agents.prompts.performance_v1 import build_performance_agent_prompt
from backend.app.agents.prompts.security_v1 import build_security_agent_prompt
from backend.app.agents.prompts.single_agent_v1 import (
    SINGLE_AGENT_SYSTEM_PROMPT_V1,
    build_single_agent_prompt,
)
from backend.app.agents.state import ReviewState
from backend.app.llm.base import LLMClient
from backend.app.llm.types import LLMMessage
from backend.app.schemas.finding import AgentReviewOutput, RawAgentFinding
from backend.app.services.cost_caps import (
    build_circuit_breaker_skip_trace,
    check_review_circuit_breaker,
)

logger = logging.getLogger(__name__)


# T3.8: Hard cap on findings per agent to bound downstream processing cost
MAX_FINDINGS_PER_AGENT = 25


def _attempt_json_repair(raw_text: str) -> AgentReviewOutput | None:
    """T3.8: Try to salvage a valid AgentReviewOutput from malformed LLM output.

    Strategies attempted in order:
    1. Direct parse (fast path).
    2. Extract first {...} JSON object using brace-depth scanning.
    3. Return None if all strategies fail.
    """
    import json as _json

    # Strategy 1: direct parse
    try:
        return AgentReviewOutput.model_validate_json(raw_text)
    except Exception:
        pass

    # Strategy 2: brace-depth scan to find first complete JSON object
    depth = 0
    start_idx = raw_text.find("{")
    if start_idx == -1:
        return None
    for i, ch in enumerate(raw_text[start_idx:], start=start_idx):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = raw_text[start_idx : i + 1]
                try:
                    obj = _json.loads(candidate)
                    return AgentReviewOutput.model_validate(obj)
                except Exception:
                    return None
    return None


async def _execute_reviewer_node(
    agent_name: str,
    messages: list[LLMMessage],
    llm_client: LLMClient,
    state: ReviewState,
) -> dict[str, Any]:
    """Execute an LLM reviewer node, parse structured findings, and record accounting.

    T3.8 & T6.2 enhancements:
    - Pre-generation circuit breaker check halting LLM calls if budget is exceeded.
    - Post-generation circuit breaker check flagging subsequent node execution if cost cap breached.
    - Attempts invalid-output repair before declaring a hard parse failure.
    - Caps findings at MAX_FINDINGS_PER_AGENT (25) to bound downstream cost.
    - Records 'repair_attempted', 'capped', and 'circuit_breaker_tripped' in trace.
    """
    start_time = time.perf_counter()

    # T6.2: Check circuit breaker before incurring LLM cost
    tripped, trip_reason = check_review_circuit_breaker(dict(state))
    if tripped:
        logger.warning(
            "Circuit breaker active: reviewer %s skipped (%s)",
            agent_name,
            trip_reason,
        )
        skip_trace = build_circuit_breaker_skip_trace(
            agent_name, trip_reason or "Review budget limit reached"
        )
        return {
            "agent_findings": {agent_name: []},
            "agent_summaries": {agent_name: ""},
            "raw_findings": [],
            "tokens_prompt": 0,
            "tokens_completion": 0,
            "cost_usd": 0.0,
            "node_latencies": {agent_name: 0.0},
            "traces": [skip_trace],
            "circuit_breaker_tripped": True,
            "circuit_breaker_reason": trip_reason,
        }

    findings: list[RawAgentFinding] = []
    error_msg: str | None = None
    summary_text = ""
    repair_attempted = False
    capped = False

    try:
        response = await llm_client.generate(
            messages=messages,
            json_mode=True,
        )
        latency = time.perf_counter() - start_time

        # Primary parse attempt
        try:
            parsed = AgentReviewOutput.model_validate_json(response.content)
            findings = parsed.findings
            summary_text = parsed.summary
        except Exception as parse_exc:
            # T3.8: attempt repair before failing
            repair_attempted = True
            logger.warning(
                "Primary parse failed for agent %s, attempting repair: %s",
                agent_name,
                parse_exc,
            )
            repaired = _attempt_json_repair(response.content)
            if repaired is not None:
                logger.info("Repair succeeded for agent %s", agent_name)
                findings = repaired.findings
                summary_text = repaired.summary
            else:
                logger.warning("Repair failed for agent %s: %s", agent_name, parse_exc)
                error_msg = f"Output parsing error: {parse_exc}"

        # T3.8: cap findings to MAX_FINDINGS_PER_AGENT
        if len(findings) > MAX_FINDINGS_PER_AGENT:
            capped = True
            logger.warning(
                "Agent %s produced %d findings, capping to %d",
                agent_name,
                len(findings),
                MAX_FINDINGS_PER_AGENT,
            )
            findings = findings[:MAX_FINDINGS_PER_AGENT]

        # T6.2: Post-call budget check
        current_total_cost = float(state.get("cost_usd", 0.0) or 0.0) + response.usage.cost_usd
        mb = state.get("max_budget_usd")
        budget_limit = float(mb) if mb is not None else 0.50
        tripped_after = current_total_cost >= budget_limit
        trip_reason_after = (
            f"Review budget limit reached (${current_total_cost:.4f} >= ${budget_limit:.4f})"
            if tripped_after
            else None
        )

        trace = {
            "node": agent_name,
            "latency_seconds": latency,
            "findings_count": len(findings),
            "tokens_prompt": response.usage.prompt_tokens,
            "tokens_completion": response.usage.completion_tokens,
            "cost_usd": response.usage.cost_usd,
            "error": error_msg,
            "repair_attempted": repair_attempted,
            "capped": capped,
            "circuit_breaker_tripped": tripped_after,
            "circuit_breaker_reason": trip_reason_after,
        }

        result_dict: dict[str, Any] = {
            "agent_findings": {agent_name: findings},
            "raw_findings": findings,
            "tokens_prompt": response.usage.prompt_tokens,
            "tokens_completion": response.usage.completion_tokens,
            "cost_usd": response.usage.cost_usd,
            "node_latencies": {agent_name: latency},
            "traces": [trace],
            "circuit_breaker_tripped": tripped_after,
            "circuit_breaker_reason": trip_reason_after,
        }
        if summary_text:
            result_dict["agent_summaries"] = {agent_name: summary_text}
            if agent_name == "single_agent":
                result_dict["summary"] = summary_text
        return result_dict

    except Exception as exc:
        latency = time.perf_counter() - start_time
        logger.error("Reviewer %s encountered generation failure: %s", agent_name, exc)
        trace = {
            "node": agent_name,
            "latency_seconds": latency,
            "findings_count": 0,
            "tokens_prompt": 0,
            "tokens_completion": 0,
            "cost_usd": 0.0,
            "error": str(exc),
            "repair_attempted": False,
            "capped": False,
        }
        return {
            "agent_findings": {agent_name: []},
            "agent_summaries": {agent_name: ""},
            "raw_findings": [],
            "tokens_prompt": 0,
            "tokens_completion": 0,
            "cost_usd": 0.0,
            "node_latencies": {agent_name: latency},
            "traces": [trace],
        }


async def single_agent_reviewer_node(state: ReviewState, llm_client: LLMClient) -> dict[str, Any]:
    """Execute baseline single-agent reviewer."""
    meta = state.get("metadata")
    diff_text = state.get("diff_text", "")

    if meta is not None:
        messages = build_single_agent_prompt(meta, diff_text)
    else:
        # Fallback if metadata not present
        messages = [
            LLMMessage(role="system", content=SINGLE_AGENT_SYSTEM_PROMPT_V1),
            LLMMessage(role="user", content=wrap_untrusted_diff(diff_text)),
        ]

    return await _execute_reviewer_node("single_agent", messages, llm_client, state)


async def security_reviewer_node(state: ReviewState, llm_client: LLMClient) -> dict[str, Any]:
    """Execute specialized security reviewer."""
    meta = state.get("metadata")
    diff_text = state.get("diff_text", "")
    messages = build_security_agent_prompt(meta, diff_text)
    return await _execute_reviewer_node("security", messages, llm_client, state)


async def performance_reviewer_node(state: ReviewState, llm_client: LLMClient) -> dict[str, Any]:
    """Execute specialized performance reviewer."""
    meta = state.get("metadata")
    diff_text = state.get("diff_text", "")
    messages = build_performance_agent_prompt(meta, diff_text)
    return await _execute_reviewer_node("performance", messages, llm_client, state)


async def maintainability_reviewer_node(
    state: ReviewState, llm_client: LLMClient
) -> dict[str, Any]:
    """Execute specialized maintainability reviewer."""
    meta = state.get("metadata")
    diff_text = state.get("diff_text", "")
    messages = build_maintainability_agent_prompt(meta, diff_text)
    return await _execute_reviewer_node("maintainability", messages, llm_client, state)
