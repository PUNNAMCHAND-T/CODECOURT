"""GitHub webhook signature verification and helper services.

Provides constant-time HMAC-SHA256 signature verification matching
GitHub's X-Hub-Signature-256 specification.
"""

import hashlib
import hmac
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.models.webhook_delivery import WebhookDelivery
    from backend.app.repositories.webhook_delivery import WebhookDeliveryRepository

# Maximum payload size accepted from GitHub webhooks (10 MB)
MAX_WEBHOOK_PAYLOAD_BYTES: int = 10 * 1024 * 1024


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    """Compute the expected X-Hub-Signature-256 header value.

    Args:
        payload_bytes: Raw request body as bytes.
        secret: Webhook shared secret string.

    Returns:
        Hex-encoded HMAC digest prefixed with 'sha256='.
    """
    mac = hmac.new(secret.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def verify_signature(
    payload_bytes: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Verify GitHub X-Hub-Signature-256 using constant-time comparison.

    Args:
        payload_bytes: Raw request body bytes.
        signature_header: The value of the X-Hub-Signature-256 HTTP header.
        secret: Webhook shared secret.

    Returns:
        True if the signature is valid, False otherwise.
    """
    if not secret:
        return False

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected_signature = compute_signature(payload_bytes, secret)
    return hmac.compare_digest(expected_signature, signature_header)


async def check_and_record_delivery(
    repository: "WebhookDeliveryRepository",
    delivery_id: str,
    event_type: str,
    action: str | None = None,
    payload: dict[str, object] | None = None,
) -> tuple[bool, "WebhookDelivery | None"]:
    """Check if delivery is already recorded; if not, record it.

    Args:
        repository: WebhookDeliveryRepository instance.
        delivery_id: Unique GitHub delivery UUID.
        event_type: GitHub event name (e.g. 'pull_request', 'ping').
        action: Event action (e.g. 'opened', 'synchronize').
        payload: Full raw payload dictionary if available.

    Returns:
        tuple (is_duplicate: bool, delivery: WebhookDelivery)
    """
    existing = await repository.get_by_delivery_id(delivery_id)
    if existing is not None:
        return True, existing

    created = await repository.create_delivery(
        delivery_id=delivery_id,
        event_type=event_type,
        action=action,
        payload=payload,
        status="received",
    )
    return False, created
