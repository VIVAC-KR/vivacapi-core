# 탐색 API 스펙 정의 (VVC-105)

> 탐색 기능(검색·필터·리스트·상세) 마일스톤 M1의 BE 스펙 확정 노트.
> 작성일: 2026-05-19
> 관련 이슈: [VVC-105](https://linear.app/lucente/issue/VVC-105) · 후속: VVC-117 / VVC-118 / VVC-119
> 관련 PR: [#52](https://github.com/VIVAC-KR/vivacapi-core/pull/52)

---

## 1. 한 줄 요약

FE/BE 병렬 구현을 위해 탐색 API 계약을 OpenAPI(`docs/openapi.json`)로 확정한다. 본 단계는 **스펙·스텁만** 다루며, 실제 DB 쿼리·필터·이미지·정렬 로직은 후속 마일스톤에서 진행한다.

---

## 2. 결정 사항 요약

| 항목 | 결정 | 비고 |
|---|---|---|
| 리소스 명명 | `/v1/explore/spots` | DB 테이블·PRODUCT.md 용어와 일치 (place X) |
| 인증 | 공개 (비로그인 가능) | 탐색은 누구나 가능해야 함 |
| 쿼리 파라미터 | `q`, `sort`, `cursor`, `limit` | 필터(`region`/`style`/`difficulty`)는 본 스펙에서 제외 |
| `limit` 정책 | 기본 20, 1 ≤ limit ≤ 50, 초과 시 422 | 자동 clamp X (FE의 잘못된 가정 방지) |
| 페이지네이션 | **cursor 방식** (opaque base64) | offset 방식 거부 |
| 정렬 enum | `popular` / `latest` / `rating` | enum만 노출. 의미·로직은 VVC-119 |
| 상세 응답 (이미지) | 본 스펙에서 제외 | 향후 컬럼·테이블 추가 시 VVC-118에서 결정 |
| 에러 envelope | 기존 `{error: {code, message, details}}` 재사용 | `SPOT_NOT_FOUND` ErrorCode 추가 |

---

## 3. 엔드포인트

### 3.1 `GET /v1/explore/spots` — 목록

**쿼리 파라미터**

| 키 | 타입 | 기본 | 설명 |
|---|---|---|---|
| `q` | `string?` | — | 검색어 (실제 매칭 로직은 후속) |
| `sort` | `SpotSort` | `popular` | `popular` / `latest` / `rating` |
| `cursor` | `string?` | — | opaque cursor (다음 페이지 토큰) |
| `limit` | `int` | 20 | 1–50, 초과 시 422 |

**응답 (`SpotListResponse`)**

```json
{
  "items": [
    {
      "uid": "uuid",
      "title": "string",
      "tagline": "string | null",
      "region_province": "string | null",
      "region_city": "string | null",
      "rating_avg": 0.0,
      "review_count": 0,
      "themes": ["string"] 
    }
  ],
  "next_cursor": "string | null",
  "has_more": false,
  "total": 0
}
```

- `next_cursor: null` → 마지막 페이지
- `total`은 첫 페이지(`cursor` 미지정)에서만 채워질 수 있음 (선택)

### 3.2 `GET /v1/explore/spots/{spot_uid}` — 상세

- 경로 파라미터: `spot_uid: UUID`
- 응답: `SpotDetail` (이미지 필드 **제외**, VVC-118)
- 미발견 시: `404 SPOT_NOT_FOUND`

---

## 4. 페이지네이션 — cursor 채택 근거 및 세부 규약

### 4.1 왜 cursor인가

- **VVC-112가 무한 스크롤 UI** → 임의 페이지 점프 불필요
- `rating_avg` 동률이 많아 offset은 동시 변동 시 중복/누락 위험
- 리뷰 작성으로 `rating_avg`/`review_count`가 실시간 갱신 → offset 드리프트 직격
- 데이터가 커지면 offset 성능 열화 (DB가 skip 행을 모두 스캔)

### 4.2 cursor 인코딩 포맷

```
next_cursor = base64( {"r": <sort_value>, "u": "<uid>", "s": "<sort_key>"} )
```

- **opaque base64(JSON)** — 서버가 포맷을 자유롭게 변경 가능. FE는 echo만.
- `"s"` 필드에 정렬 키를 함께 포함 → 정렬을 바꾸고 같은 cursor를 보내면 서버가 422로 거부
- 평문 포맷(`"4.5_uuid"` 등) 비권장 — 3rd party가 파싱하면 서버가 포맷 변경 불가

### 4.3 tie-break

- 모든 정렬에 `uid DESC`를 secondary key로 강제 → 결정론적 순서
- 필요한 복합 인덱스(`(rating_avg DESC, uid DESC)`, `(created_at DESC, uid DESC)`)는 VVC-119에서 마이그레이션

### 4.4 정렬 변경 시 동작

- cursor 내 `s`와 현재 `sort`가 불일치 → 422
- FE는 정렬 변경 시 cursor를 비우고 첫 페이지 재요청

---

## 5. 정렬 enum

| 값 | 의미 (잠정) | 확정 위치 |
|---|---|---|
| `popular` | `rating_avg DESC` 또는 `rating_avg`+`review_count` 가중치 | **VVC-119에서 확정** |
| `latest` | `created_at DESC` | VVC-119 |
| `rating` | `rating_avg DESC` | VVC-119 |

본 스펙에서는 enum만 노출하며 stub은 정렬을 수행하지 않는다.

---

## 6. 에러 응답

기존 envelope 그대로:

```json
{ "error": { "code": "<CODE>", "message": "<msg>", "details": <any | null> } }
```

본 스펙에서 새로 등장하는 코드:

| 코드 | HTTP | 사용처 |
|---|---|---|
| `SPOT_NOT_FOUND` | 404 | `GET /spots/{uid}` 미발견 |
| `VALIDATION_ERROR` | 422 | `limit` 범위 위반, `sort` enum 위반, UUID 형식 위반 등 |

---

## 7. Out of Scope (의도적 제외 — 후속 이슈)

| 항목 | 후속 이슈 |
|---|---|
| 필터(`region`/`style`/`difficulty`) ↔ Spot 컬럼 매핑 | [VVC-117](https://linear.app/lucente/issue/VVC-117) |
| 상세 응답의 이미지 필드 스키마 | [VVC-118](https://linear.app/lucente/issue/VVC-118) |
| 정렬 enum 의미 정의 + 실제 정렬 로직 + 복합 인덱스 마이그레이션 | [VVC-119](https://linear.app/lucente/issue/VVC-119) |
| 실제 검색/필터 핸들러 구현 | VVC-107 (M2-BE) |
| 결과 정렬/페이지네이션 구현 | VVC-110 (M3-BE) |
| 상세 핸들러 구현 | VVC-108 (M4-BE) |

---

## 8. 산출물 (이번 PR)

- `app/api/v1/endpoints/explore.py` — stub 라우터 (list + detail)
- `app/schemas/spot.py` — `SpotSort` / `SpotListItem` / `SpotDetail` / `SpotListResponse`
- `app/core/errors.py` — `SPOT_NOT_FOUND` 추가
- `app/api/v1/routers.py` — `/v1/explore` 마운트
- `tests/test_explore_router.py` — 스텁 계약 검증 7개 테스트
- `docs/openapi.json` — `make openapi`로 재생성 (gitignored, FE가 참고할 계약서)

---

## 9. FE 액션

1. `docs/openapi.json` 또는 본 PR 머지 후 main 브랜치의 OpenAPI 스펙으로 mock 클라이언트 생성
2. 본 스펙 결정 사항(경로/필드/페이지네이션/에러 envelope) 합의 확인
3. 정렬 변경 시 cursor 무효화 동작을 클라이언트 측에서 처리 (VVC-119 머지 전까지는 stub이므로 영향 없음)
