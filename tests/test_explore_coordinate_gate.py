"""§3 좌표 없는 스팟의 explore 노출 제외 (EXPLORE_REQUIRE_COORDINATES).

플래그 OFF가 기본이라 "켰을 때"만 검증하면 롤아웃 전 회귀를 못 잡는다 —
양쪽 상태를 모두 덮는다.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.config import settings
from vivacapi.core.errors import ErrorCode
from vivacapi.crud import spot as crud_spot
from vivacapi.models.spot import Spot


@pytest.fixture
def require_coordinates(monkeypatch):
    monkeypatch.setattr(settings, "EXPLORE_REQUIRE_COORDINATES", True)


async def _make_spot(db: AsyncSession, title: str, **kwargs) -> Spot:
    kwargs.setdefault("rating_avg", 0.0)
    kwargs.setdefault("review_count", 0)
    kwargs.setdefault("pipeline_status", "PUBLISHED")
    spot = Spot(title=title, **kwargs)
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


# ---------------------------------------------------------------------------
# 기본값(OFF) — 롤아웃 전 동작 유지
# ---------------------------------------------------------------------------


async def test_flag_defaults_off(db_client: AsyncClient, db_session: AsyncSession):
    spot = await _make_spot(db_session, "좌표 없는 스팟")

    listed = await db_client.get("/v1/explore/spots")
    assert [item["uid"] for item in listed.json()["items"]] == [spot.uid]
    assert listed.json()["items"][0]["latitude"] is None

    detail = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert detail.status_code == 200


# ---------------------------------------------------------------------------
# ON — 목록/검색/상세 전부에서 제외
# ---------------------------------------------------------------------------


async def test_list_excludes_spots_without_coordinates(
    db_client: AsyncClient, db_session: AsyncSession, require_coordinates
):
    await _make_spot(db_session, "좌표 없는 스팟")
    located = await _make_spot(
        db_session, "좌표 있는 스팟", latitude=37.79, longitude=127.52
    )

    body = (await db_client.get("/v1/explore/spots")).json()
    assert [item["uid"] for item in body["items"]] == [located.uid]
    assert body["total"] == 1


async def test_search_excludes_spots_without_coordinates(
    db_client: AsyncClient, db_session: AsyncSession, require_coordinates
):
    await _make_spot(db_session, "좌표 없는 캠핑장")
    located = await _make_spot(
        db_session, "좌표 있는 캠핑장", latitude=37.79, longitude=127.52
    )

    body = (await db_client.get("/v1/explore/spots", params={"q": "캠핑장"})).json()
    assert [item["uid"] for item in body["items"]] == [located.uid]


async def test_detail_returns_404_for_spot_without_coordinates(
    db_client: AsyncClient, db_session: AsyncSession, require_coordinates
):
    """목록에서만 빼면 북마크/공유된 URL이 계속 열려 검색으로 못 찾는 페이지가 남는다."""
    spot = await _make_spot(db_session, "좌표 없는 스팟")

    response = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == ErrorCode.SPOT_NOT_FOUND.value


async def test_images_return_404_for_spot_without_coordinates(
    db_client: AsyncClient, db_session: AsyncSession, require_coordinates
):
    spot = await _make_spot(db_session, "좌표 없는 스팟")

    response = await db_client.get(f"/v1/explore/spots/{spot.uid}/images")
    assert response.status_code == 404


async def test_admin_lookup_still_sees_spot_without_coordinates(
    db_session: AsyncSession, require_coordinates
):
    """플래그는 공개 경로(published_only=True) 전용 — 어드민 조회는 영향받지 않는다."""
    spot = await _make_spot(db_session, "좌표 없는 스팟")

    assert await crud_spot.get_spot_by_uid(db_session, spot.uid) is not None
    assert (
        await crud_spot.get_spot_by_uid(db_session, spot.uid, published_only=True)
        is None
    )
