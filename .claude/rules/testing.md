# 테스트 전략/작성 규칙

## 프레임워크

- `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"` — `async def test_*`에 마커 불필요).
- 실행: `uv run pytest`, 단일 파일은 `uv run pytest tests/path/to/test_file.py`.

## 픽스처 (`tests/conftest.py`)

- `client`: DB 미사용, 순수 HTTP 계층만 검증할 때 (예: CORS, 헬스체크).
- `db_client` / `db_session`: DB가 필요한 테스트용. 트랜잭션을 열고 테스트 종료 후 롤백해 테스트 간 상태를 격리한다 — DB에 실제 커밋되는 side effect를 남기지 않는다.
- 세션 시작 시 `apply_migrations` 픽스처(`autouse`)가 `vivac_test` DB에 alembic 마이그레이션을 1회 적용한다.

## 파일 구성

- 파일명은 `test_<대상>.py`로 기능/라우터/crud 단위와 1:1 매칭한다 (예: `test_internal_spots_crud.py`, `test_internal_spots_bulk.py`, `test_admin_auth_router.py`).
- 라우터 테스트와 crud 테스트를 분리한다 — HTTP 계층 검증(status, 응답 envelope)과 쿼리 로직 검증(필터/정렬/페이지네이션)을 같은 파일에 섞지 않는다.

## 무엇을 테스트하는가

- 에러 케이스는 `core/errors.py`의 `ErrorCode`가 올바른 status/코드로 매핑되는지 확인한다 (`test_errors.py` 참고).
- 화이트리스트 기반 필터/정렬처럼 보안 성격의 로직(임의 컬럼 주입 방지 등)은 화이트리스트 밖 입력이 거부되는 케이스를 반드시 포함한다.
- `AsyncSession` + `await` 기반 crud 함수는 실제 DB(`db_session`)로 검증한다 — mock으로 대체하지 않는다.
