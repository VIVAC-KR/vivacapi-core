from datetime import datetime, timedelta, timezone

import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import settings


def verify_google_id_token(token: str) -> dict:
    """Google ID 토큰을 검증하고 클레임(sub, email, name, picture 등)을 반환합니다.

    내부적으로 다음을 검증합니다:
    - 토큰 서명 (Google 공개키 기반)
    - 토큰 만료 (exp)
    - 발급자 (iss: accounts.google.com)
    - 수신자 (aud: GOOGLE_CLIENT_ID)

    Raises:
        ValueError: 토큰이 유효하지 않거나 이메일 미인증 시
    """
    idinfo = google_id_token.verify_oauth2_token(
        token,
        google_requests.Request(),
        settings.GOOGLE_CLIENT_ID,
    )

    if not idinfo.get("email_verified"):
        raise ValueError("Email not verified by Google")

    return idinfo


def create_access_token(user_id: str) -> str:
    """JWT 액세스 토큰을 생성합니다."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=int(settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """JWT 리프레시 토큰을 생성합니다."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=int(settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """JWT 토큰을 디코딩·검증합니다.

    Raises:
        jwt.exceptions.InvalidTokenError: 서명 불일치, 만료 등
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
