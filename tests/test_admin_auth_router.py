from typing import Any

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.config import settings
from vivacapi.models.user import StaffRole
from tests.helpers import make_user


def _patch_verify(monkeypatch: pytest.MonkeyPatch, idinfo: dict[str, Any]) -> None:
    monkeypatch.setattr(
        "vivacapi.core.deps.verify_google_id_token",
        lambda _token: idinfo,
    )


def _patch_verify_raises(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    def _raise(_token: str) -> dict[str, Any]:
        raise exc

    monkeypatch.setattr("vivacapi.core.deps.verify_google_id_token", _raise)


async def test_staff_user_login_returns_token_and_user(
    db_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    user = await make_user(
        db_session,
        email="staff@vivac.kr",
        google_sub="g-sub-staff",
        name="Staff User",
    )
    user.is_staff = True
    await db_session.commit()

    _patch_verify(
        monkeypatch,
        {
            "sub": "g-sub-staff",
            "email": "staff@vivac.kr",
            "name": "Staff User",
        },
    )

    response = await db_client.post("/v1/admin/auth/google", json={"id_token": "fake"})

    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {
        "id": user.uid,
        "email": "staff@vivac.kr",
        "name": "Staff User",
        "is_staff": True,
        "staff_role": "staff",
    }

    decoded = jwt.decode(
        body["access_token"],
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )
    assert decoded["sub"] == user.uid
    assert decoded["email"] == "staff@vivac.kr"
    assert decoded["is_staff"] is True
    assert decoded["staff_role"] == "staff"
    assert decoded["type"] == "access"


async def test_superuser_login_returns_staff_role_in_body_and_token(
    db_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """VAC-2 후속: 콘솔이 서버 왕복 없이 SUPERUSER를 판별할 수 있도록 staff_role 노출."""
    user = await make_user(
        db_session,
        email="superuser@vivac.kr",
        google_sub="g-sub-superuser",
        name="Super User",
    )
    user.is_staff = True
    user.staff_role = StaffRole.SUPERUSER
    await db_session.commit()

    _patch_verify(
        monkeypatch,
        {
            "sub": "g-sub-superuser",
            "email": "superuser@vivac.kr",
            "name": "Super User",
        },
    )

    response = await db_client.post("/v1/admin/auth/google", json={"id_token": "fake"})

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["staff_role"] == "superuser"

    decoded = jwt.decode(
        body["access_token"],
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
    )
    assert decoded["staff_role"] == "superuser"


async def test_unknown_user_returns_403(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_verify(
        monkeypatch,
        {"sub": "g-sub-unknown", "email": "nobody@vivac.kr", "name": "?"},
    )

    response = await db_client.post("/v1/admin/auth/google", json={"id_token": "fake"})
    assert response.status_code == 403


async def test_non_staff_user_returns_403(
    db_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    await make_user(
        db_session, email="user@vivac.kr", google_sub="g-sub-user", name="User"
    )
    _patch_verify(
        monkeypatch,
        {"sub": "g-sub-user", "email": "user@vivac.kr", "name": "User"},
    )

    response = await db_client.post("/v1/admin/auth/google", json={"id_token": "fake"})
    assert response.status_code == 403


async def test_invalid_id_token_returns_401(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_verify_raises(monkeypatch, ValueError("token expired"))

    response = await db_client.post(
        "/v1/admin/auth/google", json={"id_token": "expired"}
    )
    assert response.status_code == 401


async def test_aud_mismatch_returns_401(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    # google-auth raises ValueError when aud does not match GOOGLE_CLIENT_ID.
    _patch_verify_raises(monkeypatch, ValueError("Audience mismatch"))

    response = await db_client.post(
        "/v1/admin/auth/google", json={"id_token": "wrong-aud"}
    )
    assert response.status_code == 401


async def test_disallowed_domain_returns_403(
    db_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "ALLOWED_EMAIL_DOMAIN", "vivac.kr")

    user = await make_user(
        db_session,
        email="staff@other.com",
        google_sub="g-sub-other",
        name="Other",
    )
    user.is_staff = True
    await db_session.commit()

    _patch_verify(
        monkeypatch,
        {"sub": "g-sub-other", "email": "staff@other.com", "name": "Other"},
    )

    response = await db_client.post("/v1/admin/auth/google", json={"id_token": "fake"})
    assert response.status_code == 403
