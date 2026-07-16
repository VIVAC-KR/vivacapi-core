from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.deps import verify_staff_google_login
from vivacapi.core.security import create_admin_access_token
from vivacapi.schemas.auth import (
    AdminLoginResponse,
    AdminUserSummary,
    GoogleLoginRequest,
)

router = APIRouter()


@router.post(
    "/google", response_model=AdminLoginResponse, summary="콘솔 staff Google 로그인"
)
async def admin_google_login(
    body: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AdminLoginResponse:
    """vivac-console에서 발급된 Google ID 토큰을 검증해 어드민 JWT를 발급한다.

    토큰 서명/aud/iss/exp → (선택) 도메인 화이트리스트 → staff 사용자 확인.
    검증 실패 시 401/403 (verify_staff_google_login 참조).

    인증 전 호출이라 `/v1/internal/*` 라우터 단위 `require_staff` 게이트를
    탈 수 없어 `/v1/admin/auth`라는 별도 prefix를 쓴다 — 콘솔용 신규
    엔드포인트를 이 밑에 추가하지 않는다.
    """
    user = await verify_staff_google_login(db, body.id_token)

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
