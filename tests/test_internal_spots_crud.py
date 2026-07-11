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


async def _make_spot(db: AsyncSession, title: str, **kwargs):
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
# GET /v1/internal/spots — list
# ---------------------------------------------------------------------------


async def test_list_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.get("/v1/internal/spots")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_list_returns_items_with_total_count_header(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "list")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Alpha", region_province="강원")
    await _make_spot(db_session, "Bravo", region_province="경기")

    response = await db_client.get("/v1/internal/spots", headers=bearer(token))

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "2"
    body = response.json()
    assert {item["title"] for item in body} == {"Alpha", "Bravo"}
    assert set(body[0].keys()) == {
        "uid",
        "title",
        "source",
        "region_province",
        "region_city",
        "rating_avg",
        "review_count",
        "pipeline_status",
        "trust_tier",
        "updated_at",
    }


async def test_list_title_filter(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "filter")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "남이섬 캠핑장")
    await _make_spot(db_session, "설악산 야영장")

    response = await db_client.get(
        "/v1/internal/spots",
        params={"title_like": "남이섬"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "1"
    assert [item["title"] for item in response.json()] == ["남이섬 캠핑장"]


async def test_list_region_province_filter(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "region")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Alpha", region_province="강원")
    await _make_spot(db_session, "Bravo", region_province="강원")
    await _make_spot(db_session, "Charlie", region_province="경기")

    response = await db_client.get(
        "/v1/internal/spots",
        params={"region_province": "강원"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "2"
    assert {item["title"] for item in response.json()} == {"Alpha", "Bravo"}


async def test_list_source_filter(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "source")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Alpha", source="src1")
    await _make_spot(db_session, "Bravo", source="src2")

    response = await db_client.get(
        "/v1/internal/spots",
        params={"source": "src1"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "1"
    assert [item["title"] for item in response.json()] == ["Alpha"]


async def test_list_combined_filters_are_anded(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "combined")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Match", region_province="강원", source="src1")
    await _make_spot(db_session, "WrongSrc", region_province="강원", source="src2")
    await _make_spot(db_session, "WrongRegion", region_province="경기", source="src1")

    response = await db_client.get(
        "/v1/internal/spots",
        params={"region_province": "강원", "source": "src1"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "1"
    assert [item["title"] for item in response.json()] == ["Match"]


async def test_distinct_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.get("/v1/internal/spots/distinct/region_province")
    assert response.status_code == 401


async def test_distinct_returns_distinct_sorted(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "distinct")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Alpha", region_province="경기")
    await _make_spot(db_session, "Bravo", region_province="강원")
    await _make_spot(db_session, "Charlie", region_province="강원")
    await _make_spot(db_session, "Delta", region_province=None)

    response = await db_client.get(
        "/v1/internal/spots/distinct/region_province", headers=bearer(token)
    )

    assert response.status_code == 200
    assert response.json() == ["강원", "경기"]


async def test_distinct_source_field(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "distinct-src")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Alpha", source="src2")
    await _make_spot(db_session, "Bravo", source="src1")
    await _make_spot(db_session, "Charlie", source="src1")

    response = await db_client.get(
        "/v1/internal/spots/distinct/source", headers=bearer(token)
    )

    assert response.status_code == 200
    assert response.json() == ["src1", "src2"]


async def test_distinct_rejects_non_whitelisted_field(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "distinct-bad")
    token = create_access_token(staff.uid)

    response = await db_client.get(
        "/v1/internal/spots/distinct/phone", headers=bearer(token)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_list_pagination_slices_with_full_total(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "page")
    token = create_access_token(staff.uid)
    for i in range(5):
        await _make_spot(db_session, f"Spot {i}")

    response = await db_client.get(
        "/v1/internal/spots",
        params={"_start": 0, "_end": 2, "_sort": "title", "_order": "asc"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "5"
    body = response.json()
    assert [item["title"] for item in body] == ["Spot 0", "Spot 1"]


# ---------------------------------------------------------------------------
# GET /v1/internal/spots/{uid} — detail
# ---------------------------------------------------------------------------


async def test_get_one_returns_detail(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "detail")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session, "Detail Spot", address="서울시")

    response = await db_client.get(
        f"/v1/internal/spots/{spot.uid}", headers=bearer(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["uid"] == spot.uid
    assert body["title"] == "Detail Spot"
    assert body["address"] == "서울시"


async def test_get_one_not_found_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "detail404")
    token = create_access_token(staff.uid)

    response = await db_client.get(
        "/v1/internal/spots/nonexistent", headers=bearer(token)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SPOT_NOT_FOUND"


# ---------------------------------------------------------------------------
# PATCH /v1/internal/spots/{uid} — update
# ---------------------------------------------------------------------------


async def test_patch_updates_only_provided_fields(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "patch")
    token = create_access_token(staff.uid)
    spot = await _make_spot(
        db_session, "Old Title", address="old", tagline="keep me"
    )

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"title": "New Title", "address": "new"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New Title"
    assert body["address"] == "new"
    assert body["tagline"] == "keep me"


async def test_patch_not_found_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "patch404")
    token = create_access_token(staff.uid)

    response = await db_client.patch(
        "/v1/internal/spots/nonexistent",
        json={"title": "X"},
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SPOT_NOT_FOUND"


async def test_patch_updates_pipeline_status_and_trust_tier(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "pipeline")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session, "검수 대상")

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"pipeline_status": "REVIEWED", "trust_tier": 2},
        headers=bearer(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pipeline_status"] == "REVIEWED"
    assert body["trust_tier"] == 2


async def test_patch_rejects_invalid_pipeline_status(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "badstatus")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session, "검수 대상2")

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"pipeline_status": "DELETED"},
        headers=bearer(token),
    )
    assert response.status_code == 422


async def test_patch_rejects_out_of_range_trust_tier(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "badtier")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session, "검수 대상3")

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"trust_tier": 4},
        headers=bearer(token),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /v1/internal/spots/stats — 대시보드 통계
# ---------------------------------------------------------------------------


async def test_stats_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.get("/v1/internal/spots/stats")
    assert response.status_code == 401


async def test_stats_returns_aggregates(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "stats")
    token = create_access_token(staff.uid)
    a = await _make_spot(
        db_session, "A", source="src1", region_province="강원",
        latitude=1.0, longitude=2.0,
    )
    await _make_spot(db_session, "B", source="src1", region_province="경기")
    await _make_spot(
        db_session, "C", source="src2", region_province="강원",
        latitude=1.0, longitude=2.0,
    )
    db_session.add(SpotBusinessInfo(spot_uid=a.uid))
    await db_session.commit()

    response = await db_client.get(
        "/v1/internal/spots/stats", headers=bearer(token)
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["business_info_total"] == 1
    assert data["missing_coordinates"] == 1  # B는 좌표 없음
    assert {i["key"]: i["count"] for i in data["by_source"]} == {
        "src1": 2,
        "src2": 1,
    }
    assert data["by_source"][0]["count"] >= data["by_source"][-1]["count"]
    assert {i["key"]: i["count"] for i in data["by_region_province"]} == {
        "강원": 2,
        "경기": 1,
    }
