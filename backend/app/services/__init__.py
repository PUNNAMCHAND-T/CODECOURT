"""Business logic services package."""

from backend.app.services.auth import (
    create_access_token,
    decode_access_token,
    get_current_user,
    get_optional_user,
)
from backend.app.services.cost_caps import (
    BudgetExceededError,
    build_circuit_breaker_skip_trace,
    check_review_circuit_breaker,
    check_tenant_daily_budget,
    enforce_tenant_daily_budget,
    get_repository_24h_spend,
)
from backend.app.services.diff_parser import parse_unified_diff
from backend.app.services.finding_validator import (
    to_finding_create_models,
    validate_finding,
    validate_findings,
)
from backend.app.services.github_client import GitHubClient
from backend.app.services.pr_trigger import trigger_pr_review
from backend.app.services.rate_limiter import (
    RateLimitGuard,
    SlidingWindowRateLimiter,
)
from backend.app.services.review_publisher import (
    build_review_payload,
    determine_review_event,
    format_finding_comment,
    format_review_body,
    publish_pull_request_review,
)
from backend.app.services.tracing import (
    BaseTracer,
    LangfuseTracer,
    NoopTracer,
    get_tracer,
    reset_tracer,
    set_tracer,
)

__all__ = [
    "BaseTracer",
    "BudgetExceededError",
    "GitHubClient",
    "LangfuseTracer",
    "NoopTracer",
    "RateLimitGuard",
    "SlidingWindowRateLimiter",
    "build_circuit_breaker_skip_trace",
    "build_review_payload",
    "check_review_circuit_breaker",
    "check_tenant_daily_budget",
    "create_access_token",
    "decode_access_token",
    "determine_review_event",
    "enforce_tenant_daily_budget",
    "format_finding_comment",
    "format_review_body",
    "get_current_user",
    "get_optional_user",
    "get_repository_24h_spend",
    "get_tracer",
    "parse_unified_diff",
    "publish_pull_request_review",
    "reset_tracer",
    "set_tracer",
    "to_finding_create_models",
    "trigger_pr_review",
    "validate_finding",
    "validate_findings",
]
