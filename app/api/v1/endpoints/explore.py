from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import AppException, ErrorCode
from app.crud import spot as crud_spot
from app.schemas.spot import SpotDetail, SpotListResponse

router = APIRouter()


@router.get("/spots", response_model=SpotListResponse)
async def list_spots(
    page: int = Query(1, ge=1, description="페이지 번호 (1부터 시작)"),
    limit: int = Query(20, ge=1, le=50, description="페이지 크기 (1-50)"),
    session: AsyncSession = Depends(get_db),
) -> SpotListResponse:
    """탐색 가능한 spot 목록을 조회합니다 (비로그인 가능)."""
    spots, total, total_pages = await crud_spot.list_spots(session, page=page, limit=limit)
    return SpotListResponse(items=spots, page=page, total_pages=total_pages, total=total)


@router.get("/spots/{uid}", response_model=SpotDetail)
async def get_spot(uid: str, session: AsyncSession = Depends(get_db)) -> SpotDetail:
    """spot 상세 정보를 조회합니다 (비로그인 가능)."""
    spot = await crud_spot.get_spot_by_uid(session, uid)
    if spot is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")
    return spot
