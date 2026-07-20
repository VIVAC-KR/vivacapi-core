# Claude Skill 초안 — `db_inspect`

> 대응 원본: `skill-db-inspect.md`
> ← [00-index.md](./00-index.md)

`.claude/skills/db_inspect/SKILL.md`로 옮길 **초안**. 검토/수정 후 이관하면 `/db_inspect` 슬래시 커맨드로 호출 가능해질 예정이었음.

> ⚠️ **§08 코드 대조 검증 결과: `.claude/skills/`에 실제로 이관되지 않았다** (`git_commit`, `git_release`만 존재). 초안 작성 후 방치된 상태.

## 목적/트리거

DB 스키마(ORM 모델+Alembic 마이그레이션+연결설정)를 종합 점검해 `docs/db-security-review-YYYY-MM-DD.md` 보고서를 매번 새로 생성. 트리거 시점: 신규 모델/컬럼 PR 직전, 분기 정기점검(월 1회 권장), 운영 적용 전 사전검토, 외부 감사 대비 셀프체크. 인자 `$ARGUMENTS`(선택, 점검범위 키워드).

## SKILL.md 본문 요지 (그대로 복사해 쓰도록 문서에 markdown 블록으로 포함돼 있음)

- `allowed-tools`: `Bash(ls/cat/grep/rg/date/uv run alembic)`, `Read`, `Write` (DB 직접 연결 없음, 정적분석만)
- **1단계**: `date`, `ls app/models/`, `ls alembic/versions/`, `alembic current/heads` 병렬 실행 + 모델/마이그레이션/DB설정 전체 Read
- **2단계 체크리스트 A~I** (9개 카테고리, 항목별로 "발견 없음"도 명시):
  - A. 식별자/PK(SERIAL 열거가능성, 외부노출 ID, FK 인덱스, ON DELETE/UPDATE)
  - B. 유니크/제약(대소문자 정규화, functional unique index, CHECK, NOT NULL 오선언, partial unique)
  - C. PII/민감정보(평문저장, 인증정보 컬럼저장, 감사로그 존재, 마스킹/암호화)
  - D. URL/문자열 입력(스킴/도메인 검증, 최대길이, 정규식 CHECK)
  - E. 시간/타임스탬프(TIMESTAMPTZ 여부, 자동갱신, 과거값 CHECK)
  - F. 인증/IdP(OAuth subject nullable 락인, 다중IdP 확장성)
  - G. 마이그레이션 안전성(`# please adjust!` 흔적, destructive downgrade, NOT NULL 백필 누락, `CONCURRENTLY`)
  - H. 연결/풀/로깅(`echo` 운영노출위험, pool_size 정합성, `expire_on_commit` 위험, DSN노출, `SecretStr`)
  - I. 인덱스/성능(자주조회 컬럼 인덱스, 미사용 인덱스, GIN 등 적절 타입)
- **3단계**: 보고서 필수 5섹션(메타정보/점검대상요약/식별된위험항목(심각도+ID+문제/영향/완화)/우선순위권장액션표/본보고서가다루지않은것). 같은 날 기존 보고서 있으면 `-2`,`-3` 접미사
- **4단계**: 생성 경로 + High/Medium 항목 수 한 줄 안내

## 주의사항 (원문)

- DB 직접 연결 안 함 — 정적분석(파일읽기)만. 실제 메타데이터 필요한 항목은 "운영 점검 필요"로만 표시
- 추측을 사실로 적지 않음 — 근거 약한 항목은 ⚪ Info 또는 "검증 필요"
- 수정 시도 안 함 — 보고서 생성만, 실제 수정은 별도 지시 후

## 향후 개선 아이디어 (원문)

`pg_stat_*` 운영 DB 메타조회 옵션(read-only DSN), 자동수정 PR 생성 스킬(`/db_fix`) 연계, 이전 보고서와의 diff 출력, CI에서 PR 코멘트로 보고서 첨부.

## 이 문서와 실제 보고서(`db-security-review-2026-05-02.md`)의 운영방식 차이

이 초안은 "매번 새 파일 생성"을 전제로 하지만, 실제 `04-security-review.md`가 요약한 `db-security-review-2026-05-02.md`는 **같은 파일에 "2026-07-14 후속 처리 현황" 표를 덧붙이는 갱신 방식**을 써왔다. 두 방식 중 어느 쪽이 실제 운영 방침인지 정해진 바 없음 — 상세는 [08-cross-cutting-issues.md](./08-cross-cutting-issues.md) 참고.
