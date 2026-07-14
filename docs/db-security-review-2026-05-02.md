# 데이터베이스 스키마 보안/위험 점검 보고서

- **작성일:** 2026-05-02
- **대상 브랜치:** `feature/user-model-update`
- **점검 범위:** `app/models/`, `alembic/versions/`, `app/core/database.py`
- **현재 적용된 마이그레이션:** `b33fd71c6fea` (head)

> 본 보고서는 *현재 시점에 실제로 적용된* 스키마/연결 설정만을 대상으로 합니다.
> 다른 브랜치(`feature/spot-models` 등)에서 진행 중인 모델은 머지된 후 별도 점검이 필요합니다.

## 후속 처리 현황 (2026-07-14 업데이트)

작성 당시의 `app/` 구조·INTEGER PK 등은 이후 코드베이스와 달라졌다. 항목별 현재 상태:

| 항목 | 상태 | 비고 |
|---|---|---|
| H-1 정수 PK 열거 가능성 | ✅ 해결 | 전 테이블 shortuuid `VARCHAR(22)` PK로 전환 |
| H-2 email 대소문자 민감성 | ✅ 해결 | 소문자 정규화 + `lower(email)` unique index (`e5c7d9a1b3f4`) |
| M-1 PII 감사 로그 부재 | ✅ 부분 해결 | `audit_log` + 트리거 도입 (spots/spot_business_info 대상. users는 미적용) |
| M-2 picture URL 검증 누락 | ⏸ 보류 | picture는 Google OAuth 클레임에서만 저장(사용자 입력 경로 없음) — 위험 낮음 |
| M-3 google_sub 길이/IdP 가정 | ⏸ 보류 | IdP 추가 결정 시 `auth_identities` 분리 |
| M-4 신규 컬럼 시간 정합성 | ⏸ 보류 | 앱 레이어에서 `now()`만 기록 |
| M-5 partial unique index | ⏸ 보류 | soft delete 정책 미정 |
| L-1 풀 사이즈 운영 검증 | ⏸ 보류 | 단일 인스턴스 규모에서 미측정 |
| L-2 echo local 분기 | ✅ 완화 | `ENVIRONMENT`가 Literal enum으로 검증됨 |
| L-3 자격증명 처리 | ✅ 해결 | `SecretStr` 적용, `database_url` 직렬화 제외 |
| L-4 expire_on_commit 부수효과 | ✅ 해당 없음 | 권한 분기는 요청마다 새 세션에서 재조회 |
| I-2 downgrade 가드 | ⏸ 보류 | 운영 정책으로만 관리 중 |

---

## 1. 점검 대상 요약

### 1.1 테이블: `users`

| 컬럼 | 타입 | NULL | 인덱스 | 비고 |
|---|---|---|---|---|
| `id` | `INTEGER` (auto-increment) | NO | PK | SERIAL |
| `email` | `VARCHAR(320)` | NO | UNIQUE | RFC 5321 최대 길이 |
| `google_sub` | `VARCHAR(255)` | NO | UNIQUE | Google OAuth subject |
| `name` | `VARCHAR(100)` | YES | — | |
| `picture` | `VARCHAR(2048)` | YES | — | URL |
| `is_active` | `BOOLEAN` | NO | — | default=true |
| `identity_verified_at` | `TIMESTAMPTZ` | YES | — | NULL=미인증 |
| `onboarding_survey_completed_at` | `TIMESTAMPTZ` | YES | — | NULL=미완료 |
| `created_at` | `TIMESTAMPTZ` | NO | — | server_default=now() |
| `updated_at` | `TIMESTAMPTZ` | NO | — | onupdate=now() |

### 1.2 연결/엔진 설정 (`app/core/database.py`)

- `create_async_engine(database_url, echo=ENVIRONMENT == "local", pool_size=5, max_overflow=10, pool_pre_ping=True)`
- 세션 생성: `async_sessionmaker(expire_on_commit=False)`
- DSN은 `settings.database_url`에서 주입 (구체 검증은 `app/core/config.py` 참고).

---

## 2. 식별된 위험 항목

심각도 표기: 🔴 High / 🟠 Medium / 🟡 Low / ⚪ Info

### 🔴 H-1. 정수 시퀀스 PK의 열거 가능성 (Enumeration)

**문제:** `users.id`가 1부터 1씩 증가하는 SERIAL입니다. PK 값이 URL/응답/JWT 등에 노출되면 사용자 수, 가입 추세, 추정 식별자 범위 등이 외부에 드러납니다. (다른 브랜치에서 User PK를 UUID로 변경하는 작업이 있다는 메모가 있음 — 통합되면 이 항목은 자동 해소.)

**영향:** 정보 유출, 추정 기반 공격 (예: 다른 user의 ID 추측 후 권한 검증 누락 시 IDOR로 발전).

**완화:**
- PK를 UUID(v4 또는 v7)로 변경, 또는
- 외부 노출용 별도 식별자 컬럼(`public_id UUID UNIQUE NOT NULL`) 추가하고 응답에는 그 값만 사용.
- `feature/spot-models` 브랜치의 UUID 전환 작업과 통합 우선순위 ↑.

---

### 🔴 H-2. `email` UNIQUE의 대소문자 민감성

**문제:** 현재 `email` 컬럼은 `VARCHAR(320)` UNIQUE로, **대소문자 구분 인덱스**입니다. `User@example.com`과 `user@example.com`이 별개 행으로 저장될 수 있어 계정 중복/탈취 위험이 있습니다.

**영향:**
- 같은 이메일로 다중 계정 생성 → 권한/결제 정합성 문제.
- Google OAuth `email` 클레임을 신뢰해 매칭하는 코드와 결합 시 인증 우회 위험.

**완화:**
- 저장 전 `lower(email)`로 정규화 (애플리케이션 레이어), 또는
- `CREATE UNIQUE INDEX ix_users_email_lower ON users (lower(email));` 으로 functional unique index 사용 (마이그레이션 추가 권장), 또는
- PostgreSQL `CITEXT` 확장을 사용한 컬럼 타입 변경.

---

### 🟠 M-1. PII (이메일/이름/사진) 평문 저장 + 감사 로그 부재

**문제:** 이메일, 이름, 프로필 사진 URL은 모두 PII입니다. 현재 평문 저장이며, 누가 언제 어떤 PII를 조회/변경했는지 추적할 컬럼/테이블이 없습니다.

**영향:** GDPR/개인정보보호법상 처리 이력 요구사항 미충족 가능. DB 덤프 유출 시 즉시 노출.

**완화:**
- 최소한 `updated_at`만 있는 현재 구조에 **변경 이력 테이블** 또는 트리거 기반 감사 로그 도입 검토.
- 운영 DB에서 *encryption-at-rest* 적용 여부 확인 (RDS/Cloud SQL은 옵션 존재).
- 저장이 정말 필요 없는 PII (예: `picture` URL이 외부 CDN에 의존하면 캐싱 정책 정의)는 보존 정책 명시.

---

### 🟠 M-2. `picture` URL 길이/검증 누락

**문제:** `picture VARCHAR(2048)`은 길이 제한만 있고 **URL 형식/스킴/도메인 검증이 없습니다**. 클라이언트 또는 OAuth 응답이 조작되면 `javascript:`, `data:`, 내부망 IP(`http://10.0.0.x/...`) 등이 저장될 수 있습니다.

**영향:**
- 프론트엔드가 `<img src=...>`로 그대로 렌더링 시 XSS/SSRF 가능성 (특히 서버사이드에서 미리보기/프록시할 때).
- 내부망 호출로 SSRF.

**완화:**
- 스키마 단에서 `CHECK (picture LIKE 'https://%')` 또는,
- 애플리케이션에서 `https` 스킴 + 화이트리스트 도메인(`googleusercontent.com` 등) 검증 후 저장.
- 응답 시 클라이언트에 노출하기 전 sanitize.

---

### 🟠 M-3. `google_sub` 길이 가정

**문제:** `google_sub VARCHAR(255)`. Google `sub`은 문서상 21자리 숫자 문자열이지만, 향후 변경/타 IdP 통합 가능성을 고려한 검증이 없습니다. 또한 `nullable=False`이므로 **OAuth 외 가입 경로(이메일/비밀번호 등)가 추가되면 마이그레이션 필요**합니다.

**영향:** 향후 IdP 다양화 시 스키마 락인. 또한 `google_sub`가 비어있는 행을 만들기 위한 임시값(빈 문자열, dummy) 삽입 패턴이 생기면 UNIQUE 충돌/중복 계정 위험.

**완화:**
- 단기: 그대로 유지하되 IdP 추가가 결정되면 `google_sub`을 nullable로 바꾸고 `provider`, `provider_subject` 형태의 정규화 테이블(`auth_identities`) 도입.
- `CHECK (google_sub ~ '^[0-9]{1,255}$')` 등 형식 제약 추가는 *과도할 수 있음* — 도메인 변경 비용 고려해 보류 가능.

---

### 🟠 M-4. 신규 두 컬럼의 의미 강제 부재

**문제:** `identity_verified_at`, `onboarding_survey_completed_at` 모두 nullable `TIMESTAMPTZ`로, **미래 시각/과거 1900년대 등 비현실적 값**이 들어가도 DB가 막지 못합니다. 또한 `created_at`보다 *이전* 시각이 저장될 수 있습니다.

**영향:** 잘못된 클라이언트/배치 작업이 데이터 정합성을 깨뜨릴 때 추적이 어렵습니다.

**완화:**
- `CHECK (identity_verified_at IS NULL OR identity_verified_at >= created_at)`
- `CHECK (onboarding_survey_completed_at IS NULL OR onboarding_survey_completed_at >= created_at)`
- 또는 애플리케이션 레이어에서 `func.now()`만 쓰도록 enforce.

---

### 🟠 M-5. `is_active = false` 상태에서의 부분 인덱스 미사용

**문제:** `email`, `google_sub` UNIQUE 인덱스가 비활성/소프트삭제 행도 포함합니다. 미래에 *soft delete*(`deleted_at`) 또는 *재가입* 정책이 도입되면 UNIQUE 충돌이 발생합니다.

**영향:** 탈퇴 후 재가입 시나리오를 막거나, 우회를 위해 강제로 row를 변형하게 됩니다.

**완화:**
- 정책이 구체화될 때 `CREATE UNIQUE INDEX … WHERE is_active = TRUE AND deleted_at IS NULL` 형태의 partial unique index로 전환.
- 현재로서는 **결정 보류 + 위험만 인지** 권장.

---

### 🟡 L-1. `pool_size=5, max_overflow=10` — 운영 환경 적합성 미검증

**문제:** 동시 요청 수와 DB 연결 한도에 비해 작거나 클 수 있습니다. 운영 환경의 `max_connections`와 어플리케이션 인스턴스 수의 곱을 고려하지 않으면, 트래픽 급증 시 *connection storm* 또는 풀 고갈로 5xx가 발생합니다.

**완화:** 운영 인스턴스 수와 RDS/Cloud SQL `max_connections`을 기반으로 재산정, `SQLAlchemy` 풀 메트릭(`pool_size`, `checked_out`)을 모니터링.

---

### 🟡 L-2. `echo` 분기가 `ENVIRONMENT == "local"`에 의존

**문제:** `echo=settings.ENVIRONMENT == "local"`. 환경 변수 오설정으로 운영에서 `local`이 들어가면 **모든 SQL이 로그에 평문 출력**됩니다. SQL 파라미터에는 PII/토큰이 포함될 수 있습니다.

**완화:**
- 운영 환경에서 `ENVIRONMENT` 검증 (앱 부팅 시 허용값 enum 체크).
- `echo=False`를 default로 하고, 명시적 `DEBUG_SQL=true` 같은 별도 플래그로 켜는 패턴.

---

### 🟡 L-3. `DATABASE_URL` 자격증명 처리

**문제:** `app/core/config.py`에서 `database_url`을 어떻게 구성하는지 본 보고서에서는 직접 확인하지 않았습니다. 일반적으로 `postgresql+asyncpg://user:pw@host/db` 형태로 비밀번호가 포함되며, **로깅/예외 메시지에 그대로 노출되는 경로**가 있는지 점검이 필요합니다.

**완화:**
- pydantic-settings의 `SecretStr` 사용 여부 확인.
- 예외 핸들러에서 `DATABASE_URL`이 메시지에 포함되지 않도록 sanitize.
- `.env.local` 등 로컬 파일에는 비밀번호가 들어갈 수 있으므로 `.gitignore` 확인.

---

### 🟡 L-4. `expire_on_commit=False`의 부수효과

**문제:** 세션 커밋 후에도 ORM 객체 속성을 그대로 사용 가능 — 편리하지만, **stale 데이터를 반환**할 수 있습니다. 인증/권한 분기에서 stale 데이터를 사용하면 보안 결정에 영향을 줄 수 있습니다.

**완화:**
- 권한/세션 검증 시점에는 명시적으로 `await session.refresh(user)` 또는 새 세션에서 재조회.
- 핵심 분기점에서만 적용해도 충분.

---

### ⚪ I-1. 마이그레이션 파일에 `# please adjust!` 주석 잔류

**관찰:** `b33fd71c6fea_…py`, `1d762a067d5e_…py` 모두 Alembic autogenerate 기본 주석을 그대로 두고 있습니다. 위험은 아니지만, 운영 마이그레이션은 **수동 검토 흔적을 남기는 것**(주석 정리, 인덱스 추가 등)이 안전 문화에 도움이 됩니다.

---

### ⚪ I-2. 백필/다운그레이드 안전성

**관찰:** 신규 컬럼 두 개 모두 nullable이라 백필 없이 안전. 다만 `1d762a067d5e`의 downgrade는 `users` 테이블 자체를 drop합니다. 운영에서 절대 실행되어선 안 되며 — Alembic은 이를 막지 않습니다. **운영 환경에서 `alembic downgrade` 실행을 차단할 운영 정책/CI 가드**가 필요합니다.

---

## 3. 우선순위 권장 액션

| # | 우선순위 | 항목 | 작업량 |
|---|---|---|---|
| 1 | 🔴 즉시 | H-2 이메일 lowercase 정규화 + functional unique index | 마이그레이션 1개 + CRUD 1군데 |
| 2 | 🔴 단기 | H-1 PK UUID 전환 (다른 브랜치와 통합) | 큰 작업, 별도 PR 권장 |
| 3 | 🟠 단기 | M-2 picture URL 검증(스킴/도메인 화이트리스트) | 검증 함수 1개 |
| 4 | 🟠 단기 | M-4 두 신규 컬럼에 시간 정합성 CHECK 제약 | 마이그레이션 1개 |
| 5 | 🟠 중기 | M-1 감사 로그/PII 보존 정책 수립 | 설계 문서 |
| 6 | 🟡 중기 | L-2/L-3 echo 안전장치 + SecretStr 적용 | 설정 리팩터 |
| 7 | 🟠 중기 | M-3 다중 IdP 대비 `auth_identities` 분리 설계 | 설계 문서 |
| 8 | 🟡 장기 | L-1 풀 사이즈 운영 점검 | 모니터링 도입 |

---

## 4. 본 보고서가 다루지 않은 것

- 운영 PostgreSQL 인스턴스의 권한/네트워크/암호화 설정 (DB 쪽 점검 별도 필요).
- 백업/복구 정책 및 PITR 적용 여부.
- `feature/spot-models` 등 미머지 브랜치의 스키마.
- 애플리케이션 레이어 SQLi (SQLAlchemy ORM 사용으로 표면적 위험은 낮음 — 문자열 SQL 사용 위치 grep 별도 권장).
