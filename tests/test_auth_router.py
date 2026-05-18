import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, create_refresh_token
from app.models.user import User
from tests.helpers import bearer, make_expired_token, make_user

# ---------------------------------------------------------------------------
# /auth/google
# ---------------------------------------------------------------------------


async def test_google_new_user_signup_creates_user(
    db_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_idinfo: dict[str, Any] = {
        "sub": "google-sub-new-001",
        "email": "newuser@example.com",
        "name": "New User",
        "picture": "https://example.com/new.jpg",
    }
    monkeypatch.setattr(
        "app.api.v1.endpoints.auth.verify_google_id_token", lambda _token: fake_idinfo
    )

    response = await db_client.post("/v1/auth/google", json={"id_token": "fake"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]

    result = await db_session.execute(
        select(User).where(User.google_sub == "google-sub-new-001")
    )
    user = result.scalar_one()
    assert user.email == "newuser@example.com"
    assert user.name == "New User"
    assert user.picture == "https://example.com/new.jpg"


async def test_google_existing_user_login_updates_profile(
    db_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    user = await make_user(
        db_session,
        email="existing@example.com",
        google_sub="google-sub-existing",
        name="Old Name",
        picture="https://example.com/old.jpg",
    )
    original_uid = user.uid

    fake_idinfo: dict[str, Any] = {
        "sub": "google-sub-existing",
        "email": "existing@example.com",
        "name": "Updated Name",
        "picture": "https://example.com/updated.jpg",
    }
    monkeypatch.setattr(
        "app.api.v1.endpoints.auth.verify_google_id_token", lambda _token: fake_idinfo
    )

    response = await db_client.post("/v1/auth/google", json={"id_token": "fake"})
    assert response.status_code == 200

    await db_session.refresh(user)
    assert user.uid == original_uid
    assert user.name == "Updated Name"
    assert user.picture == "https://example.com/updated.jpg"

    count = await db_session.execute(
        select(User).where(User.google_sub == "google-sub-existing")
    )
    assert len(count.scalars().all()) == 1


async def test_google_inactive_user_returns_403(
    db_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    await make_user(
        db_session,
        email="inactive-g@example.com",
        google_sub="google-sub-inactive-g",
        is_active=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.auth.verify_google_id_token",
        lambda _token: {
            "sub": "google-sub-inactive-g",
            "email": "inactive-g@example.com",
            "name": "Inactive",
        },
    )

    response = await db_client.post("/v1/auth/google", json={"id_token": "fake"})
    assert response.status_code == 403


async def test_google_invalid_id_token_returns_401(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    def _raise(_token: str) -> dict[str, Any]:
        raise ValueError("Invalid Google ID token")

    monkeypatch.setattr("app.routers.auth.verify_google_id_token", _raise)

    response = await db_client.post("/v1/auth/google", json={"id_token": "bad"})
    assert response.status_code == 401


async def test_google_email_not_verified_returns_401(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    # verify_google_id_token이 email_verified=false에 대해 raise하는 동작을 시뮬레이션
    def _raise(_token: str) -> dict[str, Any]:
        raise ValueError("Email not verified by Google")

    monkeypatch.setattr("app.routers.auth.verify_google_id_token", _raise)

    response = await db_client.post("/v1/auth/google", json={"id_token": "fake"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# /auth/refresh
# ---------------------------------------------------------------------------


async def test_refresh_success_issues_new_token_pair(
    db_client: AsyncClient,
    db_session: AsyncSession,
):
    user = await make_user(
        db_session, email="r1@example.com", google_sub="sub-r1"
    )
    token = create_refresh_token(user.uid)

    response = await db_client.post(
        "/v1/auth/refresh", json={"refresh_token": token}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_refresh_with_expired_token_returns_401(
    db_client: AsyncClient,
    db_session: AsyncSession,
):
    user = await make_user(
        db_session, email="r2@example.com", google_sub="sub-r2"
    )
    expired = make_expired_token(user.uid, token_type="refresh")

    response = await db_client.post(
        "/v1/auth/refresh", json={"refresh_token": expired}
    )
    assert response.status_code == 401


async def test_refresh_with_access_token_returns_401(
    db_client: AsyncClient,
    db_session: AsyncSession,
):
    user = await make_user(
        db_session, email="r3@example.com", google_sub="sub-r3"
    )
    access = create_access_token(user.uid)

    response = await db_client.post(
        "/v1/auth/refresh", json={"refresh_token": access}
    )
    assert response.status_code == 401


async def test_refresh_inactive_user_returns_403(
    db_client: AsyncClient,
    db_session: AsyncSession,
):
    user = await make_user(
        db_session,
        email="r4@example.com",
        google_sub="sub-r4",
        is_active=False,
    )
    token = create_refresh_token(user.uid)

    response = await db_client.post(
        "/v1/auth/refresh", json={"refresh_token": token}
    )
    assert response.status_code == 403


async def test_refresh_for_nonexistent_user_returns_401(
    db_client: AsyncClient,
):
    token = create_refresh_token(uuid.uuid4())

    response = await db_client.post(
        "/v1/auth/refresh", json={"refresh_token": token}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# /auth/me  (이슈의 /users/me에 대응 — 현재 코드 기준)
# ---------------------------------------------------------------------------


async def test_me_authenticated_returns_user_payload(
    db_client: AsyncClient,
    db_session: AsyncSession,
):
    user = await make_user(
        db_session,
        email="me1@example.com",
        google_sub="sub-me1",
        name="Me One",
    )
    token = create_access_token(user.uid)

    response = await db_client.get("/v1/auth/me", headers=bearer(token))

    assert response.status_code == 200
    body = response.json()
    assert body["uid"] == str(user.uid)
    assert body["email"] == "me1@example.com"
    assert body["nickname"] == user.nickname
    assert body["membership_tier"] == "free"
    assert body["is_active"] is True


async def test_me_without_authorization_header_returns_401(
    db_client: AsyncClient,
):
    response = await db_client.get("/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_me_with_invalid_token_returns_401(
    db_client: AsyncClient,
):
    response = await db_client.get(
        "/v1/auth/me", headers=bearer("not-a-valid-jwt")
    )
    assert response.status_code == 401


async def test_me_with_expired_token_returns_401(
    db_client: AsyncClient,
    db_session: AsyncSession,
):
    user = await make_user(
        db_session, email="me4@example.com", google_sub="sub-me4"
    )
    expired = make_expired_token(user.uid, token_type="access")

    response = await db_client.get("/v1/auth/me", headers=bearer(expired))
    assert response.status_code == 401


async def test_me_inactive_user_returns_403(
    db_client: AsyncClient,
    db_session: AsyncSession,
):
    user = await make_user(
        db_session,
        email="me5@example.com",
        google_sub="sub-me5",
        is_active=False,
    )
    token = create_access_token(user.uid)

    response = await db_client.get("/v1/auth/me", headers=bearer(token))
    assert response.status_code == 403
