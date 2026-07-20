# 프로젝트 설계 문서 (`docs/projects/`)

> 대응 원본: `projects/*.md` 7개
> ← [00-index.md](./00-index.md)

## `async-job-worker-design.md` (VVC-96, 2026-05-17) — 구현 완료

FastAPI 프로세스 안에 워커 1개, `jobs` 테이블 2초 폴링, 외부 브로커 없음, 단일 Lightsail 인스턴스 가정.

- **비교 검토한 대안 5가지와 기각 사유**: Celery/Dramatiq(과함, 빈도 낮음) / `BackgroundTasks`(영속성 없음, 부적합) / LISTEN+NOTIFY(복잡도 대비 이득 작음) / 별도 워커 프로세스(단일 인스턴스라 격리 이점 약함) / SQS 등 매니지드 큐(트래픽 규모 안 맞음)
- **결정 8가지**: 매 사이클 새 세션 / 명시적 dict 핸들러 등록 / claim-작업 트랜잭션 분리 / 예외 전체 traceback 기록 / 단일사이클 함수분리 테스트 / 폴링 2초 / 동시성 1(SKIP LOCKED로 향후 확장 자연스러움) / 자동 재시도 없음
- **향후 검토(Out of Scope)**: CPU바운드 시 `asyncio.to_thread()`, graceful shutdown(>5분 작업), LISTEN/NOTIFY, 자동 재시도

## `spot-bulk-and-admin.md` (2026-05-17) — 구현 완료

캠핑 스팟 데이터 일괄 적재(엔지니어용 JSON API) + SQLAdmin 백오피스(비엔지니어용).

- **핵심 결정**: JSON 입력 / 비동기 jobs 테이블 처리 / `Spot.external_id`를 upsert 키로 신설 / 부분실패 시 전체 트랜잭션 롤백 / SQLAdmin `/admin` 마운트 / 권한은 `User.is_staff` bool 단일 / 변경이력(audit log)은 본 프로젝트 범위 밖
- **API**: `POST /internal/spots/bulk`, `POST /internal/spot-business-info/bulk`(202+job_id), `GET /internal/jobs/{job_id}`. 한도 5,000행 / 5 MiB
- **SQLAdmin 모델**: `SpotAdmin`/`SpotBusinessInfoAdmin`/`JobAdmin`/`UserAdmin`(read-only), 전 모델 `can_delete=False` 기본
- **마일스톤**: M0(스태프 권한)→M1(jobs 인프라)→M2(spots bulk)→M3(business_info bulk)→M4(SQLAdmin), 의존 그래프 포함
- **후속 검토**: 변경이력 도입 방식, 워커 다중 인스턴스 확장, 자동 재시도, SQLAdmin ARRAY 필드 UX

## `spot-groups-admin-api.md` (2026-07-15) — 최신 SoT

`vivac-console`이 임의 유저의 spot group을 조회/모더레이션하도록 `/v1/internal/groups/*` 신설. **`vivac-console-backend.md`가 낡았다고 명시적으로 정정하는 문서** — "그 문서는 `/v1/admin/*` 스냅샷이라 지금은 낡음. 실제 경로는 `/v1/internal/*`. 본 문서가 최신."

- **결정 요약**: 멤버십 체크 생략(staff는 owner/editor 무관 접근) / 라우터 단위 `require_staff` + 파괴적 작업만 `require_role(MANAGER)` / PRIVATE 그룹도 어드민은 초대 가능(앱 API와 유일한 의도적 차이) / last-owner 안전장치는 어드민도 유지 / 신규 에러코드 없음(기존 재사용)
- **엔드포인트 10개**: 목록(Refine simple-rest)/상세/메타수정(`STAFF`)/삭제(`MANAGER`)/멤버목록/멤버강제추가(`MANAGER`)/역할강제변경(`MANAGER`)/멤버강제제거(`MANAGER`)/그룹내spot목록/spot강제제거(`STAFF`, 단일항목이라 가역적)
- **권한 등급 근거**: `STAFF`=조회+단일제거(가역적)+메타수정(모더레이션, 파괴 아님) / `MANAGER`=그룹삭제(비가역)+임의유저 owner권한 부여박탈(권한상승 리스크)
- **CRUD**: 신규 함수 3개(`list_groups_admin`, `count_group_members`, `list_members_admin`), 나머지는 기존 `crud/spot_group.py` 재사용
- **FE 액션**: Refine dataProvider 리소스 3개 등록, `MANAGER` 전용 액션 UI 노출/403 토스트 처리
- **Out of Scope**: 콘솔에서 그룹 신규생성, 멤버초대 이력/알림, audit log 연동

## `spot-invites.md` (2026-07-16) — 구현 완료, ⚠️ 일부 결정 역전됨

공유 링크 기반 초대. 그룹 초대 + 일반 앱 리퍼럴을 단일 `Invite` 엔티티로 처리.

- **결정 요약(발췌)**: 공유 링크 방식(이메일 특정 아님) / `group_uid` nullable로 그룹초대·리퍼럴 겸용 / **"1회용 — 수락되면 `ACCEPTED`로 종료, 재사용 불가"** / 별도 token 컬럼 없이 `uid` 자체가 링크 토큰 / 그룹초대 생성권한은 `OWNER`만+PRIVATE 그룹 불가 / 신규가입 시 초대 소비는 best-effort(실패해도 로그인은 항상 성공)
- **스키마**: `Invite`(uid PK겸토큰, inviter_uid, group_uid nullable CASCADE, group_role nullable, status, accepted_by_uid, accepted_at), `User.referred_by_uid`
- **엔드포인트 4개**: 발급/미리보기(인증불필요)/기존유저 수락/신규가입 자동수락(`POST /v1/auth/google`에 `invite_uid` 추가)
- **테스트**: `tests/test_invites_router.py` 17개
- **트러블슈팅 기록 2건**: (1) 마이그레이션에서 enum 중복생성 — `create_table`이 타입 생성까지 관리하게 둬야 함(`create_type=False` 사전생성은 기존 컬럼에 enum 추가할 때만 유효) (2) 로컬 공유 `vivac_test` DB가 병행 브랜치 마이그레이션과 충돌 — 워크트리 전용 DB(`vivac_test_invites`)로 격리
- **Out of Scope 원안**: 초대취소(REVOKED), 만료, **재사용 가능한 링크(다수가입 허용) — "사용자가 명시적으로 1회용 선택"**, 이메일지정초대, 프론트연동, 리퍼럴 집계 API

> ⚠️ **위 굵게 표시한 "1회용" 결정은 [05-business-roadmap.md](./05-business-roadmap.md) 1.1(2026-07-20)에서 뒤집혔다.** `consume_invite_for_signup`이 일반 리퍼럴(`group_uid is None`)에 한해 `PENDING`을 유지하도록 변경돼 재사용 가능해짐. 이 문서(`spot-invites.md`) 원본은 갱신되지 않은 채 남아있다 — 상세는 [08-cross-cutting-issues.md](./08-cross-cutting-issues.md) 참고.

## `spot-search-postgres-fts.md` (VVC-107, 2026-07-15) — 구현 완료

Elasticsearch 없이 PostgreSQL(`pg_trgm`+`tsvector`)만으로 검색.

- **ES 도입 안 하는 이유(5개 검토축)**: 데이터규모(수천~수만, GIN으로 충분) / 인프라비용(EC2 t2.micro 1대로 core도 겨우 도는 인프라에 ES 클러스터는 부담) / 동기화문제(CDC/outbox 파이프라인 신규 구축 필요) / 검색요구수준(오타허용+부분매칭+가중치 정도면 충분) / 한국어형태소분석 불필요
- **전환 고려 조건(2개 이상 해당 시 재검토)**: 규모(수십만+), 검색품질요구상승(동의어사전 등), 집계요구(실시간 facet aggregation), QPS(부하분리 필요)
- **매칭**: title(A)/tagline(B)/description(C)/address(D) 가중치 `tsvector`(simple config, 한글엔 스테밍 없는 게 안전) + title에만 `pg_trgm`(similarity>0.2) 보완. category/region은 구조화 필터로 랭킹 분리
- **스코어**: `ts_rank + similarity*0.3` — **계수 0.3, 임계값 0.2는 문서가 스스로 "잠정값, 실사용 로그 쌓이면 재조정 필요"라고 명시(후속 과제)**
- **정렬**: `score DESC, rating_avg DESC, uid DESC`(결정론적)
- **페이지네이션**: 검색모드 전용 composite cursor(`{score, rating_avg, uid}`), 기본목록 cursor(`uid` 평문)와 완전 분리 — 섞어보내면 422
- **Out of Scope**: 동의어사전, sort enum 실구현(VVC-119), 지리반경검색, trigram 자동튜닝

## `vivac-console-backend.md` (2026-06-07) — ⚠️ 낡음(문서 자체가 명시)

`/v1/admin/*` 경로로 spot/spot_business_info CRUD를 설계한 문서. **문서 최상단에 경고 존재**: "구현 완료된 설계 스냅샷. 실제 구현에서 리소스 경로는 `/v1/admin/*`이 아닌 `/v1/internal/*`로 확정됐다(로그인만 `/v1/admin/auth/google`). 현재 엔드포인트 목록은 architecture.md가 기준이다."

- 원 설계 내용(참고용, 실제와 다름): `POST/GET/PATCH/DELETE /v1/admin/spots`(offset+total 페이지네이션, public API의 cursor와 의도적 분리), 동일 패턴 `/v1/admin/spot-business-info`, `require_staff` 라우터 단위 적용
- 이 경고는 짝 문서 [`spot-groups-admin-api.md`](#spot-groups-admin-apimd-2026-07-15--최신-sot)에서도 재확인됨

## `vivac-console-frontend.md` (2026-06-07) — ⚠️ 낡음(경고 누락)

별도 repo `vivac-console` 초기 세팅 문서(백엔드 짝 문서와 동시 작성). Next.js 15 App Router + TypeScript / Refine / shadcn+Tailwind / TanStack Table / React Hook Form+Zod / NextAuth(Google, hd 도메인 제한) / pnpm.

- 인증 흐름: 도메인 검증(NextAuth signIn 콜백) → 백엔드 `/v1/auth/google`로 Google ID Token 교환 → 백엔드 JWT를 세션에 저장 → 이후 `Authorization: Bearer` 자동 첨부. 회사 도메인이어도 백엔드 `is_staff=False`면 여전히 401/403
- 리소스 등록 예시가 `/spots`, `/spot-business-info`를 Refine 리소스로 등록하는 코드 스니펫 포함 — **경로 전제가 backend.md와 동일하게 `/v1/admin/*` 기준**
- 배포 옵션: Vercel(권장 초기) 또는 기존 Lightsail 함께 호스팅
- Out of Scope: 대시보드/통계, 파일업로드 UI, audit log 뷰, 역할기반 권한

> ⚠️ 짝 문서(backend.md)는 낡음을 스스로 밝혔지만 이 문서엔 그 경고가 없다 — 상세는 [08-cross-cutting-issues.md](./08-cross-cutting-issues.md) 참고.

## `vvc-105-explore-api-spec.md` (VVC-105, 2026-05-19) — 구현 완료

탐색 API(`GET /v1/explore/spots`) 계약을 OpenAPI로 확정. FE/BE 병렬 구현 목적, 스펙+스텁만(실제 쿼리/필터/정렬은 후속).

- **결정 요약**: 리소스명 `/v1/explore/spots`(DB 테이블명과 일치) / 공개(비로그인) / cursor 페이지네이션 채택(offset 명시적 거부 — 무한스크롤 UI, rating 동률 다발, 실시간 갱신에 의한 offset 드리프트, 대용량 시 성능 열화) / `limit` 기본 20, 1~50, 초과 시 422(자동 clamp 안 함, FE 오판 방지)
- **cursor**: opaque base64(JSON), `{"r", "u", "s"}` — `s`(정렬키) 불일치 시 422로 거부. tie-break는 `uid DESC` 고정
- **정렬 enum**: `popular`/`latest`/`rating` — 의미·실제 로직은 VVC-119로 분리(본 스펙은 enum만 노출)
- **Out of Scope(후속 이슈 매핑)**: 필터(VVC-117) / 이미지필드(VVC-118) / 정렬확정+인덱스(VVC-119) / 검색핸들러(VVC-107 → [완료, 위 항목 참고]) / 페이지네이션구현(VVC-110) / 상세핸들러(VVC-108)
