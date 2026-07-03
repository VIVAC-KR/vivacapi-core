from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.config import settings
from vivacapi.core.database import get_db
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.core.security import decode_token, verify_google_id_token
from vivacapi.crud.user import get_user_by_email, get_user_by_id
from vivacapi.models.user import User

_bearer = HTTPBearer(auto_error=False)


async def verify_staff_google_login(db: AsyncSession, id_token: str) -> User:
    """Google ID 토큰 검증 → 도메인 화이트리스트 → staff 사용자 확인.

    어드민 API 로그인과 SQLAdmin 세션 로그인이 공유하는 흐름.
    실패 시 AppException(UNAUTHORIZED/FORBIDDEN)을 던진다.
    """
    try:
        info = verify_google_id_token(id_token)
    except ValueError:
        raise AppException(ErrorCode.UNAUTHORIZED, "Invalid Google ID token")

    email = info.get("email")
    if not email:
        raise AppException(ErrorCode.UNAUTHORIZED, "Invalid Google ID token")

    if settings.ALLOWED_EMAIL_DOMAIN:
        _, _, domain = email.partition("@")
        if domain.lower() != settings.ALLOWED_EMAIL_DOMAIN.lower():
            raise AppException(ErrorCode.FORBIDDEN, "Email domain not allowed")

    user = await get_user_by_email(db, email)
    if user is None:
        raise AppException(ErrorCode.FORBIDDEN, "User not registered")
    if not user.is_staff:
        raise AppException(ErrorCode.FORBIDDEN, "Staff only")
    if not user.is_active:
        raise AppException(ErrorCode.FORBIDDEN, "Inactive user")

    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authorization 헤더의 JWT 액세스 토큰을 검증하고 현재 사용자를 반환합니다."""
    if credentials is None:
        raise AppException(
            ErrorCode.UNAUTHORIZED, "Missing authentication credentials"
        )

    try:
        payload = decode_token(credentials.credentials)
    except InvalidTokenError:
        raise AppException(ErrorCode.UNAUTHORIZED, "Invalid or expired token")

    if payload.get("type") != "access":
        raise AppException(ErrorCode.UNAUTHORIZED, "Invalid token type")

    user = await get_user_by_id(db, payload["sub"])

    if user is None:
        raise AppException(ErrorCode.UNAUTHORIZED, "User not found")

    if not user.is_active:
        raise AppException(ErrorCode.FORBIDDEN, "Inactive user")

    return user


async def require_staff(user: User = Depends(get_current_user)) -> User:
    if not user.is_staff:
        raise AppException(ErrorCode.FORBIDDEN, "Staff only")
    return user


CurrentStaff = Annotated[User, Depends(require_staff)]
