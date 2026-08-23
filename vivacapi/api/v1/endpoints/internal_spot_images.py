import logging
import re

import shortuuid
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.api.v1.endpoints.summaries import (
    DELETE_IMAGE_SUMMARY,
    PRESIGN_IMAGE_UPLOAD_SUMMARY,
    REGISTER_IMAGE_SUMMARY,
    UPDATE_IMAGE_SUMMARY,
)
from vivacapi.core import storage
from vivacapi.core.config import settings
from vivacapi.core.database import get_db
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud import spot as crud_spot
from vivacapi.crud import spot_image as crud_image
from vivacapi.models.spot_image import SpotImage
from vivacapi.schemas.spot_image import (
    ImagePresignRequest,
    ImagePresignResponse,
    SpotImageOut,
    SpotImageRegisterRequest,
    SpotImageUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# content_type → 파일 확장자 (presign 시 키 생성용)
_EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

# register가 끝내 호출되지 않아도 S3에 orphan으로 남지 않도록, presign은
# 최종 경로가 아닌 pending prefix에 키를 발급한다. 이 prefix는 S3 lifecycle
# rule(별도 vivac-infra 작업)로 N일 후 자동 삭제되고, register가 정상
# 호출되면 서버가 최종 경로(spots/{uid}/{key})로 copy 후 pending 원본을
# delete한다.
_PENDING_PREFIX = "uploads/pending"


def _pending_key_re(spot_uid: str) -> re.Pattern[str]:
    exts = "|".join(re.escape(ext) for ext in _EXT_BY_CONTENT_TYPE.values())
    return re.compile(
        rf"{_PENDING_PREFIX}/{re.escape(spot_uid)}/([0-9A-Za-z]{{22}}(?:{exts}))"
    )


async def _get_spot_or_404(session: AsyncSession, uid: str) -> None:
    if await crud_spot.get_spot_by_uid(session, uid) is None:
        raise AppException(ErrorCode.SPOT_NOT_FOUND, "Spot not found")


async def _get_image_or_404(
    session: AsyncSession, spot_uid: str, image_uid: str
) -> SpotImage:
    image = await crud_image.get_image_by_uid(session, spot_uid, image_uid)
    if image is None:
        raise AppException(ErrorCode.SPOT_IMAGE_NOT_FOUND, "Spot image not found")
    return image


@router.post(
    "/{uid}/images/presign",
    response_model=ImagePresignResponse,
    summary=PRESIGN_IMAGE_UPLOAD_SUMMARY,
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

    키는 최종 경로가 아닌 pending prefix(`uploads/pending/{uid}/...`)에
    발급된다 — register를 호출하지 않아도 S3에 영구히 남는 orphan 객체를
    막기 위함.
    """
    await _get_spot_or_404(session, uid)

    ext = _EXT_BY_CONTENT_TYPE.get(payload.content_type, "")
    s3_key = f"{_PENDING_PREFIX}/{uid}/{shortuuid.uuid()}{ext}"
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
    summary=REGISTER_IMAGE_SUMMARY,
)
async def register_image(
    uid: str,
    payload: SpotImageRegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> SpotImageOut:
    """S3 업로드가 끝난 이미지를 DB에 등록한다.

    presign 단계에서 발급받은 s3_key(pending prefix)만 허용하며(다른
    spot나 임의 경로는 거부), spot당 활성 이미지 수가
    IMAGE_MAX_COUNT_PER_SPOT 이상이면 422로 거부한다(VAC-16). S3에
    실제로 업로드됐는지 확인한 뒤(미업로드 시 422) IMAGE_MAX_BYTES를
    초과하면 객체를 삭제하고 422로 거부한다 —
    presigned PUT은 업로드 시점에 크기를 강제하지 못해 등록 시점에 사후
    검증한다. 통과하면 최종 경로(`spots/{uid}/{key}`)로 옮기고 저장한다.
    role은 THUMBNAIL(대표 이미지)/DETAIL(상세 이미지)이고, sort_order는
    노출 순서이자 THUMBNAIL이 여러 장일 때 대표를 가리는 기준(값이 가장
    작은 것)이다. is_public은 접근 제어가 아니라 서빙 방식 구분일 뿐이며
    — CDN URL(True)이든 presigned URL(False)이든 둘 다 공개 API에
    노출된다.
    """
    await _get_spot_or_404(session, uid)

    # presign이 발급한 키 형태(pending prefix)만 허용해 다른 spot이나
    # 버킷의 임의 객체를 이 spot 이미지로 등록하지 못하게 한다.
    match = _pending_key_re(uid).fullmatch(payload.s3_key)
    if not match:
        raise AppException(
            ErrorCode.VALIDATION_ERROR, "s3_key does not belong to this spot"
        )

    current_count = await crud_image.count_images_by_spot(session, uid)
    if current_count >= settings.IMAGE_MAX_COUNT_PER_SPOT:
        raise AppException(
            ErrorCode.SPOT_IMAGE_COUNT_LIMIT_EXCEEDED,
            f"Spot already has the maximum of {settings.IMAGE_MAX_COUNT_PER_SPOT} images",
        )

    size = await storage.head_object(payload.s3_key)
    if size is None:
        raise AppException(
            ErrorCode.VALIDATION_ERROR, "Uploaded object not found in storage"
        )
    if size > settings.IMAGE_MAX_BYTES:
        # 삭제 실패(S3 일시 장애 등)해도 클라이언트에는 진짜 원인(크기 초과)을
        # 알려야 한다 — 못 지운 객체는 VAC-15 orphan 정리가 나중에 치운다.
        try:
            await storage.delete_object(payload.s3_key)
        except ClientError:
            logger.exception(
                "Failed to delete oversized image object %s", payload.s3_key
            )
        raise AppException(
            ErrorCode.SPOT_IMAGE_TOO_LARGE,
            f"Image exceeds the {settings.IMAGE_MAX_BYTES // (1024 * 1024)}MB limit",
        )

    final_key = f"spots/{uid}/{match.group(1)}"
    await storage.copy_object(payload.s3_key, final_key)

    # DB insert가 실패하면 방금 copy한 final_key 객체를 되돌려 lifecycle
    # rule이 안 걸리는(pending prefix 밖) orphan으로 남지 않게 한다.
    # pending 원본은 아직 지우지 않았으므로 register 재시도가 가능하다.
    try:
        image = await crud_image.create_image(
            session,
            spot_uid=uid,
            s3_key=final_key,
            role=payload.role,
            sort_order=payload.sort_order,
            is_public=payload.is_public,
            content_type=payload.content_type,
        )
    except Exception:
        # 롤백(delete) 자체가 실패해도 원래 예외(진짜 원인)를 가리면 안 되고,
        # final_key가 pending prefix 밖 orphan으로 남는지도 로그로 남긴다.
        try:
            await storage.delete_object(final_key)
        except Exception:
            logger.exception(
                "failed to roll back copied object %s after register failure",
                final_key,
            )
        raise

    await storage.delete_object(payload.s3_key)

    return SpotImageOut(
        uid=image.uid,
        role=image.role,
        sort_order=image.sort_order,
        is_public=image.is_public,
        url=storage.resolve_url(image.s3_key, image.is_public),
    )


@router.patch(
    "/{uid}/images/{image_uid}",
    response_model=SpotImageOut,
    summary=UPDATE_IMAGE_SUMMARY,
)
async def update_image(
    uid: str,
    image_uid: str,
    payload: SpotImageUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> SpotImageOut:
    """role/sort_order/is_public을 부분 수정한다(전달된 필드만 반영).

    이미지가 요청한 spot uid 소유가 아니면(다른 spot 것이거나 존재하지
    않으면) 404 SPOT_IMAGE_NOT_FOUND. 한 spot에 role=thumbnail이 여러 장
    동시에 있을 수 있는 기존 데이터 모델은 그대로 두고, 서버가 단일화를
    강제하지 않는다 — 대표 선정은 sort_order로 가른다.
    """
    image = await _get_image_or_404(session, uid, image_uid)

    image = await crud_image.update_image(
        session, image, payload.model_dump(exclude_unset=True)
    )

    return SpotImageOut(
        uid=image.uid,
        role=image.role,
        sort_order=image.sort_order,
        is_public=image.is_public,
        url=storage.resolve_url(image.s3_key, image.is_public),
    )


@router.delete(
    "/{uid}/images/{image_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=DELETE_IMAGE_SUMMARY,
)
async def delete_image(
    uid: str,
    image_uid: str,
    session: AsyncSession = Depends(get_db),
) -> None:
    """이미지를 soft delete한다 — deleted_at만 세팅하고 DB row/S3 객체는 남긴다
    (복구 가능성 유지). 이후 목록/공개 API에서는 제외된다.

    이미지가 요청한 spot uid 소유가 아니면 404 SPOT_IMAGE_NOT_FOUND.
    """
    image = await _get_image_or_404(session, uid, image_uid)
    await crud_image.delete_image(session, image)
