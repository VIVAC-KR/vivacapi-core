import hashlib
import logging

import redis.asyncio as redis

from vivacapi.core.config import settings

logger = logging.getLogger(__name__)

# REDIS_URL 미설정 시 None — 이하 모든 함수가 no-op으로 fail-open한다.
# socket_connect_timeout/socket_timeout 없으면 REDIS_URL이 unreachable할 때
# OS 기본 타임아웃(수십 초)까지 매달려 fail-open 취지(빠른 폴백)가 무너진다.
_client: redis.Redis | None = (
    redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    if settings.REDIS_URL
    else None
)

_SPOTS_VERSION_KEY = "spots:version"


async def close() -> None:
    if _client is not None:
        await _client.aclose()


def _normalize_param(value: object) -> str:
    if isinstance(value, list):
        return ",".join(sorted(value))
    return "" if value is None else str(value)


async def get_cached(key: str) -> str | None:
    if _client is None:
        return None
    try:
        return await _client.get(key)
    except Exception as exc:  # redis 장애는 항상 cache miss로 취급 (fail-open)
        logger.warning("cache get failed key=%s err=%s", key, exc)
        return None


async def set_cached(key: str, value: str, ttl_seconds: int) -> None:
    if _client is None:
        return
    try:
        await _client.set(key, value, ex=ttl_seconds)
    except Exception as exc:
        logger.warning("cache set failed key=%s err=%s", key, exc)


async def incr_with_ttl(key: str, ttl_seconds: int) -> int | None:
    """key를 1 증가시키고 증가 후 값을 반환한다. 최초 증가 시에만 TTL을 건다.

    Redis 미설정/장애 시 None — 호출부가 fail-open을 판단한다.
    """
    if _client is None:
        return None
    try:
        pipe = _client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl_seconds, nx=True)
        count, _ = await pipe.execute()
        return int(count)
    except Exception as exc:
        logger.warning("rate limit counter failed key=%s err=%s", key, exc)
        return None


async def _get_spots_version() -> int:
    if _client is None:
        return 0
    try:
        value = await _client.get(_SPOTS_VERSION_KEY)
        return int(value) if value else 0
    except Exception as exc:
        logger.warning("cache version read failed err=%s", exc)
        return 0


async def bump_spots_version() -> None:
    """spot 목록/검색 캐시 전체 무효화.

    필터 조합이 무한해 개별 키를 추적할 수 없으므로, 버전을 올려 이전
    버전 키들을 더 이상 참조되지 않게 만든다 — SCAN/패턴 삭제 없이 TTL로
    자연 소멸한다.
    """
    if _client is None:
        return
    try:
        await _client.incr(_SPOTS_VERSION_KEY)
    except Exception as exc:
        logger.warning("cache version bump failed err=%s", exc)


async def make_spots_list_key(params: dict[str, object]) -> str:
    version = await _get_spots_version()
    raw = "&".join(f"{k}={_normalize_param(v)}" for k, v in sorted(params.items()))
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"spots:list:v{version}:{digest}"


def _spot_detail_version_key(uid: str) -> str:
    return f"spots:detail_version:{uid}"


async def _get_spot_detail_version(uid: str) -> int:
    if _client is None:
        return 0
    try:
        value = await _client.get(_spot_detail_version_key(uid))
        return int(value) if value else 0
    except Exception as exc:
        logger.warning("cache detail version read failed uid=%s err=%s", uid, exc)
        return 0


async def spot_detail_key(uid: str) -> str:
    version = await _get_spot_detail_version(uid)
    return f"spots:detail:{uid}:v{version}"


async def invalidate_spot_detail(uid: str) -> None:
    """상세 캐시 무효화도 목록과 동일하게 버전 증가 방식을 쓴다 (DELETE 아님).

    DELETE 방식이면 "느린 reader가 구버전 읽음 → writer commit+invalidate
    → reader가 뒤늦게 구버전을 새 TTL로 재기록"하는 race에 그대로 노출된다.
    버전을 올리면 reader가 뒤늦게 쓰더라도 그 키는 이미 낡은 버전 번호가 박혀
    있어 이후 아무도 참조하지 않는다 (list 캐시와 동일한 안전장치).
    """
    if _client is None:
        return
    try:
        await _client.incr(_spot_detail_version_key(uid))
    except Exception as exc:
        logger.warning("cache invalidate failed uid=%s err=%s", uid, exc)
