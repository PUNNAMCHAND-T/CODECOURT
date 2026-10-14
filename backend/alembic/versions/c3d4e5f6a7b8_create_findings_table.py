"""create findings table

Revision ID: c3d4e5f6a7b8
Revises: 7a8e9f1c2b3d
Create Date: 2026-10-08 19:25:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = '7a8e9f1c2b3d'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'findings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('review_id', sa.Integer(), nullable=False),
        sa.Column('agent', sa.String(length=64), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('severity', sa.String(length=32), nullable=False),
        sa.Column('file', sa.String(length=512), nullable=False),
        sa.Column('line_start', sa.Integer(), nullable=False),
        sa.Column('line_end', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('evidence', sa.Text(), nullable=False),
        sa.Column('suggested_fix', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='active', nullable=False),
        sa.Column('merged_from', sa.JSON(), nullable=True),
        sa.Column('decision_reason', sa.Text(), nullable=True),
        sa.Column('drop_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], name=op.f('fk_findings_review_id_reviews'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_findings')),
    )
    op.create_index(
        op.f('ix_findings_review_id'),
        'findings',
        ['review_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_findings_agent'),
        'findings',
        ['agent'],
        unique=False,
    )
    op.create_index(
        op.f('ix_findings_category'),
        'findings',
        ['category'],
        unique=False,
    )
    op.create_index(
        op.f('ix_findings_severity'),
        'findings',
        ['severity'],
        unique=False,
    )
    op.create_index(
        op.f('ix_findings_status'),
        'findings',
        ['status'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_findings_status'), table_name='findings')
    op.drop_index(op.f('ix_findings_severity'), table_name='findings')
    op.drop_index(op.f('ix_findings_category'), table_name='findings')
    op.drop_index(op.f('ix_findings_agent'), table_name='findings')
    op.drop_index(op.f('ix_findings_review_id'), table_name='findings')
    op.drop_table('findings')
