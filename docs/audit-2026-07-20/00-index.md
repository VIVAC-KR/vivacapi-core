# docs/ 취합 감사 — 인덱스 (2026-07-20)

> `docs/` 하위 markdown 15개 전체를 정독해 취합·분류한 결과. 원본 폴더 구조(루트/`backlog/`/`projects/`/`infra/`)와 문서 성격에 맞춰 아래 파일로 나눠 정리했다. 원본 문서는 손대지 않았다 — 이 폴더는 별도 감사 산출물이다.
> 작업 워크트리: `.claude/worktrees/docs+consolidate-audit` (branch: `worktree-docs+consolidate-audit`, 이후 merge·삭제됨)
> **2026-07-21 갱신**: 감사 이후 `business-feature-roadmap-2026-07-20.md`에서 4.2·4.4가 완료 처리됨(PR #117, #118) — [05-business-roadmap.md](./05-business-roadmap.md)에 반영. 그 외 문서는 변경 없음.

## 파일 구성

| 파일 | 대응 원본 | 내용 |
|---|---|---|
| [01-architecture-and-db.md](./01-architecture-and-db.md) | `architecture.md`, `erd.md` | 아키텍처/DB 레퍼런스 (living doc, SoT) |
| [02-projects.md](./02-projects.md) | `projects/*.md` 7개 | 프로젝트별 설계 결정 요약 |
| [03-backlog.md](./03-backlog.md) | `backlog.md`, `backlog/*.md` 6개 | 백로그 전체 (일반 + 2026-07-11 점검분) |
| [04-security-review.md](./04-security-review.md) | `db-security-review-2026-05-02.md` | DB 스키마 보안 점검 보고서 |
| [05-business-roadmap.md](./05-business-roadmap.md) | `business-feature-roadmap-2026-07-20.md` | 비즈니스 기능 로드맵 |
| [06-infra-and-testing.md](./06-infra-and-testing.md) | `infra/lightsail-setup.md`, `test-setup.md` | 인프라 프로비저닝 + 테스트 환경 |
| [07-skill-draft.md](./07-skill-draft.md) | `skill-db-inspect.md` | Claude Skill 초안 |
| [08-cross-cutting-issues.md](./08-cross-cutting-issues.md) | 전체 | **중복/충돌/누락 항목 + 코드 대조 검증 + 정리 제안** |

각 파일 안에서 원본 문서의 핵심 결정·표·수치는 요약이 아니라 보존 수준으로 옮겼다(내용 유실 방지). 문서 간 모순·중복·공백은 08번 파일에 모아뒀다 — 개별 파일을 읽을 때도 이 파일을 함께 참고할 것.

---

## 전체 인벤토리

| 파일 | 작성일 | 유형 | 상태 |
|---|---|---|---|
| `architecture.md` | 명시 없음(living doc) | 아키텍처 레퍼런스 | 최신(SoT) |
| `erd.md` | 명시 없음(living doc) | DB 스키마 레퍼런스 | 최신(SoT) |
| `backlog.md` | 항목별 상이(07-03/07-14) | 백로그(일반 운영) | 진행중 |
| `backlog/admin-list-scale-260711.md` | 2026-07-11 | 백로그(성능) | 미착수 |
| `backlog/auth-rate-limit-260711.md` | 2026-07-11 | 백로그(보안) | 미착수 |
| `backlog/deploy-tag-injection-260711.md` | 2026-07-11 | 백로그(보안) | 미착수 |
| `backlog/pipeline-status-index-260711.md` | 2026-07-11 | 백로그(성능) | 미착수(코드 대조 확인) |
| `backlog/private-image-exposure-260711.md` | 2026-07-11 | 백로그(보안) | 미착수(코드 대조 확인) |
| `backlog/prod-allowed-email-domain-260711.md` | 2026-07-11 | 백로그(보안) | 미착수(코드 대조 확인) |
| `backlog/sqladmin-session-cookie-260711.md` | 2026-07-11 | 백로그(보안) | 미착수 |
| `business-feature-roadmap-2026-07-20.md` | 2026-07-20 | 비즈니스 로드맵 | 진행중(1.1·4.2·4.4 완료, 1.2 블로킹) |
| `db-security-review-2026-05-02.md` | 2026-05-02(+2026-07-14 갱신) | 보안 점검 보고서 | 부분 해결 |
| `infra/lightsail-setup.md` | 명시 없음 | 인프라 프로비저닝 가이드 | 최신(SoT) |
| `projects/async-job-worker-design.md` | 2026-05-17 | 프로젝트 설계 노트 | 구현 완료 |
| `projects/spot-bulk-and-admin.md` | 2026-05-17 | 프로젝트 설계 노트 | 구현 완료 |
| `projects/spot-groups-admin-api.md` | 2026-07-15 | 프로젝트 API 스펙 | 최신(SoT) |
| `projects/spot-invites.md` | 2026-07-16 | 프로젝트 API 스펙 | 구현 완료 (⚠️ 일부 내용 역전, 08번 참고) |
| `projects/spot-search-postgres-fts.md` | 2026-07-15 | 프로젝트 설계 노트 | 구현 완료 |
| `projects/vivac-console-backend.md` | 2026-06-07 | 프로젝트 API 스펙 | ⚠️ 낡음(문서 자체가 명시) |
| `projects/vivac-console-frontend.md` | 2026-06-07 | 프로젝트 설계 노트(별도 repo) | ⚠️ 일부 낡음(짝 문서와 동일 문제, 경고 누락) |
| `projects/vvc-105-explore-api-spec.md` | 2026-05-19 | 프로젝트 API 스펙 | 구현 완료 |
| `skill-db-inspect.md` | 명시 없음 | Claude Skill 초안 | ⚠️ 미적용 확인 |
| `test-setup.md` | 2026-05-02 | 변경 로그성 문서 | ⚠️ 구식 가능성 |
| `openapi.json` | 생성물(자동) | API 스펙 산출물 | git 미추적, 문서 아님, 취합 대상 제외 |
| `samples/spots_bulk_sample.json` | 참고자료 | 샘플 페이로드 | 어느 문서도 명시 링크 안 함 |
| `samples/spot_business_info_bulk_sample.json` | 참고자료 | 샘플 페이로드 | 〃 |

15개 markdown 문서 전부 정독. `openapi.json`·`samples/*.json`은 산문 문서가 아니라 요약 대상에서 제외(인벤토리에는 포함).

## 타임라인 (날짜순)

```
날짜 미표기(living doc)  architecture.md, erd.md, infra/lightsail-setup.md
2026-05-02               test-setup.md
2026-05-02               db-security-review-2026-05-02.md (최초 작성)
2026-05-17               projects/async-job-worker-design.md
2026-05-17               projects/spot-bulk-and-admin.md
2026-05-19               projects/vvc-105-explore-api-spec.md
2026-06-07               projects/vivac-console-backend.md
2026-06-07               projects/vivac-console-frontend.md
2026-07-03               backlog.md (이미지 인프라 항목 기록)
2026-07-11               backlog/*-260711.md × 6
2026-07-14               backlog.md (DB 백업 항목 기록)
2026-07-14               db-security-review-2026-05-02.md (후속 처리 현황 갱신)
2026-07-15               projects/spot-groups-admin-api.md
2026-07-15               projects/spot-search-postgres-fts.md
2026-07-16               projects/spot-invites.md
2026-07-20               business-feature-roadmap-2026-07-20.md
2026-07-20               (본 감사 폴더)
```
