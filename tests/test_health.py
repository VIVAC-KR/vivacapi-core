import pytest
from httpx import AsyncClient

from vivacapi import __version__


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_body(client: AsyncClient):
    response = await client.get("/health")
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "local"


@pytest.mark.asyncio
async def test_scalar_docs_shows_version_and_git_sha_badge(client: AsyncClient):
    response = await client.get("/scalar")
    assert response.status_code == 200
    assert f"v{__version__} (dev)" in response.text
