import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.models.spot import Spot


async def _insert_with_uid(db: AsyncSession, uid: str):
    db.add(Spot(uid=uid, title="uid 규격 테스트", rating_avg=0.0, review_count=0))
    await db.commit()


async def test_uid_with_special_char_rejected(db_session: AsyncSession):
    with pytest.raises(IntegrityError):
        await _insert_with_uid(db_session, "01ktF80vUl-aADXfvW2rCw")
    await db_session.rollback()


async def test_uid_with_wrong_length_rejected(db_session: AsyncSession):
    with pytest.raises(IntegrityError):
        await _insert_with_uid(db_session, "shortuid")
    await db_session.rollback()


async def test_server_generated_uid_passes(db_session: AsyncSession):
    spot = Spot(title="자동 생성 uid", rating_avg=0.0, review_count=0)
    db_session.add(spot)
    await db_session.commit()
    assert len(spot.uid) == 22 and spot.uid.isalnum()
