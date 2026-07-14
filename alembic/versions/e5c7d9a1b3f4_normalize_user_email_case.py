"""normalize user email to lowercase + functional unique index

기존 email UNIQUE는 대소문자를 구분해 케이스만 다른 중복 계정이 가능했다
(docs/db-security-review-2026-05-02.md H-2). 기존 행을 소문자로 정규화하고
lower(email) functional unique index로 재발을 막는다.

케이스만 다른 중복 행이 이미 존재하면 이 마이그레이션은 unique 위반으로
실패한다 — 자동 병합하지 않고 수동 정리를 요구하는 것이 의도된 동작이다.

Revision ID: e5c7d9a1b3f4
Revises: f1a2b3c4d5e6
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5c7d9a1b3f4'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
    op.execute(
        "CREATE UNIQUE INDEX ix_users_email_lower ON users (lower(email))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_email_lower")
