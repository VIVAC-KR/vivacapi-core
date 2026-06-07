# vivac-console Backend — `/v1/admin/*` 라우터

> 별도 운영 콘솔(`vivac-console`, Next.js)이 호출할 `vivacapi-core`의 어드민 전용 HTTP API.
> 작성일: 2026-06-07
> 짝 문서: [vivac-console-frontend.md](./vivac-console-frontend.md)

---

## 0. 네이밍 노트

| 이름 | 의미 |
|---|---|
| **vivac-console** | 운영팀이 사용하는 별도 GUI(Next.js 리포). 호출하는 쪽 |
| **`/v1/admin/*`** | 그 콘솔이 호출하는 API 경로. 권한 의미(staff 전용 작업)를 그대로 유지 — 콘솔 외의 다른 클라이언트(CLI, 스크립트 등)도 동일 API 사용 가능 |
| **`is_staff`** | 백엔드 권한 플래그. 그대로 유지 |

즉 "콘솔이 호출하는 어드민 API"라는 관계. 경로명을 `console`로 바꾸지 않는다.

---

## 1. 배경 & 목표

기존 SQLAdmin(`/admin`)은 비상용으로 남기고, 일상 운영은 별도 Next.js 콘솔(`vivac-console`)에서 수행한다. 이 콘솔이 호출할 **어드민 전용 HTTP API**를 `vivacapi-core`에 추가한다.

핵심 원칙: **콘솔은 화면만, 데이터 규칙은 백엔드 한 곳에.**
콘솔이 DB에 직접 붙지 않고 항상 이 API를 경유함으로써, public API와 동일한 검증·사이드이펙트·정합성을 보장한다.

### 비목표

- 권한 세분화(어드민 등급 분리). `is_staff` 단일 플래그로 충분 — `is_staff=True`인 모든 유저는 모든 어드민 권한 보유
- audit log (별도 프로젝트로 분리)
- public API(`/v1/explore/*`) 변경

---

## 2. 기존 자산 (재사용)

이미 다음이 있으므로 새로 만들 필요 없음:

| 자산 | 위치 | 용도 |
|---|---|---|
| `User.is_staff` | `app/models/user.py` | 어드민 권한 플래그 |
| `require_staff` 의존성 | `app/core/deps.py` | 라우터 보호 |
| `CurrentStaff` 타입 alias | `app/core/deps.py` | `Annotated[User, Depends(require_staff)]` |
| `/v1/internal/jobs` 패턴 | `app/api/v1/routers.py` | `dependencies=[Depends(require_staff)]` 적용 사례 |
| `app/crud/spot.py` | | 재사용 — admin은 라우터·스키마만 추가 |

`api_v1_router` 등록 컨벤션은 `app/api/v1/routers.py`를 그대로 따른다.

---

## 3. 추가할 것 — 디렉터리 구조

```
app/api/v1/endpoints/
└── admin/
    ├── __init__.py
    ├── spots.py              # /v1/admin/spots
    └── spot_business_info.py # /v1/admin/spot-business-info

app/schemas/
└── admin/
    ├── __init__.py
    ├── spot.py               # SpotAdminCreate/Update/Detail/ListItem
    └── spot_business_info.py
```

`app/api/v1/routers.py` 등록:

```python
from app.api.v1.endpoints.admin import spots as admin_spots
from app.api.v1.endpoints.admin import spot_business_info as admin_sbi

api_v1_router.include_router(
    admin_spots.router,
    prefix="/admin/spots",
    tags=["admin:spots"],
    dependencies=[Depends(require_staff)],
)
api_v1_router.include_router(
    admin_sbi.router,
    prefix="/admin/spot-business-info",
    tags=["admin:spot-business-info"],
    dependencies=[Depends(require_staff)],
)
```

> **주의**: SQLAdmin이 이미 `/admin`에 마운트돼 있으므로, 어드민 API는 반드시 `/v1/admin/*` 경로(앞에 `/v1` 붙음). 경로 충돌 없음.

---

## 4. 엔드포인트 명세

### 4.1 Spot

| Method | Path | 설명 |
|---|---|---|
| GET | `/v1/admin/spots` | 목록 (검색·필터·정렬·offset 페이지네이션) |
| GET | `/v1/admin/spots/{uid}` | 상세 |
| POST | `/v1/admin/spots` | 생성 |
| PATCH | `/v1/admin/spots/{uid}` | 부분 수정 |
| DELETE | `/v1/admin/spots/{uid}` | 삭제 (하드 삭제. soft delete는 도입 시 후속 PR) |

**GET 목록 쿼리 파라미터**

| param | 타입 | 설명 |
|---|---|---|
| `q` | str | `title` / `address` ILIKE 검색 |
| `source` | str | 외부 소스 필터 (`gocamping`, `forest`, `manual`, ...) |
| `region_province` | str | 시·도 |
| `region_city` | str | 시·군·구 |
| `offset` | int | default 0 |
| `limit` | int | default 50, max 200 |
| `order_by` | str | `created_at` / `updated_at` / `title` (prefix `-`로 desc) |

**응답 — 목록**

```json
{
  "items": [
    {
      "uid": "abc...",
      "title": "...",
      "source": "gocamping",
      "external_id": "...",
      "region_province": "강원특별자치도",
      "region_city": "춘천시",
      "rating_avg": 4.2,
      "review_count": 17,
      "created_at": "2026-06-01T...",
      "updated_at": "2026-06-05T..."
    }
  ],
  "total": 1234,
  "offset": 0,
  "limit": 50
}
```

> public API는 cursor 페이지네이션이지만, 어드민 테이블 UI 친화를 위해 **offset + total** 사용. (이 결정은 의식적인 분리)

**응답 — 상세 (`SpotAdminDetail`)**

`Spot` 모델의 모든 컬럼을 노출. public의 `SpotPublic`과 달리 내부용 필드(`source`, `external_id`)도 포함.

**POST/PATCH 요청 — `SpotAdminCreate` / `SpotAdminUpdate`**

- `Create`: 모든 컬럼 입력 가능. `uid`는 서버 생성(shortuuid). `rating_avg`, `review_count`는 0으로 초기화 가능(또는 필수 제외)
- `Update`: 모든 필드 `Optional`. `model_dump(exclude_unset=True)`로 부분 갱신

### 4.2 SpotBusinessInfo

같은 패턴으로 `/v1/admin/spot-business-info`:

| Method | Path | 설명 |
|---|---|---|
| GET | `/v1/admin/spot-business-info` | 목록 |
| GET | `/v1/admin/spot-business-info/{uid}` | 상세 |
| POST | `/v1/admin/spot-business-info` | 생성 (반드시 `spot_uid` 포함) |
| PATCH | `/v1/admin/spot-business-info/{uid}` | 부분 수정 |
| DELETE | `/v1/admin/spot-business-info/{uid}` | 삭제 |

**GET 목록 추가 필터**

| param | 설명 |
|---|---|
| `spot_uid` | 특정 spot에 속한 사업 정보만 |
| `operating_status` | `OPERATING` / `CLOSED` 등 |
| `q` | `business_reg_no` / `operating_agency` 검색 |

`spot_uid`는 `spots.uid`에 대한 FK이므로 생성/수정 시 존재성 검증 필요. 없으면 422 (`SPOT_NOT_FOUND`).

---

## 5. 인증·인가

- 모든 `/v1/admin/*` 라우터에 `dependencies=[Depends(require_staff)]` 적용 (라우터 단위 일괄)
- 콘솔은 기존 `/v1/auth/google` 로그인 흐름 그대로 사용 → 발급된 JWT를 Bearer로 첨부
- `is_staff=False` 유저가 호출하면 `require_staff`가 403 반환 — 추가 검증 불필요
- 별도 admin role 컬럼이나 RBAC는 도입하지 않음

---

## 6. CRUD 레이어

`app/crud/spot.py`에 필요한 함수가 없으면 추가. 라우터에서 직접 SQLAlchemy를 호출하지 말 것 — 기존 패턴(`crud/job.py::get_job_by_id` 등) 따름.

추가 후보 함수 예:

```
crud/spot.py
  list_spots_admin(db, *, q, source, region_province, region_city, offset, limit, order_by) -> tuple[list[Spot], int]
  create_spot(db, payload: dict) -> Spot
  update_spot(db, uid: str, payload: dict) -> Spot | None
  delete_spot(db, uid: str) -> bool

crud/spot_business_info.py   (신규 파일)
  list_sbi_admin(db, *, ...) -> tuple[list[SpotBusinessInfo], int]
  get_sbi_by_id(db, uid) -> SpotBusinessInfo | None
  create_sbi(db, payload: dict) -> SpotBusinessInfo
  update_sbi(db, uid: str, payload: dict) -> SpotBusinessInfo | None
  delete_sbi(db, uid: str) -> bool
```

리스트 함수는 `(items, total_count)` 튜플 반환 — total은 단일 `count()` 쿼리로.

---

## 7. CORS

`vivac-console` 도메인을 `settings.CORS_ALLOWED_ORIGINS`에 추가. 로컬은 `http://localhost:3000`.

운영 도메인은 별도 결정 (예: `console.vivac.kr`). `.env.local` / `.env.prod`에 분리 관리.

---

## 8. 테스트

- 각 엔드포인트 단위 테스트
  - 비스태프 → 403
  - 스태프 → 정상 동작
  - 필수 필드 누락 → 422
  - 존재하지 않는 `uid` → 404
  - `spot_business_info` POST에서 잘못된 `spot_uid` → 422
- 기존 테스트 컨벤션: `tests/` 하위, `pytest-asyncio`, real DB. 자세히는 `.claude/rules/testing.md`

---

## 9. 작업 단계 (단계별 verify 포함)

> CLAUDE.md "Goal-Driven Execution" 원칙 적용 — 각 단계 끝에 verify 기준 명시.

1. **스키마 작성** (`app/schemas/admin/spot.py`, `spot_business_info.py`)
   → verify: `uv run python -c "from app.schemas.admin.spot import SpotAdminCreate; print(SpotAdminCreate.model_fields)"` 성공
2. **CRUD 함수 추가** (`app/crud/spot.py`, 신규 `app/crud/spot_business_info.py`)
   → verify: 함수 단위 테스트 통과
3. **라우터 작성** (`app/api/v1/endpoints/admin/spots.py`, `spot_business_info.py`)
   → verify: 라우터 등록 후 `uv run uvicorn app.main:app --reload`, OpenAPI docs (`/docs`)에 `admin:spots` 태그 노출
4. **라우터 등록** (`app/api/v1/routers.py`에 `include_router` 2개 추가)
   → verify: 위와 동일
5. **End-to-end 테스트** (`tests/api/v1/admin/test_spots.py` 등)
   → verify: `uv run pytest tests/api/v1/admin/` 전 케이스 통과
6. **CORS 갱신** (`app/core/config.py` 또는 `.env.local`)
   → verify: 로컬에서 `vivac-console`(3000 포트)에서 `/v1/admin/spots` 호출 성공

---

## 10. 브랜치 / PR

- 브랜치: `feature/admin-api-spots` (ASCII만 — [[feedback_branch_naming_ascii]])
- 가능하면 spot 라우터와 spot_business_info 라우터를 **각각 별 PR**로 분리 (리뷰 단위 작게)
- 직접 push 금지 — PR 필수
- 로컬 실행/테스트는 `.env.local` 사용 — [[feedback_local_env_file]]

---

## 11. 후속(이 프로젝트 범위 밖)

- audit log (`is_staff` 유저의 모든 쓰기 기록)
- soft delete (`deleted_at` 컬럼)
- 어드민 권한 세분화 (read-only staff 등)
- 파일/이미지 업로드 어드민 API
