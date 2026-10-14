"""Factory for creating LLM clients based on configuration and model names."""

import logging

from backend.app.core.config import Settings, get_settings
from backend.app.llm.base import LLMClient
from backend.app.llm.fake import FakeLLMClient
from backend.app.llm.gemini import GeminiLLMClient

logger = logging.getLogger(__name__)


def create_llm_client(
    settings: Settings | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> LLMClient:
    """Instantiate an LLMClient based on active settings and model identifier.

    Args:
        settings: Application settings. If None, loaded via get_settings().
        model: Requested model name (e.g. 'fake-llm', 'gemini-1.5-flash').
        provider: Explicit provider override ('fake', 'gemini').

    Returns:
        Configured LLMClient instance.
    """
    cfg = settings or get_settings()
    requested_model = (model or "").lower()
    requested_provider = (provider or "").lower()

    # 1. Test / fake requested explicitly
    if requested_model == "fake-llm" or requested_provider == "fake":
        return FakeLLMClient(model=model or "fake-llm")

    # 2. Gemini requested or available
    if requested_provider == "gemini" or "gemini" in requested_model:
        if cfg.gemini_api_key:
            return GeminiLLMClient(
                api_key=cfg.gemini_api_key,
                default_model=model or "gemini-1.5-flash",
            )
        logger.warning(
            "Gemini requested but GEMINI_API_KEY is not configured. Falling back to FakeLLMClient."
        )
        return FakeLLMClient(model="fake-llm")

    # 3. Default fallback if API key is present
    if cfg.gemini_api_key:
        return GeminiLLMClient(
            api_key=cfg.gemini_api_key,
            default_model=model or "gemini-1.5-flash",
        )

    # 4. Safe default for dev/test without credentials
    logger.info("No LLM API keys configured; using FakeLLMClient")
    return FakeLLMClient(model="fake-llm")
