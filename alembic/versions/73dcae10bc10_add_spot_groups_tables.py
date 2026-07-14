"""add spot_groups tables

Revision ID: 73dcae10bc10
Revises: d90640348f6b
Create Date: 2026-07-15 01:51:24.532902

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73dcae10bc10'
down_revision: Union[str, None] = 'd90640348f6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'spot_groups',
        sa.Column('uid', sa.String(length=22), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column(
            'visibility',
            sa.Enum('private', 'invite_only', 'public', name='group_visibility'),
            server_default='private',
            nullable=False,
        ),
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
        sa.CheckConstraint("uid ~ '^[0-9A-Za-z]{22}$'", name='ck_spot_groups_uid_format'),
        sa.PrimaryKeyConstraint('uid'),
    )
    op.create_table(
        'spot_group_members',
        sa.Column('group_uid', sa.String(length=22), nullable=False),
        sa.Column('user_uid', sa.String(length=22), nullable=False),
        sa.Column(
            'role',
            sa.Enum('viewer', 'contributor', 'editor', 'owner', name='group_role'),
            nullable=False,
        ),
        sa.Column('invited_by_uid', sa.String(length=22), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(['group_uid'], ['spot_groups.uid'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by_uid'], ['users.uid'], ),
        sa.ForeignKeyConstraint(['user_uid'], ['users.uid'], ),
        sa.PrimaryKeyConstraint('group_uid', 'user_uid'),
    )
    op.create_index(
        op.f('ix_spot_group_members_user_uid'), 'spot_group_members', ['user_uid'], unique=False
    )
    op.create_table(
        'spot_group_spots',
        sa.Column('group_uid', sa.String(length=22), nullable=False),
        sa.Column('spot_uid', sa.String(length=22), nullable=False),
        sa.Column('added_by_uid', sa.String(length=22), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(['added_by_uid'], ['users.uid'], ),
        sa.ForeignKeyConstraint(['group_uid'], ['spot_groups.uid'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['spot_uid'], ['spots.uid'], ),
        sa.PrimaryKeyConstraint('group_uid', 'spot_uid'),
    )


def downgrade() -> None:
    op.drop_table('spot_group_spots')
    op.drop_index(op.f('ix_spot_group_members_user_uid'), table_name='spot_group_members')
    op.drop_table('spot_group_members')
    op.drop_table('spot_groups')
    sa.Enum(name='group_role').drop(op.get_bind())
    sa.Enum(name='group_visibility').drop(op.get_bind())
