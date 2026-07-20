# 아키텍처 / DB 레퍼런스

> 대응 원본: `docs/architecture.md`, `docs/erd.md`
> ← [00-index.md](./00-index.md)

두 문서 모두 "living document" — 코드 변경 시 함께 갱신하는 것이 전제이며, 현재 실제 구현의 Source of Truth다.

## `architecture.md`

- **스택**: FastAPI / Python 3.12+ / SQLAlchemy 2.x async / PostgreSQL 16(asyncpg) / Alembic / Google OAuth 2.0+JWT / SQLAdmin + vivac-console(Refine) / S3(presigned)+CloudFront / uv / Docker Compose(local) / AWS Lightsail(prod)
- **계층**: Routers(HTTP·DI) → CRUD(쿼리, 화이트리스트) → Models(ORM) → PostgreSQL. Core는 횡단 관심사, Workers는 API 프로세스 내 asyncio task
- **인증 3흐름**:
  | 흐름 | 엔드포인트 | 토큰 | 만료 |
  |---|---|---|---|
  | 앱 사용자 | `POST /v1/auth/google` | HS256 JWT access+refresh | 30분/7일 |
  | vivac-console(staff) | `POST /v1/admin/auth/google` | HS256 JWT access | 8시간 |
  | SQLAdmin | 로그인 폼→`AdminAuth` | 서명된 세션 쿠키 | 세션 |
  - refresh 토큰은 완전 stateless(회수 불가, 의도된 트레이드오프)
  - staff 판정은 매 요청 DB 재조회, 토큰의 `is_staff` 클레임은 표시용
- **엔드포인트 전체 목록**(공개/인증필요/`/v1/internal/*`/운영UI) — 현재 실제 API 표면의 기준. `/v1/internal/*`는 라우터 단위 `require_staff`, Refine simple-rest 규약(`_start`/`_end`/`_sort`/`_order`+`X-Total-Count`)
- **Async Job Worker**: `jobs` 테이블 기반, API 프로세스 내 asyncio task, `FOR UPDATE SKIP LOCKED`로 중복처리 방지, 부팅 시 좀비 잡 정리. 설계 배경은 [02-projects.md](./02-projects.md)의 `async-job-worker-design.md` 참고
- **Audit Log**: `spots`/`spot_business_info`만 DB 트리거로 INSERT/UPDATE/DELETE 기록. 변경 주체는 `SET LOCAL app.user_id`로 주입
- **Image Storage 3단계**: presign(서버가 키 생성)→클라이언트가 S3 직접 PUT→register(경로·존재 검증 후 row 생성). `is_public`은 **서빙 방식 구분이지 접근 제어가 아님**(CDN vs presigned, 둘 다 공개 API 노출) — 이 지점이 [03-backlog.md](./03-backlog.md)의 `private-image-exposure` 이슈와 직결
- **DB 엔진**: `pool_size=5, max_overflow=10, pool_pre_ping=True`, prod는 `ssl=require`. PK는 전 테이블 shortuuid 22자
- **Configuration**: 전체 환경변수 표(ENVIRONMENT/DB_*/GOOGLE_CLIENT_ID/ALLOWED_EMAIL_DOMAIN/JWT_*/ADMIN_SESSION_SECRET/CORS_ALLOWED_ORIGINS/AWS_*/S3_*). prod 부팅 시 placeholder·약한 시크릿·잘못된 CORS 검증
- **배포**: 버전 태그(`v*.*.*`) push → GitHub Actions(`deploy.yml`) → docker buildx(amd64) → Docker Hub → SSH → Lightsail(alembic upgrade + docker compose up + 헬스체크). 프로비저닝 절차는 [06-infra-and-testing.md](./06-infra-and-testing.md) 참고. CI는 PR마다 ruff+alembic+pytest

## `erd.md`

- 전 도메인 테이블 PK: shortuuid 22자 `VARCHAR(22)`, `^[0-9A-Za-z]{22}$` CHECK (`audit_log`만 bigserial)
- **테이블**: `users`, `spots`, `spot_business_info`, `spot_reviews`, `spot_images`, `jobs`, `audit_log` — 각 컬럼/타입/nullable/인덱스 전체 Mermaid ERD로 정의
- **관계**: spots 1:1 spot_business_info(CASCADE) / spots 1:N spot_reviews·spot_images / users 1:N spot_reviews·spots(assigned_to, SET NULL)·jobs
- `audit_log`는 FK 없이 `(table_name, row_uid)` 텍스트로 대상 참조 — 원본 삭제돼도 이력 보존 목적
- **제약조건**: uid 포맷 CHECK 전 테이블, `email` lower unique index, `spots` source+external_id unique, `pipeline_status` CHECK(RAW~REJECTED), `trust_tier` CHECK(1~3), 리뷰 unique(spot_uid, user_id) + rating CHECK(0~5)
- **인덱스**: title/source/region/rating_avg/assigned_to_uid(spots), `ix_spots_published_uid`(partial, PUBLISHED만 — [03-backlog.md](./03-backlog.md)의 `pipeline-status-index` 이슈와 대비되는 지점), operating_status, spot_uid/user_id(reviews), status+created_at(jobs)
- **Audit Trigger**: `spots`/`spot_business_info`에만 부착, 신규 테이블 추가 시 트리거만 부착하면 확장 가능

## 다른 문서와의 연결

- [02-projects.md](./02-projects.md)의 `vivac-console-backend.md`는 이 문서가 실제 엔드포인트 기준(`/v1/internal/*`)이라고 스스로 인정
- [03-backlog.md](./03-backlog.md)의 이미지/pipeline_status 이슈 3건은 여기 서술된 구조(`is_public` 의미, partial index)를 전제로 발생
- [08-cross-cutting-issues.md](./08-cross-cutting-issues.md) §충돌-6: memory에 기록된 인프라(EC2+CloudFront+RDS)가 본 문서·`lightsail-setup.md`와 불일치
