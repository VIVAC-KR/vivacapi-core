# 비공개 이미지가 공개 API로 노출

- **심각도**: 중간 (보안)
- **출처**: 2026-07-11 security-auditor 점검

## 문제

`GET /v1/explore/spots/{uid}/images` (비로그인 가능)가 `is_public=False` 이미지도 presigned GET URL(1시간 유효)로 반환한다. `crud/spot_image.py:list_images_by_spot`에 `is_public` 필터가 없어 플래그가 접근 통제 역할을 못 함.

- 위치: `vivacapi/api/v1/endpoints/explore.py:47-57`, `vivacapi/crud/spot_image.py`

## 수정 방향

1. 공개 endpoint는 `is_public=True`만 반환
2. **세트 필요**: `/v1/internal/spots/{uid}/images` (전체 반환, staff 전용) 신설 — 현재 이미지 목록 endpoint가 공개용 하나뿐이라, vivac-console이 이걸 쓰고 있으면 운영자가 비공개 이미지를 못 보게 됨

## 프론트 영향

- 사용자 웹: 없음 (응답 스키마 불변, 비공개 이미지 미노출이 의도된 동작)
- vivac-console: 이미지 조회 경로 확인 후 internal endpoint로 전환 필요
