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


@router.post("/{uid}/images/presign", response_model=ImagePresignResponse)
async def presign_image_upload(
    uid: str,
    payload: ImagePresignRequest,
    session: AsyncSession = Depends(get_db),
) -> ImagePresignResponse:
    """이미지 업로드용 presigned PUT URL을 발급한다.

    키는 서버가 생성하므로 클라이언트가 임의 경로에 쓰지 못한다.
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
)
async def register_image(
    uid: str,
    payload: SpotImageRegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> SpotImageOut:
    """S3 업로드가 끝난 이미지를 DB에 등록한다."""
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
