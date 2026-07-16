import os

import shortuuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core import storage
from vivacapi.core.config import settings
from vivacapi.core.database import get_db
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud import spot as crud_spot
from vivacapi.crud import spot_image as crud_image
from vivacapi.schemas.spot_image import (
    ImagePresignRequest,
    ImagePresignResponse,
    SpotImageOut,
    SpotImageRegisterRequest,
)

router = APIRouter()

# content_type → 파일 확장자 (presign 시 키 생성용)
_EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


async def _get_spot_or_404(session: AsyncSession, uid: str) -> None:
    if await crud_spot.get_spot_by_uid(session, uid) is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")


@router.post(
    "/{uid}/images/presign",
    response_model=ImagePresignResponse,
    summary="업로드용 presigned URL 발급",
)
async def presign_image_upload(
    uid: str,
    payload: ImagePresignRequest,
    session: AsyncSession = Depends(get_db),
) -> ImagePresignResponse:
    """이미지 업로드용 presigned PUT URL을 발급한다.

    키는 서버가 생성하므로 클라이언트가 임의 경로에 쓰지 못한다. 발급된
    URL로 S3에 직접 PUT 업로드한 뒤, 응답의 s3_key로 등록 API
    (`POST /{uid}/images`)를 호출해야 최종 등록된다 — presign, S3 업로드,
    등록의 2단계 흐름이다. content_type은 ALLOWED_CONTENT_TYPES(image/jpeg,
    image/png, image/webp)만 허용하고(그 외 값은 422), URL은
    expires_in(초) 이후 만료된다.
    """
    await _get_spot_or_404(session, uid)

    ext = _EXT_BY_CONTENT_TYPE.get(payload.content_type, "")
    s3_key = f"spots/{uid}/{shortuuid.uuid()}{ext}"
    upload_url = storage.generate_presigned_put(s3_key, payload.content_type)

    return ImagePresignResponse(
        upload_url=upload_url,
        s3_key=s3_key,
        expires_in=settings.S3_PRESIGN_EXPIRE_SECONDS,
    )


@router.post(
    "/{uid}/images",
    response_model=SpotImageOut,
    status_code=status.HTTP_201_CREATED,
    summary="이미지 등록",
)
async def register_image(
    uid: str,
    payload: SpotImageRegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> SpotImageOut:
    """S3 업로드가 끝난 이미지를 DB에 등록한다.

    presign 단계에서 발급받은 s3_key만 허용하며(다른 spot나 임의 경로는
    거부), S3에 실제로 업로드됐는지 확인한 뒤 저장한다(미업로드 시 422).
    role은 THUMBNAIL(대표 이미지)/DETAIL(상세 이미지)이고, sort_order는
    노출 순서이자 THUMBNAIL이 여러 장일 때 대표를 가리는 기준(값이 가장
    작은 것)이다. is_public은 접근 제어가 아니라 서빙 방식 구분일 뿐이며
    — CDN URL(True)이든 presigned URL(False)이든 둘 다 공개 API에
    노출된다.
    """
    await _get_spot_or_404(session, uid)

    # presign이 발급한 키만 허용해 다른 spot/임의 경로 등록을 막는다.
    if os.path.dirname(payload.s3_key) != f"spots/{uid}":
        raise AppException(
            ErrorCode.VALIDATION_ERROR, "s3_key does not belong to this spot"
        )

    if not await storage.object_exists(payload.s3_key):
        raise AppException(
            ErrorCode.VALIDATION_ERROR, "Uploaded object not found in storage"
        )

    image = await crud_image.create_image(
        session,
        spot_uid=uid,
        s3_key=payload.s3_key,
        role=payload.role,
        sort_order=payload.sort_order,
        is_public=payload.is_public,
        content_type=payload.content_type,
    )

    return SpotImageOut(
        uid=image.uid,
        role=image.role,
        sort_order=image.sort_order,
        is_public=image.is_public,
        url=storage.resolve_url(image.s3_key, image.is_public),
    )
