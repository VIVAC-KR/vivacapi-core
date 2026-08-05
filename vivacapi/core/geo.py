from typing import NamedTuple

from vivacapi.core.errors import AppException, ErrorCode


class BBox(NamedTuple):
    min_lng: float
    min_lat: float
    max_lng: float
    max_lat: float


# 국내 육상/도서 영역을 여유 있게 감싼 WGS84 범위.
# 국경을 엄밀히 긋는 값이 아니라 "좌표계가 통째로 틀렸는가"를 잡는 용도다 —
# 카텍/TM 같은 미터 단위 좌표계는 값이 수십만 단위라 첫 행에서 걸린다.
# 실제 극단값(마라도 33.06N, 백령도 124.6E, 독도 131.87E, 최북단 38.6N)보다
# 넉넉히 잡아, 경계 근처 도서를 잘못 거부하지 않게 한다.
KOREA_LAT_RANGE = (32.5, 38.7)
KOREA_LNG_RANGE = (124.0, 132.5)


def is_within_korea(latitude: float, longitude: float) -> bool:
    return (
        KOREA_LAT_RANGE[0] <= latitude <= KOREA_LAT_RANGE[1]
        and KOREA_LNG_RANGE[0] <= longitude <= KOREA_LNG_RANGE[1]
    )


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
