"""Repository for persisting and querying WebhookDelivery records.

Enforces idempotency at the database layer.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.webhook_delivery import WebhookDelivery


class WebhookDeliveryRepository:
    """Data access repository for webhook deliveries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_delivery_id(self, delivery_id: str) -> WebhookDelivery | None:
        """Find a delivery record by its unique GitHub delivery UUID."""
        stmt = select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_delivery(
        self,
        delivery_id: str,
        event_type: str,
        action: str | None = None,
        payload: dict[str, Any] | None = None,
        status: str = "received",
    ) -> WebhookDelivery:
        """Record a new webhook delivery."""
        delivery = WebhookDelivery(
            delivery_id=delivery_id,
            event_type=event_type,
            action=action,
            payload=payload,
            status=status,
        )
        self.session.add(delivery)
        await self.session.commit()
        await self.session.refresh(delivery)
        return delivery
