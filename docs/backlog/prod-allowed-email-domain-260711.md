# prod에서 ALLOWED_EMAIL_DOMAIN 미설정 허용됨

- **심각도**: 낮음 (보안 — defense-in-depth 공백)
- **출처**: 2026-07-11 security-auditor 점검

## 문제

`_validate_prod_requirements`가 `ALLOWED_EMAIL_DOMAIN`을 검사하지 않아, 도메인 whitelist가 prod에서 조용히 꺼진 채 배포될 수 있음. DB `is_staff` 체크가 최종 방어선이라 직접 우회는 아님.

- 위치: `vivacapi/core/config.py:36`, `_validate_prod_requirements` (104-151)

## 수정 방향

prod validator에 `ALLOWED_EMAIL_DOMAIN` 필수 체크 한 줄 추가.

## 프론트 영향

없음.
