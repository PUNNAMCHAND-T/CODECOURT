"""create repositories, pull_requests, and reviews tables

Revision ID: 7a8e9f1c2b3d
Revises: e06e736cef9f
Create Date: 2026-10-08 14:15:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a8e9f1c2b3d'
down_revision: str | None = 'e06e736cef9f'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. repositories table
    op.create_table(
        'repositories',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('github_id', sa.Integer(), nullable=True),
        sa.Column('is_private', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('default_branch', sa.String(length=64), server_default='main', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_repositories')),
    )
    op.create_index(
        op.f('ix_repositories_full_name'),
        'repositories',
        ['full_name'],
        unique=True,
    )

    # 2. pull_requests table
    op.create_table(
        'pull_requests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('github_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('state', sa.String(length=32), server_default='open', nullable=False),
        sa.Column('author', sa.String(length=100), nullable=False),
        sa.Column('head_sha', sa.String(length=64), nullable=False),
        sa.Column('base_sha', sa.String(length=64), nullable=False),
        sa.Column('head_ref', sa.String(length=128), nullable=False),
        sa.Column('base_ref', sa.String(length=128), nullable=False),
        sa.Column('html_url', sa.String(length=512), nullable=False),
        sa.Column('diff_url', sa.String(length=512), nullable=True),
        sa.Column('changed_files', sa.Integer(), server_default='0', nullable=False),
        sa.Column('additions', sa.Integer(), server_default='0', nullable=False),
        sa.Column('deletions', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], name=op.f('fk_pull_requests_repository_id_repositories'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_pull_requests')),
        sa.UniqueConstraint('repository_id', 'number', name=op.f('uq_pull_requests_repository_id_number')),
    )
    op.create_index(
        op.f('ix_pull_requests_repository_id'),
        'pull_requests',
        ['repository_id'],
        unique=False,
    )

    # 3. reviews table
    op.create_table(
        'reviews',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pull_request_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='queued', nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('model', sa.String(length=64), server_default='fake-llm', nullable=False),
        sa.Column('prompt_versions', sa.JSON(), nullable=False),
        sa.Column('tokens_prompt', sa.Integer(), server_default='0', nullable=False),
        sa.Column('tokens_completion', sa.Integer(), server_default='0', nullable=False),
        sa.Column('tokens_total', sa.Integer(), server_default='0', nullable=False),
        sa.Column('cost_usd', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('trigger_type', sa.String(length=32), server_default='manual', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['pull_request_id'], ['pull_requests.id'], name=op.f('fk_reviews_pull_request_id_pull_requests'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_reviews')),
    )
    op.create_index(
        op.f('ix_reviews_pull_request_id'),
        'reviews',
        ['pull_request_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_reviews_status'),
        'reviews',
        ['status'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_reviews_status'), table_name='reviews')
    op.drop_index(op.f('ix_reviews_pull_request_id'), table_name='reviews')
    op.drop_table('reviews')

    op.drop_index(op.f('ix_pull_requests_repository_id'), table_name='pull_requests')
    op.drop_table('pull_requests')

    op.drop_index(op.f('ix_repositories_full_name'), table_name='repositories')
    op.drop_table('repositories')
