from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core import storage
from vivacapi.core.database import get_db
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.core.region import abbreviate_sido
from vivacapi.crud import spot as crud_spot
from vivacapi.crud import spot_image as crud_image
from vivacapi.schemas.spot import SpotDetail, SpotListItem, SpotListResponse
from vivacapi.schemas.spot_image import SpotImageOut

router = APIRouter()


@router.get("/spots", response_model=SpotListResponse)
async def list_spots(
    cursor: str | None = Query(None, description="이전 응답의 next_cursor 값"),
    limit: int = Query(20, ge=1, le=50, description="페이지 크기 (1-50)"),
    session: AsyncSession = Depends(get_db),
) -> SpotListResponse:
    """탐색 가능한 spot 목록을 조회합니다 (비로그인 가능)."""
    spots, next_cursor, has_more = await crud_spot.list_spots(
        session, cursor=cursor, limit=limit
    )
    thumbnails = await crud_image.get_thumbnails_by_spots(
        session, [spot.uid for spot in spots]
    )
    items = [
        SpotListItem(
            uid=spot.uid,
            title=spot.title,
            trust_tier=spot.trust_tier,
            category=spot.category,
            region_short=abbreviate_sido(spot.region_province),
            thumbnail_url=(
                storage.resolve_url(image.s3_key, image.is_public)
                if (image := thumbnails.get(spot.uid))
                else None
            ),
        )
        for spot in spots
    ]
    return SpotListResponse(items=items, next_cursor=next_cursor, has_more=has_more)


@router.get("/spots/{uid}", response_model=SpotDetail)
async def get_spot(uid: str, session: AsyncSession = Depends(get_db)) -> SpotDetail:
    """spot 상세 정보를 조회합니다 (비로그인 가능)."""
    spot = await crud_spot.get_spot_by_uid(session, uid, published_only=True)
    if spot is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")
    return spot


@router.get("/spots/{uid}/images", response_model=list[SpotImageOut])
async def list_spot_images(
    uid: str, session: AsyncSession = Depends(get_db)
) -> list[SpotImageOut]:
    """spot의 대표/상세 이미지 목록을 조회합니다 (비로그인 가능).

    공개 이미지는 CDN URL을, 비공개 이미지는 presigned URL을 반환합니다.
    """
    spot = await crud_spot.get_spot_by_uid(session, uid, published_only=True)
    if spot is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")

    images = await crud_image.list_images_by_spot(session, uid)
    return [
        SpotImageOut(
            uid=image.uid,
            role=image.role,
            sort_order=image.sort_order,
            is_public=image.is_public,
            url=storage.resolve_url(image.s3_key, image.is_public),
        )
        for image in images
    ]
