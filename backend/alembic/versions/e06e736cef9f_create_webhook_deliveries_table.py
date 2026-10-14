"""create webhook deliveries table

Revision ID: e06e736cef9f
Revises: 4ce5320d7e96
Create Date: 2026-10-08 13:10:27.134260

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e06e736cef9f'
down_revision: str | None = '4ce5320d7e96'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'webhook_deliveries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('delivery_id', sa.String(length=64), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=32), server_default='received', nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_webhook_deliveries')),
    )
    op.create_index(
        op.f('ix_webhook_deliveries_delivery_id'),
        'webhook_deliveries',
        ['delivery_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_webhook_deliveries_delivery_id'), table_name='webhook_deliveries')
    op.drop_table('webhook_deliveries')
