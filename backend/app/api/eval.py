"""API endpoints for evaluation benchmarks and failure analysis.

PROJECT.md §2 & §5: Endpoints serving benchmark metrics and failure taxonomy.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.schemas.eval import (
    BenchmarkOverviewResponse,
    EvalRunSummaryItem,
    FailureAnalysisResponse,
)
from backend.app.services.eval_service import (
    get_benchmark_overview,
    get_failure_analysis,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/eval", tags=["evaluation"])


@router.get(
    "/benchmark",
    response_model=BenchmarkOverviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Get cross-architecture benchmark comparison",
)
async def get_benchmark(
    split: Literal["test", "dev"] = Query(
        default="test",
        description="Dataset split to evaluate ('test' or 'dev')",
    ),
    refresh: bool = Query(
        default=False,
        description="Force recalculation instead of using memory cache",
    ),
) -> BenchmarkOverviewResponse:
    """Return aggregated benchmark metrics for single_agent, multi_agent_no_judge, and multi_agent_judge."""
    try:
        return get_benchmark_overview(split=split, use_cache=not refresh)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except Exception as err:
        logger.exception("Unexpected error computing benchmark overview: %s", err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load benchmark evaluation metrics.",
        ) from err


@router.get(
    "/runs",
    response_model=list[EvalRunSummaryItem],
    status_code=status.HTTP_200_OK,
    summary="List all benchmark evaluation runs",
)
async def list_runs(
    split: Literal["test", "dev"] = Query(
        default="test",
        description="Dataset split ('test' or 'dev')",
    ),
) -> list[EvalRunSummaryItem]:
    """Return summary list of all individual benchmark runs executed."""
    overview = get_benchmark_overview(split=split)
    return overview.runs


@router.get(
    "/failure-analysis",
    response_model=FailureAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Get failure modes diagnosis taxonomy",
)
async def get_failure_modes() -> FailureAnalysisResponse:
    """Return taxonomy distribution of evaluation failure modes."""
    return get_failure_analysis()
