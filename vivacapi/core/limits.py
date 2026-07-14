from fastapi import Request, status

from vivacapi.core.errors import AppException, ErrorCode

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
