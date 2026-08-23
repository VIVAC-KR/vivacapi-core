# 보안/인증 규약

## 토큰 정책 (의도된 트레이드오프)

- JWT는 완전 stateless — refresh 토큰(7일)도 서버 저장/회수 수단이 없다.
  유출 시 만료 전까지 유효하다는 것을 알고 선택한 트레이드오프(운영 단순성 우선).
  회수가 필요해지면 refresh 토큰만 DB에 jti를 저장하는 방식으로 전환한다.

## `/admin` 세션 쿠키

- SQLAdmin의 `AuthenticationBackend`에 넘긴 kwargs는 그대로 starlette
  `SessionMiddleware`로 전달된다. **기본값을 쓰면 안 된다** —
  `https_only=False`(Secure 플래그 없음) + `max_age=14일`이라, 8시간짜리 어드민
  JWT보다 훨씬 무른 경로가 열린다.
- 현재 설정(`main.py`): `https_only=(ENVIRONMENT != "local")`,
  `max_age=JWT_ADMIN_ACCESS_TOKEN_EXPIRE_HOURS * 3600`.
- `same_site`는 기본값 `"lax"`를 유지한다 — SQLAdmin에는 CSRF 토큰이 없어,
  cross-site POST를 막아주는 유일한 방어선이다. `"none"`으로 낮추지 말 것.

## API 문서 노출

- prod에서는 `/docs`·`/redoc`·`/openapi.json`을 끈다 (`main.py`의 `_IS_PROD`
  분기). internal 어드민 엔드포인트 스키마가 인증 없이 노출되지 않게 하기 위함.
- `openapi_url=None`이면 `/scalar`도 함께 죽는다 (openapi 문서를 참조하므로).
  prod에서 문서가 필요해지면 문서 라우트 자체에 인증을 걸어야 한다 — 되살리기만
  하면 안 된다.

## 레이트 리밋 (`core/limits.py`)

- `rate_limit(scope, times=, seconds=)` 의존성을 엔드포인트 `dependencies=`에
  얹는다. 카운터는 Redis(`cache.incr_with_ttl`), 고정 윈도우.
- 키는 **로그인 유저면 uid, 아니면 peer IP**다. CloudFront 뒤에서는 여러
  사용자가 edge IP 하나로 뭉치므로 비로그인 엔드포인트의 한도는 넉넉히 잡는다.
  `X-Forwarded-For`는 EC2에 직접 붙으면 위조 가능해 **신뢰하지 않는다** —
  IP 단위 정밀 제한이 필요하면 앱이 아니라 CloudFront/WAF rate rule로 올린다.
- `REDIS_URL` 미설정/Redis 장애 시 fail-open (제한 없이 통과). 캐시와 같은
  정책이며, 그래서 **prod에는 `REDIS_URL`이 설정돼 있어야 남용 제한이 산다**.
- 현재 한도:
  - `POST /v1/auth/google` 30회/분, `POST /v1/auth/refresh` 60회/분,
    `POST /v1/admin/auth/google` 30회/분 (IP 기준)
  - `POST /v1/invites` 20회/시간, 리뷰 작성·신고 각 30회/시간 (유저 기준)
  - `POST /v1/internal/spots/{uid}/images/presign`,
    `POST /v1/internal/spots/{uid}/images` 각 30회/분 (staff uid 기준, 두
    엔드포인트가 같은 scope `internal_image_upload`를 공유)

## 초대 링크 (`crud/invite.py`)

- 링크는 발급 후에도 계속 살아있으므로, **수락 시점에 권한 상태를 재검증한다**
  (`is_group_invite_still_valid`). 발급 시점 검사만으로는 강등/추방된 발급자가
  남긴 링크가 박제된 role을 계속 나눠주고, PRIVATE로 바뀐 그룹에도 계속 합류된다.
- 재검증 조건: 발급 후 `GROUP_INVITE_TTL`(14일) 이내 + 그룹이 아직
  PRIVATE가 아님 + 발급자가 아직 그 그룹의 `owner`.
- 만료는 `created_at` 기준 계산이며 `expires_at` 컬럼은 두지 않는다 —
  초대별로 만료를 다르게 줄 이유가 생기면 그때 컬럼을 추가한다.
- 수락 경로는 두 개다 (`POST /v1/invites/{uid}/accept`, 신규 가입 시
  `consume_invite_for_signup`). **둘 다 같은 재검증을 거친다** — 가입 흐름에서는
  검증에 걸려도 리퍼럴 귀속(`referred_by_uid`)은 남기고 그룹 합류만 건너뛴다.

## job 에러 메시지

- `job.error` / `job.result.errors[].reason`에는 `sanitize_exc_message()`를
  거친 값만 넣는다 (`core/errors.py`). traceback 전문이나 `str(exc)` 원본을
  그대로 넣지 말 것 — SQLAlchemy는 실행 SQL과 바인딩된 파라미터를 예외 문자열에
  붙이고, `GET /v1/internal/jobs/{id}`는 `STAFF`면 누구나 읽을 수 있다
  (enqueue는 `SUPERUSER`인데 결과 열람은 `STAFF` — 비대칭에 주의).
- 전문은 로그로만 남긴다 (`logger.exception` / `exc_info=exc`).

## staff 권한 등급 (`StaffRole`)

- `User.is_staff`(bool)는 콘솔 접근 여부의 큰 게이트로 그대로 두고, 그 안에서
  세부 권한은 `User.staff_role`(`StaffRole`: `STAFF` < `MANAGER` < `SUPERUSER`,
  기본값 `STAFF`)로 나눈다.
- 라우터 단위 `require_staff`(coarse gate) 위에, 등급 제한이 필요한 개별
  엔드포인트에만 `Depends(require_role(StaffRole.XXX))`를 얹는다
  (`core/deps.py`). 새 엔드포인트를 등급으로 제한할 땐 이 패턴을 따른다.
- 현재 등급 매핑:
  - `MANAGER` 이상 — `POST /v1/internal/spots/assignments` (타 staff에게
    검증 작업 할당)
  - `MANAGER` 이상 — `DELETE /v1/internal/groups/{uid}` (그룹 삭제, 비가역),
    `POST`/`PATCH`/`DELETE /v1/internal/groups/{uid}/members/*` (임의 유저에게
    `owner`까지 포함한 역할 강제 부여/박탈 — 권한 상승 리스크)
  - `SUPERUSER` 이상 — `POST /v1/internal/spots/bulk` (최대 5000행 파괴적
    upsert)
  - `SUPERUSER` 이상 — `POST /v1/internal/db-dumps`, `GET
    /v1/internal/db-dumps/{job_id}/download` (전체 DB를 pg_dump로 덤프해
    S3 presigned URL로 다운로드 — 운영 데이터 전체 노출 리스크)
  - 그 외 internal 엔드포인트는 `STAFF`만 있어도 통과 (기존 동작 유지) — spot
    group 조회/메타 수정/단일 spot 제거 포함
- `/admin`(SQLAdmin)은 아직 `staff_role`을 반영하지 않는다 — 모든 staff가
  다른 사용자의 `is_staff`/`is_active`를 토글할 수 있는 단일 평면 그대로다.
  SQLAdmin까지 등급을 반영하려면 별도 작업이 필요하다.
- `/admin`에서 사용자 생성/삭제는 막혀 있다 (`can_create/can_delete = False`)
  — 계정 생성은 Google 로그인 흐름만이 유일한 경로다.
- `staff_role`을 `SUPERUSER`로 올리는 API는 아직 없다 — DB에서 직접 값을
  바꾸거나 SQLAdmin으로 부여한다 (bootstrap 단계의 의도된 공백).

## 이미지 is_public 의미

- `spot_images.is_public`은 **서빙 방식 구분**(True=CDN URL, False=presigned
  URL)이지 접근 제어가 아니다. 두 경우 모두 공개 API에 노출된다.
  외부 비노출 이미지가 필요해지면 별도 접근 제어 필드를 도입할 것.

## 이미지 등록 s3_key 검증

- `POST /v1/internal/spots/{uid}/images`는 presign이 발급하는 키 형식
  (`uploads/pending/{uid}/{22자 shortuuid}{확장자}`)에 정확히 맞는 키만
  받는다(`_pending_key_re`). prefix만 확인하면 버킷 안의 임의 객체를 그
  spot의 이미지로 등록할 수 있다.
- presign 시 키는 항상 서버가 만든다 — 클라이언트가 준 파일명을 키에 쓰지 말 것.
- presign은 최종 경로(`spots/{uid}/...`)가 아닌 `uploads/pending/{uid}/...`
  prefix에 키를 발급한다(VAC-15). register가 호출되지 않으면 S3에 DB
  기록 없는 orphan 객체가 영구히 남기 때문 — register 성공 시 서버가
  `copy_object`로 최종 경로에 복사 후 pending 원본을 `delete_object`한다.
  `uploads/pending/` prefix에는 `vivac-infra`(terraform) 쪽에 S3 lifecycle
  rule을 걸어 N일 후 미등록 객체를 자동 삭제할 예정(별도 repo 작업, 아직
  미반영).

## 사용자 입력 LIKE 필터

- 어드민 부분일치 필터는 `col.icontains(value, autoescape=True)`를 쓴다
  (`crud/spot.py`, `crud/spot_group.py`). `ilike(f"%{value}%")`는 입력의
  `%`/`_`가 와일드카드로 살아 있어 전체 스캔을 유도할 수 있다.
