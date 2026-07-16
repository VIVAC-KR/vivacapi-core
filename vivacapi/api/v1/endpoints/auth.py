from fastapi import APIRouter, Depends
from jwt.exceptions import InvalidTokenError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.deps import get_current_user
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_google_id_token,
)
from vivacapi.crud.invite import consume_invite_for_signup
from vivacapi.crud.user import (
    create_user,
    get_user_by_google_sub,
    get_user_by_id,
    update_user_profile,
)
from vivacapi.models.user import User
from vivacapi.schemas.auth import GoogleLoginRequest, RefreshRequest, TokenResponse
from vivacapi.schemas.user import UserResponse

router = APIRouter()


@router.post("/google", response_model=TokenResponse)
async def google_login(
    body: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Google ID 토큰으로 로그인하고 JWT 토큰 쌍을 발급합니다."""
    try:
        google_info = verify_google_id_token(body.id_token)
    except ValueError:
        raise AppException(ErrorCode.UNAUTHORIZED, "Invalid Google ID token")

    user = await get_user_by_google_sub(db, google_info["sub"])
    is_new_user = user is None

    if user is None:
        try:
            user = await create_user(
                db,
                email=google_info["email"],
                google_sub=google_info["sub"],
                name=google_info.get("name"),
                picture=google_info.get("picture"),
            )
        except IntegrityError:
            # 같은 계정의 동시 첫 로그인 레이스: 다른 요청이 먼저 생성 → 재조회
            await db.rollback()
            user = await get_user_by_google_sub(db, google_info["sub"])
            if user is None:
                raise
    else:
        await update_user_profile(
            db,
            user,
            name=google_info.get("name"),
            picture=google_info.get("picture"),
        )

    if not user.is_active:
        raise AppException(ErrorCode.FORBIDDEN, "Inactive user")

    if is_new_user and body.invite_uid:
        await consume_invite_for_signup(db, body.invite_uid, user)

    return TokenResponse(
        access_token=create_access_token(user.uid),
        refresh_token=create_refresh_token(user.uid),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """리프레시 토큰으로 새 토큰 쌍을 발급합니다."""
    try:
        payload = decode_token(body.refresh_token)
    except InvalidTokenError:
        raise AppException(
            ErrorCode.UNAUTHORIZED, "Invalid or expired refresh token"
        )

    if payload.get("type") != "refresh":
        raise AppException(ErrorCode.UNAUTHORIZED, "Invalid token type")

    user = await get_user_by_id(db, payload["sub"])

    if user is None:
        raise AppException(ErrorCode.UNAUTHORIZED, "User not found")

    if not user.is_active:
        raise AppException(ErrorCode.FORBIDDEN, "Inactive user")

    return TokenResponse(
        access_token=create_access_token(user.uid),
        refresh_token=create_refresh_token(user.uid),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    """현재 로그인한 사용자 정보를 반환합니다."""
    return current_user
