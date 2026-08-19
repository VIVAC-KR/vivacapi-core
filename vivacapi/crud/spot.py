import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core import cache
from vivacapi.core.config import settings
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.core.geo import BBox
from vivacapi.models.spot import PipelineStatus, Spot
from vivacapi.models.spot_business_info import SpotBusinessInfo

# 검색 스코어 계산 가중치. 근거: docs/projects/spot-search-postgres-fts.md 4.6
_SEARCH_TRIGRAM_WEIGHT = 0.3
_SEARCH_SIMILARITY_THRESHOLD = 0.2

# total은 정확한 수치가 아니라 "후보가 충분히 많다"만 전달하면 되므로 상한에서
# 세기를 멈춘다. 예상 전체 규모(8000건 미만)보다 크게 잡아, 현재 데이터에서는
# 사실상 항상 정확한 값이 나오고 데이터가 커져도 COUNT 비용이 선형 증가하지 않는다.
TOTAL_CAP = 10_000

# 지도 응답 상한. 전국 줌아웃 시 bbox에 전체가 들어오므로 전체 규모를 덮는
# 값이어야 한다 — 잘라내면 지도가 실제보다 비어 보이는 잘못된 정보를 준다.
# 페이로드는 uid+좌표+trust_tier뿐이라 8000건도 gzip 후 100KB 안팎.
MAP_LIMIT_MAX = 8000

# 어드민 목록에서 정렬 가능한 컬럼 화이트리스트 (임의 속성 주입 방지)
_ADMIN_SORTABLE = {
    "uid": Spot.uid,
    "title": Spot.title,
    "region_province": Spot.region_province,
    "region_city": Spot.region_city,
    "rating_avg": Spot.rating_avg,
    "review_count": Spot.review_count,
    "created_at": Spot.created_at,
    "updated_at": Spot.updated_at,
}
SORTABLE_FIELDS = frozenset(_ADMIN_SORTABLE)

# 정확일치 필터 + distinct(패싯) 조회가 허용된 컬럼 화이트리스트.
# 여기에 항목만 추가하면 필터/드롭다운에 새 필드가 붙는다.
_FILTERABLE = {
    "region_province": Spot.region_province,
    "source": Spot.source,
    "pipeline_status": Spot.pipeline_status,
    "assigned_to_uid": Spot.assigned_to_uid,
}
FILTERABLE_FIELDS = frozenset(_FILTERABLE)

# 검증 큐 화면(제출/반려)에서 일반 STAFF도 PATCH로 허용하는 pipeline_status 전이.
# 그 외 전이는 SUPERUSER 전용(자유 전이, 화이트리스트 없음) — internal_spots.py 참고.
ALLOWED_PIPELINE_TRANSITIONS = {
    (PipelineStatus.ENRICHED, PipelineStatus.CURATED),
    (PipelineStatus.ENRICHED, PipelineStatus.REJECTED),
}


def _apply_explore_filters(
    stmt,
    *,
    category: list[str] | None = None,
    region_province: str | None = None,
    bbox: BBox | None = None,
    require_coordinates: bool | None = None,
):
    """explore 계열(목록/검색/지도/카운트) 공통 필터.

    모드가 달라도 같은 결과 집합을 보도록 한 곳에서만 조건을 건다 — 리스트와
    지도의 집합이 갈리면 사용자가 모드를 바꿀 때마다 장소가 나타났다 사라진다.
    pipeline_status 게이트는 임시 제거 상태
    (원복: Spot.pipeline_status == PipelineStatus.PUBLISHED 재추가).
    """
    if require_coordinates is None:
        require_coordinates = settings.EXPLORE_REQUIRE_COORDINATES

    stmt = stmt.where(Spot.deleted_at.is_(None))
    if require_coordinates:
        stmt = stmt.where(Spot.latitude.isnot(None), Spot.longitude.isnot(None))
    if category:
        stmt = stmt.where(Spot.category.op("&&")(category))
    if region_province:
        stmt = stmt.where(Spot.region_province == region_province)
    if bbox is not None:
        # BETWEEN은 NULL에 대해 false — bbox가 있으면 좌표 없는 spot은 자동 제외된다.
        stmt = stmt.where(
            Spot.latitude.between(bbox.min_lat, bbox.max_lat),
            Spot.longitude.between(bbox.min_lng, bbox.max_lng),
        )
    return stmt


def _scope_token(bbox: BBox | None) -> str:
    """커서가 발급된 조회 범위의 지문.

    지도를 움직인 뒤 이전 커서를 이어받으면 다른 영역의 위치를 가리켜 결과가
    섞인다. 서버가 커서를 조용히 무시하면 FE에서 "결과는 이상한데 에러는 없는"
    상태가 되므로, 커서에 범위를 박아두고 어긋나면 명시적으로 거부한다.
    """
    if bbox is None:
        return ""
    raw = ",".join(f"{value:.6f}" for value in bbox)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _reject_scope_mismatch(cursor_scope: str, scope: str) -> None:
    if cursor_scope != scope:
        raise AppException(
            ErrorCode.CURSOR_SCOPE_MISMATCH,
            "Cursor was issued for a different bbox — discard it and re-query",
        )


def _search_terms(query: str):
    tsquery = func.websearch_to_tsquery("simple", query)
    title_similarity = func.similarity(Spot.title, query)
    score = (
        func.ts_rank(Spot.search_vector, tsquery)
        + title_similarity * _SEARCH_TRIGRAM_WEIGHT
    )
    match = Spot.search_vector.op("@@")(tsquery) | (
        title_similarity > _SEARCH_SIMILARITY_THRESHOLD
    )
    return score, match


async def list_spots(
    session: AsyncSession,
    cursor: str | None = None,
    limit: int = 20,
    *,
    category: list[str] | None = None,
    region_province: str | None = None,
    bbox: BBox | None = None,
) -> tuple[list[Spot], str | None, bool]:
    """공개 목록 — 미삭제만 노출한다.

    커서는 `{scope}:{uid}` 형식이며 scope는 bbox 지문이다 (bbox 없으면 빈 문자열).
    """
    scope = _scope_token(bbox)
    query = _apply_explore_filters(
        select(Spot),
        category=category,
        region_province=region_province,
        bbox=bbox,
    ).order_by(Spot.uid)
    if cursor:
        cursor_scope, _, last_uid = cursor.rpartition(":")
        _reject_scope_mismatch(cursor_scope, scope)
        query = query.where(Spot.uid > last_uid)
    result = await session.execute(query.limit(limit + 1))
    spots = list(result.scalars().all())

    has_more = len(spots) > limit
    if has_more:
        spots = spots[:limit]

    next_cursor = f"{scope}:{spots[-1].uid}" if has_more else None
    return spots, next_cursor, has_more


async def count_spots(
    session: AsyncSession,
    *,
    query: str | None = None,
    category: list[str] | None = None,
    region_province: str | None = None,
    bbox: BBox | None = None,
) -> tuple[int, bool]:
    """(total, total_capped). TOTAL_CAP을 넘으면 세기를 멈추고 (TOTAL_CAP, True)."""
    stmt = _apply_explore_filters(
        select(Spot.uid),
        category=category,
        region_province=region_province,
        bbox=bbox,
    )
    if query and query.strip():
        _, match = _search_terms(query)
        stmt = stmt.where(match)

    capped = stmt.limit(TOTAL_CAP + 1).subquery()
    total = await session.scalar(select(func.count()).select_from(capped)) or 0
    if total > TOTAL_CAP:
        return TOTAL_CAP, True
    return total, False


async def list_spots_map(
    session: AsyncSession,
    *,
    query: str | None = None,
    category: list[str] | None = None,
    region_province: str | None = None,
    bbox: BBox | None = None,
    limit: int = MAP_LIMIT_MAX,
) -> tuple[list[Spot], bool]:
    """지도 핀용 조회. (spots, truncated).

    좌표 없는 spot은 EXPLORE_REQUIRE_COORDINATES와 무관하게 항상 제외한다 —
    좌표 없는 핀은 지도에 찍을 수 없다.
    커서 없이 한 번에 반환하므로 limit에 걸리면 truncated=True로 알린다.
    """
    stmt = _apply_explore_filters(
        select(Spot),
        category=category,
        region_province=region_province,
        bbox=bbox,
        require_coordinates=True,
    )
    if query and query.strip():
        _, match = _search_terms(query)
        stmt = stmt.where(match)

    result = await session.execute(stmt.order_by(Spot.uid).limit(limit + 1))
    spots = list(result.scalars().all())
    truncated = len(spots) > limit
    return spots[:limit], truncated


async def get_random_spots(session: AsyncSession, limit: int = 1) -> list[Spot]:
    """무작위 스팟 표본 조회 (Slack 정기 발송 배치용, scripts/send_spots_slack.py)."""
    query = (
        select(Spot)
        .where(Spot.deleted_at.is_(None))
        .order_by(func.random())
        .limit(limit)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


def _encode_search_cursor(score: float, rating_avg: float, uid: str, scope: str) -> str:
    payload = json.dumps({"r": score, "v": rating_avg, "u": uid, "s": scope}).encode()
    return base64.urlsafe_b64encode(payload).decode()


def _decode_search_cursor(cursor: str) -> tuple[float, float, str, str]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return (
            float(payload["r"]),
            float(payload["v"]),
            str(payload["u"]),
            str(payload.get("s", "")),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise AppException(
            ErrorCode.VALIDATION_ERROR, "Invalid cursor for search results"
        ) from exc


async def search_spots(
    session: AsyncSession,
    *,
    query: str,
    category: list[str] | None = None,
    region_province: str | None = None,
    bbox: BBox | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[list[Spot], str | None, bool]:
    """자유텍스트 검색. title(A)/tagline(B)/description(C)/address(D) 가중치
    tsvector 매칭 + title trigram 유사도 보정으로 점수를 매기고, 동점이면
    rating_avg, 그래도 동점이면 uid로 결정론적 정렬한다.
    가중치/스코어 계산 근거: docs/projects/spot-search-postgres-fts.md
    """
    scope = _scope_token(bbox)
    score, match = _search_terms(query)

    stmt = _apply_explore_filters(
        select(Spot, score.label("score")),
        category=category,
        region_province=region_province,
        bbox=bbox,
    ).where(match)

    if cursor:
        last_score, last_rating_avg, last_uid, cursor_scope = _decode_search_cursor(
            cursor
        )
        _reject_scope_mismatch(cursor_scope, scope)
        stmt = stmt.where(
            tuple_(score, Spot.rating_avg, Spot.uid)
            < tuple_(last_score, last_rating_avg, last_uid)
        )

    stmt = stmt.order_by(score.desc(), Spot.rating_avg.desc(), Spot.uid.desc())
    result = await session.execute(stmt.limit(limit + 1))
    rows = result.all()

    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    spots = [row[0] for row in rows]
    next_cursor = (
        _encode_search_cursor(
            rows[-1][1], rows[-1][0].rating_avg, rows[-1][0].uid, scope
        )
        if has_more
        else None
    )
    return spots, next_cursor, has_more


async def get_spot_by_uid(
    session: AsyncSession, uid: str, *, published_only: bool = False
) -> Spot | None:
    """단건 조회. 공개 API 경로는 published_only=True로 미삭제만 노출한다.
    관리자 경로(published_only=False)는 복구를 위해 삭제된 spot도 조회 가능해야 한다.
    pipeline_status 게이트는 임시 제거 상태 (원복: Spot.pipeline_status == PipelineStatus.PUBLISHED 재추가).

    EXPLORE_REQUIRE_COORDINATES가 켜져 있으면 좌표 없는 spot은 여기서도 없는
    것으로 취급한다 — 목록에서만 빼면 북마크/공유된 URL은 계속 열려서 검색으로는
    찾을 수 없는 페이지가 링크로만 접근 가능해진다.
    """
    query = select(Spot).where(Spot.uid == uid)
    if published_only:
        query = _apply_explore_filters(query)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def list_spots_admin(
    session: AsyncSession,
    *,
    offset: int,
    limit: int,
    sort: str = "uid",
    order: str = "asc",
    title: str | None = None,
    filters: dict[str, str | None] | None = None,
    include_deleted: bool = False,
) -> tuple[list[Spot], int]:
    """오프셋 기반 어드민 목록. (items, total)을 반환한다.

    filters: 화이트리스트(_FILTERABLE) 컬럼에 대한 정확일치 필터를 AND로 조합.
    include_deleted=False(기본)면 soft delete된 spot은 목록에서 숨긴다.
    """
    query = select(Spot)
    if not include_deleted:
        query = query.where(Spot.deleted_at.is_(None))
    if title:
        # icontains(autoescape=True) — 검색어의 %/_를 이스케이프해 사용자가
        # 와일드카드로 전체 스캔을 유도하지 못하게 한다.
        query = query.where(Spot.title.icontains(title, autoescape=True))
    for field, value in (filters or {}).items():
        col = _FILTERABLE.get(field)
        if col is not None and value:
            query = query.where(col == value)

    total = await session.scalar(select(func.count()).select_from(query.subquery()))

    column = _ADMIN_SORTABLE.get(sort, Spot.uid)
    ordering = column.desc() if order == "desc" else column.asc()
    result = await session.execute(query.order_by(ordering).offset(offset).limit(limit))
    return list(result.scalars().all()), total or 0


async def list_distinct(session: AsyncSession, field: str) -> list[str]:
    """화이트리스트 컬럼의 distinct non-null 값 목록 (드롭다운 옵션용)."""
    col = _FILTERABLE[field]
    result = await session.execute(
        select(col).where(col.is_not(None)).distinct().order_by(col)
    )
    return list(result.scalars().all())


async def get_spot_stats(session: AsyncSession, *, staff_uid: str) -> dict:
    """대시보드용 집계 통계. staff_uid 기준 My Queue 통계도 함께 반환한다."""
    total = await session.scalar(select(func.count()).select_from(Spot)) or 0
    business_info_total = (
        await session.scalar(select(func.count()).select_from(SpotBusinessInfo))
    ) or 0
    missing_coordinates = (
        await session.scalar(
            select(func.count())
            .select_from(Spot)
            .where(or_(Spot.latitude.is_(None), Spot.longitude.is_(None)))
        )
    ) or 0
    my_assigned_total = (
        await session.scalar(
            select(func.count())
            .select_from(Spot)
            .where(Spot.assigned_to_uid == staff_uid)
        )
    ) or 0
    my_completed = (
        await session.scalar(
            select(func.count())
            .select_from(Spot)
            .where(
                Spot.assigned_to_uid == staff_uid,
                Spot.pipeline_status != PipelineStatus.ENRICHED,
            )
        )
    ) or 0

    async def grouped(column) -> list[dict]:
        key = func.coalesce(column, "(미지정)")
        result = await session.execute(
            select(key, func.count()).group_by(key).order_by(func.count().desc())
        )
        return [{"key": k, "count": c} for k, c in result.all()]

    return {
        "total": total,
        "business_info_total": business_info_total,
        "missing_coordinates": missing_coordinates,
        "by_source": await grouped(Spot.source),
        "by_region_province": await grouped(Spot.region_province),
        "my_assigned_total": my_assigned_total,
        "my_completed": my_completed,
    }


async def assign_spots(session: AsyncSession, *, user_uid: str, count: int) -> int:
    """미할당 ENRICHED spot 중 count개를 user_uid에게 할당한다. 실제 할당 개수를 반환.

    FOR UPDATE SKIP LOCKED로 동시 할당 요청 간 중복 배정을 막는다.
    """
    picked = await session.execute(
        select(Spot.uid)
        .where(
            Spot.pipeline_status == PipelineStatus.ENRICHED,
            Spot.assigned_to_uid.is_(None),
        )
        .limit(count)
        .with_for_update(skip_locked=True)
    )
    uids = [row[0] for row in picked.all()]
    if not uids:
        return 0

    await session.execute(
        update(Spot).where(Spot.uid.in_(uids)).values(assigned_to_uid=user_uid)
    )
    await session.commit()
    return len(uids)


_TRUST_TIER_DECAY_DAYS = 180


async def decay_stale_trust_tiers(
    session: AsyncSession, *, threshold_days: int = _TRUST_TIER_DECAY_DAYS
) -> dict[str, int]:
    """last_verified_at 기준 threshold_days 경과(NULL 포함, 미검증 취급)한
    PUBLISHED spot의 trust_tier를 감쇠시킨다.

    tier 1/2는 한 단계 하향(숫자 증가)하고, 이미 최하위인 tier 3은 더 내릴
    곳이 없으니 assigned_to_uid를 비워 재검증 큐로 되돌린다. 감쇠 대상이 된
    row는 last_verified_at을 지금 시각으로 갱신한다 — 갱신하지 않으면 다음
    실행에서도 여전히 stale로 잡혀 매 배치마다 한 단계씩 더 감쇠(연쇄 하향)
    하게 되므로, 이 워터마크로 "한 번 감쇠하면 다음 threshold_days까지는
    보류"를 보장한다.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=threshold_days)
    stale = and_(
        Spot.pipeline_status == PipelineStatus.PUBLISHED,
        Spot.deleted_at.is_(None),
        Spot.trust_tier.isnot(None),
        or_(Spot.last_verified_at.is_(None), Spot.last_verified_at < cutoff),
    )

    downgraded = await session.execute(
        update(Spot)
        .where(stale, Spot.trust_tier < 3)
        .values(trust_tier=Spot.trust_tier + 1, last_verified_at=func.now())
        .returning(Spot.uid)
    )
    downgraded_uids = [row[0] for row in downgraded.all()]
    requeued = await session.execute(
        update(Spot)
        .where(stale, Spot.trust_tier == 3)
        .values(assigned_to_uid=None, last_verified_at=func.now())
    )
    await session.commit()
    # trust_tier는 SpotListItem/SpotDetail 공개 필드 — 감쇠된 spot만 무효화한다.
    # requeued는 assigned_to_uid만 바뀌고 공개 응답엔 없어 무효화 불필요.
    if downgraded_uids:
        await cache.bump_spots_version()
        for uid in downgraded_uids:
            await cache.invalidate_spot_detail(uid)
    return {"downgraded": len(downgraded_uids), "requeued": requeued.rowcount}


async def assign_spots_bulk(
    session: AsyncSession, *, spot_uids: list[str], user_uid: str
) -> int:
    """지정된 spot uid 목록을 user_uid에게 일괄 (재)할당한다. 기존 할당 여부는 무관하게 덮어쓴다.

    실제로 매칭돼 갱신된 개수를 반환(존재하지 않는 uid는 조용히 무시).
    """
    result = await session.execute(
        update(Spot).where(Spot.uid.in_(spot_uids)).values(assigned_to_uid=user_uid)
    )
    await session.commit()
    return result.rowcount


async def transfer_spot_assignments(
    session: AsyncSession, *, from_user_uid: str, to_user_uid: str, count: int
) -> int:
    """from_user_uid에게 할당된 검증 대기(ENRICHED) spot 중 count개를 to_user_uid로 옮긴다.

    FOR UPDATE SKIP LOCKED로 동시 재배정 요청 간 중복을 막는다.
    """
    picked = await session.execute(
        select(Spot.uid)
        .where(
            Spot.pipeline_status == PipelineStatus.ENRICHED,
            Spot.assigned_to_uid == from_user_uid,
        )
        .limit(count)
        .with_for_update(skip_locked=True)
    )
    uids = [row[0] for row in picked.all()]
    if not uids:
        return 0

    await session.execute(
        update(Spot).where(Spot.uid.in_(uids)).values(assigned_to_uid=to_user_uid)
    )
    await session.commit()
    return len(uids)


async def update_pipeline_status_bulk(
    session: AsyncSession, *, uids: list[str], pipeline_status: PipelineStatus
) -> list[str]:
    """SUPERUSER 전용 자유 전이 — 지정한 uid들의 pipeline_status를 화이트리스트 없이 일괄 변경한다.

    존재하는 uid만 반영하고 실제로 갱신된 uid 목록을 반환한다(부분 실패는 호출부가
    요청 uid와의 차집합으로 판단).
    """
    found = (
        (await session.execute(select(Spot.uid).where(Spot.uid.in_(uids))))
        .scalars()
        .all()
    )
    if not found:
        return []
    await session.execute(
        update(Spot).where(Spot.uid.in_(found)).values(pipeline_status=pipeline_status)
    )
    await session.commit()
    await cache.bump_spots_version()
    for uid in found:
        await cache.invalidate_spot_detail(uid)
    return list(found)


async def update_spot(session: AsyncSession, uid: str, data: dict) -> Spot | None:
    spot = await get_spot_by_uid(session, uid)
    if spot is None:
        return None
    for key, value in data.items():
        setattr(spot, key, value)
    await session.commit()
    await session.refresh(spot)
    await cache.bump_spots_version()
    await cache.invalidate_spot_detail(uid)
    return spot


async def delete_spot(session: AsyncSession, spot: Spot) -> None:
    await session.execute(
        update(Spot).where(Spot.uid == spot.uid).values(deleted_at=func.now())
    )
    await session.commit()
    await cache.bump_spots_version()
    await cache.invalidate_spot_detail(spot.uid)


async def restore_spot(session: AsyncSession, spot: Spot) -> Spot:
    await session.execute(
        update(Spot).where(Spot.uid == spot.uid).values(deleted_at=None)
    )
    await session.commit()
    await session.refresh(spot)
    await cache.bump_spots_version()
    await cache.invalidate_spot_detail(spot.uid)
    return spot
