from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.models.spot import Spot
from vivacapi.models.spot_category import SpotCategoryOption


async def list_category_options(session: AsyncSession) -> list[SpotCategoryOption]:
    result = await session.execute(
        select(SpotCategoryOption).order_by(SpotCategoryOption.code)
    )
    return list(result.scalars().all())


async def create_category_option(
    session: AsyncSession, code: str, label_ko: str
) -> SpotCategoryOption:
    option = SpotCategoryOption(code=code, label_ko=label_ko)
    session.add(option)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AppException(
            ErrorCode.CATEGORY_ALREADY_EXISTS, f"이미 존재하는 카테고리입니다: {code}"
        )
    await session.refresh(option)
    return option


async def delete_category_option(session: AsyncSession, code: str) -> bool:
    """카테고리를 삭제하고, 모든 스팟의 category 배열에서도 함께 제거한다."""
    option = await session.get(SpotCategoryOption, code)
    if option is None:
        return False

    await session.execute(
        update(Spot)
        .where(Spot.category.any(code))
        .values(category=func.array_remove(Spot.category, code))
    )
    await session.delete(option)
    await session.commit()
    return True
