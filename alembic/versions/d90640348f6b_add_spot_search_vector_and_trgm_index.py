"""add spot search vector and trgm index

Revision ID: d90640348f6b
Revises: 610d81c68705
Create Date: 2026-07-15 00:59:11.719314

검색(VVC-107)용 — title/tagline/description/address를 가중치(A/B/C/D)로 묶은
generated tsvector 컬럼과, title 부분/오타 매칭용 pg_trgm 인덱스를 추가한다.
설계 근거: docs/projects/spot-search-postgres-fts.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR


# revision identifiers, used by Alembic.
revision: str = 'd90640348f6b'
down_revision: Union[str, None] = '610d81c68705'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column(
        "spots",
        sa.Column(
            "search_vector",
            TSVECTOR,
            sa.Computed(
                "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('simple', coalesce(tagline, '')), 'B') || "
                "setweight(to_tsvector('simple', coalesce(description, '')), 'C') || "
                "setweight(to_tsvector('simple', coalesce(address, '')), 'D')",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.execute(
        "CREATE INDEX ix_spots_search_vector ON spots USING GIN (search_vector)"
    )
    op.execute(
        "CREATE INDEX ix_spots_title_trgm ON spots USING GIN (title gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_spots_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_spots_search_vector")
    op.drop_column("spots", "search_vector")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
