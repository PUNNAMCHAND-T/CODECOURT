"""Tests for LLM client interface, FakeLLM, Gemini provider, and cost accounting."""

import asyncio
from typing import Any

import httpx
import pytest

from backend.app.core.config import Settings
from backend.app.llm.base import LLMClient
from backend.app.llm.factory import create_llm_client
from backend.app.llm.fake import FakeLLMClient
from backend.app.llm.gemini import GeminiLLMClient
from backend.app.llm.types import (
    LLMAuthenticationError,
    LLMInvalidResponseError,
    LLMMessage,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    calculate_token_cost,
)

SAMPLE_GEMINI_RESPONSE: dict[str, Any] = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "text": '{"findings": [{"title": "Hardcoded secret", "severity": "critical"}]}'
                    }
                ],
                "role": "model",
            },
            "finishReason": "STOP",
        }
    ],
    "usageMetadata": {
        "promptTokenCount": 150,
        "candidatesTokenCount": 40,
        "totalTokenCount": 190,
    },
}


# -----------------------------------------------------------------------------
# Unit Tests: Token and Cost Accounting
# -----------------------------------------------------------------------------


def test_calculate_token_cost_known_models() -> None:
    """Verify precise cost calculation based on published per-million pricing."""
    # gemini-1.5-flash: $0.075 / 1M prompt, $0.30 / 1M completion
    cost_gemini = calculate_token_cost("gemini-1.5-flash", 1_000_000, 1_000_000)
    assert cost_gemini == 0.375

    # Small token counts
    cost_small = calculate_token_cost("gemini-1.5-flash", 1000, 500)
    expected = (1000 * 0.075 / 1e6) + (500 * 0.30 / 1e6)
    assert cost_small == round(expected, 6)

    # fake-llm: always 0.0
    cost_fake = calculate_token_cost("fake-llm", 50000, 20000)
    assert cost_fake == 0.0

    # groq llama-3.3-70b-versatile: $0.59 / 1M prompt, $0.79 / 1M completion
    cost_groq = calculate_token_cost("llama-3.3-70b-versatile", 1_000_000, 1_000_000)
    assert cost_groq == 1.38

    # Fallback default pricing for unknown model
    cost_unknown = calculate_token_cost("custom-preview-model", 1_000_000, 1_000_000)
    assert cost_unknown == 0.50  # 0.10 + 0.40


# -----------------------------------------------------------------------------
# Unit Tests: FakeLLMClient
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_llm_client_default_response() -> None:
    """Verify FakeLLMClient returns default response and accounts for tokens/cost."""
    client = FakeLLMClient(default_response='{"status": "ok"}')
    messages = [
        LLMMessage(role="system", content="You are a code reviewer."),
        LLMMessage(role="user", content="Review this diff."),
    ]

    response = await client.generate(messages)
    assert isinstance(response, LLMResponse)
    assert response.content == '{"status": "ok"}'
    assert response.model == "fake-llm"
    assert response.usage.prompt_tokens > 0
    assert response.usage.completion_tokens > 0
    assert response.usage.total_tokens == (
        response.usage.prompt_tokens + response.usage.completion_tokens
    )
    assert response.usage.cost_usd == 0.0
    assert client.call_count == 1
    assert client.calls[0] == messages


@pytest.mark.asyncio
async def test_fake_llm_client_queued_responses() -> None:
    """Verify FakeLLMClient returns queued responses in FIFO order."""
    client = FakeLLMClient(responses=['{"finding": 1}', '{"finding": 2}'])
    messages = [LLMMessage(role="user", content="diff")]

    res1 = await client.generate(messages)
    assert res1.content == '{"finding": 1}'

    res2 = await client.generate(messages)
    assert res2.content == '{"finding": 2}'

    # Third call falls back to default
    res3 = await client.generate(messages)
    assert res3.content == '{"findings": []}'
    assert client.call_count == 3


@pytest.mark.asyncio
async def test_fake_llm_client_simulated_error() -> None:
    """Verify FakeLLMClient can raise simulated errors for testing resilience."""
    client = FakeLLMClient()
    client.set_error(LLMRateLimitError("Simulated rate limit"))

    with pytest.raises(LLMRateLimitError):
        await client.generate([LLMMessage(role="user", content="test")])

    # Next call succeeds normally
    res = await client.generate([LLMMessage(role="user", content="test")])
    assert res.content == '{"findings": []}'


# -----------------------------------------------------------------------------
# Unit Tests: GeminiLLMClient (Mocked Transport)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_missing_api_key_raises_auth_error() -> None:
    """Verify missing API key raises LLMAuthenticationError immediately."""
    client = GeminiLLMClient(api_key="")
    with pytest.raises(LLMAuthenticationError):
        await client.generate([LLMMessage(role="user", content="hello")])


@pytest.mark.asyncio
async def test_gemini_generate_success_with_mock_transport() -> None:
    """Verify Gemini client correctly formats requests and parses responses."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert "models/gemini-1.5-flash:generateContent" in str(request.url)
        assert request.url.params["key"] == "test-key"
        return httpx.Response(200, json=SAMPLE_GEMINI_RESPONSE)

    transport = httpx.MockTransport(handler)
    client = GeminiLLMClient(
        api_key="test-key",
        default_model="gemini-1.5-flash",
        transport=transport,
    )

    messages = [
        LLMMessage(role="system", content="System instructions"),
        LLMMessage(role="user", content="User prompt"),
    ]

    response = await client.generate(messages, json_mode=True)
    assert "Hardcoded secret" in response.content
    assert response.model == "gemini-1.5-flash"
    assert response.usage.prompt_tokens == 150
    assert response.usage.completion_tokens == 40
    assert response.usage.total_tokens == 190
    assert response.usage.cost_usd > 0.0
    await client.close()


@pytest.mark.asyncio
async def test_gemini_rate_limit_raises_rate_limit_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify HTTP 429 raises LLMRateLimitError after bounded retries."""

    async def fake_sleep(_s: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "Resource exhausted"}})

    transport = httpx.MockTransport(handler)
    client = GeminiLLMClient(
        api_key="test-key",
        max_retries=2,
        initial_backoff=0.01,
        transport=transport,
    )

    with pytest.raises(LLMRateLimitError):
        await client.generate([LLMMessage(role="user", content="prompt")])

    await client.close()


@pytest.mark.asyncio
async def test_gemini_auth_error_fails_fast() -> None:
    """Verify HTTP 401/403 fails fast with LLMAuthenticationError."""
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, json={"error": {"message": "API key not valid"}})

    transport = httpx.MockTransport(handler)
    client = GeminiLLMClient(api_key="invalid-key", transport=transport)

    with pytest.raises(LLMAuthenticationError):
        await client.generate([LLMMessage(role="user", content="prompt")])

    # Must fail fast without retrying credentials errors
    assert attempts == 1
    await client.close()


@pytest.mark.asyncio
async def test_gemini_transient_retry_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify transient 503 error is retried and succeeds on subsequent attempt."""

    async def fake_sleep(_s: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": {"message": "Service unavailable"}})
        return httpx.Response(200, json=SAMPLE_GEMINI_RESPONSE)

    transport = httpx.MockTransport(handler)
    client = GeminiLLMClient(
        api_key="test-key",
        max_retries=3,
        initial_backoff=0.01,
        transport=transport,
    )

    res = await client.generate([LLMMessage(role="user", content="prompt")])
    assert "Hardcoded secret" in res.content
    assert calls == 2
    await client.close()


@pytest.mark.asyncio
async def test_gemini_timeout_raises_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify network timeout raises LLMTimeoutError after retries."""

    async def fake_sleep(_s: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout connecting to server")

    transport = httpx.MockTransport(handler)
    client = GeminiLLMClient(
        api_key="test-key",
        max_retries=2,
        initial_backoff=0.01,
        transport=transport,
    )

    with pytest.raises(LLMTimeoutError):
        await client.generate([LLMMessage(role="user", content="prompt")])

    await client.close()


@pytest.mark.asyncio
async def test_gemini_empty_candidates_raises_invalid_response() -> None:
    """Verify empty candidates list raises LLMInvalidResponseError."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": []})

    transport = httpx.MockTransport(handler)
    client = GeminiLLMClient(api_key="test-key", transport=transport)

    with pytest.raises(LLMInvalidResponseError):
        await client.generate([LLMMessage(role="user", content="prompt")])

    await client.close()


# -----------------------------------------------------------------------------
# Factory Tests
# -----------------------------------------------------------------------------


def test_create_llm_client_factory() -> None:
    """Verify factory routes to FakeLLMClient or GeminiLLMClient appropriately."""
    # Explicit fake
    c1 = create_llm_client(model="fake-llm")
    assert isinstance(c1, FakeLLMClient)

    c2 = create_llm_client(provider="fake")
    assert isinstance(c2, FakeLLMClient)

    # Gemini with API key
    settings = Settings(gemini_api_key="real-gemini-key")
    c3 = create_llm_client(settings=settings, model="gemini-1.5-flash")
    assert isinstance(c3, GeminiLLMClient)
    assert isinstance(c3, LLMClient)

    # Missing API key falls back to FakeLLMClient
    empty_settings = Settings(gemini_api_key="")
    c4 = create_llm_client(settings=empty_settings, model="gemini-1.5-flash")
    assert isinstance(c4, FakeLLMClient)
