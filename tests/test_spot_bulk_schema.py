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
