# 어드민 목록 count 서브쿼리 + 선행 와일드카드 ILIKE 스케일 이슈

- **심각도**: 낮음 (성능 — 수만 건 이상에서 발현)
- **출처**: 2026-07-11 sql-pro 점검

## 문제

어드민 목록이 매 페이지 요청마다 `SELECT count(*) FROM (WHERE절 쿼리)` 별도 실행 + `OFFSET/LIMIT`. `title ILIKE '%검색어%'`(선행 와일드카드)는 btree를 못 타 title 검색 시 seq scan 2회(count + 본쿼리).

- 위치: `vivacapi/crud/spot.py:86-95`, `vivacapi/crud/spot_business_info.py:40-49`

## 수정 방향

- title 검색: `pg_trgm` GIN 인덱스 (`gin_trgm_ops`)
- count: Refine simple-rest 계약(`X-Total-Count`)상 정확한 total이 필요해 근사치 전환은 트레이드오프 검토 필요

트리거 시점: spots 수만 건 + 어드민 목록 체감 지연.

## 프론트 영향

없음 (계약 불변).
