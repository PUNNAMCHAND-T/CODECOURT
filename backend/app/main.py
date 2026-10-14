"""FastAPI application factory.

Creates and configures the FastAPI app with logging, config, and routes.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.auth import router as auth_router
from backend.app.api.eval import router as eval_router
from backend.app.api.feedback import router as feedback_router
from backend.app.api.health import router as health_router
from backend.app.api.reviews import router as reviews_router
from backend.app.api.webhook import router as webhook_router
from backend.app.core.config import get_settings
from backend.app.core.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown logic for the application."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("CodeCourt API starting (env=%s)", settings.app_env)
    yield
    logger.info("CodeCourt API shutting down")


def create_app() -> FastAPI:
    """Build the FastAPI application.

    Uses the factory pattern so tests can create isolated app instances.
    """
    app = FastAPI(
        title="CodeCourt",
        description="Multi-agent code review system",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(webhook_router)
    app.include_router(reviews_router)
    app.include_router(feedback_router)
    app.include_router(eval_router)
    return app


app = create_app()
