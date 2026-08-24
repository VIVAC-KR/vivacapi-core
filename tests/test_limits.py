import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import make_user
from vivacapi.core import cache, limits
from vivacapi.core.errors import sanitize_exc_message

# ---------------------------------------------------------------------------
# sanitize_exc_message — job.result/job.error에 SQL 전문이 새지 않는지
# ---------------------------------------------------------------------------


def test_sanitize_strips_sql_and_parameters():
    raw = (
        "(psycopg.errors.NotNullViolation) null value in column \"title\"\n"
        "[SQL: INSERT INTO spots (uid, title) VALUES (%(uid)s, %(title)s)]\n"
        "[parameters: {'uid': 'abc', 'title': None}]"
    )
    reason = sanitize_exc_message(ValueError(raw))

    assert "INSERT INTO" not in reason
    assert "parameters" not in reason
    assert reason.startswith("ValueError: (psycopg.errors.NotNullViolation)")


def test_sanitize_truncates_to_max_len():
    reason = sanitize_exc_message(RuntimeError("x" * 900), max_len=100)
    assert len(reason) == 103  # 100자 + "..."
    assert reason.endswith("...")


def test_sanitize_keeps_type_when_message_empty():
    assert sanitize_exc_message(RuntimeError()) == "RuntimeError"


# ---------------------------------------------------------------------------
# rate_limit — Redis 카운터 기반, 미설정 시 fail-open
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_counter(monkeypatch):
    """Redis 대신 인메모리 카운터. incr_with_ttl과 동일한 계약(증가 후 값)."""
    counts: dict[str, int] = {}

    async def _incr(key: str, ttl_seconds: int) -> int:
        counts[key] = counts.get(key, 0) + 1
        return counts[key]

    monkeypatch.setattr(cache, "incr_with_ttl", _incr)
    return counts


async def test_rate_limit_blocks_after_threshold(
    db_client: AsyncClient, db_session: AsyncSession, fake_counter, monkeypatch
):
    user = await make_user(
        db_session, email="rl@example.com", google_sub="sub-rl"
    )

    # 실제 엔드포인트 대신 dependency를 직접 호출 — 라우트마다 한도를 바꿔 끼우지 않는다.
    dependency = limits.rate_limit("test_scope", times=2, seconds=60)

    class _Request:
        client = None

    for _ in range(2):
        await dependency(_Request(), user=user)

    with pytest.raises(Exception) as excinfo:
        await dependency(_Request(), user=user)
    assert excinfo.value.code.value == "RATE_LIMITED"
    assert excinfo.value.status_code == 429

    # 다른 유저는 별도 카운터
    other = await make_user(
        db_session, email="rl2@example.com", google_sub="sub-rl2"
    )
    await dependency(_Request(), user=other)


async def test_rate_limit_fails_open_without_redis(monkeypatch):
    async def _no_redis(key: str, ttl_seconds: int) -> None:
        return None

    monkeypatch.setattr(cache, "incr_with_ttl", _no_redis)
    dependency = limits.rate_limit("test_scope", times=1, seconds=60)

    class _Request:
        client = None

    class _User:
        uid = "u1"

    for _ in range(5):
        await dependency(_Request(), user=_User())  # 예외 없이 통과해야 한다


async def test_login_endpoint_returns_429_over_limit(
    db_client: AsyncClient, fake_counter, monkeypatch
):
    """엔드포인트에 실제로 dependency가 물려 있는지 확인 (한도 30회/분)."""
    monkeypatch.setattr(
        "vivacapi.api.v1.endpoints.auth.verify_google_id_token",
        lambda _t: (_ for _ in ()).throw(ValueError("bad token")),
    )

    for _ in range(30):
        response = await db_client.post("/v1/auth/google", json={"id_token": "x"})
        assert response.status_code == 401  # 한도 내에서는 토큰 검증 실패로 진행

    response = await db_client.post("/v1/auth/google", json={"id_token": "x"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.parametrize(
    "path,limit",
    [("/v1/explore/spots", 100), ("/v1/explore/spots/map", 60)],
)
async def test_explore_endpoints_return_429_over_limit(
    db_client: AsyncClient, fake_counter, path, limit
):
    """explore 엔드포인트에 rate_limit이 물려 있는지 확인."""
    for _ in range(limit):
        response = await db_client.get(path, params={"limit": 1})
        assert response.status_code == 200

    response = await db_client.get(path, params={"limit": 1})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
