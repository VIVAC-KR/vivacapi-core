# 초대 링크 (Invite) — `/v1/invites/*`

> 공유 링크 기반 초대. 그룹 초대와 일반 앱 리퍼럴을 하나의 `Invite` 엔티티로 처리한다.
> 작성일: 2026-07-16
> 배경: PM/UX/growth-loops 멀티에이전트 브레인스토밍(신규 기능 후보 다수 중 이번에 구현하기로 선택된 것) → 리퍼럴 개념 상세화 과정에서 기존 `SpotGroupMember.invited_by_uid`가 "이미 가입한 유저 간 그룹 초대"만 표현하고 "비회원 초대 후 가입"은 못 다룬다는 것을 확인, 별도 스키마로 분리
> 관련 코드: `vivacapi/models/invite.py`, `vivacapi/crud/invite.py`, `vivacapi/api/v1/endpoints/invites.py`, `vivacapi/api/v1/endpoints/auth.py`

---

## 1. 한 줄 요약

로그인한 유저가 `POST /v1/invites`로 1회용 공유 링크를 발급한다. `group_uid`를 지정하면 그룹 초대(수락 시 지정 role로 멤버 합류), 지정하지 않으면 일반 앱 리퍼럴(가입 시 `referred_by_uid`만 기록)이 된다. 비회원은 그 링크로 Google 로그인해 가입하면 자동 수락되고, 이미 가입된 유저는 `POST /v1/invites/{uid}/accept`로 수락한다.

---

## 2. 결정 사항 요약

| 항목 | 결정 | 근거 |
|---|---|---|
| 초대 방식 | 공유 링크(대상 불특정), 이메일 특정 초대 아님 | 사용자 선택. 이메일 발송 인프라 불필요, 구현 단순 |
| 초대 범위 | 그룹 초대 + 일반 앱 리퍼럴 둘 다, 단일 `Invite` 테이블 | `group_uid` nullable로 두 케이스 분기. 별도 테이블로 나누면 조회/수락 로직이 두 배가 됨 |
| 재사용 여부 | 1회용 (수락되면 `ACCEPTED`로 종료, 재사용 불가) | 사용자 선택. 여러 명 초대하려면 `POST /v1/invites`를 여러 번 호출해 링크를 여러 개 발급 — `accepted_by_uid` 단수 필드로 충분, 별도 이력 테이블 불필요 |
| 초대 토큰 | 별도 token 컬럼 없이 `uid` 자체를 링크에 사용 | 필드 하나 아낌 (`/invite/{uid}`) |
| 기존 `invited_by_uid`와의 관계 | 건드리지 않음. `SpotGroupMember.invited_by_uid`는 여전히 "이미 가입한 유저를 그룹에 초대"(기존 `POST /v1/groups/{uid}/members`) 용도로 유지 | `invited_by_uid`는 `users.uid` FK라 비회원을 가리킬 수 없음 — 신규 가입 유치는 `Invite` + `User.referred_by_uid`로 별도 처리 |
| 그룹 초대 생성 권한 | `GroupRole.OWNER`만, `PRIVATE` 그룹은 불가 | 기존 `POST /v1/groups/{uid}/members`(`invite_group_member`)와 동일 정책으로 통일 — 새 진입점이라고 더 느슨하게 열어주지 않음 |
| 신규가입 시 초대 소비 | `/auth/google`의 신규유저 생성 분기에서만, 실패해도 로그인은 항상 성공(best-effort) | 초대 링크가 깨져 있다고 로그인 자체가 막히면 안 됨 — `consume_invite_for_signup`은 invite가 없거나 PENDING이 아니면 조용히 무시 |
| 기존 유저가 그룹 초대 링크를 열었을 때 | `POST /v1/invites/{uid}/accept`로 별도 처리 (로그인 흐름과 분리) | 이미 계정이 있으므로 `referred_by_uid`를 건드릴 필요 없음 — 그룹 합류만 수행 |
| 일반 리퍼럴 초대를 `/accept`로 열었을 때 | `409 INVITE_NOT_ACCEPTABLE` | 합류할 그룹이 없어 수락할 대상이 없음. 리퍼럴은 신규가입 시점에만 의미 있음 |
| 에러 코드 | `INVITE_NOT_FOUND`(404), `INVITE_NOT_ACCEPTABLE`(409) 신규 추가 | 기존 코드로 표현 안 되는 두 케이스(없음 / 수락 불가능한 상태)만 최소 추가 |

---

## 3. 스키마

```python
class InviteStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"   # 현재 발급 경로 없음 — 향후 취소 기능용으로 예약

class Invite(Base):
    __tablename__ = "invites"
    uid: str(22) PK                       # 공유 링크 토큰 겸용
    inviter_uid: FK users.uid
    group_uid: FK spot_groups.uid, nullable, ondelete=CASCADE   # null=일반 리퍼럴
    group_role: GroupRole, nullable       # group_uid 있을 때만 사용
    status: InviteStatus, default PENDING
    accepted_by_uid: FK users.uid, nullable
    accepted_at: datetime, nullable
    created_at
```

`User.referred_by_uid: FK users.uid, nullable` — 신규 가입 시 1회만 세팅, 이후 불변.

`group_uid`가 `ondelete=CASCADE`라 그룹이 삭제되면 관련 invite도 함께 삭제됨 (수락 시점에 그룹이 사라져 있는 경합 상태를 원천 차단).

---

## 4. 엔드포인트

### 4.1 `POST /v1/invites` — 발급

Body: `{"group_uid": str | null, "group_role": GroupRole | null}` (둘 다 있거나 둘 다 없어야 함, pydantic model_validator로 검증 → 어긋나면 422)

- `group_uid` 있으면: 그룹 존재 확인(404), `PRIVATE`면 403(`SPOT_GROUP_INVITE_NOT_ALLOWED`), 요청자가 해당 그룹 `OWNER`가 아니면 403(멤버 아니면 404로 존재 은닉, 기존 `_get_membership_or_404` 패턴과 동일)
- 인증 필요, 미인증 401

### 4.2 `GET /v1/invites/{uid}` — 미리보기

인증 불필요(공유 링크 클릭 시 로그인 전에도 열람). `inviter_nickname`, `group_name`(있으면), `status` 반환. 없으면 404(`INVITE_NOT_FOUND`).

### 4.3 `POST /v1/invites/{uid}/accept` — 기존 로그인 유저의 그룹 합류

인증 필요. `status != PENDING` 또는 `group_uid is None`이면 409(`INVITE_NOT_ACCEPTABLE`). 이미 멤버면 `crud_group.add_member`가 던지는 409(`SPOT_GROUP_MEMBER_ALREADY_EXISTS`)가 그대로 전파.

### 4.4 `POST /v1/auth/google` — 신규가입 자동 수락

`GoogleLoginRequest`에 `invite_uid: str | None` 추가. 신규유저 생성 분기(`is_new_user`)에서만 `consume_invite_for_signup` 호출 — `referred_by_uid` 세팅 + (그룹 초대면) 멤버 합류 + invite `ACCEPTED` 처리. invite가 무효해도 로그인 자체는 항상 200.

---

## 5. CRUD (`crud/invite.py`)

```
create_invite(session, *, inviter_uid, group_uid=None, group_role=None) -> Invite
get_invite_by_uid(session, uid) -> Invite | None
accept_invite(session, invite, user_uid) -> Invite          # 기존 유저 수락
consume_invite_for_signup(session, invite_uid, new_user) -> None   # 신규가입 자동 수락, best-effort
```

그룹 합류 로직은 신규 작성하지 않고 기존 `crud/spot_group.py::add_member`를 그대로 재사용(이미 멤버/역할 배정 검증 로직 보유).

---

## 6. 테스트 (`tests/test_invites_router.py`, 17개)

- 발급: 일반 리퍼럴 성공, 그룹 초대 성공/역할 누락 422/비-owner 403/PRIVATE 그룹 403/그룹 없음 404/미인증 401
- 미리보기: 성공, 없음 404
- 수락: 그룹 합류 성공(role·invited_by_uid 검증), 이미 처리된 초대 409, 일반 리퍼럴을 accept로 열면 409, 이미 멤버인 경우 409
- 신호가입 연동: 그룹 초대로 가입 시 멤버 합류 + referred_by_uid 세팅, 일반 리퍼럴로 가입 시 referred_by_uid만 세팅, 잘못된 invite_uid로 가입해도 로그인 성공(무시), 기존 유저 로그인 시 invite_uid 있어도 소비 안 됨

---

## 7. 작업 단계 (전부 완료, verify 포함)

1. 모델 + `User.referred_by_uid` → verify: import 확인
2. 에러 코드 + 스키마 → verify: import 확인
3. `crud/invite.py` → verify: 테스트에서 간접 검증
4. 엔드포인트 + 라우터 등록 → verify: `/docs`에 `invites` 태그 노출
5. `/auth/google` 연동 → verify: 신규가입 케이스 테스트
6. alembic 마이그레이션 → verify: `uv run alembic upgrade head`
7. 테스트 작성 + 전체 회귀 → verify: `uv run pytest` (신규 17개 + 기존 240개 통과, `test_cors.py` 6개는 기존 main에도 있던 무관 실패)

---

## 8. 트러블슈팅 기록

- **마이그레이션에서 enum 중복 생성**: 브랜드 뉴 enum(`invite_status`)을 `_invite_status_enum.create(checkfirst=True)`로 미리 만들고 `create_table` 컬럼에 `create_type=False`로 참조하는 방식(기존 `staff_role` add_column 패턴 차용)을 썼다가 `DuplicateObjectError` 발생. `create_table`로 브랜드 뉴 테이블을 만들 때는 `73dcae10bc10`(spot_groups) 마이그레이션처럼 `sa.Enum(...)`을 컬럼에 직접 넣고 `create_table`이 타입 생성까지 관리하게 두는 게 맞는 패턴 — `create_type=False` 사전생성 조합은 기존 컬럼에 enum을 **추가**할 때(`add_column`)만 쓰는 패턴이었음.
- **테스트 DB 충돌**: 이 작업은 별도 워크트리(main 기준)에서 진행했는데, 로컬 Postgres의 공유 `vivac_test` DB가 병행 작업 중인 다른 브랜치(spot-review-report)의 마이그레이션까지 적용된 상태라 alembic 히스토리가 안 맞았음. `vivac_test_invites`를 별도로 만들어 이 워크트리 전용 `.env`에서 가리키도록 격리.

---

## 9. Out of Scope (후속 고려사항)

| 항목 | 사유 |
|---|---|
| 초대 취소(`REVOKED`로 전이하는 API) | enum 값은 예약해뒀지만 발급 후 취소 유스케이스는 이번 범위 밖 |
| 만료(`expires_at`) | 요청 없었음, 필요해지면 컬럼 추가로 확장 가능한 구조 |
| 재사용 가능한 링크(다수 가입 허용) | 사용자가 명시적으로 1회용 선택 |
| 이메일 지정 초대 | 사용자가 공유 링크 방식만 선택 |
| 프론트엔드 연동 (공유 UI, OG 태그, `invite_uid` 쿼리파라미터 캡처 후 Google OAuth 흐름에 전달) | growth-loops 에이전트 지적대로 백엔드 필드만으로는 실제 루프가 안 돎 — 별도 프론트 작업 필요 |
| 리퍼럴 집계/소셜 프루프 API (`GET /v1/users/me/referrals` 등) | 이번엔 스키마·소비 로직까지만, 집계 조회는 후속 판단 |
