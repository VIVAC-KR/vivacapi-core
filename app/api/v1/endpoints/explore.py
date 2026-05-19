import uuid

from fastapi import APIRouter, Query

from app.core.errors import AppException, ErrorCode
from app.schemas.spot import SpotDetail, SpotListResponse, SpotSort

router = APIRouter()


@router.get("/spots", response_model=SpotListResponse)
async def list_spots(
    q: str | None = Query(None, description="검색어"),
    sort: SpotSort = Query(SpotSort.POPULAR, description="정렬 기준"),
    cursor: str | None = Query(None, description="페이지네이션 cursor (opaque)"),
    limit: int = Query(20, ge=1, le=50, description="페이지 크기 (1-50)"),
) -> SpotListResponse:
    """탐색 가능한 spot 목록을 조회합니다 (비로그인 가능)."""
    return SpotListResponse(items=[], next_cursor=None, has_more=False, total=0)


@router.get("/spots/{spot_uid}", response_model=SpotDetail)
async def get_spot(spot_uid: uuid.UUID) -> SpotDetail:
    """spot 상세 정보를 조회합니다 (비로그인 가능)."""
    raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")
