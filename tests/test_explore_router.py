from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.errors import ErrorCode
from vivacapi.models.spot import Spot


# ---------------------------------------------------------------------------
# GET /v1/explore/spots — list
# ---------------------------------------------------------------------------


async def test_list_spots_returns_empty_cursor_shape(
    db_client: AsyncClient,
):
    response = await db_client.get("/v1/explore/spots")
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "next_cursor": None,
        "has_more": False,
    }


async def test_list_spots_accepts_cursor_and_limit(db_client: AsyncClient):
    response = await db_client.get(
        "/v1/explore/spots",
        params={"cursor": "someuid123456789ABCDE", "limit": 5},
    )
    assert response.status_code == 200


async def test_list_spots_rejects_limit_above_max(client: AsyncClient):
    response = await client.get("/v1/explore/spots", params={"limit": 51})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
    assert any(d["loc"] == ["query", "limit"] for d in body["error"]["details"])


async def test_list_spots_rejects_limit_below_min(client: AsyncClient):
    response = await client.get("/v1/explore/spots", params={"limit": 0})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR.value


# ---------------------------------------------------------------------------
# GET /v1/explore/spots/{uid} — detail
# ---------------------------------------------------------------------------


async def test_get_spot_returns_404_for_unknown_uid(
    db_client: AsyncClient, db_session: AsyncSession
):
    response = await db_client.get("/v1/explore/spots/nonexistent123456789AB")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": ErrorCode.SPOT_NOT_FOUND.value,
            "message": "Spot not found",
            "details": None,
        }
    }


# ---------------------------------------------------------------------------
# pipeline_status 노출 정책 — PUBLISHED만 공개
# ---------------------------------------------------------------------------


async def _make_spot(db: AsyncSession, title: str, **kwargs):
    spot = Spot(title=title, rating_avg=0.0, review_count=0, **kwargs)
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


async def test_list_spots_returns_only_published(
    db_client: AsyncClient, db_session: AsyncSession
):
    published = await _make_spot(
        db_session, "공개 스팟", pipeline_status="PUBLISHED", trust_tier=3
    )
    await _make_spot(db_session, "검수중 스팟", pipeline_status="CURATED")

    response = await db_client.get("/v1/explore/spots")
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["uid"] for item in items] == [published.uid]
    assert items[0]["trust_tier"] == 3


async def test_get_spot_returns_404_for_unpublished(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(db_session, "원천 스팟", pipeline_status="RAW")

    response = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == ErrorCode.SPOT_NOT_FOUND.value


async def test_get_spot_exposes_trust_tier(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(
        db_session, "공식 스팟", pipeline_status="PUBLISHED", trust_tier=1
    )

    response = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert response.status_code == 200
    assert response.json()["trust_tier"] == 1


# ---------------------------------------------------------------------------
# GET /v1/explore/spots/{uid}/images
# ---------------------------------------------------------------------------


async def test_list_spot_images_returns_404_for_unpublished(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(db_session, "검수중 스팟", pipeline_status="CURATED")

    response = await db_client.get(f"/v1/explore/spots/{spot.uid}/images")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == ErrorCode.SPOT_NOT_FOUND.value
