"""add invites and user referred_by_uid

Revision ID: 3eb2b585b548
Revises: 73dcae10bc10
Create Date: 2026-07-16 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3eb2b585b548'
down_revision: Union[str, None] = '73dcae10bc10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        'invites',
        sa.Column('uid', sa.String(length=22), nullable=False),
        sa.Column('inviter_uid', sa.String(length=22), nullable=False),
        sa.Column('group_uid', sa.String(length=22), nullable=True),
        sa.Column(
            'group_role',
            sa.Enum(
                'viewer', 'contributor', 'editor', 'owner',
                name='group_role', create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            'status',
            sa.Enum('pending', 'accepted', 'revoked', name='invite_status'),
            server_default='pending',
            nullable=False,
        ),
        sa.Column('accepted_by_uid', sa.String(length=22), nullable=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.CheckConstraint("uid ~ '^[0-9A-Za-z]{22}$'", name='ck_invites_uid_format'),
        sa.ForeignKeyConstraint(['accepted_by_uid'], ['users.uid']),
        sa.ForeignKeyConstraint(['group_uid'], ['spot_groups.uid'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['inviter_uid'], ['users.uid']),
        sa.PrimaryKeyConstraint('uid'),
    )
    op.create_index(
        op.f('ix_invites_inviter_uid'), 'invites', ['inviter_uid'], unique=False
    )
    op.create_index(
        op.f('ix_invites_group_uid'), 'invites', ['group_uid'], unique=False
    )

    op.add_column('users', sa.Column('referred_by_uid', sa.String(length=22), nullable=True))
    op.create_foreign_key(
        'fk_users_referred_by_uid_users', 'users', 'users', ['referred_by_uid'], ['uid']
    )


def downgrade() -> None:
    op.drop_constraint('fk_users_referred_by_uid_users', 'users', type_='foreignkey')
    op.drop_column('users', 'referred_by_uid')

    op.drop_index(op.f('ix_invites_group_uid'), table_name='invites')
    op.drop_index(op.f('ix_invites_inviter_uid'), table_name='invites')
    op.drop_table('invites')
    sa.Enum(name='invite_status').drop(op.get_bind())
