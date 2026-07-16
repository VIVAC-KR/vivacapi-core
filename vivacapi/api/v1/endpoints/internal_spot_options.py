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


@router.get("", response_model=list[SpotFieldOption], summary="옵션값 목록 조회")
async def list_spot_options(
    staff: CurrentStaff,
    field: SpotOptionField = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[SpotFieldOption]:
    """spots의 배열 컬럼(category/amenities 등) 중 하나에 대해 등록된 옵션값을
    code 오름차순으로 반환한다. field는 SpotOptionField에 정의된 값만 허용된다.
    조회는 staff 등급 제한 없이 STAFF만 있어도 가능하다."""
    return await crud_field_option.list_field_options(db, field)


@router.post(
    "",
    response_model=SpotFieldOption,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(StaffRole.MANAGER))],
    summary="옵션값 추가",
)
async def create_spot_option(
    payload: SpotFieldOptionCreate,
    db: AsyncSession = Depends(get_db),
) -> SpotFieldOption:
    """spots의 필드 하나에 새 옵션값(code/label_ko)을 추가한다. MANAGER 이상
    권한이 필요하다. 이미 존재하는 (field, code) 조합이면 실패한다."""
    return await crud_field_option.create_field_option(
        db, payload.field, payload.code, payload.label_ko
    )


@router.delete(
    "/{field}/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(StaffRole.MANAGER))],
    summary="옵션값 삭제",
)
async def delete_spot_option(
    field: SpotOptionField,
    code: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """옵션값을 삭제하고, 이 code를 쓰고 있던 모든 spot의 해당 배열 컬럼에서도
    함께 제거한다. MANAGER 이상 권한이 필요하다. 존재하지 않는 field/code
    조합이면 SPOT_OPTION_NOT_FOUND로 실패한다."""
    deleted = await crud_field_option.delete_field_option(db, field, code)
    if not deleted:
        raise AppException(
            ErrorCode.SPOT_OPTION_NOT_FOUND, f"항목을 찾을 수 없습니다: {field}/{code}"
        )
