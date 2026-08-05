from fastapi import Depends, Request, status

from vivacapi.core import cache
from vivacapi.core.deps import get_current_user_optional
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.models.user import User

SPOTS_BULK_MAX_BYTES = 5 * 1024 * 1024


def _too_large() -> AppException:
    return AppException(
        ErrorCode.VALIDATION_ERROR,
        "Payload exceeds 5 MiB limit",
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
    )


async def enforce_spots_bulk_size(request: Request) -> None:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = None
        if declared is not None and declared > SPOTS_BULK_MAX_BYTES:
            raise _too_large()

    # Content-Length 없는(chunked) 요청도 한도 초과분을 메모리에 다 올리지 않도록
    # 스트림 단위로 검사하고 초과 시점에 즉시 끊는다. 소비한 body는
    # request._body에 되돌려 이후 JSON 파싱이 그대로 동작하게 한다.
    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > SPOTS_BULK_MAX_BYTES:
            raise _too_large()
        chunks.append(chunk)
    request._body = b"".join(chunks)


def rate_limit(scope: str, *, times: int, seconds: int):
    """scope별로 (로그인 유저는 uid, 아니면 클라이언트 IP) 요청 횟수를 제한한다.

    카운터는 Redis에 있고, REDIS_URL 미설정/Redis 장애 시에는 캐시와 동일하게
    fail-open한다 — 레이트 리밋 때문에 서비스가 멈추지는 않게 한다.

    ponytail: 고정 윈도우 카운터다. 윈도우 경계에서 순간적으로 2배까지 통과할
    수 있지만 남용 억제 목적엔 충분하다. 정밀한 제어가 필요하면 sliding window로.
    ponytail: 비로그인 요청 키는 peer IP다 — CloudFront 뒤에서는 여러 사용자가
    edge IP 하나로 뭉치므로 한도를 넉넉히 잡았다. IP 단위 정밀 제한이 필요해지면
    앱이 아니라 CloudFront/WAF rate rule로 올린다 (X-Forwarded-For는 EC2에
    직접 붙으면 위조 가능해 여기서 신뢰하지 않는다).
    """

    async def _dependency(
        request: Request,
        user: User | None = Depends(get_current_user_optional),
    ) -> None:
        if user is not None:
            actor = f"u:{user.uid}"
        elif request.client is not None:
            actor = f"ip:{request.client.host}"
        else:
            return
        count = await cache.incr_with_ttl(f"ratelimit:{scope}:{actor}", seconds)
        if count is not None and count > times:
            raise AppException(
                ErrorCode.RATE_LIMITED,
                f"Too many requests. Try again in {seconds}s.",
            )

    return _dependency
