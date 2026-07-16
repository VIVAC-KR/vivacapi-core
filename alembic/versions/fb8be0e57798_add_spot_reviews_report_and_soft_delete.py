"""add spot reviews report and soft delete

Revision ID: fb8be0e57798
Revises: 73dcae10bc10
Create Date: 2026-07-16 17:36:00.209758

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fb8be0e57798'
down_revision: Union[str, None] = '73dcae10bc10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'spot_review_reports',
        sa.Column('uid', sa.String(length=22), nullable=False),
        sa.Column('review_uid', sa.String(length=22), nullable=False),
        sa.Column('reporter_user_uid', sa.String(length=22), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.CheckConstraint(
            "uid ~ '^[0-9A-Za-z]{22}$'", name='ck_spot_review_reports_uid_format'
        ),
        sa.ForeignKeyConstraint(['reporter_user_uid'], ['users.uid']),
        sa.ForeignKeyConstraint(
            ['review_uid'], ['spot_reviews.uid'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('uid'),
        sa.UniqueConstraint(
            'review_uid', 'reporter_user_uid', name='uq_review_reporter'
        ),
    )
    op.create_index(
        op.f('ix_spot_review_reports_reporter_user_uid'),
        'spot_review_reports',
        ['reporter_user_uid'],
        unique=False,
    )
    op.create_index(
        op.f('ix_spot_review_reports_review_uid'),
        'spot_review_reports',
        ['review_uid'],
        unique=False,
    )

    op.add_column(
        'spot_reviews', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.alter_column(
        'spot_reviews',
        'rating',
        existing_type=sa.Float(),
        type_=sa.SmallInteger(),
        existing_nullable=False,
        postgresql_using='round(rating)::smallint',
    )
    op.drop_constraint('check_review_rating_range', 'spot_reviews', type_='check')
    op.create_check_constraint(
        'check_review_rating_range', 'spot_reviews', 'rating >= 0 AND rating <= 10'
    )
    op.drop_constraint('uq_spot_user_review', 'spot_reviews', type_='unique')
    op.create_index(
        'uq_spot_user_review_active',
        'spot_reviews',
        ['spot_uid', 'user_id'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )

    op.add_column('spots', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.drop_index('ix_spots_published_uid', table_name='spots')
    op.create_index(
        'ix_spots_published_uid',
        'spots',
        ['uid'],
        postgresql_where=sa.text("pipeline_status = 'PUBLISHED' AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index('ix_spots_published_uid', table_name='spots')
    op.create_index(
        'ix_spots_published_uid',
        'spots',
        ['uid'],
        postgresql_where=sa.text("pipeline_status = 'PUBLISHED'"),
    )
    op.drop_column('spots', 'deleted_at')

    op.drop_index(
        'uq_spot_user_review_active',
        table_name='spot_reviews',
        postgresql_where=sa.text('deleted_at IS NULL'),
    )
    op.create_unique_constraint(
        'uq_spot_user_review', 'spot_reviews', ['spot_uid', 'user_id']
    )
    op.drop_constraint('check_review_rating_range', 'spot_reviews', type_='check')
    op.create_check_constraint(
        'check_review_rating_range', 'spot_reviews', 'rating >= 0 AND rating <= 5'
    )
    op.alter_column(
        'spot_reviews',
        'rating',
        existing_type=sa.SmallInteger(),
        type_=sa.Float(),
        existing_nullable=False,
    )
    op.drop_column('spot_reviews', 'deleted_at')

    op.drop_index(op.f('ix_spot_review_reports_review_uid'), table_name='spot_review_reports')
    op.drop_index(
        op.f('ix_spot_review_reports_reporter_user_uid'), table_name='spot_review_reports'
    )
    op.drop_table('spot_review_reports')
