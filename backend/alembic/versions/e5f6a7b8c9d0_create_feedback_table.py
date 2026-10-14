"""create feedback table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-09 21:40:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'feedback',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('finding_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('user_id', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['finding_id'], ['findings.id'], name=op.f('fk_feedback_finding_id_findings'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_feedback')),
        sa.UniqueConstraint('finding_id', name=op.f('uq_feedback_finding_id')),
    )
    op.create_index(
        op.f('ix_feedback_finding_id'),
        'feedback',
        ['finding_id'],
        unique=True,
    )
    op.create_index(
        op.f('ix_feedback_action'),
        'feedback',
        ['action'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_feedback_action'), table_name='feedback')
    op.drop_index(op.f('ix_feedback_finding_id'), table_name='feedback')
    op.drop_table('feedback')
