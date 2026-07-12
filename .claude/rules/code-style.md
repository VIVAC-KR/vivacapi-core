# 코드 작성 스타일

## 린트/포맷

- `ruff`로 lint + format을 통일한다 (`pyproject.toml`의 `[tool.ruff]`, `alembic/versions`는 제외 대상).
- 커스텀 line-length 설정 없음 — ruff 기본값(88)을 그대로 따른다.

## 계층별 명명

- `crud` 함수명은 `동사_대상_수식어` 순서를 쓴다 (예: `list_spots_admin`, `get_history`). 어드민/내부 전용 로직은 이름에 `_admin` 등으로 구분한다.
- 라우터 파일명은 도메인 단위로 쪼갠다 (`internal_spots.py`, `internal_spot_images.py`처럼 리소스별 분리, 하나의 거대 라우터에 몰아넣지 않는다).
- 열거형은 `enum.StrEnum`을 사용한다 (`ErrorCode`, `JobType`, `PipelineStatus` 참고).

## 주석

- 비즈니스 규칙의 "왜"가 코드만으로 드러나지 않을 때만 한글 주석을 남긴다 (예: 화이트리스트로 정렬 컬럼을 제한하는 이유, 상태 전이를 특정 방향만 허용하는 이유).
- 함수가 하는 일 자체를 설명하는 주석/docstring은 지양 — 이름과 타입으로 드러나야 한다.

## 화이트리스트 패턴

- 사용자 입력으로 정렬 컬럼, 필터 컬럼 등 ORM 속성을 동적으로 고를 때는 반드시 명시적 dict 화이트리스트를 거친다 (`_ADMIN_SORTABLE`, `_FILTERABLE` 참고). 임의 속성 문자열을 바로 `getattr`하지 않는다.
