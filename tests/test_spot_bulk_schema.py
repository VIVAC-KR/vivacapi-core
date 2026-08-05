import pytest
from pydantic import ValidationError
from starlette.requests import Request

from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.core.limits import SPOTS_BULK_MAX_BYTES, enforce_spots_bulk_size
from vivacapi.schemas.spot import SpotBulkRequest, SpotBulkRow


def _make_request(body: bytes, *, content_length: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if content_length is not None:
        headers.append((b"content-length", content_length.encode()))

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/internal/spots/bulk",
        "headers": headers,
    }
    return Request(scope, receive)


# ---------------------------------------------------------------------------
# SpotBulkRow / SpotBulkRequest 스키마
# ---------------------------------------------------------------------------


def test_minimal_row_requires_only_title():
    row = SpotBulkRow(title="Camp A")

    assert row.title == "Camp A"
    assert row.external_id is None
    assert row.rating_avg == 0.0
    assert row.review_count == 0


def test_row_accepts_all_optional_columns():
    row = SpotBulkRow(
        source="seed",
        external_id="ext-1",
        title="Camp B",
        address="서울시 강남구",
        latitude=37.5,
        longitude=127.0,
        themes=["family", "river"],
        amenities=["wifi"],
        rating_avg=4.5,
        review_count=12,
    )

    assert row.themes == ["family", "river"]
    assert row.rating_avg == 4.5
    assert row.review_count == 12


def test_row_missing_title_raises():
    with pytest.raises(ValidationError):
        SpotBulkRow()


def test_valid_request_passes():
    req = SpotBulkRequest(rows=[SpotBulkRow(title="A"), SpotBulkRow(title="B")])

    assert req.dry_run is False
    assert len(req.rows) == 2


def test_empty_rows_raises():
    with pytest.raises(ValidationError):
        SpotBulkRequest(rows=[])


def test_row_count_over_limit_raises():
    rows = [SpotBulkRow(title=f"S{i}") for i in range(5001)]

    with pytest.raises(ValidationError):
        SpotBulkRequest(rows=rows)


def test_row_count_at_limit_passes():
    rows = [SpotBulkRow(title=f"S{i}") for i in range(5000)]

    req = SpotBulkRequest(rows=rows)

    assert len(req.rows) == 5000


# ---------------------------------------------------------------------------
# enforce_spots_bulk_size 의존성
# ---------------------------------------------------------------------------


async def test_size_under_limit_passes():
    request = _make_request(b"x" * 1024)

    await enforce_spots_bulk_size(request)


async def test_size_at_limit_passes():
    request = _make_request(b"x" * SPOTS_BULK_MAX_BYTES)

    await enforce_spots_bulk_size(request)


async def test_size_over_limit_raises_413_via_content_length():
    declared = str(SPOTS_BULK_MAX_BYTES + 1)
    request = _make_request(b"", content_length=declared)

    with pytest.raises(AppException) as exc:
        await enforce_spots_bulk_size(request)

    assert exc.value.status_code == 413
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


async def test_size_over_limit_raises_413_via_body():
    body = b"x" * (SPOTS_BULK_MAX_BYTES + 1)
    request = _make_request(body)

    with pytest.raises(AppException) as exc:
        await enforce_spots_bulk_size(request)

    assert exc.value.status_code == 413
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


# ---------------------------------------------------------------------------
# 좌표계 검증 — WGS84가 아닌 적재를 입구에서 막는다
# ---------------------------------------------------------------------------


def test_row_accepts_korean_wgs84_coordinates():
    row = SpotBulkRow(title="남이섬 오토캠핑장", latitude=37.7907, longitude=127.5262)

    assert (row.latitude, row.longitude) == (37.7907, 127.5262)


@pytest.mark.parametrize(
    ("latitude", "longitude", "label"),
    [
        (445000.0, 195000.0, "카텍/TM 등 미터 단위 좌표계"),
        (127.5262, 37.7907, "lat/lng 뒤바뀜"),
        (37.7907, -122.4194, "해외 좌표 (샌프란시스코)"),
        (0.0, 0.0, "null island"),
    ],
)
def test_row_rejects_non_wgs84_coordinates(latitude, longitude, label):
    with pytest.raises(ValidationError) as exc_info:
        SpotBulkRow(title="Camp A", latitude=latitude, longitude=longitude)

    assert "outside Korea" in str(exc_info.value), label


def test_row_allows_missing_coordinates():
    """좌표 미적재 spot은 여전히 통과한다 — 적재 전 데이터가 막히면 안 된다."""
    row = SpotBulkRow(title="좌표 없는 스팟")

    assert row.latitude is None
    assert row.longitude is None


def test_bulk_request_reports_offending_row_index():
    with pytest.raises(ValidationError) as exc_info:
        SpotBulkRequest(
            rows=[
                {"title": "정상", "latitude": 37.79, "longitude": 127.52},
                {"title": "이상", "latitude": 445000.0, "longitude": 195000.0},
            ]
        )

    # 5000행 중 어느 행이 문제인지 알 수 있어야 재적재가 가능하다.
    assert exc_info.value.errors()[0]["loc"][:2] == ("rows", 1)
