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


@router.post("/google", response_model=TokenResponse, summary="Google 로그인")
async def google_login(
    body: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Google ID 토큰을 검증해 로그인하고, 최초 로그인이면 계정을 새로 만듭니다.

    발급되는 refresh_token은 완전 stateless한 JWT라 서버에 저장되지 않습니다 —
    유출되면 만료(기본 7일)까지는 회수할 방법이 없으니 클라이언트가 안전하게
    보관해야 합니다. Google 토큰 검증에 실패하면 401, 비활성 계정이면 403이
    반환됩니다.
    """
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


@router.post("/refresh", response_model=TokenResponse, summary="액세스 토큰 재발급")
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """리프레시 토큰을 검증해 새 액세스/리프레시 토큰 쌍을 발급합니다.

    리프레시 토큰은 서버에 별도 저장되지 않는 stateless JWT라 회수(revoke)할
    수단이 없습니다 — 발급 후 만료(7일)까지는 탈취돼도 계속 유효합니다.
    토큰이 유효하지 않거나 만료됐거나 refresh 타입이 아니면 401, 사용자를
    찾을 수 없어도 401, 비활성 계정이면 403이 반환됩니다.
    """
    try:
        payload = decode_token(body.refresh_token)
    except InvalidTokenError:
        raise AppException(ErrorCode.UNAUTHORIZED, "Invalid or expired refresh token")

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


@router.get("/me", response_model=UserResponse, summary="내 정보 조회")
async def me(current_user: User = Depends(get_current_user)) -> User:
    """Authorization 헤더의 액세스 토큰으로 현재 로그인한 사용자 정보를 반환합니다.

    토큰이 없거나 유효하지 않으면 401, 비활성 계정이면 403이 반환됩니다.
    """
    return current_user
