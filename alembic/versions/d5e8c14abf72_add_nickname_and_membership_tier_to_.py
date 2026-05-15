"""add nickname and membership_tier to users

Revision ID: d5e8c14abf72
Revises: b33fd71c6fea
Create Date: 2026-05-14 13:00:00.000000

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e8c14abf72'
down_revision: Union[str, None] = 'b33fd71c6fea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Backfill 전용 단어 사전. app/core/nickname.py와 동일하지만 마이그레이션은
# 시점이 고정되어야 하므로 의도적으로 인라인한다.
_ADJECTIVES = (
    "happy", "brave", "calm", "bright", "cozy", "swift", "kind", "bold",
    "gentle", "lively", "merry", "quiet", "sunny", "witty", "fancy",
    "mighty", "lucky", "jolly", "fluffy", "breezy", "eager", "fresh",
    "glad", "golden", "grand", "humble", "lush", "misty", "nimble",
    "noble", "plucky", "proud", "rapid", "royal", "silver", "snug",
    "spry", "sturdy", "tidy", "vivid", "warm", "wise", "zesty",
    "amber", "cool", "dewy", "frosty", "rustic", "shiny", "smooth",
)
_NOUNS = (
    "tiger", "panda", "otter", "fox", "owl", "deer", "whale", "lynx",
    "eagle", "bear", "hawk", "wolf", "puma", "koala", "moose",
    "bison", "ranger", "hiker", "camper", "scout",
    "pine", "oak", "river", "lake", "peak", "ridge", "valley", "meadow",
    "cliff", "brook", "ember", "lantern", "compass", "tent", "flame",
    "stove", "trail", "summit", "forest", "canyon", "glacier", "breeze",
    "stone", "branch", "dune", "harbor", "marsh", "raven", "falcon",
    "sparrow",
)


def _gen_nickname() -> str:
    adjective = secrets.choice(_ADJECTIVES)
    noun = secrets.choice(_NOUNS)
    number = secrets.randbelow(9000) + 1000
    return f"{adjective}-{noun}-{number}"


def upgrade() -> None:
    bind = op.get_bind()

    # 1) ENUM 타입 생성
    membership_tier_enum = sa.Enum(
        'free', 'member', name='membership_tier'
    )
    membership_tier_enum.create(bind, checkfirst=False)

    # 2) 컬럼 추가 (nickname은 backfill 후 NOT NULL 전환)
    op.add_column(
        'users',
        sa.Column('nickname', sa.String(length=50), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column(
            'membership_tier',
            sa.Enum('free', 'member', name='membership_tier', create_type=False),
            nullable=False,
            server_default='free',
        ),
    )

    # 3) Backfill
    rows = bind.execute(
        sa.text("SELECT uid, onboarding_survey_completed_at FROM users")
    ).fetchall()

    used: set[str] = set()
    existing = bind.execute(
        sa.text("SELECT nickname FROM users WHERE nickname IS NOT NULL")
    ).fetchall()
    used.update(row[0] for row in existing if row[0] is not None)

    for row in rows:
        uid = row[0]
        completed_at = row[1]

        for _ in range(20):
            candidate = _gen_nickname()
            if candidate not in used:
                used.add(candidate)
                break
        else:
            raise RuntimeError(
                f"Failed to generate unique nickname for user {uid} during backfill"
            )

        tier = 'member' if completed_at is not None else 'free'
        bind.execute(
            sa.text(
                "UPDATE users SET nickname = :nick, membership_tier = :tier "
                "WHERE uid = :uid"
            ),
            {"nick": candidate, "tier": tier, "uid": uid},
        )

    # 4) NOT NULL + UNIQUE 인덱스
    op.alter_column('users', 'nickname', nullable=False)
    op.create_index(
        op.f('ix_users_nickname'), 'users', ['nickname'], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_users_nickname'), table_name='users')
    op.drop_column('users', 'membership_tier')
    op.drop_column('users', 'nickname')
    sa.Enum(name='membership_tier').drop(op.get_bind(), checkfirst=False)
