import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.errors import AppException, ErrorCode
from app.main import (
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)


def _make_test_app() -> FastAPI:
    """에러 핸들러만 떼어내 검증하기 위한 격리 앱."""
    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError

    test_app = FastAPI()
    test_app.add_exception_handler(AppException, app_exception_handler)
    test_app.add_exception_handler(
        RequestValidationError, validation_exception_handler
    )
    test_app.add_exception_handler(HTTPException, http_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)

    class _Body(BaseModel):
        value: int

    @test_app.post("/echo")
    async def echo(body: _Body) -> dict:
        return {"value": body.value}

    @test_app.get("/raise/{code}")
    async def raise_code(code: str) -> None:
        raise AppException(ErrorCode(code), f"raised {code}")

    @test_app.get("/raise-with-details")
    async def raise_with_details() -> None:
        raise AppException(
            ErrorCode.USER_NOT_FOUND, "user missing", details={"user_id": "abc"}
        )

    @test_app.get("/raise-http")
    async def raise_http() -> None:
        raise HTTPException(status_code=404, detail="Not Found")

    @test_app.get("/raise-bare")
    async def raise_bare() -> None:
        raise RuntimeError("boom")

    return test_app


@pytest.fixture
async def err_client() -> AsyncClient:
    transport = ASGITransport(app=_make_test_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# 6 standard error codes — AppException 포맷 검증
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,expected_status",
    [
        (ErrorCode.UNAUTHORIZED, 401),
        (ErrorCode.FORBIDDEN, 403),
        (ErrorCode.USER_NOT_FOUND, 404),
        (ErrorCode.VALIDATION_ERROR, 422),
        (ErrorCode.INTERNAL_ERROR, 500),
        (ErrorCode.SERVICE_UNAVAILABLE, 503),
    ],
)
async def test_app_exception_maps_each_standard_code(
    err_client: AsyncClient, code: ErrorCode, expected_status: int
):
    response = await err_client.get(f"/raise/{code.value}")
    assert response.status_code == expected_status
    body = response.json()
    assert body == {
        "error": {
            "code": code.value,
            "message": f"raised {code.value}",
            "details": None,
        }
    }


async def test_app_exception_includes_details(err_client: AsyncClient):
    response = await err_client.get("/raise-with-details")
    assert response.status_code == 404
    assert response.json()["error"]["details"] == {"user_id": "abc"}


# ---------------------------------------------------------------------------
# Handler-specific behavior
# ---------------------------------------------------------------------------


async def test_request_validation_error_returns_422_with_details(
    err_client: AsyncClient,
):
    response = await err_client.post("/echo", json={"value": "not-an-int"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
    assert isinstance(body["error"]["details"], list)
    assert body["error"]["details"]  # 비어있지 않음


async def test_http_exception_is_wrapped_in_standard_format(
    err_client: AsyncClient,
):
    response = await err_client.get("/raise-http")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == ErrorCode.USER_NOT_FOUND.value
    assert body["error"]["message"] == "Not Found"


async def test_unhandled_exception_returns_500_internal_error(
    err_client: AsyncClient,
):
    response = await err_client.get("/raise-bare")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == ErrorCode.INTERNAL_ERROR.value
    assert body["error"]["message"] == "Internal server error"
    assert body["error"]["details"] is None
