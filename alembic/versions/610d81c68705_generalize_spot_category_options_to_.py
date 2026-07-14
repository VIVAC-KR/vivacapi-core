"""generalize spot_category_options to spot_field_options

Revision ID: 610d81c68705
Revises: 2cd14aeebc1d
Create Date: 2026-07-15 00:44:32.271323

카테고리 화이트리스트를 amenities/nearby_facilities/has_equipment_rental까지
확장한다. 기존 spot_category_options 테이블을 RENAME(데이터 보존)해서 확장하고,
새 3개 필드는 기존 자유 입력 값과 호환되지 않아 spots의 해당 컬럼만 NULL로
초기화한다 (다른 컬럼은 건드리지 않음, downgrade에서 데이터 복원 불가 — 의도된
비가역 초기화).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '610d81c68705'
down_revision: Union[str, None] = '2cd14aeebc1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 테이블 rename (기존 category 데이터 보존)
    op.rename_table('spot_category_options', 'spot_field_options')
    op.execute("ALTER TABLE spot_field_options RENAME CONSTRAINT spot_category_options_pkey TO spot_field_options_pkey_old")
    op.execute("ALTER TABLE spot_field_options RENAME CONSTRAINT ck_spot_category_options_code_format TO ck_spot_field_options_code_format")

    op.add_column('spot_field_options', sa.Column('field', sa.String(length=30), nullable=True))
    op.execute("UPDATE spot_field_options SET field = 'category'")
    op.alter_column('spot_field_options', 'field', nullable=False)

    op.drop_constraint('spot_field_options_pkey_old', 'spot_field_options', type_='primary')
    op.create_primary_key('spot_field_options_pkey', 'spot_field_options', ['field', 'code'])

    # 새로 화이트리스트 대상이 되는 3개 필드는 기존 자유 입력 값과 호환 안 됨
    op.execute("UPDATE spots SET amenities = NULL, nearby_facilities = NULL, has_equipment_rental = NULL")


def downgrade() -> None:
    op.drop_constraint('spot_field_options_pkey', 'spot_field_options', type_='primary')
    op.execute("DELETE FROM spot_field_options WHERE field != 'category'")
    op.drop_column('spot_field_options', 'field')
    op.create_primary_key('spot_category_options_pkey', 'spot_field_options', ['code'])
    op.execute("ALTER TABLE spot_field_options RENAME CONSTRAINT ck_spot_field_options_code_format TO ck_spot_category_options_code_format")
    op.rename_table('spot_field_options', 'spot_category_options')
