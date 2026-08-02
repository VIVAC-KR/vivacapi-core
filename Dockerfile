# syntax=docker/dockerfile:1.7

# ---------------------------------------------------------------------------
# 1단계: builder — uv로 lockfile 기반 의존성을 .venv에 설치
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.26 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# ---------------------------------------------------------------------------
# 2단계: runtime — 비루트 유저로 uvicorn 실행
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ARG GIT_SHA=dev
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    GIT_SHA=${GIT_SHA}

# pg_dump(PG16) — RDS(16)와 클라이언트 버전을 맞춰야 덤프 호환성이 보장된다.
# Debian bookworm 기본 저장소는 PG15만 제공해 PGDG 공식 저장소를 추가한다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/keyrings/postgresql.asc \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --no-create-home --home-dir /app app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv

COPY --chown=app:app vivacapi/ ./vivacapi/
COPY --chown=app:app alembic/ ./alembic/
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app scripts/ ./scripts/

USER app

EXPOSE 8000

CMD ["uvicorn", "vivacapi.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
