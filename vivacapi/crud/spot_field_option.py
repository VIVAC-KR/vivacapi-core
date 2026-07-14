from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.models.spot import Spot
from vivacapi.models.spot_field_option import SpotFieldOption, SpotOptionField


async def list_field_options(
    session: AsyncSession, field: SpotOptionField
) -> list[SpotFieldOption]:
    result = await session.execute(
        select(SpotFieldOption)
        .where(SpotFieldOption.field == field)
        .order_by(SpotFieldOption.code)
    )
    return list(result.scalars().all())


async def create_field_option(
    session: AsyncSession, field: SpotOptionField, code: str, label_ko: str
) -> SpotFieldOption:
    option = SpotFieldOption(field=field, code=code, label_ko=label_ko)
    session.add(option)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AppException(
            ErrorCode.SPOT_OPTION_ALREADY_EXISTS,
            f"이미 존재하는 항목입니다: {field}/{code}",
        )
    await session.refresh(option)
    return option


async def delete_field_option(
    session: AsyncSession, field: SpotOptionField, code: str
) -> bool:
    """항목을 삭제하고, 모든 스팟의 해당 배열 컬럼에서도 함께 제거한다."""
    option = await session.get(SpotFieldOption, {"field": field, "code": code})
    if option is None:
        return False

    column = getattr(Spot, field.value)
    await session.execute(
        update(Spot).where(column.any(code)).values(**{field.value: func.array_remove(column, code)})
    )
    await session.delete(option)
    await session.commit()
    return True
