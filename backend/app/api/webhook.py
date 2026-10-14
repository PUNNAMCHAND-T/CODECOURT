"""GitHub webhook ingestion endpoint.

Receives, verifies HMAC signature, checks delivery idempotency,
and processes GitHub webhook events.
"""

import contextlib
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.database import get_db_session
from backend.app.repositories.review import (
    PullRequestRepository,
    RepositoryRepository,
    ReviewRepository,
)
from backend.app.repositories.webhook_delivery import WebhookDeliveryRepository
from backend.app.schemas.webhook import PingWebhookPayload, PullRequestWebhookPayload
from backend.app.services.github_webhook import (
    MAX_WEBHOOK_PAYLOAD_BYTES,
    check_and_record_delivery,
    verify_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhook", tags=["webhook"])


@router.post(
    "/github",
    status_code=status.HTTP_200_OK,
    summary="GitHub Webhook Receiver",
)
@router.post(
    "",
    status_code=status.HTTP_200_OK,
    summary="GitHub Webhook Receiver (alias)",
)
async def handle_github_webhook(
    request: Request,
    response: Response,
    x_github_event: Annotated[str, Header(alias="X-GitHub-Event")],
    x_github_delivery: Annotated[str, Header(alias="X-GitHub-Delivery")],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_hub_signature_256: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> dict[str, Any]:
    """Ingest, verify, and idempotently record GitHub webhook deliveries.

    1. Checks payload size limits.
    2. Ensures webhook secret is configured.
    3. Verifies X-Hub-Signature-256 via constant-time HMAC check.
    4. Checks idempotency using X-GitHub-Delivery against database records.
    5. Dispatches event processing (ping, pull_request).
    """
    # 1. Size limit enforcement before memory buffering
    content_length_header = request.headers.get("content-length")
    if content_length_header:
        try:
            if int(content_length_header) > MAX_WEBHOOK_PAYLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Webhook payload exceeds maximum size limit",
                )
        except ValueError:
            pass

    chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > MAX_WEBHOOK_PAYLOAD_BYTES:
            logger.warning(
                "Webhook payload rejected: stream exceeded limit %d (delivery=%s)",
                MAX_WEBHOOK_PAYLOAD_BYTES,
                x_github_delivery,
            )
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Webhook payload exceeds maximum size limit",
            )
        chunks.append(chunk)
    body = b"".join(chunks)

    # 2. Secret configuration check
    if not settings.github_webhook_secret:
        logger.error("GitHub webhook secret is not configured in settings")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub webhook secret is not configured on the server",
        )

    # 3. HMAC-SHA256 signature verification
    if not verify_signature(body, x_hub_signature_256, settings.github_webhook_secret):
        logger.warning(
            "Invalid or missing HMAC signature for delivery=%s event=%s",
            x_github_delivery,
            x_github_event,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Hub-Signature-256 webhook signature",
        )

    # 4. Idempotency check via delivery ID
    repo = WebhookDeliveryRepository(session)
    raw_payload: dict[str, Any] | None = None
    with contextlib.suppress(Exception):
        parsed_json = json.loads(body.decode("utf-8"))
        if isinstance(parsed_json, dict):
            raw_payload = parsed_json

    action: str | None = None
    if isinstance(raw_payload, dict):
        raw_action = raw_payload.get("action")
        if isinstance(raw_action, str):
            action = raw_action

    is_duplicate, _ = await check_and_record_delivery(
        repository=repo,
        delivery_id=x_github_delivery,
        event_type=x_github_event,
        action=action,
        payload=raw_payload,
    )

    if is_duplicate:
        logger.info(
            "Duplicate webhook delivery detected (delivery=%s event=%s)",
            x_github_delivery,
            x_github_event,
        )
        return {
            "status": "duplicate",
            "message": "Webhook delivery already received",
            "delivery_id": x_github_delivery,
        }

    # 5. Process event
    if x_github_event == "ping":
        with contextlib.suppress(ValidationError):
            PingWebhookPayload.model_validate_json(body)
        logger.info("Received GitHub ping event (delivery=%s)", x_github_delivery)
        return {
            "status": "ok",
            "message": "pong",
            "delivery_id": x_github_delivery,
        }

    if x_github_event == "pull_request":
        try:
            payload = PullRequestWebhookPayload.model_validate_json(body)
        except ValidationError as exc:
            logger.warning(
                "Invalid pull_request payload (delivery=%s): %s",
                x_github_delivery,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid pull_request webhook payload: {exc.errors()}",
            ) from exc

        logger.info(
            "Accepted pull_request webhook: action=%s PR #%d repo=%s delivery=%s",
            payload.action,
            payload.number,
            payload.repository.full_name,
            x_github_delivery,
        )

        owner_login = (
            payload.repository.owner.get("login")
            if isinstance(payload.repository.owner, dict)
            else None
        ) or payload.repository.full_name.split("/")[0]

        repo_repo = RepositoryRepository(session)
        db_repo = await repo_repo.get_or_create(
            owner=owner_login,
            name=payload.repository.name,
            github_id=payload.repository.id,
            is_private=payload.repository.private,
        )

        author_login = (
            payload.sender.get("login", "unknown")
            if isinstance(payload.sender, dict)
            else "unknown"
        )

        pr_repo = PullRequestRepository(session)
        db_pr = await pr_repo.upsert(
            repository_id=db_repo.id,
            number=payload.number,
            title=payload.pull_request.title,
            state=payload.pull_request.state,
            author=author_login,
            head_sha=payload.pull_request.head.sha,
            base_sha=payload.pull_request.base.sha,
            head_ref=payload.pull_request.head.ref,
            base_ref=payload.pull_request.base.ref,
            html_url=payload.pull_request.html_url,
            github_id=payload.pull_request.id,
        )

        review_id: int | None = None
        if payload.action in {"opened", "synchronize", "reopened"}:
            review_repo = ReviewRepository(session)
            review = await review_repo.create_review(
                pull_request_id=db_pr.id,
                trigger_type="webhook",
                status="queued",
            )
            review_id = review.id

        await session.commit()

        response.status_code = status.HTTP_202_ACCEPTED
        res_payload: dict[str, Any] = {
            "status": "accepted",
            "event": "pull_request",
            "action": payload.action,
            "delivery_id": x_github_delivery,
            "repository": payload.repository.full_name,
            "pr_number": payload.number,
        }
        if review_id is not None:
            res_payload["review_id"] = review_id
        return res_payload

    # Other unhandled events
    logger.info(
        "Ignored unhandled GitHub event type: %s (delivery=%s)",
        x_github_event,
        x_github_delivery,
    )
    return {
        "status": "ignored",
        "event": x_github_event,
        "delivery_id": x_github_delivery,
        "message": f"Event type '{x_github_event}' is not handled",
    }
