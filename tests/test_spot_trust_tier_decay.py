from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.crud import spot as crud_spot
from vivacapi.models.spot import Spot

STALE = datetime.now(timezone.utc) - timedelta(days=181)
FRESH = datetime.now(timezone.utc) - timedelta(days=10)


async def _make_spot(db: AsyncSession, title: str, **kwargs) -> Spot:
    kwargs.setdefault("rating_avg", 0.0)
    kwargs.setdefault("review_count", 0)
    kwargs.setdefault("pipeline_status", "PUBLISHED")
    spot = Spot(title=title, **kwargs)
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


async def test_decays_stale_tier_one_and_two_by_one_step(db_session: AsyncSession):
    tier1 = await _make_spot(db_session, "tier1", trust_tier=1, last_verified_at=STALE)
    tier2 = await _make_spot(db_session, "tier2", trust_tier=2, last_verified_at=STALE)

    result = await crud_spot.decay_stale_trust_tiers(db_session)

    await db_session.refresh(tier1)
    await db_session.refresh(tier2)
    assert tier1.trust_tier == 2
    assert tier2.trust_tier == 3
    assert result["downgraded"] == 2


async def test_stale_tier_three_requeues_by_clearing_assignment(
    db_session: AsyncSession,
):
    tier3 = await _make_spot(
        db_session,
        "tier3",
        trust_tier=3,
        last_verified_at=STALE,
        assigned_to_uid=None,
    )

    result = await crud_spot.decay_stale_trust_tiers(db_session)

    await db_session.refresh(tier3)
    assert tier3.assigned_to_uid is None
    assert tier3.pipeline_status == "PUBLISHED"
    assert result["requeued"] == 1


async def test_null_last_verified_at_is_treated_as_stale(db_session: AsyncSession):
    spot = await _make_spot(db_session, "unverified", trust_tier=1)
    assert spot.last_verified_at is None

    result = await crud_spot.decay_stale_trust_tiers(db_session)

    await db_session.refresh(spot)
    assert spot.trust_tier == 2
    assert result["downgraded"] == 1


async def test_recently_verified_spot_is_untouched(db_session: AsyncSession):
    spot = await _make_spot(db_session, "fresh", trust_tier=1, last_verified_at=FRESH)

    result = await crud_spot.decay_stale_trust_tiers(db_session)

    await db_session.refresh(spot)
    assert spot.trust_tier == 1
    assert result["downgraded"] == 0
    assert result["requeued"] == 0


async def test_unpublished_and_deleted_spots_are_untouched(db_session: AsyncSession):
    curated = await _make_spot(
        db_session,
        "curated",
        trust_tier=1,
        last_verified_at=STALE,
        pipeline_status="CURATED",
    )
    deleted = await _make_spot(
        db_session,
        "deleted",
        trust_tier=1,
        last_verified_at=STALE,
        deleted_at=datetime.now(timezone.utc),
    )
    no_tier = await _make_spot(
        db_session, "no-tier", trust_tier=None, last_verified_at=STALE
    )

    result = await crud_spot.decay_stale_trust_tiers(db_session)

    await db_session.refresh(curated)
    await db_session.refresh(deleted)
    await db_session.refresh(no_tier)
    assert curated.trust_tier == 1
    assert deleted.trust_tier == 1
    assert no_tier.trust_tier is None
    assert result["downgraded"] == 0
    assert result["requeued"] == 0


async def test_decay_updates_watermark_to_prevent_cascade_on_rerun(
    db_session: AsyncSession,
):
    spot = await _make_spot(
        db_session, "watermark", trust_tier=1, last_verified_at=STALE
    )

    await crud_spot.decay_stale_trust_tiers(db_session)
    await db_session.refresh(spot)
    assert spot.trust_tier == 2
    assert spot.last_verified_at > STALE

    second_run = await crud_spot.decay_stale_trust_tiers(db_session)
    await db_session.refresh(spot)
    assert spot.trust_tier == 2
    assert second_run["downgraded"] == 0
