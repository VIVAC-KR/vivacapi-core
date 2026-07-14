# VIVAC API - Architecture Overview

> 캠퍼를 위한 장소 큐레이션 서비스 백엔드 아키텍처
>
> 이 문서는 living document다 — 라우터/모델/설정이 바뀌면 함께 갱신한다.
> DB 스키마 상세는 [erd.md](./erd.md) 참고. API 명세는 수기로 관리하지 않는다
> — `make openapi`로 `docs/openapi.json`(git 미추적)을 생성하거나, 서버 실행 후
> `/docs`(Swagger UI)를 사용한다.

## Tech Stack

| 구분 | 기술 |
|------|------|
| Framework | FastAPI |
| Language | Python 3.12+ |
| ORM | SQLAlchemy 2.x (async) |
| Database | PostgreSQL 16 (asyncpg 드라이버) |
| Migration | Alembic |
| Auth | Google OAuth 2.0 + JWT (access/refresh), SQLAdmin 세션 |
| Admin UI | SQLAdmin (`/admin`) + vivac-console (Refine 기반 별도 프론트) |
| Storage | S3 (presigned URL) + CloudFront CDN |
| Package Manager | uv |
| Local Infra | Docker Compose |
| Prod Infra | AWS Lightsail Instance + Lightsail Managed PostgreSQL |

---

## Project Structure

```
vivacapi-core/
├── vivacapi/
│   ├── main.py                  # FastAPI 앱, 미들웨어, 전역 예외 핸들러, SQLAdmin 마운트
│   ├── core/                    # 핵심 인프라 계층
│   │   ├── config.py            # pydantic-settings 환경 설정 (prod 부팅 검증 포함)
│   │   ├── database.py          # SQLAlchemy async 엔진, 세션, Base
│   │   ├── deps.py              # FastAPI 의존성 (get_current_user, require_staff)
│   │   ├── errors.py            # ErrorCode + AppException (표준 에러 봉투)
│   │   ├── limits.py            # bulk 요청 크기 제한
│   │   ├── security.py          # Google ID Token 검증, JWT 생성/디코딩
│   │   ├── storage.py           # S3 presigned URL / CDN URL 헬퍼
│   │   ├── nickname.py          # 랜덤 닉네임 생성
│   │   └── region.py            # 시/도 축약
│   ├── models/                  # SQLAlchemy ORM (user, spot, spot_business_info,
│   │                            #   spot_review, spot_image, job, audit_log)
│   ├── schemas/                 # Pydantic 요청/응답 모델
│   ├── crud/                    # DB 쿼리 함수 (정렬/필터 화이트리스트 포함)
│   ├── api/v1/
│   │   ├── routers.py           # /v1 라우터 조립 (internal은 라우터 단위 require_staff)
│   │   └── endpoints/           # auth, explore, admin_auth, internal_*
│   ├── admin/                   # SQLAdmin 인증 백엔드 (Google 로그인 → staff 세션)
│   └── workers/                 # 인프로세스 비동기 잡 워커 + bulk upsert 핸들러
├── alembic/                     # DB 마이그레이션 (감사 트리거 포함)
├── scripts/export_openapi.py    # OpenAPI 명세 export (make openapi)
├── tests/                       # pytest (실제 PostgreSQL 사용, 트랜잭션 롤백 격리)
├── docker-compose.yml           # Local PostgreSQL
├── infra/docker-compose.yml     # Prod 컨테이너 정의 (deploy.yml이 사용)
├── Makefile                     # run / db-up / migrate / test / openapi / release
└── .env.example                 # 환경 변수 템플릿
```

---

## Layered Architecture

```
Client (App / vivac-console / 브라우저)
        │ HTTP
        ▼
Routers (api/v1/endpoints) ── HTTP 입출력, 검증, DI. 비즈니스 로직 최소화
        │                      internal/*은 라우터 단위 require_staff
        ▼
CRUD (crud/) ───────────────── DB 쿼리. 정렬/필터 화이트리스트, 상태 전이 규칙
        │
        ▼
Models (models/) ───────────── SQLAlchemy ORM 테이블 정의
        │
        ▼
PostgreSQL 16 ──────────────── Local: Docker Compose / Prod: Lightsail Managed DB
                               감사 트리거(audit_log)가 spots·spot_business_info 기록
```

- **Core**(config/security/errors/storage/...)는 전 계층이 쓰는 횡단 관심사.
- **Workers**는 API 프로세스 안에서 asyncio task로 도는 잡 워커 — 아래 참조.

---

## Authentication

세 가지 인증 흐름이 있고, 모두 Google ID Token 검증에서 시작한다.

| 흐름 | 엔드포인트 | 토큰 | 만료 |
|------|-----------|------|------|
| 앱 사용자 | `POST /v1/auth/google` | HS256 JWT access + refresh | 30분 / 7일 |
| vivac-console (staff) | `POST /v1/admin/auth/google` | HS256 JWT access (+`email`, `is_staff` 클레임) | 8시간 |
| SQLAdmin (`/admin`) | 로그인 폼 → `AdminAuth` | 서명된 세션 쿠키 | 세션 |

- JWT payload: `sub`(user uid), `type`(access/refresh), `iat`, `exp`.
- refresh 토큰은 완전 stateless — 서버 저장/회수 수단이 없다. 유출 시 만료까지
  유효한 것을 알고 선택한 트레이드오프 (`.claude/rules/security.md`).
- staff 판정은 매 요청 DB 재조회(`require_staff`) — 토큰의 `is_staff` 클레임은
  표시용이며 권한 판단에 쓰지 않는다.
- staff 로그인은 `ALLOWED_EMAIL_DOMAIN` 화이트리스트(선택) + DB `is_staff=True`
  + `is_active=True`를 모두 통과해야 한다.

---

## API Endpoints

모든 에러 응답은 전역 예외 핸들러를 거쳐 표준 봉투로 통일된다
(`{"error": {"code", "message", "details"}}` — `.claude/rules/api-conventions.md`).

### 공개 (비로그인)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | 헬스체크 |
| `POST` | `/v1/auth/google` | Google ID Token 로그인 → JWT 쌍 |
| `POST` | `/v1/auth/refresh` | 토큰 갱신 |
| `GET` | `/v1/explore/spots` | 공개(PUBLISHED) spot 목록 (커서 페이지네이션) |
| `GET` | `/v1/explore/spots/{uid}` | 공개 spot 상세 |
| `GET` | `/v1/explore/spots/{uid}/images` | spot 이미지 목록 (CDN/presigned URL) |

### 인증 필요

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/auth/me` | Bearer JWT | 현재 사용자 정보 |
| `POST` | `/v1/admin/auth/google` | - (Google ID Token) | 콘솔 staff 로그인 |

### 내부 어드민 (`/v1/internal/*`, 라우터 단위 `require_staff`)

vivac-console(Refine simple-rest)용. 목록은 `_start`/`_end`/`_sort`/`_order`
쿼리와 `X-Total-Count` 헤더 규약을 따르고, 정렬/필터 컬럼은 화이트리스트로
제한된다 (밖의 값은 422).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/internal/spots` | 목록 (검색·필터·정렬·offset 페이지네이션) |
| `GET` | `/v1/internal/spots/stats` | 대시보드 통계 (My Queue 포함) |
| `POST` | `/v1/internal/spots/assignments` | 검증 대기 spot 할당 |
| `GET` | `/v1/internal/spots/distinct/{field}` | 필터 드롭다운 옵션 |
| `GET` | `/v1/internal/spots/{uid}` | 상세 |
| `PATCH` | `/v1/internal/spots/{uid}` | 부분 수정 (pipeline_status 전이 화이트리스트) |
| `GET` | `/v1/internal/spots/{uid}/history` | 감사 로그 기반 수정 이력 |
| `POST` | `/v1/internal/spots/bulk` | 대량 upsert 잡 등록 (202, 5 MiB 제한) |
| `POST` | `/v1/internal/spots/{uid}/images/presign` | 업로드용 presigned PUT URL |
| `POST` | `/v1/internal/spots/{uid}/images` | 업로드 완료 이미지 등록 |
| `GET` | `/v1/internal/spot-business-info` | 사업자 정보 목록 |
| `GET/PATCH` | `/v1/internal/spot-business-info/{uid}` | 상세/수정 |
| `GET` | `/v1/internal/spot-business-info/{uid}/history` | 수정 이력 |
| `POST` | `/v1/internal/spot-business-info/bulk` | 대량 upsert 잡 등록 |
| `GET` | `/v1/internal/jobs/{job_id}` | bulk 잡 상태 조회 |

### 운영 UI

| Path | Description |
|------|-------------|
| `/admin` | SQLAdmin — 사용자 계정 상태/권한 관리 (staff 세션 필요) |

---

## Async Job Worker

bulk upsert처럼 오래 걸리는 작업은 `jobs` 테이블에 등록하고 202를 반환한다.

- 워커는 별도 프로세스가 아니라 **API 프로세스 내 asyncio task** (`lifespan`에서
  시작). uvicorn 단일 워커 전제이며, 다중 인스턴스여도 `FOR UPDATE SKIP LOCKED`
  로 잡이 중복 처리되지 않는다.
- 부팅 시 `RUNNING` 상태로 남은 좀비 잡을 `FAILED(error=orphaned)`로 정리한다.
- 잡 실패 시 traceback을 `jobs.error`에 저장 — `/v1/internal/jobs/{id}`로 확인.
- 설계 배경: [projects/async-job-worker-design.md](./projects/async-job-worker-design.md)

## Audit Log

`spots`, `spot_business_info`의 INSERT/UPDATE/DELETE는 DB 트리거가 `audit_log`에
old/new JSONB로 기록한다. 변경 주체는 트랜잭션 시작 시
`set_config('app.user_id', ...)`(SET LOCAL)로 주입한다 — 라우터의
`crud_audit.set_audit_user`, 워커의 `process_job` 참조.

## Image Storage

업로드는 3단계로 나뉜다 — API 서버는 파일 바이트를 직접 받지 않고 presigned
URL 발급·검증만 담당한다 (`core/storage.py`).

1. **Presign** — `POST /v1/internal/spots/{uid}/images/presign`. 서버가 키를
   `spots/{uid}/{shortuuid}{ext}` 형태로 생성하고(`content_type`으로 확장자
   결정, jpeg/png/webp만 허용) S3 presigned PUT URL을 발급한다. 키를 서버가
   생성하므로 클라이언트가 임의 경로에 쓰지 못한다.
2. **직접 업로드** — 클라이언트(vivac-console/앱)가 발급받은 URL로 **S3에
   직접 PUT** (API 서버·EC2 우회).
3. **Register** — `POST /v1/internal/spots/{uid}/images`. `s3_key`가
   `spots/{uid}/` 하위 경로인지 검증하고(다른 spot 경로 등록 방지),
   `object_exists`(S3 `head_object`)로 실제 업로드됐는지 재확인한 뒤에만
   `spot_image` row를 생성한다.

조회: `is_public=True`는 CDN URL, `False`는 presigned GET URL. **is_public은
서빙 방식 구분이지 접근 제어가 아니다** — 두 경우 모두 공개 API에 노출된다.

S3 미설정 시 이미지 API만 503 (`SERVICE_UNAVAILABLE`).

---

## Database

- **Engine**: `create_async_engine` (asyncpg), `pool_size=5`, `max_overflow=10`,
  `pool_pre_ping=True`. prod는 DSN에 `ssl=require`.
- **Session**: `async_sessionmaker`, `expire_on_commit=False`
- **Migration**: Alembic. 감사 트리거·CHECK 제약처럼 autogenerate가 못 잡는
  것은 수동 마이그레이션으로 관리.
- **PK**: 모든 도메인 테이블은 shortuuid 22자(`VARCHAR(22)`) + 문자셋 CHECK.
- **Local**: Docker Compose PostgreSQL 16 / **Prod**: Lightsail Managed DB
  (프라이빗 엔드포인트, Public mode OFF)

---

## Configuration

`pydantic-settings` 기반. `ENVIRONMENT=prod`면 부팅 시 placeholder 값·약한
시크릿·잘못된 CORS/DB_HOST를 검증해 실패시킨다. 시크릿 필드는 `SecretStr`로
repr/직렬화에서 마스킹된다.

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `ENVIRONMENT` | local/dev/prod | `local` |
| `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD` | DB 접속 정보 | host/port만 기본값 |
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID | (필수) |
| `ALLOWED_EMAIL_DOMAIN` | 어드민 로그인 허용 이메일 도메인 | 없음(제한 안 함) |
| `JWT_SECRET_KEY` | JWT 서명 키 (prod 32자 이상) | (필수) |
| `JWT_ALGORITHM` | JWT 알고리즘 | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | access 만료(분) | `30` |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | refresh 만료(일) | `7` |
| `JWT_ADMIN_ACCESS_TOKEN_EXPIRE_HOURS` | 어드민 access 만료(시간) | `8` |
| `ADMIN_SESSION_SECRET` | SQLAdmin 세션 키 (JWT 키와 분리, prod 32자 이상) | (필수) |
| `CORS_ALLOWED_ORIGINS` | 허용 origin (콤마 구분) | local만 localhost:3000 |
| `AWS_REGION` | S3 리전 | `ap-northeast-2` |
| `S3_BUCKET` / `S3_ENDPOINT_URL` / `CDN_BASE_URL` | 이미지 스토리지 (미설정 시 이미지 API 503) | 없음 |
| `S3_PRESIGN_EXPIRE_SECONDS` | presigned URL 만료(초) | `3600` |

---

## Deployment

```
git tag v*.*.* push
      │
      ▼
GitHub Actions (deploy.yml)
      ├─ docker buildx (linux/amd64) → Docker Hub (버전 태그 + latest)
      └─ SSH → Lightsail Instance
           ├─ alembic upgrade head (버전 태그 이미지로)
           ├─ docker compose up -d (IMAGE_TAG 고정 — 마이그레이션과 동일 이미지)
           └─ /health 헬스체크
```

프로비저닝 절차는 [infra/lightsail-setup.md](./infra/lightsail-setup.md) 참고.
CI(`ci.yml`)는 PR마다 ruff + alembic upgrade + pytest를 실행한다.
