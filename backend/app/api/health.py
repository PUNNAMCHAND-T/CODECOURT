"""Health check endpoint."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check() -> dict[str, str]:
    """Return service health status.

    Used by Docker health checks, load balancers, and the frontend
    to verify the API is reachable.
    """
    logger.debug("Health check requested")
    return {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
    }
