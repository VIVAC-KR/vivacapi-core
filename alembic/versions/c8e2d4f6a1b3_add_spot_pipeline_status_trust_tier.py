"""add spot pipeline_status and trust_tier

Revision ID: c8e2d4f6a1b3
Revises: a1b2c3d4e5f6
Create Date: 2026-07-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c8e2d4f6a1b3'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'spots',
        sa.Column(
            'pipeline_status',
            sa.String(),
            server_default='RAW',
            nullable=False,
        ),
    )
    op.add_column('spots', sa.Column('trust_tier', sa.SmallInteger(), nullable=True))

    # 기존 row는 이미 서비스 노출 중이던 데이터 — PUBLISHED로 backfill
    op.execute("UPDATE spots SET pipeline_status = 'PUBLISHED'")

    op.create_check_constraint(
        'ck_spots_pipeline_status',
        'spots',
        "pipeline_status IN "
        "('RAW', 'ENRICHED', 'CURATED', 'REVIEWED', 'PUBLISHED', 'REJECTED')",
    )
    op.create_check_constraint(
        'ck_spots_trust_tier', 'spots', 'trust_tier BETWEEN 1 AND 3'
    )
    op.create_index(
        'ix_spots_published_uid',
        'spots',
        ['uid'],
        postgresql_where=sa.text("pipeline_status = 'PUBLISHED'"),
    )


def downgrade() -> None:
    op.drop_index('ix_spots_published_uid', table_name='spots')
    op.drop_constraint('ck_spots_trust_tier', 'spots', type_='check')
    op.drop_constraint('ck_spots_pipeline_status', 'spots', type_='check')
    op.drop_column('spots', 'trust_tier')
    op.drop_column('spots', 'pipeline_status')
