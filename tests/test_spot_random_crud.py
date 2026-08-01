from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.crud import spot as crud_spot
from vivacapi.models.spot import Spot


async def _make_spot(db: AsyncSession, title: str, **kwargs) -> Spot:
    kwargs.setdefault("rating_avg", 0.0)
    kwargs.setdefault("review_count", 0)
    spot = Spot(title=title, **kwargs)
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


async def test_get_random_spots_respects_limit(db_session: AsyncSession):
    for i in range(5):
        await _make_spot(db_session, f"spot-{i}")

    result = await crud_spot.get_random_spots(db_session, limit=3)

    assert len(result) == 3


async def test_get_random_spots_excludes_deleted(db_session: AsyncSession):
    await _make_spot(db_session, "alive")
    await _make_spot(db_session, "gone", deleted_at=datetime.now(timezone.utc))

    result = await crud_spot.get_random_spots(db_session, limit=10)

    assert [s.title for s in result] == ["alive"]
