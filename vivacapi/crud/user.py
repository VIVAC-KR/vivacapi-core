from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.nickname import generate_nickname
from vivacapi.models.user import MembershipTier, User

NICKNAME_GENERATION_ATTEMPTS = 10


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.uid == user_id))
    return result.scalar_one_or_none()


async def get_user_by_google_sub(db: AsyncSession, google_sub: str) -> User | None:
    result = await db.execute(select(User).where(User.google_sub == google_sub))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    # 이메일은 대소문자 무시 매칭 — 저장은 소문자 정규화(create_user)지만,
    # 기존 데이터/외부 입력의 케이스 차이로 staff 매칭이 어긋나지 않도록 방어한다.
    result = await db.execute(
        select(User).where(func.lower(User.email) == email.lower())
    )
    return result.scalar_one_or_none()


async def _generate_unique_nickname(db: AsyncSession) -> str:
    for _ in range(NICKNAME_GENERATION_ATTEMPTS):
        candidate = generate_nickname()
        result = await db.execute(select(User.uid).where(User.nickname == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
    raise RuntimeError(
        f"Failed to generate unique nickname after {NICKNAME_GENERATION_ATTEMPTS} attempts"
    )


async def create_user(
    db: AsyncSession,
    *,
    email: str,
    google_sub: str,
    name: str | None = None,
    picture: str | None = None,
) -> User:
    nickname = await _generate_unique_nickname(db)
    user = User(
        # 소문자 정규화 — 케이스만 다른 중복 계정 생성을 막는다
        # (docs/db-security-review-2026-05-02.md H-2).
        email=email.lower(),
        google_sub=google_sub,
        nickname=nickname,
        name=name,
        picture=picture,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_profile(
    db: AsyncSession,
    user: User,
    *,
    name: str | None = None,
    picture: str | None = None,
) -> User:
    if name is not None:
        user.name = name
    if picture is not None:
        user.picture = picture
    await db.commit()
    await db.refresh(user)
    return user


async def mark_onboarding_survey_completed(
    db: AsyncSession,
    user: User,
    *,
    completed_at: datetime | None = None,
) -> User:
    """온보딩 설문 완료를 기록하고 membership_tier를 'member'로 전이시킨다."""
    user.onboarding_survey_completed_at = completed_at or datetime.now(timezone.utc)
    user.membership_tier = MembershipTier.MEMBER
    await db.commit()
    await db.refresh(user)
    return user
