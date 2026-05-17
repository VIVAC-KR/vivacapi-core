# Changelog

모든 주요 변경사항을 이 파일에 기록합니다.  
형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/)를 따릅니다.

---

## [Unreleased]

### Added
- `require_staff` FastAPI 의존성 + `CurrentStaff` 타입 alias — `/internal`, `/admin` 라우터 게이팅용 (VVC-79)

---

## [v0.1.0] - 2026-05-17

### Added
- Google OAuth 2.0 로그인 + JWT 액세스/리프레시 토큰 인증
- Spot / SpotBusinessInfo / SpotReview ORM 모델 초기 스키마
- User 모델: `nickname`, `membership_tier` (VVC-63)
- User 모델: `identity_verified_at`, `onboarding_survey_completed_at`
- User 모델: `is_staff` — 내부 스태프 여부 컬럼 + Alembic 마이그레이션 (VVC-78)
- 표준 에러 응답 포맷 + `ErrorCode` enum (VVC-66)
- CORS 미들웨어 + 환경별 origin 화이트리스트 (`local` / `dev` / `prod`) (VVC-67)

### Infrastructure
- Lightsail 프로비저닝 가이드 + prod 환경 변수 검증 (VVC-60)
- PR CI 워크플로 — ruff lint + pytest
- Lightsail 자동 배포 워크플로 — Docker amd64 빌드/push + SSH 배포 + 헬스체크
- 배포 트리거를 `push to main` → `v*.*.*` 태그 push로 전환 + GitHub Release 자동 생성
- `make release v=v0.1.0` Makefile 타겟 추가

---
