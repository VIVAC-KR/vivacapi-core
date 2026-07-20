# 인프라 프로비저닝 + 테스트 환경

> 대응 원본: `infra/lightsail-setup.md`, `test-setup.md`
> ← [00-index.md](./00-index.md)

## `infra/lightsail-setup.md` — 최신 SoT

AWS Lightsail Instance + Managed PostgreSQL 프로비저닝 표준 절차. `architecture.md`의 인프라 설명과 완전히 정합.

- **아키텍처**: GitHub tag push(`v*.*.*`) → GitHub Actions(`deploy.yml`) → Docker Hub push → SSH(`ec2-user`) → Lightsail Instance ↔ private network ↔ Lightsail Managed PostgreSQL
- **비용**: Instance $3.50/월($3.50번들) + DB $15/월(Standard, 1GB RAM) — 첫 3개월 무료, 이후 합계 약 $18.50/월. 무료 티어는 신규 Lightsail 사용자 1회 한정
- **무료 티어 중 절대 켜면 안 되는 것**: 자동/수동 스냅샷, Load Balancer($18/월), CDN/Distribution, 4번째+ DNS Zone, Static IP 미할당 방치(1시간+)
- **절차(11단계)**: SSH 키페어 등록 → 인스턴스 생성(Amazon Linux 2023, `ec2-user`, `/home/ec2-user/vivac` 전제) + 방화벽(22/80/443) → Static IP 부여 → Managed PostgreSQL 생성(Public mode OFF 필수) → 인스턴스↔DB 연결확인(`psql`) → Docker 설치 → `.env` 작성(`chmod 600`, JWT_SECRET_KEY/ADMIN_SESSION_SECRET는 로컬과 절대 동일값 금지) → 로컬에서 `--platform linux/amd64` buildx로 이미지 빌드+push(Apple Silicon 주의: 그냥 build하면 arm64로 빌드돼 인스턴스에서 `exec format error`) → 수동 docker run sanity check + `alembic upgrade head` + `/health` 확인 → (선택) 도메인+Caddy로 Let's Encrypt SSL
- **부록 A**: 무료 티어 유지 체크리스트 8항목
- **부록 B**: 자원정리 순서 — 컨테이너정지→인스턴스삭제→Static IP삭제→DB삭제→DNS/SSH key삭제 (Static IP를 인스턴스보다 먼저 detach하면 과금 시작되므로 인스턴스 먼저 삭제하는 순서가 안전)

## `test-setup.md` (2026-05-02, `feature/test-setup` 브랜치) — ⚠️ 구식 가능성

로컬 PostgreSQL(Docker)을 그대로 쓰는 테스트 환경 구성 기록. SQLite 대신 실제 DB 엔진으로 프로덕션과 동일 조건에서 테스트.

- **신규 파일**: `docker/init-test-db.sh`(컨테이너 최초 생성 시 `vivac_test` DB 자동생성, 기존 컨테이너엔 미적용 — `make db-create-test`로 수동)
- **변경**: `docker-compose.yml`(init 스크립트 마운트, `ENV` 변수화), `Makefile`(`make test`, `make db-create-test` 타겟 추가, `ENV` 기본값 `.env`→`.env.local`), `tests/conftest.py` 신규(픽스처 4종: `apply_migrations`/`db_session`/`client`/`db_client`), `tests/test_health.py` 신규
- **환경변수**(`.env.test`): `.env.local`과 동일하되 `DB_NAME=vivac_test`만 다름, `.gitignore`로 커밋 안 됨

> **이 문서가 도입한 픽스처·명명규칙은 현재 `.claude/rules/testing.md`가 규칙 문서로 흡수해 정식화했다.** `test-setup.md`는 "왜 이렇게 세팅했는지"의 변경 로그로서 가치는 있지만, 테스트 방법을 알고 싶을 때 1차 참고 문서는 이제 `.claude/rules/testing.md`다. 자세한 우선순위 공백은 [08-cross-cutting-issues.md](./08-cross-cutting-issues.md) 참고.
