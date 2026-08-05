#!/usr/bin/env bash
# `make release`의 마지막 단계로 실행된다 (Makefile release 타깃).
# vivac-cowork를 최신으로 맞추고, 방금 릴리즈된 버전의 openapi.json을 생성해 main에 push한다.
#
# 사용: scripts/sync_cowork_openapi.sh [vX.Y.Z]
# 버전 인자가 없으면 vivacapi/__init__.py의 __version__을 쓴다.
# 릴리즈 tag가 remote에 실제로 올라간 경우에만 동작한다 (release 중단 시 no-op).
# DRY_RUN=1 로 실행하면 pull/commit/push 없이 수행할 명령만 출력한다.
set -euo pipefail

core_root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
cd "$core_root"

version="${1:-v$(sed -n 's/^__version__ *= *["'\'']\([^"'\'']*\).*/\1/p' vivacapi/__init__.py)}"

# docs는 vivac-cowork/docs로 향하는 심링크(SYMLINK-SETUP.md). 없는 worktree에서는 조용히 빠진다.
[ -L docs ] || { echo "sync-cowork: docs is not a symlink to vivac-cowork, skipping"; exit 0; }
cowork=$(dirname "$(cd docs && pwd -P)")

git ls-remote --exit-code --tags origin "refs/tags/$version" >/dev/null 2>&1 || {
  echo "sync-cowork: tag $version not on origin (release did not complete), skipping"
  exit 0
}

run() { if [ -n "${DRY_RUN:-}" ]; then echo "DRY_RUN: $*"; else "$@"; fi; }

# openapi.json은 전량 생성 파일이므로 로컬 수정본은 버리고 pull한다. 다른 파일은 건드리지 않는다.
run git -C "$cowork" checkout -- docs/openapi.json
run git -C "$cowork" checkout main
run git -C "$cowork" pull --ff-only origin main

run make openapi

run git -C "$cowork" add docs/openapi.json
if [ -z "${DRY_RUN:-}" ] && git -C "$cowork" diff --cached --quiet -- docs/openapi.json; then
  echo "sync-cowork: openapi.json unchanged for $version, nothing to push"
  exit 0
fi

run git -C "$cowork" commit -m "docs: sync openapi.json from vivacapi-core $version

Co-Authored-By: Claude <noreply@anthropic.com>"
run git -C "$cowork" push origin main
echo "sync-cowork: pushed openapi.json for $version to vivac-cowork main"
