from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.security import create_access_token
from vivacapi.models.spot import Spot
from vivacapi.models.user import StaffRole
from tests.helpers import bearer, make_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_staff(
    db: AsyncSession, suffix: str, role: StaffRole = StaffRole.SUPERUSER
):
    """상태 일괄 변경은 SUPERUSER 전용이라 이 파일의 기본 staff는 SUPERUSER로 만든다."""
    user = await make_user(
        db, email=f"staff-{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    user.is_staff = True
    user.staff_role = role
    await db.commit()
    return user


async def _make_spot(db: AsyncSession, title: str, **kwargs) -> Spot:
    spot = Spot(
        title=title,
        rating_avg=kwargs.pop("rating_avg", 0.0),
        review_count=kwargs.pop("review_count", 0),
        **kwargs,
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


# ---------------------------------------------------------------------------
# PATCH /v1/internal/spots/bulk-status — 권한
# ---------------------------------------------------------------------------


async def test_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.patch(
        "/v1/internal/spots/bulk-status",
        json={"uids": ["spot_x"], "pipeline_status": "PUBLISHED"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_non_staff_returns_403(db_client: AsyncClient, db_session: AsyncSession):
    user = await make_user(
        db_session, email="user-bulkstatus@example.com", google_sub="sub-bulkstatus"
    )
    token = create_access_token(user.uid)

    response = await db_client.patch(
        "/v1/internal/spots/bulk-status",
        json={"uids": ["spot_x"], "pipeline_status": "PUBLISHED"},
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_staff_role_returns_403(db_client: AsyncClient, db_session: AsyncSession):
    staff = await _make_staff(db_session, "staff-bs", role=StaffRole.STAFF)
    token = create_access_token(staff.uid)

    response = await db_client.patch(
        "/v1/internal/spots/bulk-status",
        json={"uids": ["spot_x"], "pipeline_status": "PUBLISHED"},
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_manager_role_returns_403(
    db_client: AsyncClient, db_session: AsyncSession
):
    manager = await _make_staff(db_session, "manager-bs", role=StaffRole.MANAGER)
    token = create_access_token(manager.uid)

    response = await db_client.patch(
        "/v1/internal/spots/bulk-status",
        json={"uids": ["spot_x"], "pipeline_status": "PUBLISHED"},
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# PATCH /v1/internal/spots/bulk-status — SUPERUSER 동작
# ---------------------------------------------------------------------------


async def test_superuser_updates_all_matching_spots(
    db_client: AsyncClient, db_session: AsyncSession
):
    superuser = await _make_staff(db_session, "su-all")
    token = create_access_token(superuser.uid)
    spot1 = await _make_spot(db_session, "일괄1", pipeline_status="RAW")
    spot2 = await _make_spot(db_session, "일괄2", pipeline_status="CURATED")

    response = await db_client.patch(
        "/v1/internal/spots/bulk-status",
        json={"uids": [spot1.uid, spot2.uid], "pipeline_status": "PUBLISHED"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body["succeeded"]) == {spot1.uid, spot2.uid}
    assert body["failed"] == []

    await db_session.refresh(spot1)
    await db_session.refresh(spot2)
    assert spot1.pipeline_status == "PUBLISHED"
    assert spot2.pipeline_status == "PUBLISHED"


async def test_superuser_partial_success_reports_missing_uids(
    db_client: AsyncClient, db_session: AsyncSession
):
    superuser = await _make_staff(db_session, "su-partial")
    token = create_access_token(superuser.uid)
    spot = await _make_spot(db_session, "일괄3", pipeline_status="RAW")

    response = await db_client.patch(
        "/v1/internal/spots/bulk-status",
        json={
            "uids": [spot.uid, "nonexistent-uid"],
            "pipeline_status": "PUBLISHED",
        },
        headers=bearer(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] == [spot.uid]
    assert body["failed"] == ["nonexistent-uid"]


async def test_superuser_bulk_status_records_audit_changed_by(
    db_client: AsyncClient, db_session: AsyncSession
):
    """VAC-2 AC: bulk 상태 변경도 audit_log에 changed_by/before-after가 남아야 한다."""
    superuser = await _make_staff(db_session, "su-audit")
    token = create_access_token(superuser.uid)
    spot = await _make_spot(db_session, "일괄감사", pipeline_status="RAW")

    response = await db_client.patch(
        "/v1/internal/spots/bulk-status",
        json={"uids": [spot.uid], "pipeline_status": "ENRICHED"},
        headers=bearer(token),
    )
    assert response.status_code == 200

    history = await db_client.get(
        f"/v1/internal/spots/{spot.uid}/history", headers=bearer(token)
    )
    assert history.status_code == 200
    entries = history.json()

    update = entries[0]
    assert update["changed_by"] == superuser.uid
    assert update["changes"]["pipeline_status"] == {
        "before": "RAW",
        "after": "ENRICHED",
    }
