"""S3 기반 이미지 스토리지 헬퍼.

- 업로드: presigned PUT URL을 발급해 클라이언트가 S3로 직접 올린다(EC2 우회).
- 공개 조회: CloudFront CDN URL을 그대로 반환한다(presigned 불필요).
- 비공개 조회: presigned GET URL을 발급한다.

presigned URL '생성'은 네트워크 호출이 아닌 로컬 서명이라 동기 호출해도 안전하다.
실제 객체 확인(head_object)만 네트워크 호출이므로 asyncio.to_thread로 감싼다.
"""

import asyncio

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from vivacapi.core.config import settings
from vivacapi.core.errors import AppException, ErrorCode

_client = None


def _s3():
    global _client
    if not settings.S3_BUCKET:
        raise AppException(
            ErrorCode.SERVICE_UNAVAILABLE, "Image storage is not configured"
        )
    if _client is None:
        _client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            endpoint_url=settings.S3_ENDPOINT_URL,
            config=Config(signature_version="s3v4"),
        )
    return _client


def generate_presigned_put(key: str, content_type: str) -> str:
    """클라이언트가 S3로 직접 PUT 업로드할 presigned URL을 발급한다."""
    return _s3().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.S3_BUCKET,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=settings.S3_PRESIGN_EXPIRE_SECONDS,
    )


def generate_presigned_get(key: str, filename: str | None = None) -> str:
    """비공개 객체를 조회할 presigned GET URL을 발급한다.

    filename을 주면 Content-Disposition을 설정해 브라우저가 그 이름으로
    바로 다운로드하게 한다(DB 덤프 등 원본 키가 사용자 친화적이지 않은 경우).
    """
    params: dict[str, str] = {"Bucket": settings.S3_BUCKET, "Key": key}
    if filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    return _s3().generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=settings.S3_PRESIGN_EXPIRE_SECONDS,
    )


def public_url(key: str) -> str:
    """공개 이미지를 서빙할 CDN URL을 만든다."""
    if not settings.CDN_BASE_URL:
        raise AppException(
            ErrorCode.SERVICE_UNAVAILABLE, "CDN base URL is not configured"
        )
    return f"{settings.CDN_BASE_URL.rstrip('/')}/{key}"


def resolve_url(key: str, is_public: bool) -> str:
    """공개 여부에 따라 적절한 조회 URL을 반환한다."""
    if is_public:
        return public_url(key)
    return generate_presigned_get(key)


async def object_exists(key: str) -> bool:
    """S3에 객체가 실제로 존재하는지 확인한다(register 단계 검증용)."""

    def _head() -> bool:
        try:
            _s3().head_object(Bucket=settings.S3_BUCKET, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    return await asyncio.to_thread(_head)


async def upload_file(key: str, file_path: str) -> None:
    """로컬 파일을 S3에 업로드한다(DB 덤프 등 큰 파일용)."""
    await asyncio.to_thread(_s3().upload_file, file_path, settings.S3_BUCKET, key)


async def copy_object(src_key: str, dest_key: str) -> None:
    """같은 버킷 안에서 객체를 복사한다(register 확정 시 pending → 최종 경로 이동용)."""
    await asyncio.to_thread(
        _s3().copy_object,
        Bucket=settings.S3_BUCKET,
        CopySource={"Bucket": settings.S3_BUCKET, "Key": src_key},
        Key=dest_key,
    )


async def delete_object(key: str) -> None:
    """S3 객체를 삭제한다(register 확정 후 pending 원본 정리용)."""
    await asyncio.to_thread(_s3().delete_object, Bucket=settings.S3_BUCKET, Key=key)
