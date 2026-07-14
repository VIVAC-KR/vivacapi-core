"""add spot_category_options table

Revision ID: 2cd14aeebc1d
Revises: b3d8f2a4c6e1
Create Date: 2026-07-14 23:43:49.409573

기존 자유 입력 카테고리 값은 새 화이트리스트 체계와 호환되지 않아 spots.category만
NULL로 초기화한다 (다른 컬럼은 건드리지 않음). downgrade에서는 데이터를 복원할 수
없다 — 의도된 비가역 초기화.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2cd14aeebc1d'
down_revision: Union[str, None] = 'b3d8f2a4c6e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('spot_category_options',
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('label_ko', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.CheckConstraint("code ~ '^[A-Z][A-Z0-9_]*$'", name='ck_spot_category_options_code_format'),
    sa.PrimaryKeyConstraint('code')
    )
    op.execute("UPDATE spots SET category = NULL")


def downgrade() -> None:
    op.drop_table('spot_category_options')
