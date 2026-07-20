# 비즈니스 기능 로드맵 제안 (2026-07-20)

> 작성일: 2026-07-20
> 배경: "현재 기능 기반으로 비즈니스적 관점에서 추가하면 좋을 기능"을 성장/획득, 리텐션/인게이지먼트, 수익화/파트너십, 신뢰/데이터품질 4개 관점으로 나눠 병렬 브레인스토밍 → 각 항목을 실제 코드(모델/엔드포인트)와 대조해 근거를 검증하고 구체화함.
> 상태 표기 규칙: 각 항목 제목에 `[제안]`(기본, 표기 생략) / `[🚧 진행중]` / `[✅ 완료 — PR #xxx]`를 붙여 구분한다. 개발 착수·완료 시 이 문서를 갱신한다. 개별 기능 설계에 들어가면 `docs/projects/<feature>.md`로 별도 설계 문서를 만든다 (예: `spot-invites.md` 참고 패턴).

---

## 0. 현재 관련 인프라 스냅샷 (근거 확인용)

이번 제안들이 딛고 서는 기존 코드 지점:

| 영역 | 파일 | 현재 상태 |
|---|---|---|
| 스팟 탐색 | `vivacapi/api/v1/endpoints/explore.py` | 라우터 레벨 인증 없음 — `GET /v1/explore/spots`, `GET /v1/explore/spots/{uid}` 완전 비로그인 공개 |
| 초대/리퍼럴 | `vivacapi/models/invite.py`, `vivacapi/api/v1/endpoints/invites.py` | `Invite`는 1회용(`status`가 `ACCEPTED`되면 재사용 불가), `group_uid` nullable로 그룹초대/일반리퍼럴 겸용, `User.referred_by_uid`에 귀속 기록은 되지만 이를 조회/집계하는 API 없음 |
| 그룹(컬렉션) | `vivacapi/api/v1/endpoints/spot_groups.py` | `GroupVisibility.PUBLIC` 그룹은 `_get_readable_group`(`get_current_user_optional` 사용, L52-66)로 **이미 비로그인 조회 가능** — 단, `GET /v1/groups`(내 그룹 목록, L130-136)는 로그인 필수이며 "공개 그룹 전체 탐색/검색" 엔드포인트는 없음 |
| 신뢰/검증 | `vivacapi/models/spot.py` | `pipeline_status`(CheckConstraint로 상태값 제한), `trust_tier`(1~3 SmallInteger), `assigned_to_uid` 존재. **검증 시점을 기록하는 타임스탬프 컬럼 없음** |
| 검증 담당자 할당 | `vivacapi/api/v1/endpoints/internal_spots.py`, `crud/spot.py:261,271` | `POST /internal/spots/assignments`(MANAGER 이상)는 `assigned_to_uid IS NULL`인 스팟에만 배정 가능. `assigned_to_uid`는 `SpotEditableFields`(`schemas/spot.py`)에 없어 **일반 PATCH로도 재할당 불가능** — 사실상 초기 배정 후 변경 수단이 없음 |
| 리뷰/신고 | `vivacapi/models/spot_review.py`, `spot_review_report.py` | 리뷰(평점 0~10, soft delete)는 있고 **리뷰 신고**는 있음(`spot_review_reports`, 내부 처리용). **스팟 자체에 대한 신고(폐쇄/접근불가 등)는 대응 모델이 없음** |
| 사업자 정보 | `vivacapi/models/spot_business_info.py` | `business_reg_no`, `operating_agency` 등 존재. **소유권 claim/셀프 편집 권한 필드 없음** |
| 예약 연동 | `vivacapi/models/spot.py` (`booking_url`) | 필드만 존재, **클릭/이벤트 트래킹 모델·엔드포인트 전무**(`click`, `analytics`, `event_log` 검색 결과 0건) |

---

## 1. 성장/획득 (Growth & Acquisition)

### 1.1 재사용 가능한 리퍼럴 링크 `[✅ 완료]` (2026-07-20, branch: `feature/reusable-referral-invite`, commit: `2ffba07`, PR 미생성 — 로컬 커밋까지만)

> 구현: `vivacapi/crud/invite.py`의 `consume_invite_for_signup`에서 `group_uid is None`(일반 리퍼럴)인 경우 `status`를 `ACCEPTED`로 전환하지 않고 `PENDING` 유지 — 같은 링크로 여러 명이 반복 가입 가능해짐. 그룹 초대(`group_uid` 있음)는 기존과 동일하게 1회용 유지. 스키마/마이그레이션 변경 없음(기존 필드만으로 해결). 테스트 1건 추가(`test_referral_invite_stays_pending_and_reusable_across_signups`), 전체 267개 통과(기존 `test_cors.py` 6개 실패는 main에도 있던 무관 이슈).
> 어뷰징 방지(재사용 횟수 제한 등)는 이번 스코프에서 의도적으로 제외 — 문서 1.1 원안대로 후속 고려사항.

- **문제**: `Invite`는 수락 즉시 `status=ACCEPTED`로 소진되는 1회용 구조라(`invite.py` docstring: "1회용 — 수락되면 status가 ACCEPTED로 바뀌어 재사용 불가"), 단톡방·SNS에 링크 하나를 뿌려 여러 명을 유입시키는 표준 리퍼럴 패턴이 안 된다. 현재는 "초대하고 싶은 사람 수만큼 `POST /v1/invites`를 반복 호출"해야 하는데, 이건 UX상 실질적으로 안 쓰인다.
- **제안**: `group_uid=None`인 일반 리퍼럴 초대에 한해 다회 수락을 허용(예: `max_uses` 또는 무제한 + 재사용 플래그). `accepted_by_uid` 단일 컬럼으로는 여러 명을 못 담으니, 리퍼럴 전용으로는 이 필드 대신 "가입 시 `referred_by_uid`만 기록하고 invite 자체는 소진 안 함" 방식이 스키마 변경이 가장 작다.
- **근거**: 신규가입 귀속 로직(`consume_invite_for_signup`, best-effort)은 이미 완성돼 있다 — 소진 정책 하나만 바뀌면 되는, 이미 깔린 인프라의 스위치를 켜는 수준의 변경.
- **난이도**: 하. **의존성**: 없음, 바로 착수 가능.
- **후속 고려사항**: 재사용 링크는 어뷰징(대량 가짜 가입) 여지가 커짐 — [4.4 검증 담당자 재할당]과는 무관하지만 별도 rate limit이나 가입당 리퍼럴 인정 상한이 필요할 수 있음.

### 1.2 스팟 상세 공개 공유 카드 (OG 메타) `[⛔ 블로킹 — 전제 무효]` (2026-07-20 조사, repo: `VIVAC-frontend`, worktree: `VIVAC-frontend/.claude/worktrees/spot-og-meta`, branch: `feature/spot-og-meta`, 커밋 없음)

> **재조사 결과 이 항목의 전제가 틀렸다.** VIVAC-frontend에 스팟 상세 페이지(`/spots/{uid}` 라우트) 자체가 없다 — 커밋 `788291c`("NextAuth v5 서버 세션 전환 및 홈 화면 개편", 2026-07-13)에서 `features/spots/*`, 스팟 리스트/지도 탐색 페이지, 관련 React Query 훅을 전부 의도적으로 제거("spots 임시 구현 제거"). 상세 페이지는 이 repo 역사상 한 번도 구현된 적 없음. 백엔드(`GET /v1/explore/spots/{uid}`, `SpotDetail`)는 여전히 정상 동작하지만, 이걸 붙일 프론트엔드 화면이 없는 상태.
> OG 메타만 추가하는 원래 스코프로는 진행 불가 — 스팟 상세 페이지 자체를 새로 설계/구현하는 훨씬 큰 작업이 선행돼야 함(라우트, `/v1/explore/spots/{uid}` 데이터 페칭, 이미지 목록 연동 등). 사용자 판단 필요, 재개하지 않고 대기.

- **문제**: 스팟을 카톡/SNS로 공유해도 텍스트 URL만 전달돼 클릭 전환이 낮다.
- **제안**: 프론트엔드(VIVAC-frontend)에서 스팟 상세 페이지에 OG 태그(사진·이름·핵심정보)를 붙여 링크 미리보기를 제공.
- **근거**: `GET /v1/explore/spots/{uid}`가 라우터 레벨 인증 없이 완전 공개(`explore.py` 상단에 `Depends(get_current_user)` 계열 의존성 부재 확인)라 **백엔드 변경이 전혀 필요 없다** — 순수 프론트엔드 작업.
- **난이도**: 하 (이 repo 범위 밖, VIVAC-frontend 작업). **의존성**: 없음.

### 1.3 공개 그룹 탐색/공유 진입점

- **문제**: "이번 주말 어디 갈지 같이 고민하는" 그룹의 스팟 리스트를 지인에게 보여주고 싶어도, 진입할 방법이 마땅치 않다.
- **재확인된 사실**: 애초 브레인스토밍에서는 "PUBLIC 그룹도 로그인해야 볼 수 있는 게 문제"로 짚었으나, 코드 확인 결과 **`GET /v1/groups/{group_uid}`와 `/spots`는 이미 비로그인으로 열람 가능**(`_get_readable_group`이 `get_current_user_optional` 사용, `spot_groups.py:52-66,153-155,193-195`). 즉 개별 그룹 상세 공유는 백엔드상 이미 동작한다.
- **제안**: 실제 갭은 "발견 가능성"이다 — (a) 그룹 상세 응답에 공유 가능한 정적 URL을 노출/문서화하고 프론트에서 공유 버튼을 붙이는 것, (b) 필요 시 `PUBLIC` 그룹을 검색/탐색할 수 있는 `GET /v1/groups/public` 같은 별도 디스커버리 엔드포인트(현재 `GET /v1/groups`는 "내 그룹"만 반환).
- **근거**: (a)는 백엔드 변경 없음. (b)는 `crud/spot_group.py`에 이미 `visibility` 필터(`list_groups_for_user`와 유사한 쿼리 패턴)가 있어 재사용 가능.
- **난이도**: (a) 하 / (b) 중. **의존성**: 없음.

### 1.4 초대 현황 대시보드 ("내가 보낸 초대")

- **문제**: `referred_by_uid` 귀속 데이터는 가입 시점에 쌓이지만, 초대를 보낸 유저에게 몇 명이 클릭·가입했는지 보여줄 API가 전무해 초대를 계속할 유인이 없다.
- **제안**: `GET /v1/invites/me` 같은 조회 엔드포인트로 내가 발급한 초대들의 pending/accepted 상태와 가입 수를 집계.
- **근거**: 데이터는 이미 쌓이는데(User.referred_by_uid, Invite.accepted_by_uid) 조회 경로가 없는, "데이터는 있고 피드백 루프만 없는" 전형적 케이스.
- **난이도**: 중 (신규 조회 crud/스키마 필요, 리워드 로직까지 가면 상). **의존성**: [1.1]과 함께 설계하면 좋음(재사용 링크 도입 시 집계 방식이 바뀌므로 순서상 1.1 이후 권장).

---

## 2. 리텐션/인게이지먼트 (Retention & Engagement)

### 2.1 개인 찜(즐겨찾기)

- **문제**: 그룹(컬렉션) 기능은 생성·초대·멤버관리가 딸린 무거운 흐름이라, "일단 저장만" 하고 싶은 가벼운 니즈를 받아줄 곳이 없다.
- **제안**: 스팟 상세에 원클릭 개인 저장. 그룹 생성 없이 즉시 저장되는 개인 전용 리스트.
- **근거**: 데이터 모델상 `spot_groups`/`spot_group_spots` 테이블 구조를 그대로 재사용하거나(예: 유저당 자동 생성되는 `PRIVATE` 기본 그룹), 별도 단순 `favorites` 조인 테이블 중 택1 — 어느 쪽이든 기존 스팟 FK 패턴 재사용.
- **난이도**: 하. **의존성**: [2.3](상태변경 알림)의 알림 대상 목록으로 바로 이어지는 선행 기능.

### 2.2 캠핑 다이어리 (내 리뷰 타임라인)

- **문제**: 리뷰를 쓰고 나면 그걸로 끝 — 자신이 다녀온 곳을 되돌아볼 화면이 없어 "내 기록"으로서의 재방문 동기가 없다.
- **제안**: 내가 쓴 리뷰(`spot_reviews`, `user_id` FK)를 시간순으로 모아 보여주는 조회 전용 탭.
- **근거**: `spot_reviews` 테이블에 `spot_uid`, `user_id`, `created_at`이 이미 있어(모델 확인) 신규 쓰기 로직 없이 `GET /v1/users/me/reviews` 같은 조회 API 하나로 끝남.
- **난이도**: 하. **의존성**: 없음.

### 2.3 찜한 스팟 상태변경 알림

- **문제**: 노지/신규 스팟은 검증 상태가 자주 바뀌는데(폐쇄, 재검증, 신뢰도 변경), 사용자가 매번 재방문해서 확인하지 않으면 최신 정보를 놓친다.
- **제안**: 찜/그룹에 담긴 스팟의 `trust_tier`·`pipeline_status`가 바뀌거나 새 리뷰가 달리면 푸시/인앱 알림.
- **근거**: 트리거 조건이 될 필드(`pipeline_status`, `trust_tier`, `spot.py:104-108`)는 이미 존재. 다만 **알림 발송 인프라(FCM/APNs 연동, 알림 구독 테이블) 자체가 전무**해 이 항목만 별도 인프라 신규 구축.
- **난이도**: 상. **의존성**: [2.1](찜 목록이 있어야 "무엇에 대해" 알릴지 정해짐), [4.1]·[4.2](신뢰도 변경 트리거가 명확해야 알림 조건이 의미 있음)와 강하게 연결 — 우선순위상 가장 늦게 착수 권장.

### 2.4 그룹 활동 피드

- **문제**: 초대까지 받아 그룹에 들어와도 이후 누가 뭘 추가했는지 알 방법이 없어 그룹이 금방 방치된다.
- **제안**: 그룹 상세 화면에 "OO님이 OO 스팟을 추가했습니다" 류의 최근 활동 로그.
- **근거**: `spot_group_spots`, `spot_group_members` 연결 테이블에 `added_by`/`created_at`류 정보가 이미 있는지에 따라 난이도가 갈림 — 별도 활동 로그 테이블 신설이 필요하면 중, 기존 컬럼 재사용으로 조회만 가능하면 하.
- **난이도**: 중. **의존성**: 없음.

---

## 3. 수익화/파트너십 (Monetization & Partnerships)

### 3.1 예약 클릭 어필리에이트

- **문제**: `Spot.booking_url`(nullable String, `spot.py:111`)이 있어 사용자가 스팟을 찾은 뒤 예약은 외부 채널(고캠핑 등)로 이탈하는데, 이 트래픽에서 수익이 전혀 발생하지 않는다.
- **제안**: `booking_url` 클릭 이벤트를 로깅(클릭 카운트 테이블 또는 이벤트 로그)하고, 제휴 가능한 채널에는 제휴 파라미터를 붙여 커미션 수취. 제휴 계약이 없는 채널은 클릭 수 자체를 향후 협상 근거 데이터로 축적.
- **근거**: `booking_url` 필드는 이미 존재하고 클릭 트래킹 인프라(이벤트 로그)만 얹으면 됨 — 결제 인프라 없이 시작 가능한 최소 실험.
- **난이도**: 하. **의존성**: [3.4]와 이벤트 로깅 인프라 공유 가능(동시 설계 권장).

### 3.2 사업자 인증 파트너십 (Verified Operator)

- **문제**: `spot_business_info`에 `business_reg_no`, `operating_agency` 등 사업자 정보가 쌓이지만, 실제 운영업체가 "이건 내 스팟"이라 주장하고 직접 관리할 방법이 없다.
- **제안**: 사업자등록번호 기반 소유권 claim 신청 → 승인 시 자신의 스팟 설명/사진/영업상태를 셀프 편집할 수 있는 권한과 "운영자 인증" 배지 부여. 이 셀프 관리 권한을 월 구독 유료 티어로 판매.
- **근거**: `trust_tier`/`pipeline_status` 검증 체계([섹션 0], [4.x])가 이미 있어 "본인확인된 사업자"라는 신뢰 레이어를 그 위에 얹는 구조로 설계 가능, 기존 어드민 검증 워크플로우(`internal_spots.py`, MANAGER 권한 패턴) 재사용 가능.
- **난이도**: 중 (claim 신청/승인 플로우, 사업자 전용 권한 스코프 신설 필요). **의존성**: [4.4](검증 담당자 재할당)가 먼저 있어야 claim 승인 처리 담당자 배정이 매끄러움.

### 3.3 피처드 리스팅 (Sponsored Placement)

- **문제**: 배너 광고 인프라를 새로 만들 여력은 없지만, 탐색 화면 자체가 이미 구매의사가 강한 트래픽(캠핑지 찾는 중)이라 노출 인벤토리로 가치가 있다.
- **제안**: 스팟에 `is_sponsored` 플래그 추가, `GET /v1/explore/spots` 결과 상단 N개에 "광고" 라벨과 함께 자연 노출. 초기엔 결제 자동화 없이 수동 인보이스로 판매.
- **근거**: 신규 결제 인프라 없이 필드 하나 + 정렬 로직(`crud/spot.py`의 기존 정렬 화이트리스트 패턴)만으로 시작 가능.
- **난이도**: 중. **의존성**: [3.2](인증 파트너 확보 후 자연스러운 업셀) 이후 착수 권장 — 순서상 3.2 다음.

### 3.4 문의 리드 판매 (Pay-per-Lead)

- **문제**: 노지/국공립 스팟처럼 `booking_url`이 없는 곳이 많아 [3.1] 어필리에이트 모델이 적용 안 되는 스팟 비중이 크다.
- **제안**: 스팟 상세의 "전화 문의" 클릭을 트래킹해 월별 리드 수를 집계, 운영업체에 리드 건수 기반 과금(초기엔 수동 정산).
- **근거**: [3.1]과 클릭 트래킹 인프라를 공유할 수 있어 추가 구축 비용이 거의 없음.
- **난이도**: 하. **의존성**: [3.1]과 이벤트 로깅 인프라 동시 설계 시 중복 작업 없음.

---

## 4. 신뢰/데이터품질 (Trust & Content Quality)

### 4.1 스팟 폐쇄/접근불가 신고

- **문제**: 노지 백패킹 스팟은 사유지화·산불통제·군사구역 지정 등으로 조용히 폐쇄되는 경우가 많다. 현재는 **리뷰 신고**(`spot_review_reports`, 리뷰 콘텐츠 대상)만 있고 **스팟 자체**의 상태 이상을 알릴 통로가 없다(`SpotReport`류 모델 검색 결과 0건). 잘못된 위치정보를 믿고 갔다가 헛걸음하는 게 이 서비스에서 가장 치명적인 신뢰 훼손 시나리오다.
- **제안**: 스팟 상세에 "폐쇄/접근불가 신고" 버튼 → 신고 누적 시 해당 스팟을 재검증 큐로 자동 편입(`pipeline_status`를 되돌리거나 별도 플래그 추가).
- **근거**: `pipeline_status`/`assigned_to_uid`/My Queue 인프라(`internal_spots.py`)가 이미 있어 "신고 → 재검증 큐 편입" 연결 로직만 추가하면 됨.
- **난이도**: 중. **의존성**: **[4.4]를 먼저 처리 권장** — 신고 급증 시 담당자 재분배 수단이 없으면 이 기능이 오히려 병목을 만듦.

### 4.2 trust_tier 신선도 기반 자동 감쇠 `[✅ 완료 — PR #117]` (2026-07-20, branch: `feature/trust-tier-freshness`, commit: `b0fe782`)

> 구현: `Spot.last_verified_at`(nullable, 기존 row는 NULL="미검증" 백필) 추가.
> `crud/spot.py`의 `decay_stale_trust_tiers`가 180일 경과(NULL 포함) +
> `PUBLISHED` + 미삭제 스팟을 대상으로, tier 1/2는 한 단계 하향(숫자 증가),
> 이미 최하위인 tier 3은 `assigned_to_uid`를 비워 재검증 큐로 되돌림(공개
> 상태는 유지). 감쇠 시 `last_verified_at`을 현재 시각으로 갱신해 다음
> threshold까지는 재감쇠하지 않도록 함(watermark) — 갱신 안 하면 배치를
> 돌릴 때마다 연쇄적으로 tier가 무너지는 버그가 생김.
> 배치 실행은 `vivacapi/workers/job_worker.py`의 온디맨드 큐 패턴이 아니라
> `docs/backlog.md`의 "DB 백업 이중화" 전례를 따라 독립 스크립트
> (`scripts/decay_trust_tier.py`) + 호스트 crontab(주 1회 권장) 패턴 채택.
> 테스트 6건 추가(`test_spot_trust_tier_decay.py`), 전체 279개 중 273개
> 통과(`test_cors.py` 6개는 main에도 있던 무관 기존 이슈).
> **스코프 밖(후속 필요)**: 스팟이 실제로 재검증될 때 `last_verified_at`을
> 갱신해주는 쓰기 경로가 없음 — PATCH(`internal_spots.py`)나 bulk upsert에서
> `trust_tier`를 설정해도 `last_verified_at`은 그대로 NULL/과거값으로 남는다.
> 지금은 컬럼 추가 + 감쇠 배치만 스코프였고, "검증 완료" 시점을 기록하는
> 쓰기 경로는 별도 작업으로 필요.

- **문제**: `trust_tier`(1~3, `spot.py:108`)는 한 번 매겨지면 갱신 트리거가 없다 — **검증 시점을 기록하는 컬럼 자체가 존재하지 않음**(모델 전체에서 `verified_at`류 컬럼 검색 결과 `User.identity_verified_at` 하나뿐, 스팟과 무관). 6개월 전엔 정확했던 정보가 지금도 "신뢰" 딱지를 달고 있을 수 있다.
- **제안**: `Spot.last_verified_at` 컬럼 추가 + 배치 job으로 일정 기간 경과 스팟(특히 tier 3/노지)의 tier를 자동 하향하거나 재검증 큐로 되돌림.
- **근거**: `trust_tier`는 이미 `SpotListItem`/`SpotDetail`(공개 API 응답 스키마)에 노출 중인, 사용자가 직접 보는 신뢰 지표 — "신선도"라는 시간 축만 빠져 있어 지금 채우는 ROI가 큼.
- **난이도**: 중 (컬럼 추가 + 배치 job 인프라, `vivacapi/workers/job_worker.py`의 기존 job 패턴 재사용 가능). **의존성**: 없음, [4.1]과 별개로 병행 가능.

### 4.3 리뷰에 "지금도 유효한가요?" 마이크로 시그널

- **문제**: 리뷰는 평점/텍스트 위주라 "이 스팟이 지금도 그 상태로 존재하는지"를 명시적으로 확인할 방법이 없다. 최신 리뷰가 있어도 실제로는 "그때는 있었다"만 증명한다.
- **제안**: 리뷰 작성 시 boolean 필드(예: `still_accessible`) 추가 → 최근 N건 응답 집계해 스팟 상세에 "최근 방문자 확인됨" 배지 노출, 부정 응답 누적 시 [4.1] 재검증 큐 트리거와 연결.
- **근거**: `spot_reviews` 테이블(`spot_review.py`)에 컬럼 하나 추가하는 수준 — 기존 작성 플로우(`POST /v1/spots/{spot_uid}/reviews`, `spot_reviews.py`) 재사용, effort 대비 신뢰 시그널 개선폭이 큼.
- **난이도**: 하. **의존성**: [4.1]과 연동하면 효과가 커지지만, 단독으로도 가치 있음(선행 불필요).

### 4.4 검증 담당자 재할당 API `[✅ 완료]` (2026-07-20, branch: `feature/spot-assignment-reassign`, commit 예정 — 로컬 커밋까지만)

> 구현: `PATCH /v1/internal/spots/{uid}/assignment`(MANAGER 이상) 신설. 요청 바디 `{"user_uid": str | None}` — 값이 있으면 재할당, `null`이면 해제까지 같은 엔드포인트에서 처리(별도 엔드포인트로 나눌 근거가 약해 기존 `/assignments` 요청 스키마처럼 단일 바디 형태 유지). staff 존재/`is_staff` 검증은 기존 `assign_spots`와 동일하게 `get_user_by_id` 재사용. crud는 신규 함수 없이 기존 범용 `update_spot(db, uid, {"assigned_to_uid": ...})` 재사용, 쓰기 전 `crud_audit.set_audit_user` 호출로 감사 추적 확보(기존 단건 PATCH/delete/restore와 동일 패턴). 신규 모델/스키마 없음(요청 스키마 `SpotReassignmentRequest` 1개만 추가). 테스트 6건 추가(정상 재할당, null 해제, 스팟 404, 비staff 대상 404, 권한부족 403, 미인증 401), 전체 273개 통과(`test_cors.py` 6개 실패는 main에도 있던 기존 무관 이슈).
> `ruff format` 실행 시 이 저장소의 28개 기존 파일이 포맷 재작성 대상으로 뜨는 pre-existing drift 발견(main에도 동일하게 존재, 로컬 ruff 버전과 저장소 기존 스타일 간 불일치로 추정) — 이번 변경 파일 3개는 전부 통과하도록 맞췄고, 무관 파일은 건드리지 않음.

- **문제**: `assigned_to_uid`는 `SpotEditableFields`(`schemas/spot.py`)에 포함돼 있지 않아 일반 PATCH로 변경 불가하고, `POST /internal/spots/assignments`(`crud/spot.py:261`)도 `assigned_to_uid IS NULL`인 스팟에만 동작 — **한 번 배정되면 재할당/해제 수단이 없다.** 담당자 휴가·퇴사·과부하 시(특히 [4.1] 신고 급증 시나리오) 검증 파이프라인이 그대로 막힌다.
- **제안**: 기존 `POST /v1/internal/spots/assignments`(MANAGER 이상) 패턴을 그대로 따르는 `PATCH` 재할당/해제 엔드포인트 추가.
- **근거**: 권한 체계(`Depends(require_role(StaffRole.MANAGER))`, `internal_spots.py:114`)와 배정 crud 로직을 거의 그대로 재사용 — 신규 모델·스키마 불필요.
- **난이도**: 하. **의존성**: 없음 — **[4.1] 착수 전 먼저 처리하는 것을 권장.**

---

## 5. 종합 — 의존성과 착수 순서 제안

```
1.1 재사용 리퍼럴 링크 ──▶ 1.4 초대 현황 대시보드
1.3(a) 그룹 공유 진입점 (즉시 가능, 백엔드 변경 없음)

4.4 검증 담당자 재할당 ──▶ 4.1 스팟 폐쇄 신고 ──▶ 2.3 찜 상태변경 알림
4.3 리뷰 유효성 시그널 (단독 가능, 4.1과 결합 시 시너지)
4.2 trust_tier 신선도 감쇠 (단독 가능)

2.1 개인 찜 ──▶ 2.3 찜 상태변경 알림
2.2 캠핑 다이어리 (단독, 즉시 가능)
2.4 그룹 활동 피드 (단독)

3.1 예약 클릭 어필리에이트 ─┬─(이벤트 로깅 공유)─▶ 3.4 문의 리드 판매
3.2 사업자 인증 파트너십 ──▶ 3.3 피처드 리스팅
   (3.2는 4.4 이후 권장 — claim 승인 담당자 배정 필요)
```

**의존성 없이 즉시 착수 가능한 항목** (난이도 하, 선행조건 없음): `1.1`, `1.3(a)`, `2.2`, `4.2`, `4.3`, `4.4`

이 문서는 우선순위를 확정하지 않는다 — 사용자가 순서를 정해 항목을 지정하면 그때 해당 항목만 `docs/projects/<feature-slug>.md`로 별도 설계 문서(스키마, 엔드포인트, 에러코드, 테스트 계획)를 작성한 뒤 착수한다.
