"""Cost capping and budget enforcement service.

PROJECT.md §6 & §7: Phase 6 Hardening - per-review budget ceilings,
LangGraph circuit breaker, and per-tenant daily expenditure caps.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.models.pull_request import PullRequest
from backend.app.models.review import Review

logger = logging.getLogger(__name__)


class BudgetExceededError(Exception):
    """Raised when repository or review budget ceiling is breached."""

    def __init__(self, message: str, current_spend: float, budget: float) -> None:
        super().__init__(message)
        self.message = message
        self.current_spend = current_spend
        self.budget = budget


async def get_repository_24h_spend(
    session: AsyncSession,
    repository_id: int,
) -> float:
    """Calculate cumulative review spend for a repository over the past 24 hours."""
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    stmt = (
        select(func.coalesce(func.sum(Review.cost_usd), 0.0))
        .join(PullRequest, Review.pull_request_id == PullRequest.id)
        .where(PullRequest.repository_id == repository_id)
        .where(Review.created_at >= cutoff)
    )
    result = await session.execute(stmt)
    spend: float = float(result.scalar_one())
    return spend


async def check_tenant_daily_budget(
    session: AsyncSession,
    repository_id: int,
    repo_full_name: str,
    settings: Settings | None = None,
) -> tuple[bool, float, float]:
    """Check if repository 24h spend is within the tenant daily budget ceiling.

    Returns:
        (is_allowed, current_spend_usd, max_daily_budget_usd)
    """
    cfg = settings or get_settings()
    current_spend = await get_repository_24h_spend(session, repository_id)
    allowed = current_spend < cfg.tenant_daily_budget_usd
    if not allowed:
        logger.warning(
            "Tenant daily budget exceeded for %s: $%.4f >= $%.4f",
            repo_full_name,
            current_spend,
            cfg.tenant_daily_budget_usd,
        )
    return allowed, current_spend, cfg.tenant_daily_budget_usd


async def enforce_tenant_daily_budget(
    session: AsyncSession,
    repository_id: int,
    repo_full_name: str,
    settings: Settings | None = None,
) -> float:
    """Validate daily expenditure for a tenant, raising BudgetExceededError if breached."""
    allowed, current_spend, budget = await check_tenant_daily_budget(
        session=session,
        repository_id=repository_id,
        repo_full_name=repo_full_name,
        settings=settings,
    )
    if not allowed:
        raise BudgetExceededError(
            f"Daily cost limit of ${budget:.2f} exceeded for repository '{repo_full_name}'. "
            f"Current 24h spend: ${current_spend:.4f}.",
            current_spend=current_spend,
            budget=budget,
        )
    return current_spend


def check_review_circuit_breaker(
    state: dict[str, Any],
    max_budget_usd: float = 0.50,
    token_limit: int = 50_000,
) -> tuple[bool, str | None]:
    """Check if a review run has tripped its cost or token circuit breaker."""
    # 1. Check existing state flag
    if state.get("circuit_breaker_tripped"):
        reason = state.get("circuit_breaker_reason") or "Circuit breaker already tripped"
        return True, reason

    # 2. Check cumulative review cost
    cost_usd = float(state.get("cost_usd", 0.0) or 0.0)
    mb = state.get("max_budget_usd")
    effective_budget = float(mb) if mb is not None else max_budget_usd
    if cost_usd >= effective_budget:
        reason = f"Review budget of ${effective_budget:.2f} reached (${cost_usd:.4f})"
        return True, reason

    # 3. Check cumulative token usage
    tokens_prompt = int(state.get("tokens_prompt", 0) or 0)
    tokens_completion = int(state.get("tokens_completion", 0) or 0)
    total_tokens = tokens_prompt + tokens_completion
    if total_tokens >= token_limit:
        reason = f"Review token limit of {token_limit:,} tokens reached ({total_tokens:,})"
        return True, reason

    return False, None


def build_circuit_breaker_skip_trace(
    agent_name: str,
    reason: str,
) -> dict[str, Any]:
    """Build a synthetic node trace when an agent call is skipped by circuit breaker."""
    return {
        "node": agent_name,
        "latency_seconds": 0.0,
        "findings_count": 0,
        "tokens_prompt": 0,
        "tokens_completion": 0,
        "cost_usd": 0.0,
        "error": f"Skipped: circuit breaker tripped ({reason})",
        "circuit_breaker_tripped": True,
        "circuit_breaker_reason": reason,
        "repair_attempted": False,
        "capped": False,
    }
