# 보안/인증 규약

## 토큰 정책 (의도된 트레이드오프)

- JWT는 완전 stateless — refresh 토큰(7일)도 서버 저장/회수 수단이 없다.
  유출 시 만료 전까지 유효하다는 것을 알고 선택한 트레이드오프(운영 단순성 우선).
  회수가 필요해지면 refresh 토큰만 DB에 jti를 저장하는 방식으로 전환한다.

## staff 권한 모델 (의도된 트레이드오프)

- staff는 단일 평면 권한이다 — 수퍼유저 구분이 없어, 모든 staff가 `/admin`
  (SQLAdmin)에서 다른 사용자의 `is_staff`/`is_active`를 토글할 수 있다.
  소규모 운영팀 전제의 트레이드오프. 팀이 커져 권한 위계가 필요해지면
  superuser 필드를 추가하고 SQLAdmin 편집을 superuser로 제한한다.
- `/admin`에서 사용자 생성/삭제는 막혀 있다 (`can_create/can_delete = False`)
  — 계정 생성은 Google 로그인 흐름만이 유일한 경로다.

## 이미지 is_public 의미

- `spot_images.is_public`은 **서빙 방식 구분**(True=CDN URL, False=presigned
  URL)이지 접근 제어가 아니다. 두 경우 모두 공개 API에 노출된다.
  외부 비노출 이미지가 필요해지면 별도 접근 제어 필드를 도입할 것.
