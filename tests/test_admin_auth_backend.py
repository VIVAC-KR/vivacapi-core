"""SQLAdmin AuthenticationBackend (`AdminAuth`) 통합 테스트.

- 로그인 폼이 받는 `id_token`을 Google JWT 검증 함수로 통과시켜 staff 사용자에게만 세션을 발급한다.
- staff 가 아닐 경우 로그인 실패 + 미인증 요청은 `/admin/login`으로 리다이렉트된다.
- `/admin/logout` 호출 시 세션이 만료된다.
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.main import app
from tests.helpers import make_user


def _patch_verify(monkeypatch: pytest.MonkeyPatch, idinfo: dict[str, Any]) -> None:
    monkeypatch.setattr(
        "vivacapi.admin.auth.verify_google_id_token", lambda _token: idinfo
    )


def _patch_verify_raises(
    monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    def _raise(_token: str) -> dict[str, Any]:
        raise exc

    monkeypatch.setattr("vivacapi.admin.auth.verify_google_id_token", _raise)


def _patch_admin_db_session(
    monkeypatch: pytest.MonkeyPatch, session: AsyncSession
) -> None:
    """`AdminAuth`가 테스트 트랜잭션 안에서 staff 사용자를 보도록 세션 컨텍스트를 교체."""

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        yield session

    monkeypatch.setattr("vivacapi.admin.auth.admin_db_session", _scope)


@pytest.fixture
async def admin_client(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncClient:
    _patch_admin_db_session(monkeypatch, db_session)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_staff_user_login_grants_admin_access(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    user = await make_user(
        db_session, email="staff@vivac.kr", google_sub="g-sub-staff", name="Staff"
    )
    user.is_staff = True
    await db_session.commit()

    _patch_verify(
        monkeypatch,
        {"sub": "g-sub-staff", "email": "staff@vivac.kr", "email_verified": True},
    )

    login = await admin_client.post(
        "/admin/login", data={"id_token": "fake"}, follow_redirects=False
    )
    assert login.status_code == 302
    assert login.headers["location"].endswith("/admin/")

    index = await admin_client.get("/admin/", follow_redirects=False)
    assert index.status_code == 200


async def test_non_staff_user_login_rejected(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    await make_user(
        db_session, email="user@vivac.kr", google_sub="g-sub-user", name="User"
    )

    _patch_verify(
        monkeypatch,
        {"sub": "g-sub-user", "email": "user@vivac.kr", "email_verified": True},
    )

    login = await admin_client.post(
        "/admin/login", data={"id_token": "fake"}, follow_redirects=False
    )
    assert login.status_code == 400


async def test_unknown_user_login_rejected(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_verify(
        monkeypatch,
        {"sub": "g-sub-nobody", "email": "nobody@vivac.kr", "email_verified": True},
    )

    login = await admin_client.post(
        "/admin/login", data={"id_token": "fake"}, follow_redirects=False
    )
    assert login.status_code == 400


async def test_invalid_google_token_rejected(
    admin_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_verify_raises(monkeypatch, ValueError("token expired"))

    login = await admin_client.post(
        "/admin/login", data={"id_token": "expired"}, follow_redirects=False
    )
    assert login.status_code == 400


async def test_missing_id_token_rejected(admin_client: AsyncClient):
    login = await admin_client.post(
        "/admin/login", data={}, follow_redirects=False
    )
    assert login.status_code == 400


async def test_unauthenticated_request_redirects_to_login(
    admin_client: AsyncClient,
):
    response = await admin_client.get("/admin/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")


async def test_logout_clears_session(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    user = await make_user(
        db_session, email="staff@vivac.kr", google_sub="g-sub-staff", name="Staff"
    )
    user.is_staff = True
    await db_session.commit()

    _patch_verify(
        monkeypatch,
        {"sub": "g-sub-staff", "email": "staff@vivac.kr", "email_verified": True},
    )

    await admin_client.post(
        "/admin/login", data={"id_token": "fake"}, follow_redirects=False
    )
    # 로그인 직후 인덱스 접근 가능
    assert (await admin_client.get("/admin/", follow_redirects=False)).status_code == 200

    logout = await admin_client.get("/admin/logout", follow_redirects=False)
    assert logout.status_code == 302

    after = await admin_client.get("/admin/", follow_redirects=False)
    assert after.status_code == 302
    assert after.headers["location"].endswith("/admin/login")


async def test_login_rejects_disallowed_email_domain(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from vivacapi.core.config import settings

    monkeypatch.setattr(settings, "ALLOWED_EMAIL_DOMAIN", "vivac.kr")

    user = await make_user(
        db_session, email="staff@other.com", google_sub="g-sub-other", name="Other"
    )
    user.is_staff = True
    await db_session.commit()

    _patch_verify(
        monkeypatch,
        {"sub": "g-sub-other", "email": "staff@other.com", "email_verified": True},
    )

    login = await admin_client.post(
        "/admin/login", data={"id_token": "fake"}, follow_redirects=False
    )
    assert login.status_code == 400


async def test_login_page_renders(admin_client: AsyncClient):
    """GSI button을 가진 커스텀 로그인 템플릿이 렌더되는지 확인."""
    response = await admin_client.get("/admin/login")
    assert response.status_code == 200
    body = response.text
    assert "g_id_onload" in body
    assert "accounts.google.com/gsi/client" in body
