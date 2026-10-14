"""Abstract base class interface for LLM providers.

Ensures provider-agnostic execution with standardized interfaces for
prompts, generation parameters, timeouts, and structured responses.
"""

from abc import ABC, abstractmethod
from typing import Any

from backend.app.llm.types import LLMMessage, LLMResponse

# Named constants (PROJECT.md §6: no magic numbers, explicit limits)
DEFAULT_LLM_TIMEOUT_SECONDS: float = 30.0
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_INITIAL_BACKOFF_SECONDS: float = 0.5
DEFAULT_TEMPERATURE: float = 0.2
DEFAULT_MAX_TOKENS: int = 4096


class LLMClient(ABC):
    """Abstract interface for all LLM provider clients."""

    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        json_mode: bool = False,
        model: str | None = None,
    ) -> LLMResponse:
        """Generate a response from the LLM provider.

        Args:
            messages: List of conversation messages (system, user, assistant).
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum completion tokens to generate.
            json_mode: If True, request structured JSON output from provider.
            model: Optional model override.

        Returns:
            Standardized LLMResponse with content, usage, and cost metrics.

        Raises:
            LLMTimeoutError: If the request exceeds timeout after retries.
            LLMRateLimitError: If provider rate limits are hit.
            LLMAuthenticationError: If API credentials are invalid.
            LLMInvalidResponseError: If output format is invalid.
            LLMProviderError: On upstream server failures.
        """

    async def __aenter__(self) -> "LLMClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()

    @abstractmethod
    async def close(self) -> None:
        """Close underlying connection pools if applicable."""
