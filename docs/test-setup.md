# 테스트 환경 구성

브랜치: `feature/test-setup`  
날짜: 2026-05-02

---

## 개요

로컬 PostgreSQL(Docker)을 그대로 활용하는 테스트 환경을 구성했다.
SQLite 대신 실제 DB 엔진을 사용하여 프로덕션과 동일한 조건에서 테스트한다.

---

## 변경 파일

### `docker/init-test-db.sh` (신규)

컨테이너 최초 생성 시 `vivac_test` 데이터베이스를 자동으로 만드는 init 스크립트.

```bash
# docker-compose.yml에서 마운트됨
/docker-entrypoint-initdb.d/init-test-db.sh
```

> 이미 실행 중인 컨테이너에는 적용되지 않는다. 이 경우 `make db-create-test`로 수동 생성한다.

---

### `docker-compose.yml` (수정)

- init 스크립트 볼륨 마운트 추가
- `db-up` / `db-down`이 `ENV` 변수를 사용하도록 수정 (기존 `.env` 하드코딩 → `$(ENV)`)

---

### `Makefile` (수정)


| 추가된 타겟                | 설명                                     |
| --------------------- | -------------------------------------- |
| `make test`           | `.env.test`로 pytest 실행                 |
| `make db-create-test` | 실행 중인 컨테이너에 `vivac_test` DB 생성 (최초 1회) |


`ENV` 기본값이 `.env` → `.env.local`로 변경됨.

---

### `tests/conftest.py` (신규)


| 픽스처                | 스코프               | 역할                                       |
| ------------------ | ----------------- | ---------------------------------------- |
| `apply_migrations` | session / autouse | 테스트 시작 시 `alembic upgrade head` 실행       |
| `db_session`       | function          | 트랜잭션 롤백으로 테스트 간 DB 상태 격리                 |
| `client`           | function          | DB 미사용 엔드포인트용 HTTP 클라이언트                 |
| `db_client`        | function          | DB 필요 엔드포인트용 HTTP 클라이언트 (`get_db` 오버라이드) |


---

### `tests/test_health.py` (신규)

`GET /health` 엔드포인트 테스트.

```
tests/test_health.py::test_health_returns_ok       PASSED
tests/test_health.py::test_health_response_body    PASSED
```

---

## 테스트 환경 구성 방법

### 최초 설정

```bash
# 1. DB 컨테이너 시작 (init 스크립트가 vivac_test를 자동 생성)
make db-up

# 2. 테스트 실행
make test
```

### 컨테이너가 이미 실행 중인 경우

```bash
# vivac_test DB 수동 생성 (1회만 실행)
make db-create-test

# 테스트 실행
make test
```

---

## 환경 변수 (`.env.test`)

`.env.local`과 동일하되 `DB_NAME=vivac_test`만 다르다.
`.gitignore`에 의해 커밋되지 않으므로 로컬에서 직접 생성해야 한다.

```
ENVIRONMENT=local
DB_HOST=localhost
DB_PORT=5432
DB_NAME=vivac_test        ← 핵심 차이
DB_USER=...
DB_PASSWORD=...
GOOGLE_CLIENT_ID=...
JWT_SECRET_KEY=...
```

---

## 테스트 작성 가이드

DB를 사용하지 않는 테스트:

```python
async def test_something(client: AsyncClient):
    response = await client.get("/some-endpoint")
    ...
```

DB가 필요한 테스트 (각 테스트 후 자동 롤백):

```python
async def test_something(db_client: AsyncClient):
    response = await db_client.post("/some-endpoint", json={...})
    ...
```

