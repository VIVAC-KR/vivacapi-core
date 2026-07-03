import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.security import create_access_token
from vivacapi.crud.audit import _compute_changes
from vivacapi.models.spot import Spot
from vivacapi.models.spot_business_info import SpotBusinessInfo
from tests.helpers import bearer, make_user

# ---------------------------------------------------------------------------
# _compute_changes — diff 계산 (DB 불필요)
# ---------------------------------------------------------------------------


def test_compute_changes_returns_only_changed_fields():
    old = {"title": "A", "unit_count": 10, "updated_at": "t1"}
    new = {"title": "A", "unit_count": 20, "updated_at": "t2"}

    changes = _compute_changes(old, new)

    assert set(changes) == {"unit_count"}
    assert changes["unit_count"].before == 10
    assert changes["unit_count"].after == 20


def test_compute_changes_ignores_updated_at():
    changes = _compute_changes({"updated_at": "t1"}, {"updated_at": "t2"})
    assert changes == {}


def test_compute_changes_insert_and_delete():
    # INSERT: old 없음 → 비-null 필드만 after로
    ins = _compute_changes(None, {"title": "A", "phone": None})
    assert set(ins) == {"title"}
    assert ins["title"].before is None and ins["title"].after == "A"

    # DELETE: new 없음 → before만
    del_ = _compute_changes({"title": "A"}, None)
    assert del_["title"].before == "A" and del_["title"].after is None


# ---------------------------------------------------------------------------
# GET /v1/internal/spots/{uid}/history
# ---------------------------------------------------------------------------


async def _make_staff(db: AsyncSession, suffix: str):
    user = await make_user(
        db, email=f"staff-{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    user.is_staff = True
    await db.commit()
    return user


async def _make_spot(db: AsyncSession, title: str = "감사 캠핑장") -> Spot:
    spot = Spot(title=title, rating_avg=0.0, review_count=0)
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


async def test_history_requires_auth(db_client: AsyncClient):
    response = await db_client.get("/v1/internal/spots/some-uid/history")
    assert response.status_code == 401


async def test_spot_patch_records_history_with_changed_by(
    db_client: AsyncClient, db_session: AsyncSession
):
    """PATCH(콘솔 편집) → history에 changed_by/diff가 기록되는 전체 흐름."""
    staff = await _make_staff(db_session, "hist1")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session)

    patch = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"title": "수정된 캠핑장"},
        headers=bearer(token),
    )
    assert patch.status_code == 200

    response = await db_client.get(
        f"/v1/internal/spots/{spot.uid}/history", headers=bearer(token)
    )
    assert response.status_code == 200
    entries = response.json()

    # 최신순: [0]=UPDATE(방금 PATCH), [1]=INSERT(생성)
    assert [e["action"] for e in entries] == ["UPDATE", "INSERT"]

    update = entries[0]
    assert update["changed_by"] == staff.uid
    assert update["changed_by_name"] == staff.name
    assert update["changes"]["title"] == {
        "before": "감사 캠핑장",
        "after": "수정된 캠핑장",
    }

    # 직접 INSERT(트리거만 기록)는 changed_by 없음
    assert entries[1]["changed_by"] is None


async def test_business_info_patch_records_history(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "hist2")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session)

    info = SpotBusinessInfo(spot_uid=spot.uid, operating_status="영업중")
    db_session.add(info)
    await db_session.commit()
    await db_session.refresh(info)

    patch = await db_client.patch(
        f"/v1/internal/spot-business-info/{info.uid}",
        json={"operating_status": "휴업"},
        headers=bearer(token),
    )
    assert patch.status_code == 200

    response = await db_client.get(
        f"/v1/internal/spot-business-info/{info.uid}/history",
        headers=bearer(token),
    )
    assert response.status_code == 200
    entries = response.json()

    assert entries[0]["action"] == "UPDATE"
    assert entries[0]["changed_by"] == staff.uid
    assert entries[0]["changes"]["operating_status"] == {
        "before": "영업중",
        "after": "휴업",
    }
