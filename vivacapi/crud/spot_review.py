from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.models.spot import Spot
from vivacapi.models.spot_review import SpotReview
from vivacapi.models.user import User


async def _recalculate_spot_rating(session: AsyncSession, spot_uid: str) -> None:
    """soft delete된 리뷰는 제외하고 spot.rating_avg/review_count를 재계산한다."""
    row = (
        await session.execute(
            select(func.avg(SpotReview.rating), func.count())
            .select_from(SpotReview)
            .where(SpotReview.spot_uid == spot_uid, SpotReview.deleted_at.is_(None))
        )
    ).one()
    avg_rating, count = row
    await session.execute(
        update(Spot)
        .where(Spot.uid == spot_uid)
        .values(
            rating_avg=float(avg_rating) if avg_rating is not None else 0.0,
            review_count=count,
        )
    )


async def get_active_review(
    session: AsyncSession, spot_uid: str, user_uid: str
) -> SpotReview | None:
    result = await session.execute(
        select(SpotReview).where(
            SpotReview.spot_uid == spot_uid,
            SpotReview.user_id == user_uid,
            SpotReview.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_review_by_uid(session: AsyncSession, uid: str) -> SpotReview | None:
    result = await session.execute(select(SpotReview).where(SpotReview.uid == uid))
    return result.scalar_one_or_none()


async def create_review(
    session: AsyncSession,
    *,
    spot_uid: str,
    user_uid: str,
    rating: int,
    content: str | None,
) -> SpotReview:
    if await get_active_review(session, spot_uid, user_uid) is not None:
        raise AppException(
            ErrorCode.REVIEW_ALREADY_EXISTS, "이미 이 spot에 작성한 리뷰가 있습니다"
        )
    review = SpotReview(
        spot_uid=spot_uid, user_id=user_uid, rating=rating, content=content
    )
    session.add(review)
    await session.flush()
    await _recalculate_spot_rating(session, spot_uid)
    await session.commit()
    await session.refresh(review)
    return review


async def list_reviews_by_spot(
    session: AsyncSession, spot_uid: str, *, offset: int, limit: int
) -> tuple[list[tuple[SpotReview, str]], int]:
    """(review, nickname) 튜플 리스트와 총 개수. soft delete된 리뷰는 제외."""
    base = select(SpotReview).where(
        SpotReview.spot_uid == spot_uid, SpotReview.deleted_at.is_(None)
    )
    total = await session.scalar(select(func.count()).select_from(base.subquery()))

    stmt = (
        select(SpotReview, User.nickname)
        .join(User, User.uid == SpotReview.user_id)
        .where(SpotReview.spot_uid == spot_uid, SpotReview.deleted_at.is_(None))
        .order_by(SpotReview.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [(review, nickname) for review, nickname in result.all()], total or 0


async def update_review(
    session: AsyncSession, review: SpotReview, data: dict
) -> SpotReview:
    for key, value in data.items():
        setattr(review, key, value)
    await session.flush()
    if "rating" in data:
        await _recalculate_spot_rating(session, review.spot_uid)
    await session.commit()
    await session.refresh(review)
    return review


async def soft_delete_review(session: AsyncSession, review: SpotReview) -> None:
    await session.execute(
        update(SpotReview)
        .where(SpotReview.uid == review.uid)
        .values(deleted_at=func.now())
    )
    await _recalculate_spot_rating(session, review.spot_uid)
    await session.commit()
