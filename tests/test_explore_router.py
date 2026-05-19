from httpx import AsyncClient

from app.core.errors import ErrorCode


# ---------------------------------------------------------------------------
# GET /v1/explore/spots — list (stub)
# ---------------------------------------------------------------------------


async def test_list_spots_returns_empty_with_cursor_pagination_shape(
    client: AsyncClient,
):
    response = await client.get("/v1/explore/spots")
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "next_cursor": None,
        "has_more": False,
        "total": 0,
    }


async def test_list_spots_accepts_all_query_params(client: AsyncClient):
    response = await client.get(
        "/v1/explore/spots",
        params={"q": "hello", "sort": "latest", "cursor": "abc", "limit": 5},
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


async def test_list_spots_rejects_invalid_sort_enum(client: AsyncClient):
    response = await client.get("/v1/explore/spots", params={"sort": "trending"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
    assert any(d["loc"] == ["query", "sort"] for d in body["error"]["details"])


# ---------------------------------------------------------------------------
# GET /v1/explore/spots/{spot_uid} — detail (stub)
# ---------------------------------------------------------------------------


async def test_get_spot_returns_404_with_spot_not_found_code(client: AsyncClient):
    response = await client.get(
        "/v1/explore/spots/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": ErrorCode.SPOT_NOT_FOUND.value,
            "message": "Spot not found",
            "details": None,
        }
    }


async def test_get_spot_rejects_non_uuid_path(client: AsyncClient):
    response = await client.get("/v1/explore/spots/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
