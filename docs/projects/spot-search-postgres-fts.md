# Spot 검색 설계 — PostgreSQL FTS + trigram (VVC-107)

> 탐색 검색(`q` 파라미터) 구현 설계 노트. `GET /v1/explore/spots` 확장.
> 작성일: 2026-07-15
> 관련 스펙: [vvc-105-explore-api-spec.md](./vvc-105-explore-api-spec.md) (`q` 파라미터 자리만 예약, 매칭 로직은 본 문서에서 확정)

---

## 1. 한 줄 요약

Elasticsearch 없이 PostgreSQL 확장(`pg_trgm` + `tsvector`)만으로 검색 구현. 이유와 전환 조건은 2장, 실제 매칭/가중치는 3장, 나머지 결정 근거는 4장.

---

## 2. Elasticsearch — 언제 고려하나

### 2.1 지금 도입 안 하는 이유

| 검토 항목 | 현재 상태 | 판단 |
|---|---|---|
| 데이터 규모 | spot 수천~수만 단위 (큐레이션 플랫폼, 크롤링 대량 수집형 아님) | GIN 인덱스로 충분히 감당 |
| 인프라 비용 | ES 클러스터 별도 운영(EC2 t2.micro 1대로 core도 겨우 도는 인프라) | 추가 서버 운영 부담이 이득보다 큼 |
| 동기화 문제 | ES 도입 시 Postgres → ES 데이터 동기화 파이프라인(CDC/outbox) 신규 구축 필요 | 지금 그 파이프라인이 존재하지 않음 — 신규 실패 지점 추가 |
| 검색 요구 수준 | 오타 허용 + 부분 매칭 + 필드별 가중치 정도 | pg_trgm + tsvector로 충족 가능한 범위 |
| 한국어 형태소 분석 | 필요 없음 (짧은 캠핑장/글램핑 키워드 위주, 복합명사 분해 요구 낮음) | nori 같은 전용 analyzer 아직 불필요 |

**결론:** 지금 ES 도입은 얻는 이득보다 운영 복잡도 증가가 크다. 오버엔지니어링.

### 2.2 전환을 고려할 조건 (2개 이상 해당 시 재검토)

1. **규모** — spot 수가 수십만 이상으로 늘어나 GIN 인덱스 스캔 비용이 API 응답 시간(p95)에 실측으로 영향을 줄 때
2. **검색 품질 요구 상승** — 동의어 사전("애견동반" ↔ "펫프렌들리"), 복합명사 형태소 분해 등 `simple` config + trigram으로 감당 안 되는 요구가 반복적으로 나올 때
3. **집계 요구** — 검색과 동시에 카테고리/지역별 대량 facet aggregation을 실시간으로 계산해야 할 때 (지금은 `spot_field_options` 화이트리스트가 이미 알려진 값 집합이라 aggregation 없이 필터만으로 충분)
4. **QPS** — 검색 트래픽이 늘어 Postgres 본 DB(쓰기 트래픽과 동일 인스턴스)에 부하 분리가 필요해질 때

### 2.3 전환 시 접근 방식 (지금 미리 만들지 않음, 방향만 기록)

- Postgres를 계속 source of truth로 유지, ES/OpenSearch는 검색 전용 read replica 성격으로 붙인다.
- 동기화는 outbox 패턴(스팟 변경 시 이벤트 테이블 기록 → 별도 워커가 ES에 반영) 또는 Debezium CDC.
- 애플리케이션 코드는 지금부터 `crud/spot.py`의 `search_spots` 함수 하나에 검색 쿼리를 몰아뒀기 때문에, 라우터/스키마 변경 없이 이 함수 내부만 ES 클라이언트 호출로 교체 가능한 구조. 지금 시점에 인터페이스나 어댑터 계층을 미리 만들지는 않는다 (YAGNI — 아직 필요하지 않은 추상화).

---

## 3. 검색 구현 — 어디서 무엇을 쓰는가

### 3.1 엔드포인트

`GET /v1/explore/spots?q=<검색어>&category=<code>&region_province=<지역>&cursor=&limit=`

- `q` 없으면 기존 동작(전체 목록, `uid` 오름차순 cursor) 그대로 유지 — 회귀 없음.
- `q` 있으면 검색 모드로 분기 (`crud/spot.py::search_spots`).

### 3.2 매칭 대상 필드와 사용 기술

| 필드 | 역할 | 기술 | 가중치 |
|---|---|---|---|
| `title` | 스팟 이름 | `tsvector` (`simple` config) | **A** (최고) |
| `tagline` | 한줄설명 | `tsvector` (`simple` config) | **B** |
| `description` | 상세 설명 | `tsvector` (`simple` config) | **C** |
| `address` | 주소 | `tsvector` (`simple` config) | **D** (최저) |
| `title` | 오타/부분어 보완 | `pg_trgm` similarity | 별도 보정치 (아래 3.4) |
| `category` | 카테고리(구조화 값) | array `&&` 정확 매칭 | 필터(랭킹 미개입) |
| `region_province` | 지역(구조화 값) | 등호 매칭 | 필터(랭킹 미개입) |

`category`/`region_province`는 `spot_field_options` 화이트리스트로 관리되는 구조화 값이라 자유텍스트 랭킹에 섞지 않고 `WHERE` 절 필터로만 사용한다 — 자유텍스트(제목/설명/주소)와 구조화 필터를 분리하는 이유는 4.2 참고.

### 3.3 `simple` config를 쓰는 이유

Postgres 기본 `english` config는 영어 스테머라 한글에 적용되지 않는다. `simple` config는 스테밍 없이 공백/구두점 기준 토큰화만 수행 — 한글에서 스테밍이 없다는 게 오히려 안전(잘못된 어간 추출로 인한 오탐 없음). 대신 짧은 한글 단어의 부분 매칭이 약해지는 단점은 3.4의 trigram으로 보완한다.

### 3.4 오타/부분 매칭 보완 — `pg_trgm`

`tsvector` 매칭은 토큰 단위라 "글램핑장" 검색어가 "글램핑" 토큰을 못 찾는 경우가 있다. `title` 컬럼에 `pg_trgm` GIN 인덱스를 걸어 `similarity(title, q) > 0.2`인 행도 결과에 포함시킨다 (OR 조건). trigram을 `title`에만 적용하는 이유: 사용자가 부분/오타로 검색할 때 가장 흔한 대상이 이름이고, 모든 필드에 걸면 인덱스 크기·false positive가 커짐.

### 3.5 최종 스코어 계산

```sql
score = ts_rank(search_vector, websearch_to_tsquery('simple', :q))
        + similarity(title, :q) * 0.3
```

- `ts_rank`가 주 스코어 (필드 가중치 A/B/C/D가 여기 반영됨).
- `similarity * 0.3`은 trigram 매칭 시 순위에 보정치를 더하는 역할 — 계수 0.3은 `ts_rank`가 보통 0~1 범위로 나오는 것 대비 trigram 매칭을 "약한 신호"로 취급하기 위한 임의값. 정식 A/B 테스트 없이 정한 시작값이므로, 실사용 검색 로그가 쌓이면 재조정 대상 (4.6 참고).
- 정렬: `score DESC, rating_avg DESC, uid DESC` — 텍스트 관련도 1차, 동률이면 평점, 그래도 동률이면 `uid`로 결정론적 정렬 보장.

### 3.6 페이지네이션 (검색 모드 전용 cursor)

- 검색 결과는 `score` 기준 정렬이라 기존처럼 `uid` 하나만으로는 keyset pagination이 불가능(순서가 뒤바뀔 수 있음).
- cursor를 `base64({"r": <score>, "v": <rating_avg>, "u": <uid>})`로 인코딩 — [vvc-105-explore-api-spec.md 4.2](./vvc-105-explore-api-spec.md)에서 이미 정의한 opaque cursor 포맷을 검색 모드에 적용한 것.
- 다음 페이지 조건: `(score, rating_avg, uid) < (last_score, last_rating_avg, last_uid)` 튜플 비교 (SQL `ROW(...) < ROW(...)`) — `ORDER BY score DESC, rating_avg DESC, uid DESC`와 동일한 순서 의미. 정렬 키 3개를 모두 cursor에 담는 이유: 정렬 기준(`ORDER BY`)에 있는 키 중 하나라도 cursor 비교에서 빠지면 동점 구간에서 행이 중복되거나 누락될 수 있음
- `q` 없는 기본 목록의 기존 cursor(평문 `uid`)는 그대로 유지, 포맷 변경 없음 — 두 모드는 `q` 유무로 완전히 분리되어 있어 서로 cursor를 섞어 보내면(예: 검색 응답의 cursor를 `q` 없는 요청에 재사용) `422 VALIDATION_ERROR`로 거부한다.

---

## 4. 결정 사항과 근거

| # | 결정 | 근거 |
|---|---|---|
| 4.1 | ES 대신 Postgres 확장(`pg_trgm`+`tsvector`) 채택 | 2장 참고 — 규모/인프라/동기화 비용 대비 이득 없음 |
| 4.2 | 자유텍스트(제목/설명/주소)와 구조화 필터(카테고리/지역) 분리 | 같은 파이프라인에 섞으면 `ts_rank`가 구조화 값 매칭까지 반영해 랭킹이 왜곡됨. 구조화 값은 이미 `spot_field_options`가 화이트리스트로 관리하는 유한 집합이라 정확 매칭이 맞고, 랭킹에 낄 이유가 없음 |
| 4.3 | `to_tsvector` config로 `english` 대신 `simple` 채택 | `english` 스테머가 한글에 무의미하게 작동(또는 깨짐) — `simple`은 최소한 토큰화는 안전하게 수행 |
| 4.4 | `search_vector`를 `GENERATED ALWAYS AS ... STORED` 컬럼으로 생성 | 별도 트리거/애플리케이션 코드로 재계산할 필요 없이 Postgres가 INSERT/UPDATE 시 자동 갱신 — 코드 추가 없이 정합성 보장 |
| 4.5 | `pg_trgm`을 `title`에만 적용(전체 필드 X) | 부분/오타 검색의 실사용 빈도가 이름에 가장 높고, 전체 필드에 걸면 인덱스 크기와 낮은 관련도 매칭(false positive)만 늘어남. 필요해지면 `address`에도 추가 검토(4.6번 후속 과제) |
| 4.6 | trigram 보정 계수(0.3), similarity 임계값(0.2)은 잠정값 | 실사용 검색 로그 없는 상태에서 초기값 — 출시 후 클릭률/재검색률 등으로 튜닝 필요. **후속 과제로 남김**, 지금 정교한 튜닝 로직을 만들지 않음(YAGNI) |
| 4.7 | 검색 모드 cursor를 `{score, uid}` composite로, 기본 목록은 기존 `uid` cursor 유지 | 기존 목록 경로에 회귀 없이(테스트 그대로 통과) 검색 모드만 별도 cursor 규약 적용. 두 규약을 하나로 통일하는 리팩터링(VVC-119 sort 확정)은 별도 이슈로 분리 — 지금 범위 아님 |
| 4.8 | `category`/`region_province` 필터는 화이트리스트 dict(`_FILTERABLE`) 안 거침 | `_FILTERABLE`은 어드민 목록에서 **동적 필드명 문자열**(쿼리 키)로 임의 컬럼을 고를 때 주입을 막는 장치. 본 검색 엔드포인트는 FastAPI가 타입 검증하는 고정 파라미터(`category: list[str]`, `region_province: str`)라 애초에 임의 컬럼 지정이 불가능 — 같은 위험이 없어 같은 장치를 억지로 적용하지 않음 |
| 4.9 | 검색 결과에서도 `pipeline_status == PUBLISHED`만 노출 | 기존 공개 API 정책과 동일 — 검색이라고 예외 두지 않음 |

---

## 5. Out of Scope (의도적 제외)

| 항목 | 이유 |
|---|---|
| 동의어 사전 | ES 전환 조건(2.2-2) 충족 전까지 불필요 |
| `sort` enum(`popular`/`latest`/`rating`) 실제 구현 | VVC-119 별도 이슈, 검색 모드와 무관 |
| 지리 반경 검색(`earthdistance`/PostGIS) | 이번 요청 범위 밖 — 필요 시 별도 설계 |
| trigram 계수 자동 튜닝 | 실사용 로그 쌓이기 전까지 의미 없음 |
