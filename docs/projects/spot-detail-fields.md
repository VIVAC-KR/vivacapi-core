# 스팟 상세 응답 필드 확장

> 작성일: 2026-07-17
> 요청 출처: FE `spot-detail-schema-request.md` (`GET /v1/explore/spots/{uid}` 응답 필드 확장 요청)
> 관련 커밋: `47811a4` (필드 확장), `d3031ca` (코드리뷰 반영 수정)

---

## 1. 배경

FE 상세페이지(`spot-detail`) UI가 `SpotDetail` 응답에 5개 필드(`uid`/`title`/`address`/`website_url`/`trust_tier`)만 노출하던 것을 확장해달라고 요청. 요청 필드 대부분은 이미 `Spot` 모델 컬럼(`SpotEditableFields` 공유 정의)으로 존재해, 신규 수집이 아니라 **기존 데이터를 조회 API에 노출**하는 작업이었다.

## 2. 이번 범위에서 추가한 필드

`vivacapi/schemas/spot.py`의 `SpotDetail`에 다음 필드를 명시적으로 추가:

`tagline`, `category`, `themes`, `is_fee_required`, `is_pet_allowed`, `features`(note), `camp_sight_type`, `unit_count`, `total_area_m2`, `fire_pit_type`, `latitude`, `longitude`, `address_detail`, `description`, `amenities`, `nearby_facilities`, `has_equipment_rental`, `phone`, `booking_url`, `image_url`(신규 조인), `rating_avg`, `review_count`

`image_url`은 `list_spots`와 동일하게 `spot_image` THUMBNAIL 이미지를 조인해 채운다 (`vivacapi/api/v1/endpoints/explore.py:_resolve_thumbnail_url`).

## 3. 이번 범위에서 제외한 것

원본 요청 문서에 "BE 확인 필요"로 명시된 항목 — 대응 DB 컬럼 자체가 없어 신규 설계 결정이 필요함:

- **이용요금**: 시스템 전체 미수집. 신규 필드 추가 여부부터 결정 필요.
- **`note`의 `severity` enum**: 현재 `features` 컬럼은 단일 텍스트. 구조화된 심각도(`info`/`warning`/`critical`) 도입 여부 결정 필요.

## 4. 코드리뷰에서 발견/수정한 이슈

1차 구현에서 `SpotDetail(SpotEditableFields)` 상속 방식을 썼다가, `xhigh` 코드리뷰(10-angle)에서 다음 문제 확인 후 명시적 화이트리스트 방식으로 재작성:

- **내부 전용 컬럼 공개 노출**: `pipeline_status`, `has_liability_insurance`(업체 배상보험 가입여부), `postal_code`, `region_province`/`region_city`, `pet_policy`, `altitude`가 FE 요청 목록에 없음에도 상속으로 인해 비로그인 공개 API에 노출되고 있었음.
- **OpenAPI 계약 변경**: `address`/`website_url`/`trust_tier`가 required → optional로 바뀌어 있었음(원복).
- **검증 우회**: `image_url`을 생성 후 속성 할당으로 채우는데 `validate_assignment` 미설정 상태라 타입 검증을 우회할 수 있었음 → `model_config`에 `validate_assignment=True` 추가.
- **중복 로직**: 썸네일 URL 조합 로직이 `list_spots`/`get_spot`에 중복 → `_resolve_thumbnail_url` 헬퍼로 추출.
- 내부 전용 필드가 공개 응답에 없음을 확인하는 회귀 테스트 추가 (`test_get_spot_hides_internal_only_fields`).

### 의도적으로 남겨둔 것

- `GET /v1/explore/spots/{uid}`가 스팟 조회 + 썸네일 조회로 쿼리 1회 → 2회 증가. 단일 쿼리로 합치려면 crud 레이어 join이 필요 — 이번 스코프 밖.

## 5. BE가 FE에 회신할 질문 (원본 요청 문서 기준, 미결)

1. `category`(배열)와 `camp_sight_type`(단일 문자열)이 실제로 다른 층위 분류가 맞는지.
2. `rating_avg`/`review_count`가 "미수집"인지 "리뷰 없어서 0"인 정상 상태인지 (FE 문구 분기용).
3. 이용요금 필드 신규 추가 계획/시점.
4. `note`에 `severity` enum 추가 가능 여부.
5. `phone`/`websiteUrl`/`bookingUrl` 3개 모두 null인 스팟 비율 (액션바 승격 규칙 실효성 판단용).
