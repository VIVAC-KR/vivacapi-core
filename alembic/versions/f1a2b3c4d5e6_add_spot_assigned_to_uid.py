"""add spots.assigned_to_uid

Revision ID: f1a2b3c4d5e6
Revises: 0efcde5399a3
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = '0efcde5399a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('spots', sa.Column('assigned_to_uid', sa.String(22), nullable=True))
    op.create_index(op.f('ix_spots_assigned_to_uid'), 'spots', ['assigned_to_uid'])
    op.create_foreign_key(
        'spots_assigned_to_uid_fkey',
        'spots',
        'users',
        ['assigned_to_uid'],
        ['uid'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('spots_assigned_to_uid_fkey', 'spots', type_='foreignkey')
    op.drop_index(op.f('ix_spots_assigned_to_uid'), table_name='spots')
    op.drop_column('spots', 'assigned_to_uid')
