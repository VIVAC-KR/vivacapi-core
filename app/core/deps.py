from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import AppException, ErrorCode
from app.core.security import decode_token
from app.crud.user import get_user_by_id
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


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
