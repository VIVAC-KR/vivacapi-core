from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.models.user_block import UserBlock


async def get_block(
    session: AsyncSession, blocker_uid: str, blocked_uid: str
) -> UserBlock | None:
    result = await session.execute(
        select(UserBlock).where(
            UserBlock.blocker_uid == blocker_uid, UserBlock.blocked_uid == blocked_uid
        )
    )
    return result.scalar_one_or_none()


async def block_user(
    session: AsyncSession, *, blocker_uid: str, blocked_uid: str
) -> UserBlock:
    """이미 차단돼 있으면 그대로 반환한다(멱등) — 반복 호출이 에러가 될 이유가 없다."""
    existing = await get_block(session, blocker_uid, blocked_uid)
    if existing is not None:
        return existing
    block = UserBlock(blocker_uid=blocker_uid, blocked_uid=blocked_uid)
    session.add(block)
    await session.commit()
    await session.refresh(block)
    return block


async def unblock_user(
    session: AsyncSession, *, blocker_uid: str, blocked_uid: str
) -> None:
    block = await get_block(session, blocker_uid, blocked_uid)
    if block is None:
        return
    await session.delete(block)
    await session.commit()


async def has_block_between(session: AsyncSession, user_a: str, user_b: str) -> bool:
    """양방향 중 한쪽이라도 차단했으면 True."""
    result = await session.execute(
        select(UserBlock.blocker_uid)
        .where(
            ((UserBlock.blocker_uid == user_a) & (UserBlock.blocked_uid == user_b))
            | ((UserBlock.blocker_uid == user_b) & (UserBlock.blocked_uid == user_a))
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None
