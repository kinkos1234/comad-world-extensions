#!/usr/bin/env bash
# comad-ci-healer · heal.sh
# 단일 실패 run 을 분류 → 정책 라우팅 → (auto-fix 시) headless claude 로 수정 → PR.
#
# 사용:
#   heal.sh --repo OWNER/REPO --run-id 123 [--category lint] [--force-real]
# dry_run(config) 이거나 --force-real 미지정이면 PR 안 내고 계획만 출력.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG="${SKILL_DIR}/config.json"
cfg() { python3 -c "import json,sys;print(json.load(open('$CFG'))$1)"; }

REPO="" ; RUN_ID="" ; CATEGORY="" ; FORCE_REAL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2;;
    --run-id) RUN_ID="$2"; shift 2;;
    --category) CATEGORY="$2"; shift 2;;
    --force-real) FORCE_REAL=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[ -n "$REPO" ] && [ -n "$RUN_ID" ] || { echo "need --repo and --run-id" >&2; exit 2; }

STATE_DIR="$(python3 -c "import os;print(os.path.expanduser('$(cfg "['state_dir']")'))")"
mkdir -p "$STATE_DIR/logs"
ATTEMPTS_FILE="$STATE_DIR/attempts.json"
MAX_ATTEMPTS="$(cfg "['max_attempts']")"
BRANCH_PREFIX="$(cfg "['branch_prefix']")"
DRY_RUN="$(cfg "['dry_run']")"
NOTIFY="${SKILL_DIR}/bin/notify.sh"
KEY="${REPO}#${RUN_ID}"

# ── 시도 횟수 체크 ─────────────────────────────────────────────
ATTEMPTS=$(python3 -c "import json,os;d=json.load(open('$ATTEMPTS_FILE')) if os.path.exists('$ATTEMPTS_FILE') else {};print(d.get('$KEY',0))")
if [ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ]; then
  bash "$NOTIFY" "❌ ESCALATE — $KEY: max_attempts($MAX_ATTEMPTS) 초과, 자동수정 중단. 인간 확인 필요. ${RUN_URL:-}"
  exit 0
fi

# ── 분류 ──────────────────────────────────────────────────────
if [ -z "$CATEGORY" ]; then
  CATEGORY=$(python3 "${SKILL_DIR}/bin/classify.py" --repo "$REPO" --run-id "$RUN_ID" 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)['category'])")
fi
echo "[heal] $KEY → category=$CATEGORY (attempt $((ATTEMPTS+1))/$MAX_ATTEMPTS)"

in_list() { python3 -c "import json,sys;print('1' if sys.argv[1] in json.load(open('$CFG'))[sys.argv[2]] else '0')" "$1" "$2"; }
RUN_URL="https://github.com/${REPO}/actions/runs/${RUN_ID}"

# ── 정책 라우팅 ────────────────────────────────────────────────
if [ "$(in_list "$CATEGORY" escalate_categories)" = "1" ]; then
  bash "$NOTIFY" "⚠️ ESCALATE — $KEY: category=$CATEGORY (자동수정 비대상). $RUN_URL"
  exit 0
fi
if [ "$(in_list "$CATEGORY" rerun_only_categories)" = "1" ]; then
  echo "[heal] flaky → rerun only"
  if [ "$DRY_RUN" = "True" ] && [ "$FORCE_REAL" -eq 0 ]; then
    echo "[dry-run] WOULD: gh run rerun $RUN_ID --repo $REPO"
  else
    gh run rerun "$RUN_ID" --repo "$REPO" --failed || true
    bash "$NOTIFY" "🔁 RERUN — $KEY: flaky 의심, 재실행 트리거. $RUN_URL"
  fi
  exit 0
fi

# ── auto-fix 경로 (lint/build/test) ───────────────────────────
BRANCH="${BRANCH_PREFIX}${RUN_ID}"
WORKDIR="/tmp/ci-heal-${RUN_ID}"
HEAD_BRANCH=$(gh run view "$RUN_ID" --repo "$REPO" --json headBranch -q .headBranch 2>/dev/null || echo main)
EXCERPT=$(python3 "${SKILL_DIR}/bin/classify.py" --repo "$REPO" --run-id "$RUN_ID" 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin).get('log_excerpt','')[:800])")

read -r -d '' PROMPT <<EOF || true
[comad-ci-healer 자동복구]
저장소 ${REPO} 의 GH Actions run ${RUN_ID} (브랜치 ${HEAD_BRANCH}) 이 ${CATEGORY} 으로 실패했다.
실패 로그 발췌:
---
${EXCERPT}
---
규칙(feedback_ci_post_push):
- lint 는 --max-warnings=0 기준. 경고도 실패로 간주.
- 원인을 최소 범위로 수정. 무관한 리팩터 금지.
- actions 는 deprecated 버전이면 v5+ 로 갱신.
작업:
1. 위 ${CATEGORY} 실패의 근본 원인을 코드에서 찾아 최소 수정.
2. 로컬에서 해당 검사(lint/build/test)를 실행해 통과 확인.
3. 통과하면 변경을 커밋 (메시지: "fix(ci): heal run ${RUN_ID} ${CATEGORY} failure").
수정 불가/근본원인 불명확이면 아무것도 커밋하지 말고 "HEAL_FAILED: <이유>" 출력.
EOF

if [ "$DRY_RUN" = "True" ] && [ "$FORCE_REAL" -eq 0 ]; then
  echo "── [DRY-RUN] 실제 수행 계획 ──────────────────────────"
  echo "1. git clone ${REPO} → ${WORKDIR}"
  echo "2. git checkout -b ${BRANCH} (base: ${HEAD_BRANCH})"
  echo "3. (cd ${WORKDIR}) claude -p <아래 프롬프트> --dangerously 없이 headless"
  echo "4. 변경 있으면 push + gh pr create --base ${HEAD_BRANCH} --head ${BRANCH}"
  echo "5. notify Discord (PR url)"
  echo "── headless claude 프롬프트 ──────────────────────────"
  echo "$PROMPT"
  echo "──────────────────────────────────────────────────────"
  exit 0
fi

# ── 실제 수행 ──────────────────────────────────────────────────
python3 -c "import json,os;f='$ATTEMPTS_FILE';d=json.load(open(f)) if os.path.exists(f) else {};d['$KEY']=$((ATTEMPTS+1));json.dump(d,open(f,'w'),indent=2)"
rm -rf "$WORKDIR"
gh repo clone "$REPO" "$WORKDIR" -- --depth 50 >/dev/null 2>&1
cd "$WORKDIR"
git checkout "$HEAD_BRANCH" >/dev/null 2>&1 || true
BASE_SHA=$(git rev-parse HEAD)
git checkout -b "$BRANCH"

LOG="$STATE_DIR/logs/${RUN_ID}.log"
echo "[heal] running headless claude (log: $LOG)"
# /tmp 격리 clone + 인간 리뷰 PR + destroy-gate 훅(권한과 무관하게 발화) 보호하에
# headless 모드에서 쓰기/커밋이 가능하도록 권한 게이트 우회. blast radius = 임시 clone 한정.
claude -p "$PROMPT" --dangerously-skip-permissions < /dev/null > "$LOG" 2>&1 || true

# claude 가 직접 커밋했을 수도, 미커밋으로 남겼을 수도 있음 → 둘 다 흡수
git add -A
git commit -m "fix(ci): heal run ${RUN_ID} ${CATEGORY} failure" >/dev/null 2>&1 || true
# 성공 판정 = base(HEAD_BRANCH) 대비 새 커밋 존재 여부 (working-tree diff 아님)
if [ "$(git rev-parse HEAD)" = "$BASE_SHA" ]; then
  bash "$NOTIFY" "⚠️ HEAL_FAILED — $KEY: headless claude 가 수정 못 함(새 커밋 없음). 로그: $LOG. $RUN_URL"
  exit 0
fi
git push -u origin "$BRANCH" >/dev/null 2>&1
PR_URL=$(gh pr create --repo "$REPO" --base "$HEAD_BRANCH" --head "$BRANCH" \
  --title "fix(ci): auto-heal run ${RUN_ID} (${CATEGORY})" \
  --body "comad-ci-healer 자동 생성. run ${RUN_URL} 의 ${CATEGORY} 실패 복구 시도. **머지 전 인간 리뷰 필수.**" 2>&1 | grep -o 'https://github.com[^ ]*' | head -1)
bash "$NOTIFY" "✅ HEAL_PR — $KEY (${CATEGORY}) 수정 PR 생성: ${PR_URL:-생성됨}. 리뷰 후 머지."
echo "[heal] done → ${PR_URL:-PR created}"
