from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode


# ---------------------------------------------------------------------------
# GET /v1/explore/spots — list
# ---------------------------------------------------------------------------


async def test_list_spots_returns_empty_page_shape(
    db_client: AsyncClient,
):
    response = await db_client.get("/v1/explore/spots")
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "page": 1,
        "total_pages": 0,
        "total": 0,
    }


async def test_list_spots_accepts_page_and_limit(db_client: AsyncClient):
    response = await db_client.get(
        "/v1/explore/spots",
        params={"page": 1, "limit": 5},
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


async def test_list_spots_rejects_page_below_min(client: AsyncClient):
    response = await client.get("/v1/explore/spots", params={"page": 0})
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
