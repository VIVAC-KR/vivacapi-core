# Backlog

우선순위 미정 / 시점 대기 항목. 착수 시 이 파일에서 지우고 이슈/PR로 전환.

## 이미지 기능 운영 세팅 (v0.5.8 배포됨, 인프라 미설정 — 2026-07-03 기록)

코드는 배포됐지만 아래 세팅 전까지 이미지 API만 503을 반환한다 (나머지 기능 정상).

- [ ] S3 버킷 생성 (이미지 원본 저장용)
- [ ] CloudFront 오리진 연결 (공개 이미지 서빙)
- [ ] EC2/IAM 권한: `s3:PutObject`, `s3:HeadObject` (presign 발급·검증용)
- [ ] S3 버킷 CORS: 브라우저 직접 PUT 허용
- [ ] `.env`에 `S3_BUCKET`, `CDN_BASE_URL` 설정 (선택: `AWS_REGION`, `S3_PRESIGN_EXPIRE_SECONDS`)

## DB 백업 이중화 (pg_dump → S3, 2026-07-14 기록)

RDS 자동 백업 retention이 계정 Free Tier 제한으로 1일 고정(7일 등으로 상향 시도 시 `FreeTierRestrictionError`, 콘솔에서도 해제 불가 — AWS Support 티켓 필요). RDS 삭제/계정 이슈 등 RDS 자체 장애에 대비해 별도 pg_dump 백업을 S3에 쌓는 방안 합의, 착수는 보류.

- [ ] AWS Support에 Free Tier Restriction 해제 요청 (해제되면 이 백업 필요성 재평가)
- [ ] S3 버킷 생성 (`vivac-db-backups`) + Lifecycle rule로 N일(예 30일) 지난 오브젝트 자동 삭제
- [ ] EC2(`vivac-web-prod`) instance profile에 해당 버킷 `s3:PutObject`만 허용하는 IAM role 추가
- [ ] EC2 IMDS hop-limit 확인 (`MetadataOptions`) — 기본 1이면 Docker 컨테이너에서 instance profile 인식 안 됨, 2로 상향 필요할 수 있음
- [ ] RDS 엔진(postgres) 버전 확인 후 동일 버전의 `postgres:<ver>-alpine` 이미지로 pg_dump 실행 (버전 불일치 시 호환성 문제)
- [ ] `scripts/backup_db.sh` 작성 — `docker run postgres:<ver>-alpine pg_dump -Fc` → `docker run amazon/aws-cli s3 cp` (앱 이미지는 건드리지 않음, host에 postgresql-client 설치도 불필요)
- [ ] EC2 host crontab 등록, 주기 12시간 (`0 3,15 * * *`)

## audit_log 보관정책

- [ ] audit_log 무한 증가 대응 — N개월 초과분 삭제 배치. 데이터가 쌓여 실측 필요해지는 시점에.

## 인증 엔드포인트 rate limiting

- [ ] `/v1/auth/*`, `/v1/admin/auth/*` 요청 제한 — 앱 레벨 도입 대신 리버스 프록시(Caddy `rate_limit`) 레벨에서 처리하는 것을 우선 검토. 트래픽이 생겨 남용이 관측되는 시점에.

## 수정 이력 화면 고도화 (수요 발생 시)

- [ ] 이력 페이지네이션 (현재 최신 100건 고정)
- [ ] 필드 한글 라벨 API (현재 프론트 매핑으로 충분)
