import pytest
import shortuuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core import storage
from vivacapi.core.security import create_access_token
from vivacapi.models.spot import Spot
from vivacapi.models.spot_image import SpotImage
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
        title="이미지 캠핑장",
        rating_avg=0.0,
        review_count=0,
        pipeline_status="PUBLISHED",  # 공개 이미지 조회 경로가 PUBLISHED만 노출
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


# S3에 없는 객체를 흉내내는 키. 등록 API가 키 '형식'부터 검사하므로
# presign이 발급하는 형태(22자 shortuuid)를 그대로 유지해야 한다.
_MISSING_STEM = "missingObject000000000"


def _presign_key(spot_uid: str, stem: str | None = None) -> str:
    return f"spots/{spot_uid}/{stem or shortuuid.uuid()}.jpg"


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
        return _MISSING_STEM not in key

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
        json={"s3_key": _presign_key("other-spot")},
        headers=bearer(token),
    )
    assert response.status_code == 422


async def test_register_rejects_key_not_issued_by_presign(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage
):
    """prefix만 맞고 presign이 발급한 형식이 아닌 키(임의 객체)는 거부한다."""
    token = await _make_staff_token(db_session, "img4b")
    spot = await _make_spot(db_session)

    response = await db_client.post(
        f"/v1/internal/spots/{spot.uid}/images",
        json={"s3_key": f"spots/{spot.uid}/photo.jpg"},
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
        json={"s3_key": _presign_key(spot.uid, _MISSING_STEM)},
        headers=bearer(token),
    )
    assert response.status_code == 422


async def test_register_then_public_listing(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage
):
    token = await _make_staff_token(db_session, "img6")
    spot = await _make_spot(db_session)
    key = _presign_key(spot.uid)

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


async def _register_image(
    db_client: AsyncClient, token: str, spot_uid: str, **overrides
) -> dict:
    key = _presign_key(spot_uid)
    payload = {"s3_key": key, "role": "detail", "sort_order": 0, **overrides}
    response = await db_client.post(
        f"/v1/internal/spots/{spot_uid}/images",
        json=payload,
        headers=bearer(token),
    )
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------------------
# PATCH /v1/internal/spots/{uid}/images/{image_uid} — 수정
# ---------------------------------------------------------------------------


async def test_update_image_requires_auth(db_client: AsyncClient):
    response = await db_client.patch(
        "/v1/internal/spots/x/images/y", json={"role": "thumbnail"}
    )
    assert response.status_code == 401


async def test_update_image_unknown_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    token = await _make_staff_token(db_session, "img7")
    spot = await _make_spot(db_session)

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}/images/no-such-image",
        json={"role": "thumbnail"},
        headers=bearer(token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SPOT_IMAGE_NOT_FOUND"


async def test_update_image_rejects_other_spots_image(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage
):
    token = await _make_staff_token(db_session, "img8")
    spot = await _make_spot(db_session)
    other_spot = await _make_spot(db_session)
    image = await _register_image(db_client, token, other_spot.uid)

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}/images/{image['uid']}",
        json={"role": "thumbnail"},
        headers=bearer(token),
    )
    assert response.status_code == 404


async def test_update_image_role_reflected_in_public_listing(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage
):
    token = await _make_staff_token(db_session, "img9")
    spot = await _make_spot(db_session)
    image = await _register_image(db_client, token, spot.uid, role="detail")

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}/images/{image['uid']}",
        json={"role": "thumbnail"},
        headers=bearer(token),
    )
    assert response.status_code == 200
    assert response.json()["role"] == "thumbnail"

    listing = await db_client.get(f"/v1/explore/spots/{spot.uid}/images")
    assert listing.json()[0]["role"] == "thumbnail"


async def test_update_image_partial_leaves_other_fields_untouched(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage
):
    token = await _make_staff_token(db_session, "img10")
    spot = await _make_spot(db_session)
    image = await _register_image(
        db_client, token, spot.uid, role="detail", sort_order=5, is_public=False
    )

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}/images/{image['uid']}",
        json={"role": "thumbnail"},
        headers=bearer(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "thumbnail"
    assert body["sort_order"] == 5
    assert body["is_public"] is False


# ---------------------------------------------------------------------------
# DELETE /v1/internal/spots/{uid}/images/{image_uid} — 삭제
# ---------------------------------------------------------------------------


async def test_delete_image_requires_auth(db_client: AsyncClient):
    response = await db_client.delete("/v1/internal/spots/x/images/y")
    assert response.status_code == 401


async def test_delete_image_unknown_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    token = await _make_staff_token(db_session, "img11")
    spot = await _make_spot(db_session)

    response = await db_client.delete(
        f"/v1/internal/spots/{spot.uid}/images/no-such-image",
        headers=bearer(token),
    )
    assert response.status_code == 404


async def test_delete_image_rejects_other_spots_image(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage
):
    token = await _make_staff_token(db_session, "img12")
    spot = await _make_spot(db_session)
    other_spot = await _make_spot(db_session)
    image = await _register_image(db_client, token, other_spot.uid)

    response = await db_client.delete(
        f"/v1/internal/spots/{spot.uid}/images/{image['uid']}",
        headers=bearer(token),
    )
    assert response.status_code == 404


async def test_delete_image_soft_deletes_and_keeps_row(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage
):
    """DB row와 S3 객체는 남기고 deleted_at만 세팅한다 (복구 가능성 유지)."""
    token = await _make_staff_token(db_session, "img13")
    spot = await _make_spot(db_session)
    image = await _register_image(db_client, token, spot.uid)

    response = await db_client.delete(
        f"/v1/internal/spots/{spot.uid}/images/{image['uid']}",
        headers=bearer(token),
    )
    assert response.status_code == 204

    listing = await db_client.get(f"/v1/explore/spots/{spot.uid}/images")
    assert listing.json() == []

    row = await db_session.get(SpotImage, image["uid"])
    assert row is not None
    assert row.deleted_at is not None
