from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.deps import CurrentStaff, require_role
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud import spot_field_option as crud_field_option
from vivacapi.models.spot_field_option import SpotOptionField
from vivacapi.models.user import StaffRole
from vivacapi.schemas.spot_field_option import SpotFieldOption, SpotFieldOptionCreate

router = APIRouter()


@router.get("", response_model=list[SpotFieldOption])
async def list_spot_options(
    staff: CurrentStaff,
    field: SpotOptionField = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[SpotFieldOption]:
    return await crud_field_option.list_field_options(db, field)


@router.post(
    "",
    response_model=SpotFieldOption,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(StaffRole.MANAGER))],
)
async def create_spot_option(
    payload: SpotFieldOptionCreate,
    db: AsyncSession = Depends(get_db),
) -> SpotFieldOption:
    return await crud_field_option.create_field_option(
        db, payload.field, payload.code, payload.label_ko
    )


@router.delete(
    "/{field}/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(StaffRole.MANAGER))],
)
async def delete_spot_option(
    field: SpotOptionField,
    code: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    deleted = await crud_field_option.delete_field_option(db, field, code)
    if not deleted:
        raise AppException(
            ErrorCode.SPOT_OPTION_NOT_FOUND, f"항목을 찾을 수 없습니다: {field}/{code}"
        )
