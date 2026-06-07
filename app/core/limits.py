from fastapi import Request, status

from app.core.errors import AppException, ErrorCode

SPOTS_BULK_MAX_BYTES = 5 * 1024 * 1024


async def enforce_spots_bulk_size(request: Request) -> None:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = None
        if declared is not None and declared > SPOTS_BULK_MAX_BYTES:
            raise AppException(
                ErrorCode.VALIDATION_ERROR,
                "Payload exceeds 5 MiB limit",
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )

    body = await request.body()
    if len(body) > SPOTS_BULK_MAX_BYTES:
        raise AppException(
            ErrorCode.VALIDATION_ERROR,
            "Payload exceeds 5 MiB limit",
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        )
