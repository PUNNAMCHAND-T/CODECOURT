"""Google Gemini REST API implementation of LLMClient.

Uses direct async HTTP calls via httpx without requiring heavy external SDKs.
Supports system instructions, JSON mode, retry with exponential backoff,
token accounting, and cost calculation.
"""

import asyncio
import logging
import time
from typing import Any

import httpx

from backend.app.llm.base import (
    DEFAULT_INITIAL_BACKOFF_SECONDS,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    LLMClient,
)
from backend.app.llm.types import (
    LLMAuthenticationError,
    LLMInvalidResponseError,
    LLMMessage,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    LLMUsage,
    calculate_token_cost,
)

logger = logging.getLogger(__name__)

GEMINI_API_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODEL: str = "gemini-3.8-flash"


class GeminiLLMClient(LLMClient):
    """Client for Google Gemini REST API."""

    def __init__(
        self,
        api_key: str,
        default_model: str = DEFAULT_GEMINI_MODEL,
        timeout: float = DEFAULT_LLM_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.default_model = default_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            transport=transport,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        await self._client.aclose()

    def _format_payload(
        self,
        messages: list[LLMMessage],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> dict[str, Any]:
        """Convert standard LLMMessage list to Gemini REST API payload."""
        system_parts: list[dict[str, str]] = []
        contents: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                system_parts.append({"text": msg.content})
            elif msg.role == "user":
                contents.append({"role": "user", "parts": [{"text": msg.content}]})
            elif msg.role == "assistant":
                contents.append({"role": "model", "parts": [{"text": msg.content}]})

        # Ensure at least one content message exists
        if not contents:
            contents.append({"role": "user", "parts": [{"text": "Begin."}]})

        payload: dict[str, Any] = {"contents": contents}

        if system_parts:
            payload["system_instruction"] = {"parts": system_parts}

        gen_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if json_mode:
            gen_config["responseMimeType"] = "application/json"

        payload["generationConfig"] = gen_config
        return payload

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        json_mode: bool = False,
        model: str | None = None,
    ) -> LLMResponse:
        """Call Gemini generateContent endpoint with retries and timing."""
        if not self.api_key:
            raise LLMAuthenticationError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in .env."
            )

        effective_model = model or self.default_model
        endpoint = f"{GEMINI_API_BASE_URL}/models/{effective_model}:generateContent"
        payload = self._format_payload(messages, temperature, max_tokens, json_mode)
        params = {"key": self.api_key}

        start_time = time.perf_counter()
        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = await self._client.post(
                    endpoint,
                    params=params,
                    json=payload,
                )

                # Transient errors: 429 rate limit or 503/502/504 server overload
                if response.status_code in {429, 502, 503, 504} and attempt < self.max_retries - 1:
                    delay = self.initial_backoff * (2**attempt)
                    logger.warning(
                        "Gemini API returned %d; retrying in %.2fs (attempt %d/%d)",
                        response.status_code,
                        delay,
                        attempt + 1,
                        self.max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue

                if response.status_code == 401 or response.status_code == 403:
                    raise LLMAuthenticationError(
                        f"Gemini API authentication failed ({response.status_code}): {response.text}"
                    )

                if response.status_code == 429:
                    raise LLMRateLimitError(f"Gemini API rate limit exceeded: {response.text}")

                if response.status_code >= 500:
                    raise LLMProviderError(
                        f"Gemini API server error ({response.status_code}): {response.text}"
                    )

                if not response.is_success:
                    raise LLMProviderError(
                        f"Gemini API request failed ({response.status_code}): {response.text}"
                    )

                raw_json = response.json()
                latency_ms = int((time.perf_counter() - start_time) * 1000)

                # Extract response text
                candidates = raw_json.get("candidates", [])
                if not candidates:
                    raise LLMInvalidResponseError(
                        f"Gemini returned no candidates in response: {raw_json}"
                    )

                first_candidate = candidates[0]
                content_parts = first_candidate.get("content", {}).get("parts", [])
                if not content_parts:
                    raise LLMInvalidResponseError(
                        f"Gemini candidate has no content parts: {first_candidate}"
                    )

                text = content_parts[0].get("text", "")

                # Usage & token accounting
                usage_meta = raw_json.get("usageMetadata", {})
                prompt_tokens = int(usage_meta.get("promptTokenCount", 0))
                completion_tokens = int(usage_meta.get("candidatesTokenCount", 0))
                total_tokens = int(
                    usage_meta.get("totalTokenCount", prompt_tokens + completion_tokens)
                )

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
                    content=text,
                    model=effective_model,
                    usage=usage,
                    latency_ms=latency_ms,
                    raw_response=raw_json,
                )

            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                last_exception = exc
                if attempt < self.max_retries - 1:
                    delay = self.initial_backoff * (2**attempt)
                    logger.warning(
                        "Gemini request timed out; retrying in %.2fs (attempt %d/%d)",
                        delay,
                        attempt + 1,
                        self.max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise LLMTimeoutError(
                    f"Gemini request timed out after {self.max_retries} attempts: {exc}"
                ) from exc

            except (
                LLMAuthenticationError,
                LLMRateLimitError,
                LLMProviderError,
                LLMInvalidResponseError,
            ):
                raise

            except Exception as exc:
                last_exception = exc
                logger.error("Unexpected error calling Gemini API: %s", exc)
                raise LLMProviderError(
                    f"Unexpected error communicating with Gemini: {exc}"
                ) from exc

        if last_exception:
            raise LLMProviderError(
                f"Failed to call Gemini API: {last_exception}"
            ) from last_exception
        raise LLMProviderError("Exhausted retries calling Gemini API without response")
