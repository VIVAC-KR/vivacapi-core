from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud import spot as crud_spot
from vivacapi.models.spot import Spot

import pytest


async def _make_spot(db: AsyncSession, title: str, **kwargs) -> Spot:
    kwargs.setdefault("rating_avg", 0.0)
    kwargs.setdefault("review_count", 0)
    spot = Spot(title=title, **kwargs)
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


async def test_search_matches_title(db_session: AsyncSession):
    spot = await _make_spot(db_session, "위례 캠핑장", pipeline_status="PUBLISHED")
    await _make_spot(db_session, "무관 스팟", pipeline_status="PUBLISHED")

    spots, _, _ = await crud_spot.search_spots(db_session, query="캠핑장")
    assert [s.uid for s in spots] == [spot.uid]


async def test_search_matches_tagline_description_address(db_session: AsyncSession):
    by_tagline = await _make_spot(
        db_session,
        "태그라인 스팟",
        pipeline_status="PUBLISHED",
        tagline="애견동반 가능한 감성 글램핑",
    )
    by_description = await _make_spot(
        db_session,
        "설명 스팟",
        pipeline_status="PUBLISHED",
        description="예약전 반드시 애견동반 정책을 확인하세요",
    )
    by_address = await _make_spot(
        db_session,
        "주소 스팟",
        pipeline_status="PUBLISHED",
        address="경기도 애견동반 캠핑로 123",
    )

    spots, _, _ = await crud_spot.search_spots(db_session, query="애견동반")
    uids = {s.uid for s in spots}
    assert uids == {by_tagline.uid, by_description.uid, by_address.uid}


async def test_search_partial_match_via_trigram(db_session: AsyncSession):
    spot = await _make_spot(db_session, "글램핑장", pipeline_status="PUBLISHED")

    spots, _, _ = await crud_spot.search_spots(db_session, query="글램핑")
    assert [s.uid for s in spots] == [spot.uid]


async def test_search_excludes_unpublished(db_session: AsyncSession):
    await _make_spot(db_session, "미공개 캠핑장", pipeline_status="CURATED")

    spots, _, _ = await crud_spot.search_spots(db_session, query="캠핑장")
    assert spots == []


async def test_search_filters_by_category(db_session: AsyncSession):
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

    spots, _, _ = await crud_spot.search_spots(
        db_session, query="캠핑장", category=["GLAMPING"]
    )
    assert [s.uid for s in spots] == [glamping.uid]


async def test_search_filters_by_region_province(db_session: AsyncSession):
    gangwon = await _make_spot(
        db_session,
        "강원 캠핑장",
        pipeline_status="PUBLISHED",
        region_province="강원도",
    )
    await _make_spot(
        db_session,
        "경기 캠핑장",
        pipeline_status="PUBLISHED",
        region_province="경기도",
    )

    spots, _, _ = await crud_spot.search_spots(
        db_session, query="캠핑장", region_province="강원도"
    )
    assert [s.uid for s in spots] == [gangwon.uid]


async def test_search_ranks_title_match_above_description_match(
    db_session: AsyncSession,
):
    title_match = await _make_spot(db_session, "글램핑장", pipeline_status="PUBLISHED")
    description_match = await _make_spot(
        db_session,
        "무관 스팟",
        pipeline_status="PUBLISHED",
        description="여기는 글램핑장 아니라 그냥 캠핑장 입니다",
    )

    spots, _, _ = await crud_spot.search_spots(db_session, query="글램핑장")
    assert [s.uid for s in spots] == [title_match.uid, description_match.uid]


async def test_search_pagination_continues_without_gap_or_duplicate(
    db_session: AsyncSession,
):
    created = [
        await _make_spot(
            db_session, f"캠핑장 {i}", pipeline_status="PUBLISHED", rating_avg=float(i)
        )
        for i in range(5)
    ]

    first_page, cursor, has_more = await crud_spot.search_spots(
        db_session, query="캠핑장", limit=2
    )
    assert len(first_page) == 2
    assert has_more is True

    second_page, cursor2, has_more2 = await crud_spot.search_spots(
        db_session, query="캠핑장", limit=2, cursor=cursor
    )
    assert len(second_page) == 2
    assert has_more2 is True

    third_page, cursor3, has_more3 = await crud_spot.search_spots(
        db_session, query="캠핑장", limit=2, cursor=cursor2
    )
    assert len(third_page) == 1
    assert has_more3 is False
    assert cursor3 is None

    all_uids = [s.uid for s in first_page + second_page + third_page]
    assert len(all_uids) == len(set(all_uids)) == len(created)


async def test_search_raises_on_malformed_cursor(db_session: AsyncSession):
    with pytest.raises(AppException) as exc_info:
        await crud_spot.search_spots(
            db_session, query="캠핑장", cursor="not-a-valid-cursor"
        )
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
