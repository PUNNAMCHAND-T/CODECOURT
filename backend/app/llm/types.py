"""Type definitions, pricing tables, and exceptions for LLM clients.

Provides provider-agnostic message models, usage tracking, and cost accounting.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

LLMRole = Literal["system", "user", "assistant"]


class LLMMessage(BaseModel):
    """A single conversation turn in an LLM prompt."""

    model_config = ConfigDict(extra="forbid")

    role: LLMRole
    content: str


class LLMUsage(BaseModel):
    """Token consumption and estimated USD cost for an LLM generation."""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = Field(ge=0, default=0)
    completion_tokens: int = Field(ge=0, default=0)
    total_tokens: int = Field(ge=0, default=0)
    cost_usd: float = Field(ge=0.0, default=0.0)


class LLMResponse(BaseModel):
    """Standardized response from any LLM provider."""

    model_config = ConfigDict(extra="ignore")

    content: str
    model: str
    usage: LLMUsage
    latency_ms: int = Field(ge=0, default=0)
    raw_response: dict[str, Any] | None = None


# Pricing per 1,000,000 tokens in USD (PROJECT.md §6 & §8: recorded costs)
# Format: (prompt_cost_per_million, completion_cost_per_million)
MODEL_PRICING_PER_MILLION: dict[str, tuple[float, float]] = {
    # Google Gemini family
    "gemini-3.8-flash": (0.10, 0.40),
    "gemini-2.5-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.0-flash-exp": (0.00, 0.00),
    "gemini-1.5-pro": (1.25, 5.00),
    # Groq models
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    # Test fake
    "fake-llm": (0.00, 0.00),
}

# Fallback default pricing when model is not explicitly listed (e.g. custom or preview models)
DEFAULT_FALLBACK_PRICING: tuple[float, float] = (0.10, 0.40)


def calculate_token_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Calculate the estimated USD cost of an LLM generation.

    Args:
        model: Model identifier string.
        prompt_tokens: Number of prompt/input tokens.
        completion_tokens: Number of candidate/completion tokens.

    Returns:
        Total estimated cost in USD rounded to 6 decimal places.
    """
    clean_model = model.strip().lower()
    prompt_rate, completion_rate = MODEL_PRICING_PER_MILLION.get(
        clean_model,
        DEFAULT_FALLBACK_PRICING,
    )
    cost = (prompt_tokens * (prompt_rate / 1_000_000.0)) + (
        completion_tokens * (completion_rate / 1_000_000.0)
    )
    return round(cost, 6)


# -----------------------------------------------------------------------------
# Exception Hierarchy
# -----------------------------------------------------------------------------


class LLMError(Exception):
    """Base exception for all LLM client operations."""


class LLMTimeoutError(LLMError):
    """Raised when an LLM API request exceeds the configured timeout."""


class LLMRateLimitError(LLMError):
    """Raised when the LLM provider rate limit is exceeded."""


class LLMAuthenticationError(LLMError):
    """Raised when the LLM API key is missing or invalid."""


class LLMInvalidResponseError(LLMError):
    """Raised when the LLM returns an unparseable or malformed response."""


class LLMProviderError(LLMError):
    """Raised for server-side provider errors (5xx)."""
