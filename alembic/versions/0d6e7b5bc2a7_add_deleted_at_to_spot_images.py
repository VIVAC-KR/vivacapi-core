"""add deleted_at to spot_images

Revision ID: 0d6e7b5bc2a7
Revises: 58f418a45d9a
Create Date: 2026-08-22 16:35:02.239205

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d6e7b5bc2a7'
down_revision: Union[str, None] = '58f418a45d9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('spot_images', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('spot_images', 'deleted_at')
