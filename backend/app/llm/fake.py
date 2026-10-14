"""Fake LLM client for tests and evaluation baselines without external API calls.

Provides deterministic responses, records call history for assertions,
and accurately accounts for simulated tokens and costs.
"""

from collections import deque
from collections.abc import Sequence

from backend.app.llm.base import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    LLMClient,
)
from backend.app.llm.types import (
    LLMMessage,
    LLMResponse,
    LLMUsage,
    calculate_token_cost,
)


class FakeLLMClient(LLMClient):
    """In-memory deterministic LLM client for tests.

    Never makes network requests. Records every invocation for test assertions.
    """

    def __init__(
        self,
        default_response: str = '{"findings": []}',
        responses: Sequence[str] | None = None,
        model: str = "fake-llm",
        simulated_latency_ms: int = 15,
        error_to_raise: Exception | None = None,
    ) -> None:
        self.default_response = default_response
        self._response_queue: deque[str] = deque(responses or [])
        self.model = model
        self.simulated_latency_ms = simulated_latency_ms
        self.error_to_raise = error_to_raise
        self.calls: list[list[LLMMessage]] = []

    def set_responses(self, responses: Sequence[str]) -> None:
        """Enqueue a sequence of canned responses."""
        self._response_queue = deque(responses)

    def set_error(self, error: Exception | None) -> None:
        """Configure an exception to raise on the next invocation."""
        self.error_to_raise = error

    @property
    def call_count(self) -> int:
        """Number of generation requests received."""
        return len(self.calls)

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        json_mode: bool = False,
        model: str | None = None,
    ) -> LLMResponse:
        """Return next queued canned response or default_response."""
        self.calls.append(messages)

        if self.error_to_raise is not None:
            err = self.error_to_raise
            self.error_to_raise = None
            raise err

        effective_model = model or self.model

        content = self._response_queue.popleft() if self._response_queue else self.default_response

        # Realistic token estimation: ~4 chars per token
        prompt_text = " ".join(m.content for m in messages)
        prompt_tokens = max(1, len(prompt_text) // 4)
        completion_tokens = max(1, len(content) // 4)
        total_tokens = prompt_tokens + completion_tokens

        cost_usd = calculate_token_cost(
            effective_model,
            prompt_tokens,
            completion_tokens,
        )

        usage = LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
        )

        return LLMResponse(
            content=content,
            model=effective_model,
            usage=usage,
            latency_ms=self.simulated_latency_ms,
            raw_response={"mock": True, "call_index": len(self.calls)},
        )

    async def close(self) -> None:
        """No-op for in-memory fake client."""
        return None
