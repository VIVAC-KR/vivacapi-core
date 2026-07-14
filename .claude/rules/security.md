# 보안/인증 규약

## 토큰 정책 (의도된 트레이드오프)

- JWT는 완전 stateless — refresh 토큰(7일)도 서버 저장/회수 수단이 없다.
  유출 시 만료 전까지 유효하다는 것을 알고 선택한 트레이드오프(운영 단순성 우선).
  회수가 필요해지면 refresh 토큰만 DB에 jti를 저장하는 방식으로 전환한다.

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
  - `SUPERUSER` 이상 — `POST /v1/internal/spots/bulk` (최대 5000행 파괴적
    upsert)
  - 그 외 internal 엔드포인트는 `STAFF`만 있어도 통과 (기존 동작 유지)
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
