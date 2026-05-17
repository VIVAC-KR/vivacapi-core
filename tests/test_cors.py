import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.core.config import Settings


# ---------------------------------------------------------------------------
# CORS middleware — preflight 응답 검증
# ---------------------------------------------------------------------------


async def test_preflight_from_allowed_origin_is_accepted(client: AsyncClient):
    response = await client.options(
        "/auth/google",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "POST" in response.headers["access-control-allow-methods"]


async def test_preflight_from_disallowed_origin_is_blocked(client: AsyncClient):
    response = await client.options(
        "/auth/google",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert "access-control-allow-origin" not in response.headers


# ---------------------------------------------------------------------------
# Settings — CORS_ALLOWED_ORIGINS 파싱 및 검증
# ---------------------------------------------------------------------------


_VALID_BASE = {
    "DB_HOST": "localhost",
    "DB_NAME": "vivac",
    "DB_USER": "vivac",
    "DB_PASSWORD": "pw",
    "GOOGLE_CLIENT_ID": "x.apps.googleusercontent.com",
    "JWT_SECRET_KEY": "x" * 64,
}

_VALID_PROD_BASE = {
    **_VALID_BASE,
    "ENVIRONMENT": "prod",
    "DB_HOST": "ls-xxx.ap-northeast-2.rds.amazonaws.com",
}


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**_VALID_BASE, **overrides})


def test_cors_origins_parsed_from_comma_separated_string():
    s = _settings(
        CORS_ALLOWED_ORIGINS="https://a.example.com, https://b.example.com"
    )
    assert s.CORS_ALLOWED_ORIGINS == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_cors_local_default_when_unset():
    s = _settings(ENVIRONMENT="local")
    assert s.CORS_ALLOWED_ORIGINS == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_cors_dev_default_is_empty_when_unset():
    s = _settings(ENVIRONMENT="dev")
    assert s.CORS_ALLOWED_ORIGINS == []


def test_prod_rejects_wildcard_origin():
    with pytest.raises(ValidationError, match="cannot include '\\*'"):
        Settings(
            _env_file=None,
            **_VALID_PROD_BASE,
            CORS_ALLOWED_ORIGINS="*",
        )


def test_prod_rejects_localhost_origin():
    with pytest.raises(ValidationError, match="not allowed in prod"):
        Settings(
            _env_file=None,
            **_VALID_PROD_BASE,
            CORS_ALLOWED_ORIGINS="http://localhost:3000",
        )


def test_prod_rejects_empty_origins():
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS must be set"):
        Settings(
            _env_file=None,
            **_VALID_PROD_BASE,
            CORS_ALLOWED_ORIGINS="",
        )
