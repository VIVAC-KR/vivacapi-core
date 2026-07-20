"""add spots.last_verified_at

Revision ID: 3faa9de7cf2a
Revises: fb8be0e57798
Create Date: 2026-07-20 17:47:39.595905

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3faa9de7cf2a'
down_revision: Union[str, None] = 'fb8be0e57798'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('spots', sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('spots', 'last_verified_at')
