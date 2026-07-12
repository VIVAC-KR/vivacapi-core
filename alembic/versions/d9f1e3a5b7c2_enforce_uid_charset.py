"""enforce uid charset: [0-9A-Za-z]{22} on all shortuuid PKs

기존에 외부(ETL 직접 삽입 등)에서 들어온 규격 외 uid('-' 등 포함) row는
삭제한다 — 데이터 오너 승인됨 (2026-07-12). ETL이 재수집으로 복구한다.

Revision ID: d9f1e3a5b7c2
Revises: c8e2d4f6a1b3
Create Date: 2026-07-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd9f1e3a5b7c2'
down_revision: Union[str, None] = 'c8e2d4f6a1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UID_RE = "'^[0-9A-Za-z]{22}$'"

# (테이블, PK 컬럼) — FK 자식이 먼저 오도록 정렬
_TABLES = (
    "spot_images",
    "spot_reviews",
    "spot_business_info",
    "spots",
    "jobs",
    "users",
)


def upgrade() -> None:
    # 1) 규격 외 spot을 참조하는 자식 row 삭제
    for child in ("spot_images", "spot_reviews", "spot_business_info"):
        op.execute(
            f"DELETE FROM {child} WHERE spot_uid IN "
            f"(SELECT uid FROM spots WHERE uid !~ {_UID_RE})"
        )
    # 2) 각 테이블의 규격 외 uid row 삭제 (users는 서버 생성만 존재하나 방어적으로 동일 처리 전 확인)
    for table in ("spot_images", "spot_reviews", "spot_business_info", "spots", "jobs"):
        op.execute(f"DELETE FROM {table} WHERE uid !~ {_UID_RE}")

    # 3) CHECK constraint 부여 — 이후 어떤 경로로도 규격 외 uid 삽입 불가
    for table in _TABLES:
        op.create_check_constraint(
            f"ck_{table}_uid_format", table, f"uid ~ {_UID_RE}"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f"ck_{table}_uid_format", table, type_="check")
    # 삭제된 row는 복구 불가 (ETL 재수집으로 복구)
