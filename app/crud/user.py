import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.nickname import generate_nickname
from app.models.user import MembershipTier, User

NICKNAME_GENERATION_ATTEMPTS = 10


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.uid == user_id))
    return result.scalar_one_or_none()


async def get_user_by_google_sub(db: AsyncSession, google_sub: str) -> User | None:
    result = await db.execute(select(User).where(User.google_sub == google_sub))
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
        email=email,
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
