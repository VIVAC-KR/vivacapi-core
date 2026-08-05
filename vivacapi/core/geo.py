from typing import NamedTuple

from vivacapi.core.errors import AppException, ErrorCode


class BBox(NamedTuple):
    min_lng: float
    min_lat: float
    max_lng: float
    max_lat: float


def parse_bbox(raw: str) -> BBox:
    """`min_lng,min_lat,max_lng,max_lat` (GeoJSON/OGC 순서 — 경도 먼저).

    한국 좌표 범위(위도 33~38, 경도 124~132)는 서로 겹치지 않아 순서를 바꿔
    보내도 값 자체는 유효 범위 안이라 통과한다 — 그러면 에러 없이 빈 결과만
    돌아와 원인 추적이 어렵다. 그래서 min<max 위반은 조용히 빈 결과로 넘기지
    않고 명시적으로 거부한다.
    """
    parts = raw.split(",")
    if len(parts) != 4:
        raise AppException(
            ErrorCode.VALIDATION_ERROR,
            "bbox must be 'min_lng,min_lat,max_lng,max_lat'",
        )
    try:
        min_lng, min_lat, max_lng, max_lat = (float(p) for p in parts)
    except ValueError as exc:
        raise AppException(
            ErrorCode.VALIDATION_ERROR, "bbox values must be numbers"
        ) from exc

    if not (-180 <= min_lng <= 180 and -180 <= max_lng <= 180):
        raise AppException(ErrorCode.VALIDATION_ERROR, "bbox longitude out of range")
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise AppException(ErrorCode.VALIDATION_ERROR, "bbox latitude out of range")
    # 날짜변경선을 넘는 bbox(min_lng > max_lng)는 지원하지 않는다 — 국내 전용.
    if min_lng >= max_lng or min_lat >= max_lat:
        raise AppException(
            ErrorCode.VALIDATION_ERROR,
            "bbox must satisfy min_lng < max_lng and min_lat < max_lat "
            "(order is lng,lat — not lat,lng)",
        )
    return BBox(min_lng, min_lat, max_lng, max_lat)
