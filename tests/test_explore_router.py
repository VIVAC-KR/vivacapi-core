from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core import storage
from vivacapi.core.errors import ErrorCode
from vivacapi.models.spot import Spot
from vivacapi.models.spot_image import SpotImage, SpotImageRole


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
# GET /v1/explore/spots?q= — 검색
# ---------------------------------------------------------------------------


async def test_list_spots_with_q_returns_matching_spot(
    db_client: AsyncClient, db_session: AsyncSession
):
    matched = await _make_spot(db_session, "위례 캠핑장", pipeline_status="PUBLISHED")
    await _make_spot(db_session, "무관 스팟", pipeline_status="PUBLISHED")

    response = await db_client.get("/v1/explore/spots", params={"q": "캠핑장"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["uid"] for item in items] == [matched.uid]


async def test_list_spots_with_q_and_category_filter(
    db_client: AsyncClient, db_session: AsyncSession
):
    glamping = await _make_spot(
        db_session,
        "제주 캠핑장",
        pipeline_status="PUBLISHED",
        category=["GLAMPING"],
    )
    await _make_spot(
        db_session,
        "제주 오토캠핑장",
        pipeline_status="PUBLISHED",
        category=["AUTO_CAMPING"],
    )

    response = await db_client.get(
        "/v1/explore/spots", params={"q": "캠핑장", "category": "GLAMPING"}
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["uid"] for item in items] == [glamping.uid]


async def test_list_spots_with_q_rejects_malformed_cursor(db_client: AsyncClient):
    response = await db_client.get(
        "/v1/explore/spots", params={"q": "캠핑장", "cursor": "not-a-valid-cursor"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR.value


async def test_list_spots_without_q_uses_default_cursor_behavior(
    db_client: AsyncClient, db_session: AsyncSession
):
    """q 없으면 기존 uid-cursor 목록 동작 그대로 — 회귀 없음을 확인."""
    spot = await _make_spot(db_session, "검색어 없음 스팟", pipeline_status="PUBLISHED")

    response = await db_client.get("/v1/explore/spots")
    assert response.status_code == 200
    assert response.json()["items"][0]["uid"] == spot.uid


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


async def test_list_spots_exposes_category_and_region_short(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(
        db_session,
        "약칭 스팟",
        pipeline_status="PUBLISHED",
        region_province="경상남도",
        category=["글램핑", "오토캠핑"],
    )

    response = await db_client.get("/v1/explore/spots")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["uid"] == spot.uid
    assert item["region_short"] == "경남"
    assert item["category"] == ["글램핑", "오토캠핑"]
    assert item["thumbnail_url"] is None


async def test_list_spots_unmapped_region_returns_original(
    db_client: AsyncClient, db_session: AsyncSession
):
    await _make_spot(
        db_session,
        "미매핑 지역 스팟",
        pipeline_status="PUBLISHED",
        region_province="해외",
    )

    response = await db_client.get("/v1/explore/spots")
    assert response.status_code == 200
    assert response.json()["items"][0]["region_short"] == "해외"


async def test_list_spots_exposes_thumbnail_url(
    db_client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(
        storage, "resolve_url", lambda key, is_public: f"https://cdn.fake/{key}"
    )
    spot = await _make_spot(db_session, "썸네일 스팟", pipeline_status="PUBLISHED")
    db_session.add(
        SpotImage(
            spot_uid=spot.uid,
            s3_key=f"spots/{spot.uid}/thumb.jpg",
            role=SpotImageRole.THUMBNAIL,
        )
    )
    await db_session.commit()

    response = await db_client.get("/v1/explore/spots")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["thumbnail_url"] == f"https://cdn.fake/spots/{spot.uid}/thumb.jpg"


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


async def test_get_spot_exposes_editable_fields(
    db_client: AsyncClient, db_session: AsyncSession
):
    spot = await _make_spot(
        db_session,
        "상세 스팟",
        pipeline_status="PUBLISHED",
        tagline="한줄설명",
        category=["AUTO_CAMPING"],
        themes=["강변"],
        is_fee_required=True,
        is_pet_allowed=False,
        features="우천 시 일부 침수",
        camp_sight_type="데크",
        unit_count=10,
        total_area_m2=500.5,
        fire_pit_type="개별 화로대",
        latitude=37.1,
        longitude=127.1,
        address_detail="1층",
        amenities=["샤워실"],
        nearby_facilities=["편의점"],
        has_equipment_rental=["텐트"],
        phone="033-1234-5678",
        booking_url="https://example.com/booking",
    )

    response = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert response.status_code == 200
    body = response.json()
    assert body["tagline"] == "한줄설명"
    assert body["category"] == ["AUTO_CAMPING"]
    assert body["themes"] == ["강변"]
    assert body["is_fee_required"] is True
    assert body["is_pet_allowed"] is False
    assert body["features"] == "우천 시 일부 침수"
    assert body["camp_sight_type"] == "데크"
    assert body["unit_count"] == 10
    assert body["total_area_m2"] == 500.5
    assert body["fire_pit_type"] == "개별 화로대"
    assert body["latitude"] == 37.1
    assert body["longitude"] == 127.1
    assert body["address_detail"] == "1층"
    assert body["amenities"] == ["샤워실"]
    assert body["nearby_facilities"] == ["편의점"]
    assert body["has_equipment_rental"] == ["텐트"]
    assert body["phone"] == "033-1234-5678"
    assert body["booking_url"] == "https://example.com/booking"
    assert body["rating_avg"] == 0.0
    assert body["review_count"] == 0
    assert body["image_url"] is None


async def test_get_spot_exposes_image_url(
    db_client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(
        storage, "resolve_url", lambda key, is_public: f"https://cdn.fake/{key}"
    )
    spot = await _make_spot(db_session, "이미지 스팟", pipeline_status="PUBLISHED")
    db_session.add(
        SpotImage(
            spot_uid=spot.uid,
            s3_key=f"spots/{spot.uid}/thumb.jpg",
            role=SpotImageRole.THUMBNAIL,
        )
    )
    await db_session.commit()

    response = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert response.status_code == 200
    assert (
        response.json()["image_url"] == f"https://cdn.fake/spots/{spot.uid}/thumb.jpg"
    )


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
