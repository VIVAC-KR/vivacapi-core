"""add spots coordinates index for bbox queries

Revision ID: a7c3e1f9b204
Revises: 4f801d8a7469
Create Date: 2026-08-05

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a7c3e1f9b204"
down_revision: str | Sequence[str] | None = "4f801d8a7469"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_spots_coordinates",
        "spots",
        ["latitude", "longitude"],
        postgresql_where=(
            "latitude IS NOT NULL AND longitude IS NOT NULL AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_spots_coordinates", table_name="spots")
