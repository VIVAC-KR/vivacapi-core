import pytest
import shortuuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.api.v1.endpoints import internal_spot_images
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


def _pending_key(spot_uid: str, stem: str | None = None) -> str:
    """presign이 발급하는 pending prefix 키 형태(register 입력용)."""
    return f"uploads/pending/{spot_uid}/{stem or shortuuid.uuid()}.jpg"


def _final_key(spot_uid: str, stem: str) -> str:
    """register가 확정 저장하는 최종 경로(pending → 여기로 copy+delete됨)."""
    return f"spots/{spot_uid}/{stem}.jpg"


@pytest.fixture
def fake_storage(monkeypatch):
    """S3 호출을 막고 로컬에서 검증 가능한 값으로 대체."""
    calls = {"copied": [], "deleted": []}
    monkeypatch.setattr(
        storage, "generate_presigned_put", lambda key, ct: f"https://s3.fake/{key}"
    )
    monkeypatch.setattr(
        storage, "resolve_url", lambda key, is_public: f"https://cdn.fake/{key}"
    )

    async def _head(key: str) -> int | None:
        return None if _MISSING_STEM in key else 1024

    async def _copy(src_key: str, dest_key: str) -> None:
        calls["copied"].append((src_key, dest_key))

    async def _delete(key: str) -> None:
        calls["deleted"].append(key)

    monkeypatch.setattr(storage, "head_object", _head)
    monkeypatch.setattr(storage, "copy_object", _copy)
    monkeypatch.setattr(storage, "delete_object", _delete)
    return calls


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
    # 서버가 키를 생성하므로 해당 spot 경로 밖으로 나갈 수 없다.
    # 최종 경로(spots/)가 아닌 pending prefix로 발급된다 — register가
    # 호출되지 않아도 S3에 orphan으로 영구히 남지 않도록(VAC-15).
    assert body["s3_key"].startswith(f"uploads/pending/{spot.uid}/")
    assert body["s3_key"].endswith(".jpg")
    assert body["upload_url"] == f"https://s3.fake/{body['s3_key']}"


async def test_presign_rate_limited_after_threshold(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage, monkeypatch
):
    """한도(30회/분) 초과 시 429 — presign/register가 scope를 공유하는지도 확인."""
    from vivacapi.core import cache

    counts: dict[str, int] = {}

    async def _incr(key: str, ttl_seconds: int) -> int:
        counts[key] = counts.get(key, 0) + 1
        return counts[key]

    monkeypatch.setattr(cache, "incr_with_ttl", _incr)

    token = await _make_staff_token(db_session, "img-rl")
    spot = await _make_spot(db_session)

    for _ in range(30):
        response = await db_client.post(
            f"/v1/internal/spots/{spot.uid}/images/presign",
            json={"filename": "a.jpg", "content_type": "image/jpeg"},
            headers=bearer(token),
        )
        assert response.status_code == 200

    response = await db_client.post(
        f"/v1/internal/spots/{spot.uid}/images",
        json={"s3_key": _pending_key(spot.uid)},
        headers=bearer(token),
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


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
        json={"s3_key": _pending_key("other-spot")},
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
        json={"s3_key": f"uploads/pending/{spot.uid}/photo.jpg"},
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
        json={"s3_key": _pending_key(spot.uid, _MISSING_STEM)},
        headers=bearer(token),
    )
    assert response.status_code == 422


async def test_register_rejects_oversized_object_and_deletes_it(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage, monkeypatch
):
    from vivacapi.core.config import settings

    token = await _make_staff_token(db_session, "img5b")
    spot = await _make_spot(db_session)
    key = _pending_key(spot.uid)
    deleted: list[str] = []

    async def _head(k: str) -> int | None:
        return settings.IMAGE_MAX_BYTES + 1

    async def _delete(k: str) -> None:
        deleted.append(k)

    monkeypatch.setattr(storage, "head_object", _head)
    monkeypatch.setattr(storage, "delete_object", _delete)

    response = await db_client.post(
        f"/v1/internal/spots/{spot.uid}/images",
        json={"s3_key": key},
        headers=bearer(token),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SPOT_IMAGE_TOO_LARGE"
    assert deleted == [key]


async def test_register_rejects_when_spot_at_image_count_limit(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage, monkeypatch
):
    from vivacapi.core.config import settings

    monkeypatch.setattr(settings, "IMAGE_MAX_COUNT_PER_SPOT", 2)
    token = await _make_staff_token(db_session, "img5c")
    spot = await _make_spot(db_session)
    await _register_image(db_client, token, spot.uid)
    await _register_image(db_client, token, spot.uid)

    response = await db_client.post(
        f"/v1/internal/spots/{spot.uid}/images",
        json={"s3_key": _pending_key(spot.uid)},
        headers=bearer(token),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SPOT_IMAGE_COUNT_LIMIT_EXCEEDED"


async def test_register_allowed_again_after_soft_deleting_to_free_slot(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage, monkeypatch
):
    from vivacapi.core.config import settings

    monkeypatch.setattr(settings, "IMAGE_MAX_COUNT_PER_SPOT", 1)
    token = await _make_staff_token(db_session, "img5d")
    spot = await _make_spot(db_session)
    image = await _register_image(db_client, token, spot.uid)

    blocked = await db_client.post(
        f"/v1/internal/spots/{spot.uid}/images",
        json={"s3_key": _pending_key(spot.uid)},
        headers=bearer(token),
    )
    assert blocked.status_code == 422

    await db_client.delete(
        f"/v1/internal/spots/{spot.uid}/images/{image['uid']}",
        headers=bearer(token),
    )

    allowed = await db_client.post(
        f"/v1/internal/spots/{spot.uid}/images",
        json={"s3_key": _pending_key(spot.uid)},
        headers=bearer(token),
    )
    assert allowed.status_code == 201


async def test_register_then_public_listing(
    db_client: AsyncClient, db_session: AsyncSession, fake_storage
):
    token = await _make_staff_token(db_session, "img6")
    spot = await _make_spot(db_session)
    stem = shortuuid.uuid()
    pending_key = _pending_key(spot.uid, stem)
    final_key = _final_key(spot.uid, stem)

    created = await db_client.post(
        f"/v1/internal/spots/{spot.uid}/images",
        json={"s3_key": pending_key, "role": "thumbnail", "sort_order": 1},
        headers=bearer(token),
    )
    assert created.status_code == 201
    assert created.json()["role"] == "thumbnail"

    # register 확정 시 pending → 최종 경로로 copy 후 pending 원본을 delete한다
    assert fake_storage["copied"] == [(pending_key, final_key)]
    assert fake_storage["deleted"] == [pending_key]

    # 공개 조회 (비로그인) — 노출되는 URL은 최종 경로 기준
    listing = await db_client.get(f"/v1/explore/spots/{spot.uid}/images")
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 1
    assert items[0]["url"] == f"https://cdn.fake/{final_key}"


async def test_register_rolls_back_copy_when_db_insert_fails(
    db_client: AsyncClient,
    db_session: AsyncSession,
    fake_storage,
    monkeypatch,
):
    """DB insert 실패 시 copy된 final_key를 되돌려 lifecycle rule 밖(pending
    prefix 밖)의 orphan으로 남기지 않는다. pending 원본은 지우지 않으므로
    재시도 가능해야 한다."""
    token = await _make_staff_token(db_session, "img4c")
    spot = await _make_spot(db_session)
    stem = shortuuid.uuid()
    pending_key = _pending_key(spot.uid, stem)
    final_key = _final_key(spot.uid, stem)

    async def _fail_create_image(*args, **kwargs):
        raise RuntimeError("db insert failed")

    monkeypatch.setattr(
        internal_spot_images.crud_image, "create_image", _fail_create_image
    )

    with pytest.raises(RuntimeError, match="db insert failed"):
        await db_client.post(
            f"/v1/internal/spots/{spot.uid}/images",
            json={"s3_key": pending_key},
            headers=bearer(token),
        )

    assert fake_storage["copied"] == [(pending_key, final_key)]
    # final_key는 되돌려졌고(delete), pending 원본은 삭제 호출이 없어야 한다
    assert fake_storage["deleted"] == [final_key]


async def _register_image(
    db_client: AsyncClient, token: str, spot_uid: str, **overrides
) -> dict:
    key = _pending_key(spot_uid)
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
