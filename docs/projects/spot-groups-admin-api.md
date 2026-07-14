# Spot Group 어드민 API 스펙 — `/v1/internal/groups/*`

> `vivac-console`이 spot group(유저가 만드는 spot 컬렉션)을 직접 관리할 수 있도록 하는 어드민 API 계약.
> 작성일: 2026-07-15
> 선행 작업: 앱(유저)용 `/v1/groups/*` API — `vivacapi/api/v1/endpoints/spot_groups.py`, `vivacapi/crud/spot_group.py`, `vivacapi/models/spot_group.py`
> 짝 문서 참고 포맷: [vivac-console-backend.md](./vivac-console-backend.md) (단, 그 문서는 `/v1/admin/*` 스냅샷이라 지금은 낡음 — 실제 경로는 `/v1/internal/*`. 본 문서가 최신.)

---

## 1. 한 줄 요약

앱 API(`/v1/groups/*`)는 "내가 멤버인 그룹"만 다룬다. 콘솔은 **아무 유저의 그룹이나** 조회/모더레이션해야 하므로, 멤버십 체크를 건너뛰고 `require_staff`(+ 일부 `MANAGER` 등급)로 게이트하는 별도 `/v1/internal/groups/*` 라우터를 신설한다. CRUD 로직은 기존 `crud/spot_group.py`를 거의 그대로 재사용한다.

---

## 2. 결정 사항 요약

| 항목 | 결정 | 비고 |
|---|---|---|
| 리소스 경로 | `/v1/internal/groups` | `.claude/rules/api-conventions.md` — 콘솔은 `/v1/internal/*`만 호출 |
| 목록 페이지네이션 | Refine simple-rest (`_start`/`_end`/`_sort`/`_order` + `X-Total-Count` 헤더) | `internal_spots.py::list_spots`와 동일 패턴, 앱 API의 cursor 방식과 별개 |
| 인증 | 라우터 단위 `require_staff`, 파괴적 작업만 엔드포인트별 `require_role(StaffRole.MANAGER)` | `.claude/rules/security.md` 기존 등급 매핑 확장 |
| 멤버십 체크 | 없음 (staff는 owner/editor 여부와 무관하게 접근) | 앱 API의 `require_group_role`/`_get_readable_group`은 미적용 |
| PRIVATE 그룹 초대 제한 | 어드민은 우회 가능 | 앱 API는 `PRIVATE`면 초대 자체를 403으로 막지만, 어드민은 지원/모더레이션 목적상 예외 |
| last-owner 안전장치 | 유지 | 어드민도 그룹을 owner 0명 상태로 만들 수 없음 (기존 `crud_group.update_member_role`/`remove_member` 그대로 재사용 — 강제로 우회하려면 그룹 자체를 삭제) |
| 에러 envelope | 기존 재사용, 신규 코드 없음 | `SPOT_GROUP_NOT_FOUND`, `SPOT_GROUP_MEMBER_NOT_FOUND`, `SPOT_GROUP_MEMBER_ALREADY_EXISTS`, `SPOT_GROUP_LAST_OWNER_REQUIRED`, `USER_NOT_FOUND` |

---

## 3. 엔드포인트

### 3.1 `GET /v1/internal/groups` — 목록 (Refine simple-rest)

**쿼리 파라미터**

| 키 | 타입 | 기본 | 설명 |
|---|---|---|---|
| `_start` | int | 0 | offset |
| `_end` | int | 25 | offset + limit(`_end - _start`) |
| `_sort` | str | `uid` | 화이트리스트: `uid`/`name`/`visibility`/`created_at`/`updated_at`. 밖이면 422 |
| `_order` | str | `asc` | `asc`/`desc` |
| `name_like` | str? | — | `name` ILIKE 부분 검색 |
| `visibility` | str? | — | `private`/`invite_only`/`public` 정확일치 |
| `user_uid` | str? | — | 이 유저가 (역할 무관) 멤버인 그룹만 — 특정 유저 문의 대응용 |

**응답** — `list[SpotGroupAdminListItem]`, 헤더 `X-Total-Count`

```json
[
  {
    "uid": "abc...",
    "name": "내 캠핑지 모음",
    "visibility": "private",
    "member_count": 1,
    "spot_count": 12,
    "created_at": "2026-07-01T...",
    "updated_at": "2026-07-10T..."
  }
]
```

### 3.2 `GET /v1/internal/groups/{uid}` — 상세

멤버십 무관 조회. 없으면 `404 SPOT_GROUP_NOT_FOUND`.

응답 `SpotGroupAdminDetail`: `uid`, `name`, `description`, `visibility`, `member_count`, `spot_count`, `created_at`, `updated_at`

### 3.3 `PATCH /v1/internal/groups/{uid}` — 메타 수정 (모더레이션)

Body: 기존 `SpotGroupUpdate` 재사용 (`name`/`description`/`visibility`, 모두 optional, `exclude_unset`).

부적절한 이름/설명 수정, 강제 visibility 변경(예: 신고된 PUBLIC 그룹을 PRIVATE로) 용도.

### 3.4 `DELETE /v1/internal/groups/{uid}` — 삭제 · **`MANAGER` 이상**

하드 삭제, 멤버/spot 매핑 cascade. 204.

### 3.5 `GET /v1/internal/groups/{uid}/members` — 멤버 목록

응답 `list[SpotGroupAdminMemberOut]` — `users` 테이블과 join해서 `nickname`/`email` 포함(콘솔 화면에서 uid만으로는 식별 불가):

```json
[
  {
    "user_uid": "...",
    "nickname": "...",
    "email": "...",
    "role": "owner",
    "invited_by_uid": null,
    "created_at": "..."
  }
]
```

### 3.6 `POST /v1/internal/groups/{uid}/members` — 강제 추가 · **`MANAGER` 이상**

Body: `{"user_uid": "...", "role": "viewer|contributor|editor|owner"}`

- 대상 유저 미존재 → `404 USER_NOT_FOUND`
- 이미 멤버 → `409 SPOT_GROUP_MEMBER_ALREADY_EXISTS`
- **PRIVATE 그룹이어도 허용** (앱 API와의 유일한 의도적 차이, 2번 표 참고)

### 3.7 `PATCH /v1/internal/groups/{uid}/members/{user_uid}` — 역할 강제 변경 · **`MANAGER` 이상**

Body: `{"role": "..."}`. 대상이 그룹의 유일한 owner면 `409 SPOT_GROUP_LAST_OWNER_REQUIRED`.

### 3.8 `DELETE /v1/internal/groups/{uid}/members/{user_uid}` — 강제 제거 · **`MANAGER` 이상**

대상이 유일한 owner면 `409 SPOT_GROUP_LAST_OWNER_REQUIRED` (그룹째 지우려면 3.4 사용).

### 3.9 `GET /v1/internal/groups/{uid}/spots` — 그룹 내 spot 목록

기존 `SpotGroupSpotItem` 재사용 (offset/limit 쿼리, `_start`/`_end` 아님 — 앱 쪽 페이지네이션과 동일 단순 offset/limit이라 굳이 Refine 포맷 강제 안 함).

### 3.10 `DELETE /v1/internal/groups/{uid}/spots/{spot_uid}` — spot 강제 제거

부적절 spot 모더레이션 제거. `STAFF`만으로 허용(단일 항목, 되돌리기 쉬움 — 3.4/3.6~3.8의 `MANAGER` 기준과 다름, 4번 참고).

---

## 4. 권한 등급 근거 (`.claude/rules/security.md` 확장)

| 등급 | 대상 | 이유 |
|---|---|---|
| `STAFF` | 3.1, 3.2, 3.3, 3.5, 3.9, 3.10 | 조회 전반 + 단일 spot 제거(가역적) + 메타 수정(모더레이션 성격, 데이터 파괴 아님) |
| `MANAGER` 이상 | 3.4, 3.6, 3.7, 3.8 | 그룹 삭제(비가역) / 임의 유저에게 `owner` 권한 부여·박탈(권한 상승 리스크) — 기존 "`MANAGER` 이상 — 타 staff에게 검증 작업 할당" 패턴과 동일한 급의 민감도 |

구현 시 `.claude/rules/security.md`의 "현재 등급 매핑" 표에 위 내용 추가.

---

## 5. CRUD 레이어 — 신규 함수 (`crud/spot_group.py`에 추가, 기존 함수 재사용)

```
list_groups_admin(session, *, offset, limit, sort, order, name_like, visibility, user_uid) -> (items, total)
count_group_members(session, group_uid) -> int
list_members_admin(session, group_uid) -> list[tuple[SpotGroupMember, User]]   # nickname/email용 join
```

재사용(신규 함수 불필요): `get_group_by_uid`, `update_group`, `delete_group`, `add_member`, `update_member_role`, `remove_member`, `list_group_spots`, `remove_spot`, `count_group_spots`.

---

## 6. 스키마

기존 `schemas/spot_group.py`에 admin 섹션 추가 (spot.py의 `SpotAdminListItem`/`SpotAdminDetail` 배치 방식과 동일):

```
SpotGroupAdminListItem   — uid, name, visibility, member_count, spot_count, created_at, updated_at
SpotGroupAdminDetail     — uid, name, description, visibility, member_count, spot_count, created_at, updated_at
SpotGroupAdminMemberOut  — user_uid, nickname, email, role, invited_by_uid, created_at
```

`SpotGroupUpdate`, `SpotGroupMemberInvite`, `SpotGroupMemberRoleUpdate`는 앱 API 스키마 그대로 재사용.

---

## 7. 라우터 등록

```python
# vivacapi/api/v1/routers.py
from vivacapi.api.v1.endpoints import internal_spot_groups

api_v1_router.include_router(
    internal_spot_groups.router,
    prefix="/internal/groups",
    tags=["internal"],
    dependencies=[Depends(require_staff)],
)
```

파일: `vivacapi/api/v1/endpoints/internal_spot_groups.py` (기존 `internal_spots.py`와 동일 디렉터리/명명 컨벤션 — admin 서브패키지 분리하지 않음, 기존 internal 라우터들이 전부 flat이라 그에 맞춤).

---

## 8. 테스트

`tests/test_internal_spot_groups.py` (라우터 테스트 — HTTP 계층/응답 envelope). 필수 케이스:

- 비staff → 403 (라우터 레벨)
- `STAFF` 등급으로 목록/상세/멤버조회/spot조회/메타수정/spot제거 성공
- `STAFF` 등급으로 그룹삭제·멤버추가·역할변경·멤버제거 시도 → 403 (`MANAGER` 필요)
- `MANAGER` 등급으로 위 4개 성공
- PRIVATE 그룹에 `MANAGER`가 멤버 강제 추가 성공 (앱 API와의 차이 검증)
- last-owner 강등/제거 시도 → 409 (앱 API와 동일 안전장치 재확인)
- 존재하지 않는 `uid`/`user_uid` → 404

---

## 9. 작업 단계 (verify 포함)

1. **CRUD 함수 추가** (`crud/spot_group.py`) → verify: 함수 단위 `uv run pytest`로 커버(라우터 테스트에 흡수해도 무방)
2. **스키마 추가** (`schemas/spot_group.py`) → verify: `uv run python -c "from vivacapi.schemas.spot_group import SpotGroupAdminDetail"`
3. **라우터 작성** (`endpoints/internal_spot_groups.py`) → verify: `/docs`에 `internal` 태그로 노출
4. **라우터 등록** (`routers.py`) → verify: 위와 동일
5. **`security.md` 표 갱신** → verify: 리뷰 시 육안 확인
6. **테스트 작성 + 통과** → verify: `uv run pytest tests/test_internal_spot_groups.py`
7. **전체 회귀** → verify: `uv run pytest` 전체 통과

---

## 10. FE(vivac-console) 액션

1. 본 문서 3장 스펙으로 Refine `dataProvider` 리소스 등록 (`spot-groups`, `spot-group-members`, `spot-group-spots`)
2. 목록은 `X-Total-Count` 헤더 기반 페이지네이션 (기존 spots/spot-business-info 리소스와 동일 패턴 재사용 가능)
3. 멤버 추가/역할변경/제거, 그룹 삭제 액션은 화면에서 `MANAGER` 이상만 노출하거나, 403 응답을 사용자에게 "권한 부족" 토스트로 처리
4. `role` enum(`viewer`/`contributor`/`editor`/`owner`), `visibility` enum(`private`/`invite_only`/`public`) — 앱 쪽과 동일 값이므로 공유 상수로 관리 권장

---

## 11. Out of Scope

| 항목 | 사유 |
|---|---|
| 콘솔에서 그룹 신규 생성 | 그룹은 유저가 만드는 개념 — 어드민이 대신 만들 유스케이스 없음(요청 시 후속) |
| 멤버 초대 이력/알림 | 별도 프로젝트 |
| audit log 연동 (`crud/audit.py`) | 기존 spot 어드민 수정에도 이제 막 붙은 패턴 — group까지 확장은 후속 판단 |
