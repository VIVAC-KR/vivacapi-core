---
name: git_release
description: 커밋된 feature/fix 브랜치를 push→PR→merge하고, 버전을 bump해 새 PR로 merge한 뒤, release tag를 push해 prod 배포까지 진행합니다.
disable-model-invocation: true
allowed-tools: Bash(git checkout *) Bash(git pull *) Bash(git push *) Bash(git branch *) Bash(git log *) Bash(git status *) Bash(git add *) Bash(git commit *) Bash(git stash *) Bash(git tag *) Bash(make release *) Bash(sed *) Bash(gh pr create *) Bash(gh pr checks *) Bash(gh pr merge *) Bash(gh run list *) Bash(gh run view *) Bash(gh run watch *) Bash(curl *)
---

# Git Release — push부터 prod 배포까지

feature/fix 브랜치에 커밋이 이미 준비된 상태에서 시작해, main에 merge하고
버전을 올려 tag를 push함으로써 `deploy.yml`(tag push 트리거)을 발동시키고
prod 헬스체크까지 확인합니다.

**전제**: 현재 브랜치가 main이 아니고, 커밋할 변경사항은 이미 커밋 완료된
상태(`git_commit` skill 또는 직접 커밋). main 직접 push는 금지 — 반드시
PR을 거칩니다.

## 절차

### 1단계: feature 브랜치 push + PR

```bash
git status --short   # main이 아닌지, 커밋 안 된 변경이 없는지 확인
git push -u origin <현재브랜치>
gh pr create --title "<type>: <제목>" --body "$(cat <<'EOF'
## 요약
<변경 내용>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- `git status --short`에 이번 작업과 무관한 미추적 파일이 보이면 무시하고 진행 (건드리지 않음).
- PR 본문은 최근 커밋 메시지·diff 내용을 요약해 작성.

### 2단계: CI 통과 확인 후 merge

```bash
sleep 20 && gh pr checks <PR번호> --watch --interval 15
gh pr merge <PR번호> --merge
git checkout main && git pull
```

- CI가 실패하면 **merge하지 않고 중단**, 원인 보고.

### 3단계: 버전 bump 브랜치 + PR

이 repo는 `vivacapi/__init__.py`의 `__version__`이 버전 소스.

```bash
grep -n "__version__" vivacapi/__init__.py   # 현재 버전 확인
git checkout -b chore/bump-v<NEW>
sed -i '' 's/<OLD>/<NEW>/' vivacapi/__init__.py
git add vivacapi/__init__.py
git commit -m "$(cat <<'EOF'
chore: bump version to v<NEW> (<한 줄 요약>)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
git push -u origin chore/bump-v<NEW>
gh pr create --title "chore: bump version to v<NEW>" --body "<이전 PR 번호> 릴리즈 준비.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- semver 판단: 스키마/계약 변경이 있는 기능 추가는 minor(`0.x.0`), 버그·테스트 보강은 patch(`0.0.x`). 애매하면 사용자에게 확인.

### 4단계: bump PR도 CI 통과 후 merge

```bash
sleep 20 && gh pr checks <PR번호> --watch --interval 15
gh pr merge <PR번호> --merge
git checkout main && git pull
```

### 5단계: release tag push (배포 트리거)

`Makefile`의 `release` 타깃은 main 브랜치·clean tree를 요구한다.

```bash
git status --short
```

- 이번 작업과 무관한 미추적 파일 때문에 dirty하면 **삭제하지 말고** stash로 비켜준다:
  ```bash
  git stash -u
  make release v=v<NEW>
  git stash pop
  ```
- 무관한 변경이 없으면 바로:
  ```bash
  make release v=v<NEW>
  ```

### 6단계: 배포 워크플로우 대기 + 검증

```bash
sleep 20
RUN_ID=$(gh run list --workflow deploy.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch $RUN_ID --exit-status
gh run view $RUN_ID --json conclusion --jq .conclusion   # success 확인

curl -fsS https://api.vivac.app/health
```

- 이번 변경과 관련된 endpoint가 있으면 curl로 한 번 더 실동작 확인 (예: 새 필드가 응답에 보이는지, 새 필터가 걸리는지).
- `conclusion`이 `success`가 아니면 **배포 실패로 보고**, 롤백 여부는 사용자에게 확인 후 진행.

## 주의사항

- **main 직접 push 금지.** 모든 변경은 PR을 거친다 (repo CLAUDE.local.md 규칙).
- **CI 실패 시 강제 merge 금지.**
- **무관한 미추적/미커밋 파일은 절대 add/commit/삭제하지 않는다.** stash로만 비켜간다.
- `--no-verify`, `--force`, `git reset --hard` 등 파괴적/훅 우회 옵션은 사용하지 않는다.
- 이 skill은 push·merge·prod 배포까지 실행하는 **되돌리기 어려운 작업**이다. 사용자가 "push/merge/배포까지 진행"을 명시적으로 요청했을 때만 전 단계를 이어서 실행하고, 단순히 "커밋해줘"에는 반응하지 않는다(그건 `git_commit` skill의 몫).
