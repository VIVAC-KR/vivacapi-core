from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.security import create_access_token
from vivacapi.models.spot import Spot
from vivacapi.models.spot_business_info import SpotBusinessInfo
from tests.helpers import bearer, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_staff(db: AsyncSession, suffix: str):
    user = await make_user(
        db, email=f"staff-{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    user.is_staff = True
    await db.commit()
    return user


async def _make_spot(db: AsyncSession, title: str = "Spot") -> Spot:
    spot = Spot(title=title, rating_avg=0.0, review_count=0)
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


async def _make_info(db: AsyncSession, spot_uid: str, **kwargs) -> SpotBusinessInfo:
    info = SpotBusinessInfo(spot_uid=spot_uid, **kwargs)
    db.add(info)
    await db.commit()
    await db.refresh(info)
    return info


# ---------------------------------------------------------------------------
# GET /v1/internal/spot-business-info — list
# ---------------------------------------------------------------------------


async def test_list_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.get("/v1/internal/spot-business-info")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_list_filters_by_spot_uid(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "bi-list")
    token = create_access_token(staff.uid)
    spot_a = await _make_spot(db_session, "A")
    spot_b = await _make_spot(db_session, "B")
    await _make_info(db_session, spot_a.uid, business_type="국립공원")
    await _make_info(db_session, spot_b.uid, business_type="민간")

    response = await db_client.get(
        "/v1/internal/spot-business-info",
        params={"spot_uid": spot_a.uid},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "1"
    body = response.json()
    assert len(body) == 1
    assert body[0]["spot_uid"] == spot_a.uid
    assert body[0]["business_type"] == "국립공원"


async def test_list_rejects_non_whitelisted_sort(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "bi-bad-sort")
    token = create_access_token(staff.uid)

    response = await db_client.get(
        "/v1/internal/spot-business-info",
        params={"_sort": "business_reg_no"},
        headers=bearer(token),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# GET /{uid} — detail
# ---------------------------------------------------------------------------


async def test_get_one_returns_detail(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "bi-detail")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session)
    info = await _make_info(
        db_session, spot.uid, business_reg_no="123-45-67890"
    )

    response = await db_client.get(
        f"/v1/internal/spot-business-info/{info.uid}", headers=bearer(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["uid"] == info.uid
    assert body["spot_uid"] == spot.uid
    assert body["business_reg_no"] == "123-45-67890"


async def test_get_one_not_found_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "bi-404")
    token = create_access_token(staff.uid)

    response = await db_client.get(
        "/v1/internal/spot-business-info/nonexistent", headers=bearer(token)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SPOT_BUSINESS_INFO_NOT_FOUND"


# ---------------------------------------------------------------------------
# PATCH /{uid} — update
# ---------------------------------------------------------------------------


async def test_patch_updates_only_provided_fields(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "bi-patch")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session)
    info = await _make_info(
        db_session,
        spot.uid,
        operating_status="운영중",
        operating_agency="keep me",
    )

    response = await db_client.patch(
        f"/v1/internal/spot-business-info/{info.uid}",
        json={"operating_status": "휴업"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["operating_status"] == "휴업"
    assert body["operating_agency"] == "keep me"


async def test_patch_not_found_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "bi-patch404")
    token = create_access_token(staff.uid)

    response = await db_client.patch(
        "/v1/internal/spot-business-info/nonexistent",
        json={"operating_status": "휴업"},
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SPOT_BUSINESS_INFO_NOT_FOUND"
