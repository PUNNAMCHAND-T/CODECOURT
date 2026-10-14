"""LLM provider interface, factory, and concrete implementations."""

from backend.app.llm.base import (
    DEFAULT_INITIAL_BACKOFF_SECONDS,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    LLMClient,
)
from backend.app.llm.factory import create_llm_client
from backend.app.llm.fake import FakeLLMClient
from backend.app.llm.gemini import GeminiLLMClient
from backend.app.llm.types import (
    MODEL_PRICING_PER_MILLION,
    LLMAuthenticationError,
    LLMError,
    LLMInvalidResponseError,
    LLMMessage,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMRole,
    LLMTimeoutError,
    LLMUsage,
    calculate_token_cost,
)

__all__ = [
    "DEFAULT_INITIAL_BACKOFF_SECONDS",
    "DEFAULT_LLM_TIMEOUT_SECONDS",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_TEMPERATURE",
    "MODEL_PRICING_PER_MILLION",
    "FakeLLMClient",
    "GeminiLLMClient",
    "LLMAuthenticationError",
    "LLMClient",
    "LLMError",
    "LLMInvalidResponseError",
    "LLMMessage",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMResponse",
    "LLMRole",
    "LLMTimeoutError",
    "LLMUsage",
    "calculate_token_cost",
    "create_llm_client",
]
