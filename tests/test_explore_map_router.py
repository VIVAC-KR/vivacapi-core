from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.errors import ErrorCode
from vivacapi.models.spot import Spot

# 실좌표 근사 (WGS84): 춘천 남이섬 부근 / 제주 서귀포 부근
_CHUNCHEON = (37.7907, 127.5262)
_JEJU = (33.2541, 126.5601)
# 춘천은 포함하고 제주는 제외하는 bbox (min_lng,min_lat,max_lng,max_lat)
_BBOX_CHUNCHEON = "127.0,37.0,128.0,38.0"


async def _make_spot(db: AsyncSession, title: str, **kwargs) -> Spot:
    kwargs.setdefault("rating_avg", 0.0)
    kwargs.setdefault("review_count", 0)
    spot = Spot(title=title, **kwargs)
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


async def _make_located(db: AsyncSession, title: str, point, **kwargs) -> Spot:
    lat, lng = point
    return await _make_spot(db, title, latitude=lat, longitude=lng, **kwargs)


# ---------------------------------------------------------------------------
# bbox 파싱 — 잘못된 입력이 조용히 빈 결과가 되지 않아야 한다
# ---------------------------------------------------------------------------


async def test_bbox_rejects_wrong_arity(db_client: AsyncClient):
    response = await db_client.get(
        "/v1/explore/spots", params={"bbox": "127.0,37.0,128.0"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR.value


async def test_bbox_rejects_non_numeric(db_client: AsyncClient):
    response = await db_client.get(
        "/v1/explore/spots", params={"bbox": "127.0,37.0,128.0,abc"}
    )
    assert response.status_code == 422


async def test_bbox_rejects_swapped_lat_lng_order(db_client: AsyncClient):
    """lat,lng 순서로 보내면 거부된다 — 빈 결과로 조용히 넘기지 않는다.

    검증이 없으면 이 실수는 에러 없이 0건만 돌려주므로 발견이 늦다. 한국의
    경도(124~132)는 위도 범위(-90~90)를 벗어나므로 순서를 바꾼 순간 걸린다.
    """
    response = await db_client.get(
        "/v1/explore/spots", params={"bbox": "37.0,127.0,38.0,128.0"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR.value


async def test_bbox_rejects_out_of_range_latitude(db_client: AsyncClient):
    response = await db_client.get(
        "/v1/explore/spots", params={"bbox": "127.0,-91.0,128.0,38.0"}
    )
    assert response.status_code == 422


async def test_bbox_rejects_inverted_box(db_client: AsyncClient):
    response = await db_client.get(
        "/v1/explore/spots", params={"bbox": "128.0,37.0,127.0,38.0"}
    )
    assert response.status_code == 422
    assert "lng,lat" in response.json()["error"]["message"]


# ---------------------------------------------------------------------------
# GET /v1/explore/spots — bbox 필터
# ---------------------------------------------------------------------------


async def test_list_filters_by_bbox(db_client: AsyncClient, db_session: AsyncSession):
    inside = await _make_located(db_session, "춘천 캠핑장", _CHUNCHEON)
    await _make_located(db_session, "제주 캠핑장", _JEJU)

    response = await db_client.get(
        "/v1/explore/spots", params={"bbox": _BBOX_CHUNCHEON}
    )
    assert response.status_code == 200
    assert [item["uid"] for item in response.json()["items"]] == [inside.uid]


async def test_list_bbox_excludes_spots_without_coordinates(
    db_client: AsyncClient, db_session: AsyncSession
):
    """좌표가 NULL이면 BETWEEN이 false — bbox 조회에서는 자동으로 빠진다."""
    await _make_spot(db_session, "좌표 없는 스팟")

    response = await db_client.get(
        "/v1/explore/spots", params={"bbox": _BBOX_CHUNCHEON}
    )
    assert response.json()["items"] == []


async def test_list_bbox_and_q_combine_as_and(
    db_client: AsyncClient, db_session: AsyncSession
):
    match = await _make_located(db_session, "춘천 글램핑장", _CHUNCHEON)
    await _make_located(db_session, "춘천 무관 스팟", _CHUNCHEON)
    await _make_located(db_session, "제주 글램핑장", _JEJU)

    response = await db_client.get(
        "/v1/explore/spots", params={"q": "글램핑장", "bbox": _BBOX_CHUNCHEON}
    )
    assert [item["uid"] for item in response.json()["items"]] == [match.uid]


async def test_list_bbox_and_category_combine_as_and(
    db_client: AsyncClient, db_session: AsyncSession
):
    match = await _make_located(
        db_session, "춘천 글램핑", _CHUNCHEON, category=["GLAMPING"]
    )
    await _make_located(
        db_session, "춘천 오토캠핑", _CHUNCHEON, category=["AUTO_CAMPING"]
    )
    await _make_located(db_session, "제주 글램핑", _JEJU, category=["GLAMPING"])

    response = await db_client.get(
        "/v1/explore/spots",
        params={"bbox": _BBOX_CHUNCHEON, "category": "GLAMPING"},
    )
    assert [item["uid"] for item in response.json()["items"]] == [match.uid]


async def test_list_items_expose_coordinates(
    db_client: AsyncClient, db_session: AsyncSession
):
    await _make_located(db_session, "좌표 노출 스팟", _CHUNCHEON)

    item = (await db_client.get("/v1/explore/spots")).json()["items"][0]
    assert (item["latitude"], item["longitude"]) == _CHUNCHEON


# ---------------------------------------------------------------------------
# 커서 스코프 검증 (§7)
# ---------------------------------------------------------------------------


async def test_cursor_from_other_bbox_is_rejected(
    db_client: AsyncClient, db_session: AsyncSession
):
    for i in range(3):
        await _make_located(db_session, f"춘천 스팟 {i}", _CHUNCHEON)

    first = await db_client.get(
        "/v1/explore/spots", params={"bbox": _BBOX_CHUNCHEON, "limit": 1}
    )
    cursor = first.json()["next_cursor"]
    assert cursor is not None

    moved = await db_client.get(
        "/v1/explore/spots",
        params={"bbox": "126.0,33.0,127.0,34.0", "cursor": cursor, "limit": 1},
    )
    assert moved.status_code == 400
    assert moved.json()["error"]["code"] == ErrorCode.CURSOR_SCOPE_MISMATCH.value


async def test_cursor_from_same_bbox_is_accepted(
    db_client: AsyncClient, db_session: AsyncSession
):
    for i in range(3):
        await _make_located(db_session, f"춘천 스팟 {i}", _CHUNCHEON)

    first = await db_client.get(
        "/v1/explore/spots", params={"bbox": _BBOX_CHUNCHEON, "limit": 1}
    )
    cursor = first.json()["next_cursor"]

    second = await db_client.get(
        "/v1/explore/spots",
        params={"bbox": _BBOX_CHUNCHEON, "cursor": cursor, "limit": 1},
    )
    assert second.status_code == 200
    assert second.json()["items"][0]["uid"] != first.json()["items"][0]["uid"]


async def test_bbox_cursor_rejected_when_bbox_dropped(
    db_client: AsyncClient, db_session: AsyncSession
):
    """bbox로 발급한 커서를 bbox 없이 재사용하는 것도 스코프 불일치다."""
    for i in range(3):
        await _make_located(db_session, f"춘천 스팟 {i}", _CHUNCHEON)

    first = await db_client.get(
        "/v1/explore/spots", params={"bbox": _BBOX_CHUNCHEON, "limit": 1}
    )
    response = await db_client.get(
        "/v1/explore/spots",
        params={"cursor": first.json()["next_cursor"], "limit": 1},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == ErrorCode.CURSOR_SCOPE_MISMATCH.value


async def test_search_cursor_from_other_bbox_is_rejected(
    db_client: AsyncClient, db_session: AsyncSession
):
    for i in range(3):
        await _make_located(db_session, f"춘천 캠핑장 {i}", _CHUNCHEON)

    first = await db_client.get(
        "/v1/explore/spots",
        params={"q": "캠핑장", "bbox": _BBOX_CHUNCHEON, "limit": 1},
    )
    cursor = first.json()["next_cursor"]
    assert cursor is not None

    moved = await db_client.get(
        "/v1/explore/spots",
        params={"q": "캠핑장", "bbox": "126.0,33.0,127.0,34.0", "cursor": cursor},
    )
    assert moved.status_code == 400
    assert moved.json()["error"]["code"] == ErrorCode.CURSOR_SCOPE_MISMATCH.value


# ---------------------------------------------------------------------------
# total (§5)
# ---------------------------------------------------------------------------


async def test_total_counts_beyond_current_page(
    db_client: AsyncClient, db_session: AsyncSession
):
    for i in range(3):
        await _make_located(db_session, f"춘천 스팟 {i}", _CHUNCHEON)

    body = (await db_client.get("/v1/explore/spots", params={"limit": 1})).json()
    assert len(body["items"]) == 1
    assert body["total"] == 3
    assert body["total_capped"] is False


async def test_total_respects_filters(db_client: AsyncClient, db_session: AsyncSession):
    await _make_located(db_session, "춘천 스팟", _CHUNCHEON)
    await _make_located(db_session, "제주 스팟", _JEJU)

    body = (
        await db_client.get("/v1/explore/spots", params={"bbox": _BBOX_CHUNCHEON})
    ).json()
    assert body["total"] == 1


async def test_total_is_capped(
    db_client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr("vivacapi.crud.spot.TOTAL_CAP", 2)
    for i in range(3):
        await _make_located(db_session, f"춘천 스팟 {i}", _CHUNCHEON)

    body = (await db_client.get("/v1/explore/spots")).json()
    assert body["total"] == 2
    assert body["total_capped"] is True


# ---------------------------------------------------------------------------
# GET /v1/explore/spots/map (§6)
# ---------------------------------------------------------------------------


async def test_map_returns_lightweight_items(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_located(db_session, "춘천 캠핑장", _CHUNCHEON, trust_tier=2)

    response = await db_client.get("/v1/explore/spots/map")
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "uid": spot.uid,
                "latitude": _CHUNCHEON[0],
                "longitude": _CHUNCHEON[1],
                "trust_tier": 2,
            }
        ],
        "truncated": False,
    }


async def test_map_route_is_not_shadowed_by_detail_route(db_client: AsyncClient):
    """/spots/map이 /spots/{uid}에 먹히면 404 SPOT_NOT_FOUND가 온다."""
    response = await db_client.get("/v1/explore/spots/map")
    assert response.status_code == 200
    assert "items" in response.json()


async def test_map_always_excludes_spots_without_coordinates(
    db_client: AsyncClient, db_session: AsyncSession
):
    """EXPLORE_REQUIRE_COORDINATES가 꺼져 있어도 지도 응답에는 좌표 없는 핀이 없다."""
    await _make_spot(db_session, "좌표 없는 스팟")
    located = await _make_located(db_session, "춘천 스팟", _CHUNCHEON)

    body = (await db_client.get("/v1/explore/spots/map")).json()
    assert [item["uid"] for item in body["items"]] == [located.uid]


async def test_map_filters_by_bbox_and_q(
    db_client: AsyncClient, db_session: AsyncSession
):
    match = await _make_located(db_session, "춘천 글램핑장", _CHUNCHEON)
    await _make_located(db_session, "제주 글램핑장", _JEJU)
    await _make_located(db_session, "춘천 무관 스팟", _CHUNCHEON)

    body = (
        await db_client.get(
            "/v1/explore/spots/map",
            params={"q": "글램핑장", "bbox": _BBOX_CHUNCHEON},
        )
    ).json()
    assert [item["uid"] for item in body["items"]] == [match.uid]


async def test_map_reports_truncation(db_client: AsyncClient, db_session: AsyncSession):
    for i in range(3):
        await _make_located(db_session, f"춘천 스팟 {i}", _CHUNCHEON)

    body = (await db_client.get("/v1/explore/spots/map", params={"limit": 2})).json()
    assert len(body["items"]) == 2
    assert body["truncated"] is True


async def test_map_rejects_limit_above_max(client: AsyncClient):
    response = await client.get("/v1/explore/spots/map", params={"limit": 8001})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR.value


async def test_map_allows_full_scale_limit(db_client: AsyncClient):
    """전국 줌아웃 시 전체(8000건 규모)를 한 번에 받을 수 있어야 한다."""
    response = await db_client.get("/v1/explore/spots/map", params={"limit": 8000})
    assert response.status_code == 200
