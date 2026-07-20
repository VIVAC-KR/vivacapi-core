# DB 스키마 보안 점검 보고서

> 대응 원본: `db-security-review-2026-05-02.md`
> ← [00-index.md](./00-index.md)

- 작성일 2026-05-02, 대상 브랜치 `feature/user-model-update`, 점검 범위 `app/models/`, `alembic/versions/`, `app/core/database.py` (당시 `users` 테이블만, `app/` 구조 — 현재 `vivacapi/`와 다름에 유의)
- **문서 자체에 "2026-07-14 후속 처리 현황" 표가 있어 각 항목이 최신화됨** — 아래는 그 표 그대로.

## 후속 처리 현황 (2026-07-14 기준)

| 항목 | 상태 | 비고 |
|---|---|---|
| H-1 정수 PK 열거 가능성 | ✅ 해결 | 전 테이블 shortuuid `VARCHAR(22)` PK로 전환 |
| H-2 email 대소문자 민감성 | ✅ 해결 | 소문자 정규화 + `lower(email)` unique index |
| M-1 PII 감사 로그 부재 | ✅ 부분 해결 | `audit_log`+트리거 도입(spots/spot_business_info만, **users는 미적용**) |
| M-2 picture URL 검증 누락 | ⏸ 보류 | Google OAuth 클레임에서만 저장(사용자 입력 경로 없음) — 위험 낮음 |
| M-3 google_sub 길이/IdP 가정 | ⏸ 보류 | IdP 추가 결정 시 `auth_identities` 분리 |
| M-4 신규 컬럼 시간 정합성 | ⏸ 보류 | 앱 레이어에서 `now()`만 기록 |
| M-5 partial unique index | ⏸ 보류 | soft delete 정책 미정 |
| L-1 풀 사이즈 운영 검증 | ⏸ 보류 | 단일 인스턴스 규모에서 미측정 |
| L-2 echo local 분기 | ✅ 완화 | `ENVIRONMENT`가 Literal enum으로 검증됨 |
| L-3 자격증명 처리 | ✅ 해결 | `SecretStr` 적용, `database_url` 직렬화 제외 |
| L-4 expire_on_commit 부수효과 | ✅ 해당 없음 | 권한 분기는 요청마다 새 세션 재조회 |
| I-2 downgrade 가드 | ⏸ 보류 | 운영 정책으로만 관리 중 |

## 원본 점검 항목 (2026-05-02 시점, 참고용)

| 심각도 | 항목 | 요지 |
|---|---|---|
| 🔴 H-1 | 정수 시퀀스 PK 열거가능성 | `users.id` SERIAL — 가입추세·범위 추정 위험 |
| 🔴 H-2 | email UNIQUE 대소문자 민감성 | `User@x.com`/`user@x.com` 별개 행 가능, 다중계정/인증우회 위험 |
| 🟠 M-1 | PII 평문저장+감사로그 부재 | 이메일/이름/사진 평문, 변경이력 추적 불가 |
| 🟠 M-2 | picture URL 검증 누락 | 스킴/도메인 검증 없어 XSS/SSRF 여지 |
| 🟠 M-3 | google_sub 길이 가정 | 타 IdP 확장 시 스키마 락인 |
| 🟠 M-4 | 신규 컬럼 시간 정합성 부재 | `identity_verified_at` 등이 `created_at`보다 과거일 수 있음 |
| 🟠 M-5 | partial unique index 부재 | soft delete/재가입 도입 시 UNIQUE 충돌 가능 |
| 🟡 L-1 | pool_size 운영 적합성 미검증 | connection storm 위험 |
| 🟡 L-2 | echo가 `ENVIRONMENT=="local"`에만 의존 | 오설정 시 SQL 평문 로그(PII/토큰 포함 가능) |
| 🟡 L-3 | DATABASE_URL 자격증명 처리 | 로깅/예외 노출 경로 점검 필요 |
| 🟡 L-4 | expire_on_commit=False 부수효과 | stale 데이터로 권한분기 영향 가능 |
| ⚪ I-1 | 마이그레이션 `# please adjust!` 주석 잔류 | 위험 아님, 수동검토 흔적 문화 권장 |
| ⚪ I-2 | 백필/다운그레이드 안전성 | `1d762a067d5e` downgrade가 `users` 테이블 drop — 운영 차단 정책/가드 필요 |

## 우선순위 권장 액션 (원본)

1. 🔴즉시 H-2 email lowercase 정규화+functional unique index
2. 🔴단기 H-1 PK UUID 전환
3. 🟠단기 M-2 picture URL 검증
4. 🟠단기 M-4 시간정합성 CHECK
5. 🟠중기 M-1 감사로그/PII 보존정책
6. 🟡중기 L-2/L-3 echo안전장치+SecretStr
7. 🟠중기 M-3 다중IdP 대비 auth_identities 분리
8. 🟡장기 L-1 풀사이즈 운영점검

## 본 보고서가 다루지 않은 것 (원본 명시)

운영 PostgreSQL 인스턴스 권한/네트워크/암호화, 백업/복구 정책, 미머지 브랜치 스키마, 애플리케이션 레이어 SQLi(ORM 사용으로 표면적 위험 낮음, 별도 grep 권장)

## 참고

- `skill-db-inspect.md`([07-skill-draft.md](./07-skill-draft.md))는 이런 보고서를 `/db_inspect` 명령으로 **매번 새 파일 생성**하는 방식을 제안하는데, 이 문서는 실제로는 **같은 파일을 갱신**해온 이력이 있다 — 운영 방침 차이는 [08-cross-cutting-issues.md](./08-cross-cutting-issues.md) 참고.
