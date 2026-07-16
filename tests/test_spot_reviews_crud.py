import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import make_user
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud import spot as crud_spot
from vivacapi.crud import spot_review as crud_review
from vivacapi.models.spot import PipelineStatus, Spot


async def _make_spot(db: AsyncSession, title: str = "Spot") -> Spot:
    spot = Spot(
        title=title,
        rating_avg=0.0,
        review_count=0,
        pipeline_status=PipelineStatus.PUBLISHED,
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


async def test_create_review_recalculates_spot_rating(db_session: AsyncSession):
    spot = await _make_spot(db_session)
    user = await make_user(db_session, email="a@example.com", google_sub="sub-a")

    await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=user.uid, rating=8, content="good"
    )

    updated = await crud_spot.get_spot_by_uid(db_session, spot.uid)
    assert updated.rating_avg == 8.0
    assert updated.review_count == 1


async def test_create_duplicate_active_review_raises(db_session: AsyncSession):
    spot = await _make_spot(db_session)
    user = await make_user(db_session, email="b@example.com", google_sub="sub-b")
    await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=user.uid, rating=5, content=None
    )

    with pytest.raises(AppException) as exc_info:
        await crud_review.create_review(
            db_session, spot_uid=spot.uid, user_uid=user.uid, rating=7, content=None
        )
    assert exc_info.value.code == ErrorCode.REVIEW_ALREADY_EXISTS


async def test_soft_delete_excludes_from_average_and_allows_rereview(
    db_session: AsyncSession,
):
    spot = await _make_spot(db_session)
    user = await make_user(db_session, email="c@example.com", google_sub="sub-c")
    review = await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=user.uid, rating=10, content=None
    )

    await crud_review.soft_delete_review(db_session, review)

    updated = await crud_spot.get_spot_by_uid(db_session, spot.uid)
    assert updated.rating_avg == 0.0
    assert updated.review_count == 0

    # soft delete 후에는 같은 유저가 같은 spot에 다시 리뷰를 작성할 수 있어야 한다.
    new_review = await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=user.uid, rating=6, content=None
    )
    assert new_review.uid != review.uid

    updated = await crud_spot.get_spot_by_uid(db_session, spot.uid)
    assert updated.rating_avg == 6.0
    assert updated.review_count == 1


async def test_update_review_rating_recalculates_average(db_session: AsyncSession):
    spot = await _make_spot(db_session)
    user = await make_user(db_session, email="d@example.com", google_sub="sub-d")
    review = await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=user.uid, rating=4, content=None
    )

    await crud_review.update_review(db_session, review, {"rating": 10})

    updated = await crud_spot.get_spot_by_uid(db_session, spot.uid)
    assert updated.rating_avg == 10.0


async def test_list_reviews_excludes_soft_deleted(db_session: AsyncSession):
    spot = await _make_spot(db_session)
    user = await make_user(db_session, email="e@example.com", google_sub="sub-e")
    review = await crud_review.create_review(
        db_session, spot_uid=spot.uid, user_uid=user.uid, rating=9, content=None
    )
    await crud_review.soft_delete_review(db_session, review)

    rows, total = await crud_review.list_reviews_by_spot(
        db_session, spot.uid, offset=0, limit=20
    )
    assert rows == []
    assert total == 0
