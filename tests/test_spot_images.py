import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core import storage
from vivacapi.core.security import create_access_token
from vivacapi.models.spot import Spot
from tests.helpers import bearer, make_user


async def _make_staff_token(db: AsyncSession, suffix: str) -> str:
    user = await make_user(
        db, email=f"staff-{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    user.is_staff = True
    await db.commit()
    return create_access_token(user.uid)


async def _make_spot(db: AsyncSession) -> Spot:
    spot = Spot(
        title="이미지 캠핑장", rating_avg=0.0, review_count=0,
        pipeline_status="PUBLISHED",  # 공개 이미지 조회 경로가 PUBLISHED만 노출
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


@pytest.fixture
def fake_storage(monkeypatch):
    """S3 호출을 막고 로컬에서 검증 가능한 값으로 대체."""
    monkeypatch.setattr(
        storage, "generate_presigned_put", lambda key, ct: f"https://s3.fake/{key}"
    )
    monkeypatch.setattr(
        storage, "resolve_url", lambda key, is_public: f"https://cdn.fake/{key}"
    )

    async def _exists(key: str) -> bool:
        return not key.endswith("missing.jpg")

    monkeypatch.setattr(storage, "object_exists", _exists)


# ---------------------------------------------------------------------------
# POST /v1/internal/spots/{uid}/images/presign
# ---------------------------------------------------------------------------


async def test_presign_requires_auth(db_client: AsyncClient):
    response = await db_client.post(
        "/v1/internal/spots/x/images/presign",
        json={"filename": "a.jpg", "content_type": "image/jpeg"},
    )
    assert response.status_code == 401


async def test_presign_unknown_spot_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    token = await _make_staff_token(db_session, "img1")
    response = await db_client.post(
        "/v1/internal/spots/no-such-spot/images/presign",
        json={"filename": "a.jpg", "content_type": "image/jpeg"},
        headers=bearer(token),
    )
    assert response.status_code == 404


async def test_presign_rejects_disallowed_content_type(
    db_client: AsyncClient, db_session: AsyncSession
):
    token = await _make_staff_token(db_session, "img2")
    response = await db_client.post(
        "/v1/internal/spots/x/images/presign",
        json={"filename": "a.gif", "content_type": "image/gif"},
        headers=bearer(token),
    )
    assert response.status_code == 422


async def test_presign_returns_scoped_key(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage
):
    token = await _make_staff_token(db_session, "img3")
    spot = await _make_spot(db_session)

    response = await db_client.post(
        f"/v1/internal/spots/{spot.uid}/images/presign",
        json={"filename": "a.jpg", "content_type": "image/jpeg"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    body = response.json()
    # 서버가 키를 생성하므로 해당 spot 경로 밖으로 나갈 수 없다
    assert body["s3_key"].startswith(f"spots/{spot.uid}/")
    assert body["s3_key"].endswith(".jpg")
    assert body["upload_url"] == f"https://s3.fake/{body['s3_key']}"


# ---------------------------------------------------------------------------
# POST /v1/internal/spots/{uid}/images — 등록
# ---------------------------------------------------------------------------


async def test_register_rejects_key_of_other_spot(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage
):
    token = await _make_staff_token(db_session, "img4")
    spot = await _make_spot(db_session)

    response = await db_client.post(
        f"/v1/internal/spots/{spot.uid}/images",
        json={"s3_key": "spots/other-spot/x.jpg"},
        headers=bearer(token),
    )
    assert response.status_code == 422


async def test_register_rejects_missing_object(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage
):
    token = await _make_staff_token(db_session, "img5")
    spot = await _make_spot(db_session)

    response = await db_client.post(
        f"/v1/internal/spots/{spot.uid}/images",
        json={"s3_key": f"spots/{spot.uid}/missing.jpg"},
        headers=bearer(token),
    )
    assert response.status_code == 422


async def test_register_then_public_listing(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage
):
    token = await _make_staff_token(db_session, "img6")
    spot = await _make_spot(db_session)
    key = f"spots/{spot.uid}/photo.jpg"

    created = await db_client.post(
        f"/v1/internal/spots/{spot.uid}/images",
        json={"s3_key": key, "role": "thumbnail", "sort_order": 1},
        headers=bearer(token),
    )
    assert created.status_code == 201
    assert created.json()["role"] == "thumbnail"

    # 공개 조회 (비로그인)
    listing = await db_client.get(f"/v1/explore/spots/{spot.uid}/images")
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 1
    assert items[0]["url"] == f"https://cdn.fake/{key}"
