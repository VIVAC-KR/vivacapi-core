from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import AppException, ErrorCode
from app.core.security import create_admin_access_token, verify_google_id_token
from app.crud.user import get_user_by_email
from app.schemas.auth import (
    AdminLoginResponse,
    AdminUserSummary,
    GoogleLoginRequest,
)

router = APIRouter()


@router.post("/google", response_model=AdminLoginResponse)
async def admin_google_login(
    body: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AdminLoginResponse:
    """vivac-console에서 발급된 Google ID 토큰을 검증해 어드민 JWT를 발급한다.

    1) Google ID 토큰 서명/aud/iss/exp 검증 (실패 → 401)
    2) (선택) ALLOWED_EMAIL_DOMAIN과 이메일 도메인 일치 여부 확인 (실패 → 403)
    3) DB에서 이메일로 사용자 조회 (없음 → 403, 스태프 자동가입 금지)
    4) is_staff=True 인지 확인 (실패 → 403)
    5) 어드민 액세스 토큰 발급
    """
    try:
        google_info = verify_google_id_token(body.id_token)
    except ValueError:
        raise AppException(ErrorCode.UNAUTHORIZED, "Invalid Google ID token")

    email = google_info["email"]

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

    access_token = create_admin_access_token(
        user.uid, email=user.email, is_staff=user.is_staff
    )
    return AdminLoginResponse(
        access_token=access_token,
        user=AdminUserSummary(
            id=user.uid,
            email=user.email,
            name=user.name,
            is_staff=user.is_staff,
        ),
    )
