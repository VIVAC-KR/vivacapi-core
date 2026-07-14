from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.security import create_access_token
from vivacapi.models.spot import Spot
from vivacapi.models.spot_category import SpotCategoryOption
from vivacapi.models.user import StaffRole
from tests.helpers import bearer, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_staff(
    db: AsyncSession, suffix: str, role: StaffRole = StaffRole.STAFF
):
    user = await make_user(
        db, email=f"staff-{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    user.is_staff = True
    user.staff_role = role
    await db.commit()
    return user


async def _make_category(db: AsyncSession, code: str, label_ko: str) -> SpotCategoryOption:
    option = SpotCategoryOption(code=code, label_ko=label_ko)
    db.add(option)
    await db.commit()
    return option


async def _make_spot(db: AsyncSession, title: str, **kwargs) -> Spot:
    spot = Spot(title=title, rating_avg=0.0, review_count=0, **kwargs)
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


# ---------------------------------------------------------------------------
# GET /v1/internal/categories — list
# ---------------------------------------------------------------------------


async def test_list_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.get("/v1/internal/categories")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_list_returns_options_sorted_by_code(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "list1")
    token = create_access_token(staff.uid)
    await _make_category(db_session, "GLAMPING", "글램핑")
    await _make_category(db_session, "CAR_CAMPING", "차박")

    response = await db_client.get("/v1/internal/categories", headers=bearer(token))

    assert response.status_code == 200
    codes = [item["code"] for item in response.json()]
    assert codes == ["CAR_CAMPING", "GLAMPING"]


# ---------------------------------------------------------------------------
# POST /v1/internal/categories — create
# ---------------------------------------------------------------------------


async def test_create_category_as_manager_succeeds(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "create1", role=StaffRole.MANAGER)
    token = create_access_token(staff.uid)

    response = await db_client.post(
        "/v1/internal/categories",
        json={"code": "NATIONAL_PARK", "label_ko": "국립공원"},
        headers=bearer(token),
    )

    assert response.status_code == 201
    assert response.json() == {"code": "NATIONAL_PARK", "label_ko": "국립공원"}


async def test_create_category_forbidden_for_staff_role(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "create2", role=StaffRole.STAFF)
    token = create_access_token(staff.uid)

    response = await db_client.post(
        "/v1/internal/categories",
        json={"code": "NATIONAL_PARK", "label_ko": "국립공원"},
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_create_category_duplicate_code_returns_409(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "create3", role=StaffRole.MANAGER)
    token = create_access_token(staff.uid)
    await _make_category(db_session, "GLAMPING", "글램핑")

    response = await db_client.post(
        "/v1/internal/categories",
        json={"code": "GLAMPING", "label_ko": "다른 이름"},
        headers=bearer(token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CATEGORY_ALREADY_EXISTS"


# ---------------------------------------------------------------------------
# DELETE /v1/internal/categories/{code} — delete + cascade
# ---------------------------------------------------------------------------


async def test_delete_category_as_manager_removes_it_and_cascades_into_spots(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "delete1", role=StaffRole.MANAGER)
    token = create_access_token(staff.uid)
    await _make_category(db_session, "GLAMPING", "글램핑")
    spot_with = await _make_spot(db_session, "With", category=["GLAMPING", "CAR_CAMPING"])
    spot_without = await _make_spot(db_session, "Without", category=["CAR_CAMPING"])

    response = await db_client.delete(
        "/v1/internal/categories/GLAMPING", headers=bearer(token)
    )

    assert response.status_code == 204

    remaining = await db_session.execute(
        select(SpotCategoryOption).where(SpotCategoryOption.code == "GLAMPING")
    )
    assert remaining.scalar_one_or_none() is None

    await db_session.refresh(spot_with)
    await db_session.refresh(spot_without)
    assert spot_with.category == ["CAR_CAMPING"]
    assert spot_without.category == ["CAR_CAMPING"]


async def test_delete_category_not_found_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "delete2", role=StaffRole.MANAGER)
    token = create_access_token(staff.uid)

    response = await db_client.delete(
        "/v1/internal/categories/NONEXISTENT", headers=bearer(token)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CATEGORY_NOT_FOUND"


async def test_delete_category_forbidden_for_staff_role(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "delete3", role=StaffRole.STAFF)
    token = create_access_token(staff.uid)
    await _make_category(db_session, "GLAMPING", "글램핑")

    response = await db_client.delete(
        "/v1/internal/categories/GLAMPING", headers=bearer(token)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_delete_category_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.delete("/v1/internal/categories/GLAMPING")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
