# pipeline_status 일반 인덱스 부재

- **심각도**: 낮음 (성능 — 데이터 누적 시 발현)
- **출처**: 2026-07-11 sql-pro 점검

## 문제

`spots.pipeline_status` 인덱스는 partial(`WHERE pipeline_status = 'PUBLISHED'`, 공개 API용)뿐. 어드민 목록에서 `RAW`/`CURATED` 등 비-PUBLISHED 값으로 필터하면 seq scan. ETL 특성상 RAW/ENRICHED row가 다수 누적될 가능성 높음.

- 위치: `vivacapi/models/spot.py`, `vivacapi/crud/spot.py` (`_FILTERABLE`)

## 수정 방향

`Index("ix_spots_pipeline_status", "pipeline_status")` 추가 (partial index는 유지). 트리거 시점: ETL 대량 유입으로 spots가 수만 건 넘거나 어드민 필터 체감 지연 시.

## 프론트 영향

없음.
