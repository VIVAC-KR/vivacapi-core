import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.api.v1.endpoints.explore_docs import (
    GET_SPOT_SUMMARY,
    LIST_SPOT_IMAGES_SUMMARY,
    LIST_SPOTS_FOR_MAP_SUMMARY,
    LIST_SPOTS_SUMMARY,
)
from vivacapi.core import cache, storage
from vivacapi.core.config import settings
from vivacapi.core.database import get_db
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.core.geo import parse_bbox
from vivacapi.core.region import abbreviate_sido
from vivacapi.crud import spot as crud_spot
from vivacapi.crud import spot_image as crud_image
from vivacapi.models.spot_image import SpotImage
from vivacapi.schemas.spot import (
    SpotDetail,
    SpotListItem,
    SpotListResponse,
    SpotMapItem,
    SpotMapResponse,
)
from vivacapi.schemas.spot_image import SpotImageOut

_BBOX_DESCRIPTION = (
    "지도 영역 필터 `min_lng,min_lat,max_lng,max_lat` — **경도가 먼저**다 "
    "(GeoJSON/OGC 순서). 예: `127.5,35.2,127.9,35.5`. "
    "q/category와는 AND로 결합된다."
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_thumbnail_url(thumbnails: dict[str, SpotImage], uid: str) -> str | None:
    image = thumbnails.get(uid)
    return storage.resolve_url(image.s3_key, image.is_public) if image else None


@router.get("/spots", response_model=SpotListResponse, summary=LIST_SPOTS_SUMMARY)
async def list_spots(
    q: str | None = Query(None, description="검색어 (제목/한줄설명/설명/주소)"),
    category: list[str] | None = Query(None, description="카테고리 코드 필터"),
    region_province: str | None = Query(None, description="지역(도/시) 필터"),
    bbox: str | None = Query(None, description=_BBOX_DESCRIPTION),
    cursor: str | None = Query(None, description="이전 응답의 next_cursor 값"),
    limit: int = Query(20, ge=1, le=50, description="페이지 크기 (1-50)"),
    session: AsyncSession = Depends(get_db),
) -> SpotListResponse:
    """탐색 가능한 spot 목록을 조회합니다 (비로그인 가능).

    q가 있으면 검색 모드(가중치 기반 관련도 정렬)로 분기한다.
    검색 모드의 cursor는 기본 목록과 포맷이 다르므로 서로 재사용할 수 없다
    (설계 근거: docs/projects/spot-search-postgres-fts.md).

    cursor는 발급 시점의 bbox에 묶인다 — 다른 bbox로 재사용하면
    `400 CURSOR_SCOPE_MISMATCH`로 거부한다.
    """
    parsed_bbox = parse_bbox(bbox) if bbox else None
    cache_key = await cache.make_spots_list_key(
        {
            "q": q,
            "category": category,
            "region_province": region_province,
            "bbox": bbox,
            "cursor": cursor,
            "limit": limit,
        }
    )
    cached = await cache.get_cached(cache_key)
    if cached is not None:
        logger.info("cache hit spots_list key=%s", cache_key)
        return Response(content=cached, media_type="application/json")
    logger.info("cache miss spots_list key=%s", cache_key)

    if q and q.strip():
        spots, next_cursor, has_more = await crud_spot.search_spots(
            session,
            query=q,
            category=category,
            region_province=region_province,
            bbox=parsed_bbox,
            cursor=cursor,
            limit=limit,
        )
    else:
        spots, next_cursor, has_more = await crud_spot.list_spots(
            session,
            cursor=cursor,
            limit=limit,
            category=category,
            region_province=region_province,
            bbox=parsed_bbox,
        )
    total, total_capped = await crud_spot.count_spots(
        session,
        query=q,
        category=category,
        region_province=region_province,
        bbox=parsed_bbox,
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
            thumbnail_url=_resolve_thumbnail_url(thumbnails, spot.uid),
            latitude=spot.latitude,
            longitude=spot.longitude,
        )
        for spot in spots
    ]
    response = SpotListResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        total=total,
        total_capped=total_capped,
    )
    await cache.set_cached(
        cache_key, response.model_dump_json(), settings.SPOTS_LIST_CACHE_TTL_SECONDS
    )
    return response


# /spots/{uid}보다 먼저 등록해야 한다 — 순서가 바뀌면 "map"이 uid로 매칭된다.
@router.get(
    "/spots/map", response_model=SpotMapResponse, summary=LIST_SPOTS_FOR_MAP_SUMMARY
)
async def list_spots_for_map(
    q: str | None = Query(None, description="검색어 (제목/한줄설명/설명/주소)"),
    category: list[str] | None = Query(None, description="카테고리 코드 필터"),
    region_province: str | None = Query(None, description="지역(도/시) 필터"),
    bbox: str | None = Query(None, description=_BBOX_DESCRIPTION),
    limit: int = Query(
        crud_spot.MAP_LIMIT_MAX,
        ge=1,
        le=crud_spot.MAP_LIMIT_MAX,
        description=f"최대 핀 개수 (1-{crud_spot.MAP_LIMIT_MAX})",
    ),
    session: AsyncSession = Depends(get_db),
) -> SpotMapResponse:
    """지도 핀 렌더링용 경량 목록을 조회합니다 (비로그인 가능).

    필터(q/category/region_province/bbox)는 `GET /v1/explore/spots`와 동일한
    조건을 쓰므로 두 모드의 결과 집합이 갈리지 않는다. 커서 없이 한 번에
    반환하며, 클러스터링은 클라이언트 몫이다.
    """
    parsed_bbox = parse_bbox(bbox) if bbox else None
    cache_key = await cache.make_spots_list_key(
        {
            "kind": "map",
            "q": q,
            "category": category,
            "region_province": region_province,
            "bbox": bbox,
            "limit": limit,
        }
    )
    cached = await cache.get_cached(cache_key)
    if cached is not None:
        logger.info("cache hit spots_map key=%s", cache_key)
        return Response(content=cached, media_type="application/json")
    logger.info("cache miss spots_map key=%s", cache_key)

    spots, truncated = await crud_spot.list_spots_map(
        session,
        query=q,
        category=category,
        region_province=region_province,
        bbox=parsed_bbox,
        limit=limit,
    )
    response = SpotMapResponse(
        items=[SpotMapItem.model_validate(spot) for spot in spots],
        truncated=truncated,
    )
    await cache.set_cached(
        cache_key, response.model_dump_json(), settings.SPOTS_LIST_CACHE_TTL_SECONDS
    )
    return response


@router.get("/spots/{uid}", response_model=SpotDetail, summary=GET_SPOT_SUMMARY)
async def get_spot(uid: str, session: AsyncSession = Depends(get_db)) -> SpotDetail:
    """spot 상세 정보를 조회합니다 (비로그인 가능).

    pipeline_status가 PUBLISHED이고 삭제되지 않은 spot만 노출한다 — 파이프라인
    검토 중이거나 소프트 삭제된 spot은 존재해도 SPOT_NOT_FOUND로 응답한다.
    EXPLORE_REQUIRE_COORDINATES가 켜져 있으면 좌표 없는 spot도 SPOT_NOT_FOUND다.
    """
    cache_key = await cache.spot_detail_key(uid)
    cached = await cache.get_cached(cache_key)
    if cached is not None:
        logger.info("cache hit spot_detail key=%s", cache_key)
        return Response(content=cached, media_type="application/json")
    logger.info("cache miss spot_detail key=%s", cache_key)

    spot = await crud_spot.get_spot_by_uid(session, uid, published_only=True)
    if spot is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")
    thumbnails = await crud_image.get_thumbnails_by_spots(session, [uid])
    detail = SpotDetail.model_validate(spot)
    detail.image_url = _resolve_thumbnail_url(thumbnails, uid)
    await cache.set_cached(
        cache_key, detail.model_dump_json(), settings.SPOT_DETAIL_CACHE_TTL_SECONDS
    )
    return detail


@router.get(
    "/spots/{uid}/images",
    response_model=list[SpotImageOut],
    summary=LIST_SPOT_IMAGES_SUMMARY,
)
async def list_spot_images(
    uid: str, session: AsyncSession = Depends(get_db)
) -> list[SpotImageOut]:
    """spot의 대표/상세 이미지 목록을 조회합니다 (비로그인 가능).

    is_public은 서빙 방식 구분(True=CDN URL, False=presigned URL)이며
    접근 제어가 아닙니다 — 모든 이미지가 비로그인 사용자에게 노출됩니다.
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
