# 🌲 VIVAC API Core

> **VIVAC**은 캠퍼들을 위한 장소 큐레이션 플랫폼입니다. 서비스의 철학과 가치가 궁금하시다면 [PRODUCT.md](./PRODUCT.md)를 참고해 주세요.

FastAPI + PostgreSQL 기반 백엔드입니다. 전체 구조는 [docs/architecture.md](./docs/architecture.md), DB 스키마는 [docs/erd.md](./docs/erd.md)를 참고하세요.

## Quickstart

```bash
# 1. 환경 변수
cp .env.example .env.local   # 값 채우기

# 2. 로컬 PostgreSQL (docker-compose)
make db-up

# 3. 마이그레이션
make migrate

# 4. 개발 서버 (http://localhost:8000, Swagger UI: /docs)
make run
```

## 자주 쓰는 명령

| 명령 | 설명 |
|------|------|
| `make run` | 개발 서버 (--reload) |
| `make test` | 테스트 (`vivac_test` DB, `.env.test` 필요 — [docs/test-setup.md](./docs/test-setup.md)) |
| `uv run ruff check .` | 린트 |
| `make migrate` / `make migrate-new m="..."` | 마이그레이션 적용/생성 |
| `make openapi` | OpenAPI 명세 생성 (`docs/openapi.json`, git 미추적) |
| `make release v=v0.x.0` | 태그 push → 배포 트리거 |

## 문서

- [docs/architecture.md](./docs/architecture.md) — 아키텍처, 엔드포인트, 설정
- [docs/erd.md](./docs/erd.md) — DB 스키마
- [docs/infra/lightsail-setup.md](./docs/infra/lightsail-setup.md) — 프로덕션 프로비저닝
- [docs/backlog.md](./docs/backlog.md) — 대기 중인 작업
- `.claude/rules/` — 코드 스타일·API 규약·보안·테스트 규칙
