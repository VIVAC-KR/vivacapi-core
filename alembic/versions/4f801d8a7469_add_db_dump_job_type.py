"""add db_dump job type

Revision ID: 4f801d8a7469
Revises: 3faa9de7cf2a
Create Date: 2026-08-01 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f801d8a7469"
down_revision: Union[str, None] = "3faa9de7cf2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'db_dump'")


def downgrade() -> None:
    # Postgres는 enum value DROP을 지원하지 않는다 — 원복 불가(no-op).
    pass
