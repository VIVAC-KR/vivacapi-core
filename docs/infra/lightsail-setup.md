# AWS Lightsail 프로비저닝 가이드

> VIVAC API를 AWS Lightsail Instance + Managed PostgreSQL로 배포하기 위한 표준 절차.
> 본 문서대로 따라하면 외부에서 인스턴스 SSH 접속이 가능하고, FastAPI 컨테이너가 Managed DB와 통신할 수 있는 상태가 된다.

---

## 0. 개요 및 비용

### 아키텍처

```
GitHub (push to main)
      │
      ▼
GitHub Actions  ──── docker push ──▶  Docker Hub
      │
      ▼ (SSH)
Lightsail Instance  ◀──── private network ───▶  Lightsail Managed PostgreSQL
($3.50 / Ubuntu / Docker)                       ($15 Standard, 1GB RAM)
```

### 비용


| 리소스                                         | 비용      | 무료 티어        |
| ------------------------------------------- | ------- | ------------ |
| Lightsail Instance ($3.50 번들)               | $3.50/월 | **첫 3개월 무료** |
| Lightsail Managed PostgreSQL ($15 Standard) | $15/월   | **첫 3개월 무료** |
| Static IP (인스턴스에 attach 시)                  | $0      | 항상 무료        |
| 송수신 1 TB/월                                  | $0      | 번들 포함        |


3개월 후 합계: **약 $18.50/월**.

> ⚠️ 무료 티어는 신규 Lightsail 사용자에게 1회 제공된다. 같은 AWS 계정에서 이전에 Lightsail을 사용한 적이 있다면 적용되지 않을 수 있음 — 콘솔 → Billing → Free Tier에서 확인.

### 무료 티어 동안 절대 켜면 안 되는 항목

- 자동 스냅샷 (Auto-Snapshot) — $0.05/GB·월
- 수동 스냅샷 — 같은 단가
- Lightsail Load Balancer — $18/월
- Lightsail CDN/Distribution
- 추가 IP 또는 4번째 이상의 DNS Zone
- Static IP 미할당 상태로 1시간 이상 방치 — $0.005/시간

---

## 1. 사전 준비

- AWS 계정 (관리자 IAM 사용자)
- 로컬에 `aws` CLI (선택, 콘솔만으로도 진행 가능)
- 도메인 (선택 — 11번 단계에서만 필요)

---

## 2. SSH 키 페어 등록

1. Lightsail 콘솔 → **Account → SSH keys**
2. 리전: **Seoul (ap-northeast-2)** 선택
3. **Create key pair** 클릭, 이름 `vivac-prod-key`로 저장
4. 다운로드된 `.pem` 파일을 로컬 `~/.ssh/vivac-prod-key.pem`에 보관, 권한 변경:
  ```bash
   mv ~/Downloads/vivac-prod-key.pem ~/.ssh/
   chmod 400 ~/.ssh/vivac-prod-key.pem
  ```

> 이미 가지고 있는 키 페어를 업로드해도 무방.

---

## 3. Lightsail Instance 생성

1. 콘솔 → **Instances → Create instance**
2. 리전: **Seoul, Zone A (ap-northeast-2a)**
3. Platform: **Linux/Unix**
4. Blueprint: **OS Only → Ubuntu 24.04 LTS**
5. 사이즈: **$3.50/월 번들** (1 vCPU / 512 MB RAM / 20 GB SSD / 1 TB 전송)
6. SSH key pair: 위에서 만든 `vivac-prod-key`
7. **Automatic snapshots: OFF** (반드시 비활성)
8. 인스턴스 이름: `vivac-api-prod`
9. **Create instance**

### 3-1. 인스턴스 방화벽 설정

콘솔 → 인스턴스 클릭 → **Networking** 탭 → **IPv4 Firewall**


| Application | Protocol | Port | Source                          |
| ----------- | -------- | ---- | ------------------------------- |
| SSH         | TCP      | 22   | 본인 IP만 (가능하면 제한, 어렵다면 Anywhere) |
| HTTP        | TCP      | 80   | Anywhere                        |
| HTTPS       | TCP      | 443  | Anywhere                        |


> FastAPI는 컨테이너 내부 8000 포트로 listen하고, 호스트 80/443으로 reverse proxy하거나 docker port mapping `80:8000`으로 노출한다.

---

## 4. Static IP 부여

1. 콘솔 → **Networking → Create static IP**
2. 리전: **Seoul**
3. Attach to instance: `vivac-api-prod`
4. 이름: `vivac-api-prod-ip`
5. **Create**

이 IP는 **인스턴스에 attach된 동안 무료**, detach되면 시간당 $0.005가 부과된다. 인스턴스를 삭제할 때는 Static IP도 같이 삭제해야 한다.

---

## 5. Lightsail Managed PostgreSQL 생성

1. 콘솔 → **Databases → Create database**
2. 리전: **Seoul**
3. **PostgreSQL** → 최신 16.x
4. 사이즈: **$15 Standard 번들** (1 GB RAM / 40 GB SSD / 100 GB 전송)
  - HA(High Availability)는 $30이며 무료 티어 대상 아님 — Standard 선택
5. Master username: `vivac` (변경 가능)
6. Master password: **자동 생성 권장** (콘솔에서 한번만 표시됨, 즉시 password manager에 보관)
7. Database 이름: `vivac`
8. **Automatic snapshots: OFF**
9. 이름: `vivac-db-prod`
10. **Create database**

생성 완료까지 약 10~15분.

### 5-1. Public mode 비활성

기본값으로 Public mode는 OFF여야 한다. 콘솔 → DB → **Networking** 탭에서 **Public mode = OFF** 확인.

이 상태에서 같은 AWS 리전 내 같은 Lightsail 계정의 인스턴스만 DB에 접근 가능하다. 외부 인터넷에서는 접속 불가.

### 5-2. 엔드포인트 확인

DB → **Connect** 탭에서 다음 값을 메모:

- Endpoint (private): `ls-xxxxx.xxxxx.ap-northeast-2.rds.amazonaws.com`
- Port: `5432`
- Master username, password, database 이름

이 값들이 곧 `.env.production`의 `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` 가 된다.

---

## 6. 인스턴스 ↔ DB 연결 확인

```bash
ssh -i ~/.ssh/vivac-prod-key.pem ubuntu@<STATIC_IP>

# 인스턴스 안에서
sudo apt-get update
sudo apt-get install -y postgresql-client
PGPASSWORD='<MASTER_PASSWORD>' psql \
  -h <DB_ENDPOINT> -p 5432 -U vivac -d vivac -c 'select 1;'
```

`?column?` 컬럼에 `1`이 출력되면 연결 정상.

---

## 7. 인스턴스에 Docker 설치

SSH로 인스턴스 접속 후:

```bash
# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
# 적용을 위해 한 번 로그아웃 후 재접속
exit
```

재접속 후:

```bash
docker --version
docker run --rm hello-world
```

---

## 8. .env.production 작성

인스턴스 안의 적절한 위치(예: `/home/ubuntu/vivac/.env.production`)에 다음 내용으로 파일 생성:

```env
ENVIRONMENT=prod

DB_HOST=ls-xxxxx.xxxxx.ap-northeast-2.rds.amazonaws.com
DB_PORT=5432
DB_NAME=vivac
DB_USER=vivac
DB_PASSWORD=<5번에서 받은 마스터 패스워드>

GOOGLE_CLIENT_ID=<프로덕션용 OAuth 클라이언트 ID>

JWT_SECRET_KEY=<반드시 새로 생성: python -c "import secrets; print(secrets.token_urlsafe(64))">
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
```

권한 잠금:

```bash
chmod 600 .env.production
```

> `JWT_SECRET_KEY`는 로컬/dev와 **절대 동일한 값을 사용하지 말 것**. config.py의 prod 검증이 placeholder 문자열을 거부한다.

---

## 9. 이미지 빌드 및 Docker Hub push (로컬에서)

> 이 단계는 **로컬 개발 머신**에서 수행한다. Lightsail 인스턴스가 아니다.

### 9-1. Docker Hub 레포 준비

1. Docker Hub에 `vivacapi-core` 레포지토리 생성
  - Public이면 인스턴스에서 `docker login` 없이 pull 가능
  - Private이면 인스턴스에서도 `docker login` 필요
2. 로컬에서 로그인:
  ```bash
   docker login
  ```

### 9-2. amd64로 빌드 후 push

Lightsail $3.50 번들은 **x86_64(amd64)** CPU다. Mac(Apple Silicon)에서 그냥 `docker build` 하면 `linux/arm64`로 빌드되어 인스턴스에서 `exec format error`가 발생하거나 QEMU 에뮬레이션으로 매우 느려진다. 반드시 `--platform linux/amd64`를 명시한다.

```bash
# Buildx 빌더 1회 준비 (이미 있으면 스킵)
docker buildx create --use --name vivac-builder 2>/dev/null \
  || docker buildx use vivac-builder

# amd64로 빌드 → 바로 Docker Hub로 push
docker buildx build --platform linux/amd64 \
  -t <DOCKERHUB_USER>/vivacapi-core:latest \
  --push .
```

> `--push`는 결과를 로컬 daemon에 적재하지 않고 곧장 레지스트리로 올린다. 로컬에서 amd64 이미지를 직접 돌려 검증하고 싶다면 `--load`로 빌드 후 `docker run --platform linux/amd64 ...` (에뮬레이션이라 느림).

---

## 10. 부팅 sanity check (수동 docker run)

9번에서 push한 이미지를 인스턴스에서 받아 실행:

```bash
docker pull <DOCKERHUB_USER>/vivacapi-core:latest

docker run -d \
  --name vivac-api \
  --env-file .env.production \
  -p 80:8000 \
  --restart unless-stopped \
  <DOCKERHUB_USER>/vivacapi-core:latest

# DB 마이그레이션 적용
docker exec vivac-api uv run alembic upgrade head

# 헬스체크
curl http://localhost/health
# {"status":"ok","environment":"prod"}
```

외부에서:

```bash
curl http://<STATIC_IP>/health
```

---

## 11. (선택) 도메인 + Let's Encrypt SSL

### 11-1. 도메인 연결

기존 보유 도메인의 DNS 관리 페이지 또는 Lightsail DNS Zone(3개까지 무료) 에서 A 레코드를 Static IP로 지정.

```
api.vivac.app  A  <STATIC_IP>
```

### 11-2. Let's Encrypt (Caddy 권장)

Caddy는 도메인을 가리키면 자동으로 SSL을 발급/갱신한다. 80/443 포트가 호스트에서 비어 있어야 한다.

```bash
# 위 10번에서 시작한 컨테이너의 포트 매핑을 80:8000 → 8000:8000으로 변경
docker stop vivac-api && docker rm vivac-api
docker run -d \
  --name vivac-api \
  --env-file .env.production \
  -p 8000:8000 \
  --restart unless-stopped \
  <DOCKERHUB_USER>/vivacapi-core:latest

# Caddy 설치
sudo apt-get install -y caddy
```

`/etc/caddy/Caddyfile`:

```
api.vivac.app {
    reverse_proxy localhost:8000
}
```

```bash
sudo systemctl reload caddy
curl https://api.vivac.app/health
```

---

## 부록 A. 무료 티어 유지 체크리스트

- Static IP가 인스턴스에 attach되어 있다 (detach 1시간이면 과금)
- 인스턴스 자동 스냅샷 OFF
- DB 자동 스냅샷 OFF
- 수동 스냅샷을 만들지 않았다
- Lightsail Load Balancer를 만들지 않았다
- CDN/Distribution을 만들지 않았다
- DNS Zone 4개 미만
- 1 TB/월 송수신 미만 (콘솔에서 모니터링)

## 부록 B. 자원 정리 (3개월 후 또는 종료 시)

순서: **컨테이너 정지 → 인스턴스 삭제 → Static IP 삭제 → DB 삭제 → DNS Zone/SSH key 삭제**

Static IP를 인스턴스보다 먼저 detach하면 시간당 $0.005가 발생하므로, 인스턴스를 먼저 삭제하면 자동으로 detach된 시점부터 즉시 삭제하는 흐름이 안전하다.