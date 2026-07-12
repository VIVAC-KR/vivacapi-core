"""add cascade delete and unique constraint on spot_business_info.spot_uid

Revision ID: 0efcde5399a3
Revises: d9f1e3a5b7c2
Create Date: 2026-07-12 16:32:18.239343

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0efcde5399a3'
down_revision: Union[str, None] = 'd9f1e3a5b7c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f('ix_spot_business_info_spot_uid'), table_name='spot_business_info')
    op.create_unique_constraint(
        'uq_spot_business_info_spot_uid', 'spot_business_info', ['spot_uid']
    )
    op.drop_constraint(
        'spot_business_info_spot_uid_fkey', 'spot_business_info', type_='foreignkey'
    )
    op.create_foreign_key(
        'spot_business_info_spot_uid_fkey',
        'spot_business_info',
        'spots',
        ['spot_uid'],
        ['uid'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint(
        'spot_business_info_spot_uid_fkey', 'spot_business_info', type_='foreignkey'
    )
    op.create_foreign_key(
        'spot_business_info_spot_uid_fkey', 'spot_business_info', 'spots', ['spot_uid'], ['uid']
    )
    op.drop_constraint(
        'uq_spot_business_info_spot_uid', 'spot_business_info', type_='unique'
    )
    op.create_index(
        op.f('ix_spot_business_info_spot_uid'), 'spot_business_info', ['spot_uid'], unique=False
    )
