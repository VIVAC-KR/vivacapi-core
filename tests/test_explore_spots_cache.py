from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import make_user
from vivacapi.core import cache
from vivacapi.crud import spot as crud_spot
from vivacapi.crud import spot_review as crud_review
from vivacapi.models.spot import Spot
from vivacapi.workers.spots_bulk import spots_bulk_upsert_handler


@pytest.fixture
async def fake_cache(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache, "_client", fake)
    yield fake
    await fake.aclose()


async def _make_spot(db: AsyncSession, title: str, **kwargs) -> Spot:
    spot = Spot(title=title, rating_avg=0.0, review_count=0, **kwargs)
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


# ---------------------------------------------------------------------------
# 캐시 hit — 두 번째 호출은 crud를 다시 부르지 않는다
# ---------------------------------------------------------------------------


async def test_list_spots_second_call_hits_cache(
    db_client: AsyncClient, db_session: AsyncSession, fake_cache, monkeypatch
):
    await _make_spot(db_session, "캐시 목록 스팟", pipeline_status="PUBLISHED")

    call_count = 0
    original_list_spots = crud_spot.list_spots

    async def counting_list_spots(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await original_list_spots(*args, **kwargs)

    monkeypatch.setattr(crud_spot, "list_spots", counting_list_spots)

    first = await db_client.get("/v1/explore/spots")
    second = await db_client.get("/v1/explore/spots")

    assert first.status_code == 200
    assert second.json() == first.json()
    assert call_count == 1


async def test_get_spot_second_call_hits_cache(
    db_client: AsyncClient, db_session: AsyncSession, fake_cache, monkeypatch
):
    spot = await _make_spot(db_session, "캐시 상세 스팟", pipeline_status="PUBLISHED")

    call_count = 0
    original_get_spot = crud_spot.get_spot_by_uid

    async def counting_get_spot(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await original_get_spot(*args, **kwargs)

    monkeypatch.setattr(crud_spot, "get_spot_by_uid", counting_get_spot)

    first = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    second = await db_client.get(f"/v1/explore/spots/{spot.uid}")

    assert first.status_code == 200
    assert second.json() == first.json()
    assert call_count == 1


# ---------------------------------------------------------------------------
# 무효화 — 데이터 변경 후 stale 응답이 나오면 안 된다
# ---------------------------------------------------------------------------


async def test_spot_update_invalidates_detail_cache(
    db_client: AsyncClient, db_session: AsyncSession, fake_cache
):
    spot = await _make_spot(db_session, "원본 제목", pipeline_status="PUBLISHED")

    first = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert first.json()["title"] == "원본 제목"

    await crud_spot.update_spot(db_session, spot.uid, {"title": "수정된 제목"})

    second = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert second.json()["title"] == "수정된 제목"


async def test_review_creation_invalidates_detail_but_not_list_version(
    db_client: AsyncClient, db_session: AsyncSession, fake_cache
):
    spot = await _make_spot(db_session, "리뷰 스팟", pipeline_status="PUBLISHED")
    user = await make_user(db_session)

    await db_client.get("/v1/explore/spots")
    await db_client.get(f"/v1/explore/spots/{spot.uid}")
    version_before = await fake_cache.get("spots:version")

    await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=user.uid, rating=5, content=None
    )

    version_after = await fake_cache.get("spots:version")
    assert version_after == version_before

    detail = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert detail.json()["rating_avg"] == 5.0
    assert detail.json()["review_count"] == 1


async def test_trust_tier_decay_invalidates_detail_cache(
    db_client: AsyncClient, db_session: AsyncSession, fake_cache
):
    stale = datetime.now(timezone.utc) - timedelta(days=181)
    spot = await _make_spot(
        db_session,
        "감쇠 스팟",
        pipeline_status="PUBLISHED",
        trust_tier=1,
        last_verified_at=stale,
    )

    first = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert first.json()["trust_tier"] == 1

    await crud_spot.decay_stale_trust_tiers(db_session)

    second = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert second.json()["trust_tier"] == 2


async def test_bulk_upsert_invalidates_existing_spot_detail_cache(
    db_client: AsyncClient, db_session: AsyncSession, fake_cache
):
    spot = await _make_spot(
        db_session,
        "벌크 이전 제목",
        pipeline_status="PUBLISHED",
        source="vivac_partner",
        external_id="vp-00123",
    )

    first = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert first.json()["title"] == "벌크 이전 제목"

    await spots_bulk_upsert_handler(
        db_session,
        {
            "dry_run": False,
            "rows": [
                {
                    "source": "vivac_partner",
                    "external_id": "vp-00123",
                    "title": "벌크 이후 제목",
                }
            ],
        },
    )
    # 벌크 upsert는 Core insert/on_conflict라 세션의 identity map에 이미 로드된
    # spot ORM 객체를 갱신하지 않는다 — 테스트에서 db_session/db_client가
    # 세션을 공유하니 아래 GET이 같은 객체를 보게 explicit refresh 필요
    # (프로덕션은 요청마다 새 세션이라 해당 없음).
    await db_session.refresh(spot)

    second = await db_client.get(f"/v1/explore/spots/{spot.uid}")
    assert second.json()["title"] == "벌크 이후 제목"


# ---------------------------------------------------------------------------
# fail-open — redis 장애 시 캐싱 없이 DB로 정상 응답
# ---------------------------------------------------------------------------


class _BrokenRedis:
    async def get(self, *_args, **_kwargs):
        raise ConnectionError("redis down")

    async def set(self, *_args, **_kwargs):
        raise ConnectionError("redis down")

    async def incr(self, *_args, **_kwargs):
        raise ConnectionError("redis down")

    async def delete(self, *_args, **_kwargs):
        raise ConnectionError("redis down")


async def test_cache_failure_falls_back_to_db(
    db_client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(cache, "_client", _BrokenRedis())
    await _make_spot(db_session, "장애 스팟", pipeline_status="PUBLISHED")

    response = await db_client.get("/v1/explore/spots")
    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == "장애 스팟"
