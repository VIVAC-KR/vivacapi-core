from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.security import create_access_token
from vivacapi.models.spot import Spot
from vivacapi.models.spot_business_info import SpotBusinessInfo
from vivacapi.models.user import StaffRole
from tests.helpers import bearer, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_staff(
    db: AsyncSession, suffix: str, role: StaffRole = StaffRole.STAFF
):
    user = await make_user(
        db, email=f"staff-{suffix}@example.com", google_sub=f"sub-{suffix}"
    )
    user.is_staff = True
    user.staff_role = role
    await db.commit()
    return user


async def _make_spot(db: AsyncSession, title: str, **kwargs):
    spot = Spot(
        title=title,
        rating_avg=kwargs.pop("rating_avg", 0.0),
        review_count=kwargs.pop("review_count", 0),
        **kwargs,
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


# ---------------------------------------------------------------------------
# GET /v1/internal/spots — list
# ---------------------------------------------------------------------------


async def test_list_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.get("/v1/internal/spots")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_list_returns_items_with_total_count_header(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "list")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Alpha", region_province="강원")
    await _make_spot(db_session, "Bravo", region_province="경기")

    response = await db_client.get("/v1/internal/spots", headers=bearer(token))

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "2"
    body = response.json()
    assert {item["title"] for item in body} == {"Alpha", "Bravo"}
    assert set(body[0].keys()) == {
        "uid",
        "title",
        "source",
        "region_province",
        "region_city",
        "rating_avg",
        "review_count",
        "pipeline_status",
        "trust_tier",
        "updated_at",
    }


async def test_list_rejects_non_whitelisted_sort(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "bad-sort")
    token = create_access_token(staff.uid)

    response = await db_client.get(
        "/v1/internal/spots",
        params={"_sort": "phone"},
        headers=bearer(token),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_list_title_filter(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "filter")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "남이섬 캠핑장")
    await _make_spot(db_session, "설악산 야영장")

    response = await db_client.get(
        "/v1/internal/spots",
        params={"title_like": "남이섬"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "1"
    assert [item["title"] for item in response.json()] == ["남이섬 캠핑장"]


async def test_list_region_province_filter(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "region")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Alpha", region_province="강원")
    await _make_spot(db_session, "Bravo", region_province="강원")
    await _make_spot(db_session, "Charlie", region_province="경기")

    response = await db_client.get(
        "/v1/internal/spots",
        params={"region_province": "강원"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "2"
    assert {item["title"] for item in response.json()} == {"Alpha", "Bravo"}


async def test_list_source_filter(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "source")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Alpha", source="src1")
    await _make_spot(db_session, "Bravo", source="src2")

    response = await db_client.get(
        "/v1/internal/spots",
        params={"source": "src1"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "1"
    assert [item["title"] for item in response.json()] == ["Alpha"]


async def test_list_pipeline_status_filter(
    db_client: AsyncClient, db_session: AsyncSession
):
    """검증 큐 화면이 pipeline_status=ENRICHED로 필터링해 조회하는 경로."""
    staff = await _make_staff(db_session, "pipeline-filter")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Alpha", pipeline_status="ENRICHED")
    await _make_spot(db_session, "Bravo", pipeline_status="RAW")

    response = await db_client.get(
        "/v1/internal/spots",
        params={"pipeline_status": "ENRICHED"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "1"
    assert [item["title"] for item in response.json()] == ["Alpha"]


async def test_list_combined_filters_are_anded(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "combined")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Match", region_province="강원", source="src1")
    await _make_spot(db_session, "WrongSrc", region_province="강원", source="src2")
    await _make_spot(db_session, "WrongRegion", region_province="경기", source="src1")

    response = await db_client.get(
        "/v1/internal/spots",
        params={"region_province": "강원", "source": "src1"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "1"
    assert [item["title"] for item in response.json()] == ["Match"]


async def test_distinct_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.get("/v1/internal/spots/distinct/region_province")
    assert response.status_code == 401


async def test_distinct_returns_distinct_sorted(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "distinct")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Alpha", region_province="경기")
    await _make_spot(db_session, "Bravo", region_province="강원")
    await _make_spot(db_session, "Charlie", region_province="강원")
    await _make_spot(db_session, "Delta", region_province=None)

    response = await db_client.get(
        "/v1/internal/spots/distinct/region_province", headers=bearer(token)
    )

    assert response.status_code == 200
    assert response.json() == ["강원", "경기"]


async def test_distinct_source_field(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "distinct-src")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Alpha", source="src2")
    await _make_spot(db_session, "Bravo", source="src1")
    await _make_spot(db_session, "Charlie", source="src1")

    response = await db_client.get(
        "/v1/internal/spots/distinct/source", headers=bearer(token)
    )

    assert response.status_code == 200
    assert response.json() == ["src1", "src2"]


async def test_distinct_pipeline_status_field(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "distinct-status")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Alpha", pipeline_status="ENRICHED")
    await _make_spot(db_session, "Bravo", pipeline_status="RAW")
    await _make_spot(db_session, "Charlie", pipeline_status="RAW")

    response = await db_client.get(
        "/v1/internal/spots/distinct/pipeline_status", headers=bearer(token)
    )

    assert response.status_code == 200
    assert response.json() == ["ENRICHED", "RAW"]


async def test_distinct_rejects_non_whitelisted_field(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "distinct-bad")
    token = create_access_token(staff.uid)

    response = await db_client.get(
        "/v1/internal/spots/distinct/phone", headers=bearer(token)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_list_pagination_slices_with_full_total(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "page")
    token = create_access_token(staff.uid)
    for i in range(5):
        await _make_spot(db_session, f"Spot {i}")

    response = await db_client.get(
        "/v1/internal/spots",
        params={"_start": 0, "_end": 2, "_sort": "title", "_order": "asc"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "5"
    body = response.json()
    assert [item["title"] for item in body] == ["Spot 0", "Spot 1"]


# ---------------------------------------------------------------------------
# GET /v1/internal/spots/{uid} — detail
# ---------------------------------------------------------------------------


async def test_get_one_returns_detail(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "detail")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session, "Detail Spot", address="서울시")

    response = await db_client.get(
        f"/v1/internal/spots/{spot.uid}", headers=bearer(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["uid"] == spot.uid
    assert body["title"] == "Detail Spot"
    assert body["address"] == "서울시"


async def test_get_one_not_found_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "detail404")
    token = create_access_token(staff.uid)

    response = await db_client.get(
        "/v1/internal/spots/nonexistent", headers=bearer(token)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SPOT_NOT_FOUND"


# ---------------------------------------------------------------------------
# PATCH /v1/internal/spots/{uid} — update
# ---------------------------------------------------------------------------


async def test_patch_updates_only_provided_fields(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "patch")
    token = create_access_token(staff.uid)
    spot = await _make_spot(
        db_session, "Old Title", address="old", tagline="keep me"
    )

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"title": "New Title", "address": "new"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New Title"
    assert body["address"] == "new"
    assert body["tagline"] == "keep me"


async def test_patch_not_found_returns_404(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "patch404")
    token = create_access_token(staff.uid)

    response = await db_client.patch(
        "/v1/internal/spots/nonexistent",
        json={"title": "X"},
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SPOT_NOT_FOUND"


async def test_patch_updates_trust_tier(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "pipeline")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session, "검수 대상")

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"trust_tier": 2},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()["trust_tier"] == 2


# ---------------------------------------------------------------------------
# PATCH pipeline_status — 검증 큐(제출/반려) 전이 검증
# ENRICHED -> CURATED / REJECTED 두 전이만 허용, 그 외는 전부 거부.
# ---------------------------------------------------------------------------


async def test_patch_pipeline_status_enriched_to_curated(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "curate")
    token = create_access_token(staff.uid)
    spot = await _make_spot(
        db_session, "검증 대상", pipeline_status="ENRICHED", assigned_to_uid=staff.uid
    )

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"pipeline_status": "CURATED"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()["pipeline_status"] == "CURATED"


async def test_patch_pipeline_status_enriched_to_rejected(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "reject")
    token = create_access_token(staff.uid)
    spot = await _make_spot(
        db_session, "검증 대상2", pipeline_status="ENRICHED", assigned_to_uid=staff.uid
    )

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"pipeline_status": "REJECTED"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()["pipeline_status"] == "REJECTED"


async def test_patch_pipeline_status_rejects_skip_ahead_transition(
    db_client: AsyncClient, db_session: AsyncSession
):
    """RAW -> PUBLISHED처럼 단계를 건너뛰는 전이는 이 화면 스코프가 아니다."""
    staff = await _make_staff(db_session, "skipahead")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session, "검증 대상3", pipeline_status="RAW")

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"pipeline_status": "PUBLISHED"},
        headers=bearer(token),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    await db_session.refresh(spot)
    assert spot.pipeline_status == "RAW"


async def test_patch_pipeline_status_rejects_reverse_transition(
    db_client: AsyncClient, db_session: AsyncSession
):
    """CURATED -> ENRICHED처럼 되돌리는 전이도 이 엔드포인트로는 불가."""
    staff = await _make_staff(db_session, "revert")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session, "검증 대상4", pipeline_status="CURATED")

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"pipeline_status": "ENRICHED"},
        headers=bearer(token),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_patch_pipeline_status_transition_check_precedes_not_found(
    db_client: AsyncClient, db_session: AsyncSession
):
    """존재하지 않는 spot이면 전이 규칙과 무관하게 404를 반환한다."""
    staff = await _make_staff(db_session, "notfound")
    token = create_access_token(staff.uid)

    response = await db_client.patch(
        "/v1/internal/spots/nonexistent",
        json={"pipeline_status": "CURATED"},
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SPOT_NOT_FOUND"


async def test_patch_rejects_invalid_pipeline_status(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "badstatus")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session, "검수 대상2")

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"pipeline_status": "DELETED"},
        headers=bearer(token),
    )
    assert response.status_code == 422


async def test_patch_rejects_out_of_range_trust_tier(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "badtier")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session, "검수 대상3")

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"trust_tier": 4},
        headers=bearer(token),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH — 검증 대기(ENRICHED)는 할당된 담당자만 수정 가능
# ---------------------------------------------------------------------------


async def test_patch_enriched_forbidden_when_unassigned(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "unassigned")
    token = create_access_token(staff.uid)
    spot = await _make_spot(db_session, "미할당", pipeline_status="ENRICHED")

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"title": "수정 시도"},
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_patch_enriched_forbidden_when_assigned_to_other_staff(
    db_client: AsyncClient, db_session: AsyncSession
):
    owner = await _make_staff(db_session, "owner")
    other = await _make_staff(db_session, "other")
    token = create_access_token(other.uid)
    spot = await _make_spot(
        db_session, "타인 할당", pipeline_status="ENRICHED", assigned_to_uid=owner.uid
    )

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"title": "수정 시도"},
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_patch_enriched_allowed_for_assigned_staff(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "assignee")
    token = create_access_token(staff.uid)
    spot = await _make_spot(
        db_session, "본인 할당", pipeline_status="ENRICHED", assigned_to_uid=staff.uid
    )

    response = await db_client.patch(
        f"/v1/internal/spots/{spot.uid}",
        json={"title": "수정됨"},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()["title"] == "수정됨"


# ---------------------------------------------------------------------------
# GET /v1/internal/spots?assigned_to_uid= — My Queue 필터
# ---------------------------------------------------------------------------


async def test_list_assigned_to_uid_filter(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "myqueue")
    other = await _make_staff(db_session, "myqueue-other")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "Mine", assigned_to_uid=staff.uid)
    await _make_spot(db_session, "Theirs", assigned_to_uid=other.uid)
    await _make_spot(db_session, "Unassigned")

    response = await db_client.get(
        "/v1/internal/spots",
        params={"assigned_to_uid": staff.uid},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "1"
    assert [item["title"] for item in response.json()] == ["Mine"]


# ---------------------------------------------------------------------------
# POST /v1/internal/spots/assignments — spot 할당
# ---------------------------------------------------------------------------


async def test_assign_spots_picks_unassigned_enriched_only(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "assigner", role=StaffRole.MANAGER)
    target = await _make_staff(db_session, "assignee-target")
    token = create_access_token(staff.uid)
    await _make_spot(db_session, "E1", pipeline_status="ENRICHED")
    await _make_spot(db_session, "E2", pipeline_status="ENRICHED")
    await _make_spot(db_session, "Raw", pipeline_status="RAW")
    already = await _make_spot(
        db_session, "Already", pipeline_status="ENRICHED", assigned_to_uid=target.uid
    )

    response = await db_client.post(
        "/v1/internal/spots/assignments",
        json={"user_uid": target.uid, "count": 10},
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json()["assigned_count"] == 2

    listed = await db_client.get(
        "/v1/internal/spots",
        params={"assigned_to_uid": target.uid},
        headers=bearer(token),
    )
    assert listed.headers["x-total-count"] == "3"  # 기존 1 + 신규 2
    await db_session.refresh(already)
    assert already.assigned_to_uid == target.uid


async def test_assign_spots_is_cumulative_across_calls(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "assigner2", role=StaffRole.MANAGER)
    target = await _make_staff(db_session, "assignee-target2")
    token = create_access_token(staff.uid)
    for i in range(3):
        await _make_spot(db_session, f"Round1-{i}", pipeline_status="ENRICHED")

    first = await db_client.post(
        "/v1/internal/spots/assignments",
        json={"user_uid": target.uid, "count": 2},
        headers=bearer(token),
    )
    assert first.json()["assigned_count"] == 2

    for i in range(2):
        await _make_spot(db_session, f"Round2-{i}", pipeline_status="ENRICHED")

    second = await db_client.post(
        "/v1/internal/spots/assignments",
        json={"user_uid": target.uid, "count": 3},
        headers=bearer(token),
    )
    assert second.json()["assigned_count"] == 3  # 남은 ENRICHED(1) + 신규(2)


async def test_assign_spots_rejects_non_staff_target(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "assigner3", role=StaffRole.MANAGER)
    non_staff = await make_user(
        db_session, email="not-staff@example.com", google_sub="sub-not-staff"
    )
    token = create_access_token(staff.uid)

    response = await db_client.post(
        "/v1/internal/spots/assignments",
        json={"user_uid": non_staff.uid, "count": 5},
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"


async def test_assign_spots_forbidden_for_staff_role(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "assigner4", role=StaffRole.STAFF)
    target = await _make_staff(db_session, "assignee-target4")
    token = create_access_token(staff.uid)

    response = await db_client.post(
        "/v1/internal/spots/assignments",
        json={"user_uid": target.uid, "count": 1},
        headers=bearer(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_assign_spots_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.post(
        "/v1/internal/spots/assignments",
        json={"user_uid": "someone", "count": 1},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /v1/internal/spots/stats — 대시보드 통계
# ---------------------------------------------------------------------------


async def test_stats_unauthenticated_returns_401(db_client: AsyncClient):
    response = await db_client.get("/v1/internal/spots/stats")
    assert response.status_code == 401


async def test_stats_returns_aggregates(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "stats")
    token = create_access_token(staff.uid)
    a = await _make_spot(
        db_session, "A", source="src1", region_province="강원",
        latitude=1.0, longitude=2.0,
    )
    await _make_spot(db_session, "B", source="src1", region_province="경기")
    await _make_spot(
        db_session, "C", source="src2", region_province="강원",
        latitude=1.0, longitude=2.0,
    )
    db_session.add(SpotBusinessInfo(spot_uid=a.uid))
    await db_session.commit()

    response = await db_client.get(
        "/v1/internal/spots/stats", headers=bearer(token)
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["business_info_total"] == 1
    assert data["missing_coordinates"] == 1  # B는 좌표 없음
    assert {i["key"]: i["count"] for i in data["by_source"]} == {
        "src1": 2,
        "src2": 1,
    }
    assert data["by_source"][0]["count"] >= data["by_source"][-1]["count"]
    assert {i["key"]: i["count"] for i in data["by_region_province"]} == {
        "강원": 2,
        "경기": 1,
    }
    assert data["my_assigned_total"] == 0
    assert data["my_completed"] == 0


async def test_stats_my_queue_counts(
    db_client: AsyncClient, db_session: AsyncSession
):
    staff = await _make_staff(db_session, "myqueuestats")
    token = create_access_token(staff.uid)
    await _make_spot(
        db_session, "Pending1", pipeline_status="ENRICHED", assigned_to_uid=staff.uid
    )
    await _make_spot(
        db_session, "Pending2", pipeline_status="ENRICHED", assigned_to_uid=staff.uid
    )
    await _make_spot(
        db_session, "Done", pipeline_status="CURATED", assigned_to_uid=staff.uid
    )
    await _make_spot(db_session, "NotMine", pipeline_status="ENRICHED")

    response = await db_client.get(
        "/v1/internal/spots/stats", headers=bearer(token)
    )

    assert response.status_code == 200
    data = response.json()
    assert data["my_assigned_total"] == 3
    assert data["my_completed"] == 1
