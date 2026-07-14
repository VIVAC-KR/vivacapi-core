# API 설계/응답 규약

## 클라이언트별 API 접근 규칙

- `vivac-console`(내부 운영 콘솔)과 통신할 땐 `/v1/internal/...` 형식의 API만으로 반드시 통신해야 한다. (`v1`은 `v2`, `v3`... 로 버전업될 수 있음)
  - 유일한 예외는 로그인(`/v1/admin/auth/google`) — 인증 전이라 `internal`의 라우터 단위 `require_staff`를 탈 수 없어 별도 prefix를 쓴다. 콘솔용 신규 엔드포인트를 이 밑에 추가하지 않는다.

## 에러 응답 봉투

- 모든 에러는 `vivacapi/main.py`의 전역 exception handler를 거쳐 아래 형식으로 통일된다.

  ```json
  {
    "error": {
      "code": "SPOT_NOT_FOUND",
      "message": "...",
      "details": null
    }
  }
  ```

- 도메인 에러는 `HTTPException`을 직접 던지지 말고 `vivacapi.core.errors.AppException` + `ErrorCode`를 사용한다. `ErrorCode`에 없는 케이스는 새 값을 추가한다 (`_DEFAULT_STATUS`에 status code 매핑 필수).
- starlette/fastapi `HTTPException`도 동일 봉투로 감싸지므로 라우팅 404 등 프레임워크 레벨 에러도 포맷이 깨지지 않는다.

## 내부 어드민 리스트 엔드포인트 (Refine simple-rest 호환)

- `internal_spots.py`, `internal_spot_business_info.py` 등 `vivac-console` 목록 조회 엔드포인트는 Refine의 simple-rest data provider 규약을 따른다:
  - Query params: `_start`, `_end`, `_sort`, `_order`
  - 응답 헤더 `X-Total-Count`에 전체 개수 반환 (CORS `expose_headers`에 등록 필요)
- 정렬/필터 허용 컬럼은 화이트리스트(`_ADMIN_SORTABLE`, `_FILTERABLE` 패턴)로 관리해 임의 컬럼 주입을 막는다.

## 인증

- `/v1/internal/...` 라우터는 개별 엔드포인트가 아니라 `include_router(..., dependencies=[Depends(require_staff)])`로 라우터 단위에서 인증을 건다.
