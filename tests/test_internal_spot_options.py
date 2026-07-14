import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.security import create_access_token
from vivacapi.models.spot import Spot
from vivacapi.models.spot_field_option import SpotFieldOption
from vivacapi.models.user import StaffRole
from tests.helpers import bearer, make_user

ALL_FIELDS = ["category", "amenities", "nearby_facilities", "has_equipment_rental"]


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


async def _make_option(
    db: AsyncSession, field: str, code: str, label_ko: str
) -> SpotFieldOption:
    option = SpotFieldOption(field=field, code=code, label_ko=label_ko)
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
# GET /v1/internal/spot-options — list
# ---------------------------------------------------------------------------


async def test_list_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.get("/v1/internal/spot-options?field=category")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_list_returns_options_sorted_by_code_and_scoped_to_field(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "list1")
    token = create_access_token(staff.uid)
    await _make_option(db_session, "category", "GLAMPING", "글램핑")
    await _make_option(db_session, "category", "CAR_CAMPING", "차박")
    # 다른 필드 데이터가 섞여 나오지 않는지 확인
    await _make_option(db_session, "amenities", "WIFI", "와이파이")

    response = await db_client.get(
        "/v1/internal/spot-options?field=category", headers=bearer(token)
    )

    assert response.status_code == 200
    codes = [item["code"] for item in response.json()]
    assert codes == ["CAR_CAMPING", "GLAMPING"]


async def test_list_invalid_field_returns_422(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "list2")
    token = create_access_token(staff.uid)

    response = await db_client.get(
        "/v1/internal/spot-options?field=not_a_real_field", headers=bearer(token)
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /v1/internal/spot-options — create
# ---------------------------------------------------------------------------


async def test_create_option_as_manager_succeeds(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "create1", role=StaffRole.MANAGER)
    token = create_access_token(staff.uid)

    response = await db_client.post(
        "/v1/internal/spot-options",
        json={"field": "category", "code": "NATIONAL_PARK", "label_ko": "국립공원"},
        headers=bearer(token),
    )

    assert response.status_code == 201
    assert response.json() == {
        "field": "category",
        "code": "NATIONAL_PARK",
        "label_ko": "국립공원",
    }


async def test_create_option_forbidden_for_staff_role(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "create2", role=StaffRole.STAFF)
    token = create_access_token(staff.uid)

    response = await db_client.post(
        "/v1/internal/spot-options",
        json={"field": "category", "code": "NATIONAL_PARK", "label_ko": "국립공원"},
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_create_option_duplicate_returns_409(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "create3", role=StaffRole.MANAGER)
    token = create_access_token(staff.uid)
    await _make_option(db_session, "category", "GLAMPING", "글램핑")

    response = await db_client.post(
        "/v1/internal/spot-options",
        json={"field": "category", "code": "GLAMPING", "label_ko": "다른 이름"},
        headers=bearer(token),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SPOT_OPTION_ALREADY_EXISTS"


async def test_create_option_same_code_different_field_both_allowed(
    db_client: AsyncClient, db_session: AsyncSession
):
    """같은 code가 다른 field에서는 중복으로 취급되지 않는다 (복합 PK 확인)."""
    staff = await _make_staff(db_session, "create4", role=StaffRole.MANAGER)
    token = create_access_token(staff.uid)
    await _make_option(db_session, "category", "OTHER", "기타")

    response = await db_client.post(
        "/v1/internal/spot-options",
        json={"field": "amenities", "code": "OTHER", "label_ko": "기타"},
        headers=bearer(token),
    )

    assert response.status_code == 201


# ---------------------------------------------------------------------------
# DELETE /v1/internal/spot-options/{field}/{code} — delete + cascade (필드별)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ALL_FIELDS)
async def test_delete_option_removes_it_and_cascades_into_spots(
    db_client: AsyncClient, db_session: AsyncSession, field: str
):
    staff = await _make_staff(db_session, f"delete-{field}", role=StaffRole.MANAGER)
    token = create_access_token(staff.uid)
    await _make_option(db_session, field, "TARGET", "대상")
    spot_with = await _make_spot(db_session, "With", **{field: ["TARGET", "KEEP"]})
    spot_without = await _make_spot(db_session, "Without", **{field: ["KEEP"]})

    response = await db_client.delete(
        f"/v1/internal/spot-options/{field}/TARGET", headers=bearer(token)
    )

    assert response.status_code == 204

    remaining = await db_session.execute(
        select(SpotFieldOption).where(
            SpotFieldOption.field == field, SpotFieldOption.code == "TARGET"
        )
    )
    assert remaining.scalar_one_or_none() is None

    await db_session.refresh(spot_with)
    await db_session.refresh(spot_without)
    assert getattr(spot_with, field) == ["KEEP"]
    assert getattr(spot_without, field) == ["KEEP"]


async def test_delete_option_not_found_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "delete-404", role=StaffRole.MANAGER)
    token = create_access_token(staff.uid)

    response = await db_client.delete(
        "/v1/internal/spot-options/category/NONEXISTENT", headers=bearer(token)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SPOT_OPTION_NOT_FOUND"


async def test_delete_option_forbidden_for_staff_role(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "delete-403", role=StaffRole.STAFF)
    token = create_access_token(staff.uid)
    await _make_option(db_session, "category", "GLAMPING", "글램핑")

    response = await db_client.delete(
        "/v1/internal/spot-options/category/GLAMPING", headers=bearer(token)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_delete_option_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.delete("/v1/internal/spot-options/category/GLAMPING")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
