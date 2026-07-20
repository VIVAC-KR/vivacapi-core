# 교차 이슈 — 중복 / 충돌 / 누락 / 검증

> `docs/` 15개 문서 전체를 가로지르는 문제만 모았다. 개별 문서 내용은 01~07번 파일 참고.
> ← [00-index.md](./00-index.md)

## 중복 항목

1. **auth rate limiting 중복 기재** — [03-backlog.md](./03-backlog.md)의 `backlog.md`(일반) 항목과 `backlog/auth-rate-limit-260711.md`가 동일 이슈를 각각 다룬다. 후자가 더 상세(위치·완화책·프론트영향 명시). `backlog.md` 쪽 항목을 지우고 후자 링크로 대체하는 게 자연스럽다.

## 충돌 항목

2. **`spot-invites.md` ↔ `business-feature-roadmap` 1.1의 결정 역전** — [02-projects.md](./02-projects.md)의 `spot-invites.md`(2026-07-16)는 "1회용, 재사용 불가"를 명시적 설계 결정으로 기록했는데, [05-business-roadmap.md](./05-business-roadmap.md) 1.1(2026-07-20, 4일 뒤)이 이를 "재사용 가능"으로 뒤집었다. 로드맵 문서는 이 사실을 알고 근거도 남겼지만(`consume_invite_for_signup`가 일반 리퍼럴에 한해 `PENDING` 유지), **`spot-invites.md` 본문 자체는 갱신되지 않아 "결정 사항 요약" 표의 "재사용 여부: 1회용" 행이 지금은 사실과 다르다.**

3. **`vivac-console-backend.md` 자체 인지 낡음** — [02-projects.md](./02-projects.md) 참고. 문서 상단에 "실제 경로는 `/v1/internal/*`, architecture.md가 기준"이라고 이미 명시. 충돌이 아니라 **문서가 스스로 낡았다고 선언한 케이스**지만, 뒤에 이어지는 엔드포인트 표(POST/DELETE 등)는 그 선언과 별개로 옛 내용 그대로라 실수로 인용될 위험.

4. **`vivac-console-frontend.md`는 낡음 표기 없음** — 짝 문서(backend.md)가 낡았다고 선언했지만 frontend.md는 `/v1/admin/*` 경로를 그대로 전제한 코드 스니펫·리소스 등록 예시를 담고 있는데 정정 표기가 없다. **backend.md와 달리 이 문서엔 "낡음" 경고가 누락됨.**

5. **`db-security-review` 문서 내부 자기 갱신 패턴** — [04-security-review.md](./04-security-review.md) 참고. 최초 작성(2026-05-02)과 후속 처리 현황(2026-07-14)이 한 파일 안에 공존. 충돌은 아니고 오히려 좋은 패턴이지만, [07-skill-draft.md](./07-skill-draft.md)의 `skill-db-inspect.md`가 제안하는 "매번 새 보고서 생성" 방식과는 운영 방침이 다르다 — 향후 `/db_inspect` 실행 시 어느 쪽을 따를지 불명확.

6. **memory 기록과의 불일치 (docs 범위 밖이지만 발견됨)** — 이 세션의 저장된 memory(`project_infra_architecture.md`)는 "vivac.app: CloudFront+ACM → EC2 t2.micro(Docker) → RDS t3.micro, EC2 아직 미생성"이라 되어 있는데, [01-architecture-and-db.md](./01-architecture-and-db.md)와 [06-infra-and-testing.md](./06-infra-and-testing.md) 둘 다 일관되게 **Lightsail Instance + Lightsail Managed PostgreSQL**을 현재 인프라로 기술한다. EC2/RDS 조합은 두 SoT 문서 어디에도 없다 — memory가 stale한 것으로 보임.

## 누락/공백

7. **`vivac-console-frontend.md` 낡음 미표기** — 충돌 4번과 동일 사안. `/v1/admin/*` 전제 코드를 그대로 따라가면 실제 구현(`/v1/internal/*`)과 어긋난다.

8. **`spot-invites.md` 갱신 누락** — 충돌 2번과 동일 사안.

9. **`skill-db-inspect.md` 미적용 방치** — [07-skill-draft.md](./07-skill-draft.md) 참고. `.claude/skills/`에 `db_inspect` 없음(확인 완료). 초안 작성 후 이관 단계가 누락된 채 남음.

10. **`test-setup.md` 구식화** — [06-infra-and-testing.md](./06-infra-and-testing.md) 참고. 이 문서가 도입한 픽스처·규칙은 현재 `.claude/rules/testing.md`가 흡수해 정식화했다. 두 문서 간 우선순위(어느 쪽이 1차 참고 문서인지)가 명시돼 있지 않음.

11. **`architecture.md`/`erd.md` 갱신일 부재** — "living document"라 명시했지만 문서 안에 마지막 갱신 날짜 필드가 없어, 실제 코드와 어긋난 지 얼마나 됐는지 문서만 보고는 알 수 없다.

12. **샘플 JSON 참조 누락** — `samples/spots_bulk_sample.json`, `samples/spot_business_info_bulk_sample.json`이 같은 기능을 설계한 `docs/projects/spot-bulk-and-admin.md`에서 명시적으로 링크되지 않는다. 어느 문서도 이 두 샘플 파일을 가리키지 않아, 존재를 아는 사람만 찾을 수 있는 상태.

13. **`vvc-105-explore-api-spec.md` 후속 이슈 상태 불명** — VVC-117(필터)/118(이미지필드)/119(정렬확정) 완료 여부가 이 문서 범위 밖이라 명시돼 있는데, `spot-search-postgres-fts.md`가 사실상 VVC-119 관련 정렬 로직(`score DESC, rating_avg DESC, uid DESC`)까지 구현했음에도 원 스펙 문서에 "후속 완료됨" 역참조가 없다.

## 코드 대조 검증 (전수 검증 아님, 의심스러운 5건만 샘플 확인)

| 항목 | 문서 주장 | 코드 확인 결과 |
|---|---|---|
| `backlog/private-image-exposure-260711.md` | `list_images_by_spot`에 `is_public` 필터 없음 | ✅ 확인 — `vivacapi/crud/spot_image.py:7-16`, 필터 없음. **미해결** |
| `backlog/prod-allowed-email-domain-260711.md` | `_validate_prod_requirements`가 `ALLOWED_EMAIL_DOMAIN` 안 검사 | ✅ 확인 — `vivacapi/core/config.py:105`부터 해당 필드 언급 없음. **미해결** |
| `backlog/pipeline-status-index-260711.md` | `pipeline_status`는 partial index뿐 | ✅ 확인 — `vivacapi/models/spot.py`에 `postgresql_where="pipeline_status = 'PUBLISHED' AND deleted_at IS NULL"` 하나뿐. **미해결** |
| `skill-db-inspect.md` | `.claude/skills/db_inspect/SKILL.md`로 이관 예정 | ✅ 확인 — 해당 디렉터리 없음(`.claude/skills/`엔 `git_commit`, `git_release`만 존재). **미이관** |
| `backlog.md` 이미지 인프라 항목 | `S3_BUCKET`/`CDN_BASE_URL` 미설정 | ✅ 확인 — `.env.example`에 없음. **여전히 미설정** |

## 정리 제안 (요약)

- `backlog.md`의 auth rate limit 항목을 삭제하고 `backlog/auth-rate-limit-260711.md` 링크로 대체
- `spot-invites.md`의 "재사용 여부: 1회용" 행에 로드맵 1.1 완료로 뒤집힌 사실 각주 추가
- `vivac-console-frontend.md` 상단에 backend.md와 동일한 낡음 경고 추가
- `skill-db-inspect.md`를 실제 이관하거나, 이관 안 할 거면 문서에 "보류" 표기
- memory의 인프라 기록(EC2+CloudFront+RDS)을 Lightsail 기준으로 정정

이 폴더는 취합·분류·문제 표시만 수행했다. 실제 원본 문서 수정/삭제는 사용자 지시 후 별도 진행.
