"""create eval tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-09 12:40:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = 'c3d4e5f6a7b8'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. eval_cases
    op.create_table(
        'eval_cases',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('case_key', sa.String(length=128), nullable=False),
        sa.Column('split', sa.String(length=32), nullable=False),
        sa.Column('language', sa.String(length=32), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('has_bug', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('pr_title', sa.String(length=255), nullable=False),
        sa.Column('filename', sa.String(length=512), nullable=False),
        sa.Column('diff_text', sa.Text(), nullable=False),
        sa.Column('ground_truth_json', sa.JSON(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_eval_cases_case_key', 'eval_cases', ['case_key'], unique=True)
    op.create_index('ix_eval_cases_split', 'eval_cases', ['split'], unique=False)
    op.create_index('ix_eval_cases_category', 'eval_cases', ['category'], unique=False)

    # 2. eval_runs
    op.create_table(
        'eval_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_key', sa.String(length=128), nullable=False),
        sa.Column('config', sa.String(length=64), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('split', sa.String(length=32), nullable=False),
        sa.Column('total_cases', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_cases', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('partial_cases', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_cases', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_findings', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tokens_total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('duration_seconds', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_eval_runs_run_key', 'eval_runs', ['run_key'], unique=True)
    op.create_index('ix_eval_runs_config', 'eval_runs', ['config'], unique=False)

    # 3. eval_results
    op.create_table(
        'eval_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('case_key', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tokens_prompt', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tokens_completion', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('findings_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('findings_json', sa.JSON(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False, server_default=''),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['run_id'], ['eval_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_eval_results_run_id', 'eval_results', ['run_id'], unique=False)
    op.create_index('ix_eval_results_case_key', 'eval_results', ['case_key'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_eval_results_case_key', table_name='eval_results')
    op.drop_index('ix_eval_results_run_id', table_name='eval_results')
    op.drop_table('eval_results')

    op.drop_index('ix_eval_runs_config', table_name='eval_runs')
    op.drop_index('ix_eval_runs_run_key', table_name='eval_runs')
    op.drop_table('eval_runs')

    op.drop_index('ix_eval_cases_category', table_name='eval_cases')
    op.drop_index('ix_eval_cases_split', table_name='eval_cases')
    op.drop_index('ix_eval_cases_case_key', table_name='eval_cases')
    op.drop_table('eval_cases')
