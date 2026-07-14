from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.deps import CurrentStaff, require_role
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud import spot_category as crud_category
from vivacapi.models.user import StaffRole
from vivacapi.schemas.spot_category import SpotCategoryOption, SpotCategoryOptionCreate

router = APIRouter()


@router.get("", response_model=list[SpotCategoryOption])
async def list_categories(
    staff: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> list[SpotCategoryOption]:
    return await crud_category.list_category_options(db)


@router.post(
    "",
    response_model=SpotCategoryOption,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(StaffRole.MANAGER))],
)
async def create_category(
    payload: SpotCategoryOptionCreate,
    db: AsyncSession = Depends(get_db),
) -> SpotCategoryOption:
    return await crud_category.create_category_option(
        db, payload.code, payload.label_ko
    )


@router.delete(
    "/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(StaffRole.MANAGER))],
)
async def delete_category(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    deleted = await crud_category.delete_category_option(db, code)
    if not deleted:
        raise AppException(ErrorCode.CATEGORY_NOT_FOUND, f"카테고리를 찾을 수 없습니다: {code}")
