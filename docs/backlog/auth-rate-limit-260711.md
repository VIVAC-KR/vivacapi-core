# auth endpoint rate limiting 부재

- **심각도**: 낮음 (보안)
- **출처**: 2026-07-11 security-auditor 점검

## 문제

`/v1/auth/google`, `/v1/auth/refresh`, `/v1/admin/auth/google`에 무제한 요청 가능. 토큰 brute-force는 HS256 서명상 비현실적이나, Google API 호출 유발·계정 enumeration(401/403 응답 차이로 등록/staff 여부 구분)·DoS 여지.

- 위치: `vivacapi/api/v1/endpoints/auth.py:28-100`, `admin_auth.py:16`

## 수정 방향

- reverse proxy(CloudFront/nginx) 레벨 기본 rate limit 1개 — 앱 코드 수정 없이 해결 가능
- 어드민 로그인 실패 응답 401/403 단일화 검토

## 프론트 영향

없음 (정상 사용 범위 요청은 영향 없음).
