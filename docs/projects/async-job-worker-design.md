# 비동기 Job 워커 설계 노트 (VVC-96)

> `jobs` 테이블 기반 비동기 워커를 FastAPI lifespan에 통합하기 위한 설계 결정과 트레이드오프 정리.
> 작성일: 2026-05-17

---

## 1. 한 줄 요약

FastAPI 프로세스 안에 비동기 워커 1개를 같이 띄워, DB의 `jobs` 테이블을 2초마다 폴링하며 PENDING 작업을 하나씩 처리한다. 외부 브로커(Redis/RabbitMQ) 없음. 단일 Lightsail 인스턴스 가정.

---

## 2. 동작 흐름

```
[앱 부팅 = lifespan 진입]
   ↓
1. orphan 정리: status='running' job → 'failed' (error="orphaned")
   ↓
2. asyncio.create_task()로 워커 spawn
   ↓
[워커 루프]
   ↓ (매 2초)
3. SELECT ... WHERE status='pending' FOR UPDATE SKIP LOCKED LIMIT 1
   ↓
4. 잡은 행: status='running', started_at=now() 갱신 + 커밋 (락 해제)
   ↓
5. JobType → 핸들러 매핑 dispatch → 실제 작업 수행
   ↓
6. 결과 기록: status='succeeded'|'failed', finished_at, result/error
   ↓
[앱 종료 = lifespan 종료]
   ↓
7. 워커 task.cancel() + 종료 대기
```

---

## 3. 다른 접근법 비교

### A. 외부 브로커 (Celery / Dramatiq / arq + Redis)

| 항목 | 평가 |
|---|---|
| 기능성 | 재시도, 스케줄, 우선순위, dead-letter queue 등 풍부 |
| 인프라 | Redis 추가 필요 (Lightsail에 +1 컨테이너 또는 ElastiCache) |
| 운영 | 워커 프로세스 별도 배포·모니터링 |
| 적합 시점 | 작업 빈도 분당 수백+, 풍부한 기능 필요 |

**현 단계엔 과함.** 작업이 수동 트리거(엔지니어 직접) 기반이라 빈도가 낮음.

### B. FastAPI `BackgroundTasks`

| 항목 | 평가 |
|---|---|
| 단순성 | 의존성 0, 코드 한 줄 |
| 영속성 | **없음** — 인스턴스 죽으면 작업 유실 |
| 상태 추적 | 불가 |

**부적합.** 진행 상태 폴링 API(VVC-94)가 있고, 데이터 유실이 허용되지 않는 일괄 적재 시나리오.

### C. PostgreSQL `LISTEN/NOTIFY` 병행

| 항목 | 평가 |
|---|---|
| Latency | 폴링 없이 즉시 처리 (millisecond 단위) |
| DB 부하 | 폴링 제거 가능 |
| 복잡도 | LISTEN 전용 커넥션 점유 + 알림 유실 대비 폴링 병행 → 결국 둘 다 구현 |
| asyncpg 지원 | OK이지만 SQLAlchemy 비동기 통합이 까다로움 |

**최적이지만 복잡도 대비 이득이 작음.** 2초 폴링 latency가 수동 트리거 시나리오에서 무시 가능.

### D. 별도 워커 프로세스 (FastAPI와 분리)

| 항목 | 평가 |
|---|---|
| 격리 | 워커 죽어도 API 살아있음 |
| 운영 | docker-compose에 워커 컨테이너 추가 |
| 스케일 | 워커만 독립 스케일 가능 |

**Lightsail 단일 인스턴스라 격리 이점이 약함.** 워커가 무거워지면 M4 이후 재검토.

### E. SQS / Cloud Tasks 등 매니지드 큐

**우리 트래픽 규모에 맞지 않음.** vendor lock 비용 대비 효용 낮음.

---

## 4. 성능·운영 분석

| 우려 | 영향도 | 완화책 |
|---|---|---|
| 폴링 쿼리 부하 | 무시 가능 (초당 0.5쿼리) | — |
| **CPU 바운드 작업 시 GIL 경합** | bulk 5000행 검증/upsert 중 API 응답 latency 증가 가능 | `asyncio.to_thread()`로 CPU 작업 분리 (필요 시) |
| **DB 커넥션 풀 압박** | 워커가 2~3 커넥션 상시 점유 | 풀 크기 확인 |
| 처리량 (동시성 1) | 무거운 job 1개가 다른 job 차단 | SKIP LOCKED 덕에 N 워커로 확장 코드 변경 적음 |
| 2초 폴링 latency | 무시 가능 (수동 트리거 시나리오) | 필요 시 LISTEN/NOTIFY 추가 |
| **단일 인스턴스 = 단일 장애점** | 인스턴스 죽으면 처리 중단 | orphan 정리로 좀비 방지 |
| **graceful shutdown 중 long task** | cancel하면 running 상태로 남음 | 부팅 시 orphan 정리로 보완 (이중 처리 위험은 핸들러 멱등성으로 별도 해결) |

---

## 5. 결정 사항

| # | 항목 | 결정 | 이유 |
|---|---|---|---|
| 1 | DB 세션 | 매 사이클 새 세션 | 커넥션 회수 + 트랜잭션 격리 |
| 2 | 핸들러 등록 | 명시적 dict (`HANDLERS = {JobType.X: handler}`) | 단순·디버깅 쉬움 |
| 3 | 트랜잭션 경계 | claim 트랜잭션과 작업 트랜잭션 분리 | 락 빠르게 해제, 진행 상태 polling 가능 |
| 4 | 핸들러 예외 | traceback 전체 기록 → `error` 컬럼 | 운영 디버깅에 유용 |
| 5 | 테스트 전략 | 단일 사이클을 함수로 분리해 직접 호출 | 결정론적, 빠름 (실제 워커 spawn은 통합 테스트) |
| 6 | 폴링 주기 | 2초 | DB 부하 무시 가능 + 수동 트리거 시나리오라 latency 무관 |
| 7 | 동시성 | 1 (단일 워커) | 데이터 정합성 우선. SKIP LOCKED라 향후 N 확장 자연스러움 |
| 8 | 자동 재시도 | 없음 | 운영자가 새 job 생성하는 단순 정책 |

---

## 6. 구현 구조

```
app/
├── workers/
│   ├── __init__.py
│   ├── job_worker.py       # 워커 루프 + lifespan 통합
│   └── handlers.py         # JobType → callable 매핑 (현 시점엔 빈 dict)
└── main.py                 # lifespan에서 워커 spawn
```

**핵심 함수:**
- `cleanup_orphaned_jobs(db)` — running → failed 일괄 전환
- `claim_next_job(db) -> Job | None` — SKIP LOCKED 기반 1건 claim
- `process_job(db, job)` — 핸들러 dispatch + 결과 기록
- `run_worker_cycle(session_factory)` — 1사이클 = claim + process (단위 테스트에서 직접 호출)
- `job_worker_loop(session_factory)` — 무한 루프 + 2초 sleep

---

## 7. 향후 검토 (Out of Scope)

- bulk upsert가 CPU 바운드로 판명되면 `asyncio.to_thread()` 적용 또는 워커 프로세스 분리
- 작업이 길어지면(>5분) graceful shutdown 패턴 추가
- 작업 빈도가 분당 수십 건 이상으로 늘면 LISTEN/NOTIFY 또는 N 워커 확장
- 자동 재시도 (지수 백오프 등)
