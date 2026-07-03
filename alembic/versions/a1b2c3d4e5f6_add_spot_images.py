"""add spot_images

Revision ID: a1b2c3d4e5f6
Revises: b7f3a1c9d2e4
Create Date: 2026-06-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
# feature/audit-history(b7f3a1c9d2e4) 뒤에 체인됨 — audit PR(#78)을 먼저 머지할 것.
down_revision: Union[str, None] = 'b7f3a1c9d2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'spot_images',
        sa.Column('uid', sa.String(length=22), nullable=False),
        sa.Column('spot_uid', sa.String(length=22), nullable=False),
        sa.Column('s3_key', sa.String(), nullable=False),
        sa.Column(
            'role',
            sa.Enum('thumbnail', 'detail', name='spot_image_role'),
            nullable=False,
        ),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_public', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('content_type', sa.String(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(['spot_uid'], ['spots.uid'], ),
        sa.PrimaryKeyConstraint('uid'),
    )
    op.create_index(
        op.f('ix_spot_images_spot_uid'), 'spot_images', ['spot_uid'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_spot_images_spot_uid'), table_name='spot_images')
    op.drop_table('spot_images')
    sa.Enum(name='spot_image_role').drop(op.get_bind())
