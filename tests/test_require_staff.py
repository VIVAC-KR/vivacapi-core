import pytest
from fastapi import APIRouter
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_staff
from app.core.security import create_access_token
from app.main import app
from app.core.database import get_db
from tests.helpers import bearer, make_user


# 테스트용 더미 라우터 — require_staff 가 라우터 레벨에 적용된 상황을 재현
_test_router = APIRouter(
    prefix="/test-internal",
    dependencies=[pytest.importorskip("fastapi").Depends(require_staff)],
)


@_test_router.get("/ping")
async def _ping():
    return {"ok": True}


app.include_router(_test_router)


# ---------------------------------------------------------------------------
# require_staff 의존성
# ---------------------------------------------------------------------------


@pytest.fixture
async def staff_client(db_session: AsyncSession) -> AsyncClient:
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


async def test_staff_user_passes(staff_client: AsyncClient, db_session: AsyncSession):
    user = await make_user(db_session, email="staff@example.com", google_sub="sub-staff")
    user.is_staff = True
    await db_session.commit()

    token = create_access_token(str(user.uid))
    response = await staff_client.get("/test-internal/ping", headers=bearer(token))

    assert response.status_code == 200


async def test_non_staff_user_gets_403(
    staff_client: AsyncClient, db_session: AsyncSession
):
    user = await make_user(db_session, email="user@example.com", google_sub="sub-user")
    # is_staff 기본값 False

    token = create_access_token(str(user.uid))
    response = await staff_client.get("/test-internal/ping", headers=bearer(token))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_unauthenticated_gets_401(staff_client: AsyncClient):
    response = await staff_client.get("/test-internal/ping")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
