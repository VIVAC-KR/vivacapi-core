from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.config import settings
from vivacapi.crud.user import create_user
from vivacapi.models.user import User


async def make_user(
    db: AsyncSession,
    *,
    email: str = "tester@example.com",
    google_sub: str = "google-sub-tester",
    name: str | None = "Tester",
    picture: str | None = None,
    is_active: bool = True,
) -> User:
    user = await create_user(
        db,
        email=email,
        google_sub=google_sub,
        name=name,
        picture=picture,
    )
    if not is_active:
        user.is_active = False
        await db.commit()
        await db.refresh(user)
    return user


def make_expired_token(user_id: str, *, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": token_type,
        "iat": now - timedelta(days=30),
        "exp": now - timedelta(days=1),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
