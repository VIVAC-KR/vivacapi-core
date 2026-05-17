# Spot 데이터 일괄 적재 & 내부 백오피스

> 내부 운영자가 캠핑 스팟 데이터를 일괄 적재하고, 적재된 데이터를 웹 UI에서 관리하기 위한 백엔드 구성 계획.
> 작성일: 2026-05-17

---

## 1. 배경 & 목표

캠핑 스팟 데이터를 외부 소스(고캠핑, 산림청, 자체 수집)에서 받아 `spots` / `spot_business_info` 테이블에 적재해야 한다.
운영자는 두 갈래로 나뉜다.

- **엔지니어**: 정제된 JSON 페이로드를 인터널 API로 전송해 일괄 적재
- **비엔지니어(내부 관리자)**: 적재된 데이터를 웹 GUI에서 조회·수정·삭제

본 프로젝트의 목표는 위 두 워크플로를 가능하게 만드는 것이다. 별도 프론트엔드 개발 없이 **백엔드만으로 완결**한다.

### 비목표 (Non-goals)

- 외부 사용자(일반 캠퍼)에게 노출되는 어떤 UI도 만들지 않는다
- 일반 캠퍼용 API(`/spots` 조회 등) 신설은 본 프로젝트 범위 밖
- 권한 세분화(어드민 등급 분리)는 하지 않는다 — `admin` / `user` 두 단계만
- 변경 이력(audit log)은 본 프로젝트에 포함하지 않는다(향후 별도 검토)

---

## 2. 핵심 결정 사항

| 항목 | 결정 | 이유 |
|---|---|---|
| 적재 입력 포맷 | JSON (`application/json`) | CSV 직렬화 규약 불필요, ARRAY 컬럼 자연스러움 |
| 처리 방식 | 비동기 작업 (DB `jobs` 테이블 + 백그라운드 폴러) | 단일 Lightsail 인스턴스에 적합, 외부 브로커 불필요 |
| upsert 키 | `Spot.external_id` 컬럼 신설 (외부 소스 ID 보관) | 외부 데이터 재적재 시 자연 매칭, 사람이 봐도 직관적 |
| 부분 실패 정책 | 전체 트랜잭션 롤백 | 단순. 응답에 실패 행 인덱스/사유만 리포트 |
| 백오피스 구현 | FastAPI에 **SQLAdmin** `/admin` 마운트 | 현 스택(FastAPI + SQLAlchemy async) 1차 지원, 자동 CRUD UI |
| 권한 모델 | `User.is_staff` bool | 별도 admin 테이블 / enum 대비 단순, Django 관례와 유사 |
| 변경 이력 | 본 프로젝트에서는 도입하지 않음 | 도입 방식(SQLAlchemy event hook / 외부 도구 등) 추후 비교 |

---

## 3. 데이터 모델 변경

### 3.1. `users` 테이블 — `is_staff` 컬럼 추가

```python
# users.is_staff: Boolean, NOT NULL, default False
```

- 마이그레이션 시 기존 행은 모두 `False`로 채움
- 스태프 승격은 DBA가 SQL로 직접 수행(별도 API 없음)

### 3.2. `spots` 테이블 — `external_id` 컬럼 추가

```python
# spots.external_id: String(255), nullable, unique
```

- 외부 소스 식별자 보관 (예: `"gocamping:12345"`, `"forest:67890"`, `"manual:2026-05-spot-001"`)
- 적재 페이로드에 `external_id`가 있으면 해당 행에 대해 **upsert**, 없으면 **신규 insert**
- 동일 `external_id` 재적재 시 기존 행 업데이트

### 3.3. `jobs` 테이블 — 신규

```python
class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class JobType(StrEnum):
    SPOTS_BULK_UPSERT = "spots_bulk_upsert"
    SPOT_BUSINESS_INFO_BULK_UPSERT = "spot_business_info_bulk_upsert"

class Job(Base):
    uid: UUID (PK)
    type: JobType
    status: JobStatus (default PENDING)
    payload: JSONB             # 입력 페이로드 원본
    result: JSONB | None       # 행별 처리 결과 (성공 카운트, 실패 인덱스/사유)
    error: Text | None         # 예외 메시지
    created_by: UUID (FK users.uid)
    created_at, started_at, finished_at: timestamp
```

- 한 행이라도 실패하면 전체 트랜잭션 롤백 후 `status = FAILED`로 종료, `result`에 행별 실패 사유 기록
- SQLAdmin에서 진행 상황 조회 가능

---

## 4. API 설계 (인터널)

모든 인터널 엔드포인트는 라우터 레벨에서 `require_staff` 의존성으로 일괄 게이팅. 비스태프 호출 시 403 FORBIDDEN.

### 4.1. `POST /internal/spots/bulk`

```json
{
  "dry_run": false,
  "rows": [
    {
      "external_id": "gocamping:12345",
      "title": "...",
      "address": "...",
      "themes": ["..."],
      "amenities": ["..."],
      ...
    }
  ]
}
```

- 응답: `202 Accepted` + `{ "job_id": "<uuid>" }`
- 즉시 반환, 실제 처리는 백그라운드 워커가 수행
- `dry_run: true`인 경우에도 동일하게 job을 만들되, 실제 DB 변경은 커밋하지 않음

### 4.2. `POST /internal/spot-business-info/bulk`

```json
{
  "dry_run": false,
  "rows": [
    {
      "spot_external_id": "gocamping:12345",
      "business_reg_no": "...",
      ...
    }
  ]
}
```

- `spot_external_id`로 `spots` 행을 조회하여 매핑
- 매핑 실패 시 해당 행 실패 처리 → 전체 롤백

### 4.3. `GET /internal/jobs/{job_id}`

- 진행 상태 폴링용
- 응답: `status`, `result` (행별 성공/실패 리포트), `error`

### 4.4. 페이로드 한도

- 한 요청당 행 수 상한: **5,000행** (운영 중 조정 가능, 초과 시 400 VALIDATION_ERROR)
- 한 요청당 페이로드 크기 상한: **5 MiB** (FastAPI/Starlette 단에서 검증)

---

## 5. 비동기 처리 구조

### 5.1. 워커

- 앱 시작 시 `asyncio` 백그라운드 태스크로 단일 워커 기동 (`app.main.lifespan`에서 spawn)
- 폴링 주기: 2초 (PENDING 작업 1건 꺼내 RUNNING으로 전환 후 처리)
- 동시성: 1 — 단일 인스턴스 가정, 데이터 정합성 보장이 최우선
- 워커 행 락: `SELECT ... FOR UPDATE SKIP LOCKED` 로 다중 워커 환경 대비(향후 확장)

### 5.2. 장애 처리

- 워커가 처리 중 인스턴스가 죽으면 해당 job은 `RUNNING` 상태로 남음
- 부팅 시 lifespan에서 `RUNNING` 상태인 job을 `FAILED` (with `error="orphaned"`)로 전환 후 워커 시작
- 재시도는 운영자가 새 job을 만드는 방식(자동 재시도 없음 — 단순화)

---

## 6. 백오피스 (SQLAdmin)

### 6.1. 마운트

- 라이브러리: [`sqladmin`](https://github.com/aminalaee/sqladmin)
- 경로: `/admin`
- 인증 백엔드: 기존 Google JWT 재사용
  - 미인증 시 SQLAdmin 로그인 페이지 → Google OAuth 흐름 진입 후 콜백
  - `is_staff=False`이면 로그인 실패 처리

### 6.2. 등록 모델

| ModelView | 컬럼 노출 | 검색 가능 | 비고 |
|---|---|---|---|
| `SpotAdmin` | uid, external_id, title, region_province, region_city, rating_avg, updated_at | title, address, external_id | ARRAY 필드 입력 UX 검증 필요 |
| `SpotBusinessInfoAdmin` | uid, spot 관계, business_reg_no, operating_status, licensed_at | business_reg_no | spot은 read-only 표시 |
| `JobAdmin` | uid, type, status, created_at, finished_at, created_by | type, status | payload/result는 디테일에서만 (큰 JSON) |
| `UserAdmin` | uid, email, nickname, role, is_active, created_at | email, nickname | read-only (생성/삭제 금지) |

- 모든 모델 `can_delete = False` 기본 (Spot/BusinessInfo만 명시적 허용 검토)
- `form_excluded_columns`: `created_at`, `updated_at`, `uid`

---

## 7. 마일스톤 & 이슈 분해

### M0 — 기반 (스태프 권한 모델)

| # | 제목 | DoD |
|---|---|---|
| M0-1 | `User.is_staff` 컬럼 추가 + Alembic 마이그레이션 | `is_staff` Boolean 컬럼, 기존 행 `False` backfill, 다운그레이드 가능 |
| M0-2 | `require_staff` 의존성 추가 + 라우터 레벨 적용 | `/internal`, `/admin` 라우터에 일괄 게이팅, 비스태프 호출 시 `AppException(FORBIDDEN)`, 테스트 포함 |

### M1 — Jobs 인프라

| # | 제목 | DoD |
|---|---|---|
| M1-1 | `jobs` 테이블 + 모델 + 마이그레이션 | Job 모델, JobStatus/JobType enum, JSONB 컬럼, 적절한 인덱스(`status`, `created_at`) |
| M1-2 | 비동기 워커 (lifespan 통합) | asyncio 태스크 폴러, 부팅 시 RUNNING→FAILED 정리, 단위 테스트로 워커 1사이클 검증 |
| M1-3 | `GET /internal/jobs/{id}` | admin only, 상태/결과 반환, 404 케이스 포함 테스트 |

### M2 — Spots Bulk Upsert

| # | 제목 | DoD |
|---|---|---|
| M2-1 | `Spot.external_id` 컬럼 + 마이그레이션 | nullable, unique index. 기존 행은 NULL로 유지 |
| M2-2 | `SpotBulkRow` Pydantic 스키마 | Spot 컬럼 1:1 매핑, 행 단위 검증, 페이로드 한도(5000행/5MiB) 검증 |
| M2-3 | `POST /internal/spots/bulk` + Job 핸들러 | job 생성 → 202 반환, 워커에서 upsert 처리, dry_run 지원, 전체 롤백 + 행별 실패 리포트, e2e 테스트 |

### M3 — SpotBusinessInfo Bulk Upsert

| # | 제목 | DoD |
|---|---|---|
| M3-1 | `SpotBusinessInfoBulkRow` 스키마 + 핸들러 | `spot_external_id`로 spot 매핑, 매핑 실패 시 행 실패 처리 + 전체 롤백, e2e 테스트 |

### M4 — SQLAdmin 백오피스

| # | 제목 | DoD |
|---|---|---|
| M4-1 | `sqladmin` 의존성 추가 + `/admin` 마운트 | 빈 ModelView 등록, admin 마운트 후 헬스 확인 |
| M4-2 | `AuthenticationBackend` 구현 | Google JWT 검증 재사용, admin role 게이팅, 로그인/로그아웃 흐름 동작 확인 |
| M4-3 | `SpotAdmin` / `SpotBusinessInfoAdmin` ModelView | column_list / searchable / sortable / form_excluded, ARRAY 필드 입력 동작 검증 |
| M4-4 | `JobAdmin` / `UserAdmin` ModelView | Job 진행 상황 조회, User는 read-only |

### 의존 그래프

```
M0-1 ─┬─ M0-2 ─┬─ M2-* ─┬─ M3-*
      │        │         │
      │        ├─ M4-1 ─ M4-2 ─ M4-3, M4-4
      │        │
      └─ M1-1 ─┴─ M1-2 ─ M1-3
```

- M0-1은 모든 작업의 선행 조건
- M1(jobs 인프라)과 M2(spots) 사이엔 M1-1, M1-2가 M2-3 이전에 필요
- M4-3/M4-4는 M0/M1/M2/M3 완료 후

---

## 8. 오픈 이슈 / 후속 검토

- **변경 이력**: SQLAlchemy `after_update/after_delete` 이벤트 훅 / Postgres logical decoding / 외부 도구(예: pgaudit) 중 운영 비용/가시성 균형 검토
- **워커 동시성**: 단일 인스턴스 가정. 다중 인스턴스로 확장 시 `SELECT ... FOR UPDATE SKIP LOCKED` 기반으로 자연 확장 가능
- **자동 재시도**: 현재 미지원. 외부 데이터 소스 장애 등에서 필요해지면 재검토
- **SQLAdmin ARRAY 필드 UX**: 콤마 입력 / JSON 입력 / 태그 입력 중 어떤 형태가 기본인지 직접 확인 필요. 필요 시 커스텀 form 구현
