#!/usr/bin/env bash
# install.sh — copy this repo's hooks/skills/config into ~/.claude/.
#
# Safe to re-run: overwrites existing files (takes a .bak-<ts> before each).
# Does NOT touch ~/.claude/settings.json — hook registration is a separate
# step the user runs once (see README.md § Wiring hooks into settings.json).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${CLAUDE_HOME:-$HOME/.claude}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }

mkdir -p "$TARGET/hooks/pre-tool-use" "$TARGET/hooks/stop" "$TARGET/hooks/lib" \
         "$TARGET/workflows" \
         "$TARGET/skills/comad-learn/bin" "$TARGET/skills/comad-memory/bin" \
         "$TARGET/skills/comad-qa-evidence/bin" \
         "$TARGET/skills/comad-second-opinion/bin" \
         "$TARGET/skills/comad-parallel/scripts" \
         "$TARGET/skills/comad-parallel/references" \
         "$TARGET/skills/comad-ci-healer/bin" \
         "$TARGET/skills/comad-pr-review/bin" \
         "$TARGET/skills/comad-pr-review/templates" \
         "$TARGET/skills/harness-report/bin" \
         "$TARGET/skills/comad-recall/bin" \
         "$TARGET/skills/comad-foresight/bin" \
         "$TARGET/skills/comad-foresight/references" \
         "$TARGET/skills/comad-sdd/scripts" \
         "$TARGET/.comad/approvals" "$TARGET/.comad/pending" \
         "$TARGET/.comad/memory" "$TARGET/.comad/evolve"

# --- helper ---
copy_file() {
  local src="$1" dst="$2"
  if [ -f "$dst" ] && ! cmp -s "$src" "$dst"; then
    cp "$dst" "${dst}.bak-${TS}"
    log "backed up existing → ${dst}.bak-${TS}"
  fi
  cp "$src" "$dst"
  log "installed $(basename "$dst")"
}

# --- hooks ---
for f in destroy-gate.sh destroy-gate.py usage-gate.sh no-env-commit.sh no-env-commit.py qa-gate-before-push.sh qa-gate-before-push.py README.md; do
  copy_file "$REPO_ROOT/hooks/pre-tool-use/$f" "$TARGET/hooks/pre-tool-use/$f"
done
copy_file "$REPO_ROOT/hooks/stop/t6-capture.sh" "$TARGET/hooks/stop/t6-capture.sh" \
         "$TARGET/hooks/stop/claim-done-gate.sh" \
         "$TARGET/hooks/stop/claim-done-gate.py" \
         "$TARGET/hooks/stop/premature-completion-detector.sh" \
         "$TARGET/hooks/stop/premature-completion-detector.py" \
         "$TARGET/hooks/stop/numeric-claim-gate.sh" \
         "$TARGET/hooks/stop/numeric-claim-gate.py" \
         "$TARGET/hooks/stop/inventory-gate.sh" \
         "$TARGET/hooks/stop/inventory-gate.py"
copy_file "$REPO_ROOT/hooks/stop/claim-done-gate.sh" "$TARGET/hooks/stop/claim-done-gate.sh"
copy_file "$REPO_ROOT/hooks/stop/claim-done-gate.py" "$TARGET/hooks/stop/claim-done-gate.py"
copy_file "$REPO_ROOT/hooks/stop/premature-completion-detector.sh" "$TARGET/hooks/stop/premature-completion-detector.sh"
copy_file "$REPO_ROOT/hooks/stop/premature-completion-detector.py" "$TARGET/hooks/stop/premature-completion-detector.py"
copy_file "$REPO_ROOT/hooks/stop/numeric-claim-gate.sh" "$TARGET/hooks/stop/numeric-claim-gate.sh"
copy_file "$REPO_ROOT/hooks/stop/numeric-claim-gate.py" "$TARGET/hooks/stop/numeric-claim-gate.py"
copy_file "$REPO_ROOT/hooks/stop/inventory-gate.sh" "$TARGET/hooks/stop/inventory-gate.sh"
copy_file "$REPO_ROOT/hooks/stop/inventory-gate.py" "$TARGET/hooks/stop/inventory-gate.py"
copy_file "$REPO_ROOT/hooks/stop/adversarial-review-gate.sh" "$TARGET/hooks/stop/adversarial-review-gate.sh"
copy_file "$REPO_ROOT/hooks/stop/adversarial-review-gate.py" "$TARGET/hooks/stop/adversarial-review-gate.py"

# --- hooks/lib: shared libs imported by stop hooks (adversarial-review-gate) and
#     by comad-world's nightly-audit.sh (decisions escalation queue). ---
for f in decisions.py substantial_change.py; do
  copy_file "$REPO_ROOT/hooks/lib/$f" "$TARGET/hooks/lib/$f"
done

chmod +x "$TARGET/hooks/pre-tool-use/destroy-gate.sh" \
         "$TARGET/hooks/pre-tool-use/destroy-gate.py" \
         "$TARGET/hooks/pre-tool-use/usage-gate.sh" \
         "$TARGET/hooks/pre-tool-use/no-env-commit.sh" \
         "$TARGET/hooks/pre-tool-use/no-env-commit.py" \
         "$TARGET/hooks/pre-tool-use/qa-gate-before-push.sh" \
         "$TARGET/hooks/pre-tool-use/qa-gate-before-push.py" \
         "$TARGET/hooks/stop/t6-capture.sh" \
         "$TARGET/hooks/stop/adversarial-review-gate.sh"

# --- skills ---
for f in SKILL.md; do
  copy_file "$REPO_ROOT/skills/comad-learn/$f" "$TARGET/skills/comad-learn/$f"
  copy_file "$REPO_ROOT/skills/comad-memory/$f" "$TARGET/skills/comad-memory/$f"
  copy_file "$REPO_ROOT/skills/comad-qa-evidence/$f" "$TARGET/skills/comad-qa-evidence/$f"
  copy_file "$REPO_ROOT/skills/comad-second-opinion/$f" "$TARGET/skills/comad-second-opinion/$f"
done
for f in validate-pending.py validate-feedback.py; do
  copy_file "$REPO_ROOT/skills/comad-learn/bin/$f" "$TARGET/skills/comad-learn/bin/$f"
done
for f in lib.py sync.py search.py trace.py refresh.py; do
  copy_file "$REPO_ROOT/skills/comad-memory/bin/$f" "$TARGET/skills/comad-memory/bin/$f"
done
for f in init-qa-evidence.py validate-qa-evidence.py; do
  copy_file "$REPO_ROOT/skills/comad-qa-evidence/bin/$f" "$TARGET/skills/comad-qa-evidence/bin/$f"
  chmod +x "$TARGET/skills/comad-qa-evidence/bin/$f"
done
for f in validate-second-opinion.py; do
  copy_file "$REPO_ROOT/skills/comad-second-opinion/bin/$f" "$TARGET/skills/comad-second-opinion/bin/$f"
  chmod +x "$TARGET/skills/comad-second-opinion/bin/$f"
done

# --- comad-parallel (Codex 병렬 외주 + 5종 comad 통합 게이트) ---
copy_file "$REPO_ROOT/skills/comad-parallel/SKILL.md" "$TARGET/skills/comad-parallel/SKILL.md"
copy_file "$REPO_ROOT/skills/comad-parallel/package.json" "$TARGET/skills/comad-parallel/package.json"
copy_file "$REPO_ROOT/skills/comad-parallel/package-lock.json" "$TARGET/skills/comad-parallel/package-lock.json"
for f in parallel.sh parallel.cmd parallel-job.sh parallel-job.cmd parallel-job.js parallel-job-worker.js codex-output-schema.json; do
  copy_file "$REPO_ROOT/skills/comad-parallel/scripts/$f" "$TARGET/skills/comad-parallel/scripts/$f"
done
chmod +x "$TARGET/skills/comad-parallel/scripts/parallel.sh" \
         "$TARGET/skills/comad-parallel/scripts/parallel-job.sh"
for f in anti-patterns.md codex-guide.md examples.md instruction-templates.md role-separation.md tech-stack.md; do
  copy_file "$REPO_ROOT/skills/comad-parallel/references/$f" "$TARGET/skills/comad-parallel/references/$f"
done

# --- comad-ci-healer (GH Actions 자가복구 상시 에이전트) ---
#   launchd plist + webhook 은 사용자 로컬에서만 설정(공개 repo 비포함). SKILL.md 참고.
copy_file "$REPO_ROOT/skills/comad-ci-healer/SKILL.md" "$TARGET/skills/comad-ci-healer/SKILL.md"
copy_file "$REPO_ROOT/skills/comad-ci-healer/config.json" "$TARGET/skills/comad-ci-healer/config.json"
for f in poll.py classify.py heal.sh notify.sh run.sh; do
  copy_file "$REPO_ROOT/skills/comad-ci-healer/bin/$f" "$TARGET/skills/comad-ci-healer/bin/$f"
done
chmod +x "$TARGET/skills/comad-ci-healer/bin/heal.sh" \
         "$TARGET/skills/comad-ci-healer/bin/notify.sh" \
         "$TARGET/skills/comad-ci-healer/bin/run.sh"

# --- comad-pr-review (Autonomous 4-axis PR Reviewer) ---
copy_file "$REPO_ROOT/skills/comad-pr-review/SKILL.md" "$TARGET/skills/comad-pr-review/SKILL.md"
copy_file "$REPO_ROOT/skills/comad-pr-review/config.json" "$TARGET/skills/comad-pr-review/config.json"
copy_file "$REPO_ROOT/skills/comad-pr-review/rubric.md" "$TARGET/skills/comad-pr-review/rubric.md"
for f in review.sh post.sh run.sh; do
  copy_file "$REPO_ROOT/skills/comad-pr-review/bin/$f" "$TARGET/skills/comad-pr-review/bin/$f"
done
chmod +x "$TARGET/skills/comad-pr-review/bin/review.sh" \
         "$TARGET/skills/comad-pr-review/bin/post.sh" \
         "$TARGET/skills/comad-pr-review/bin/run.sh"
copy_file "$REPO_ROOT/skills/comad-pr-review/templates/comad-pr-review.yml" "$TARGET/skills/comad-pr-review/templates/comad-pr-review.yml"

# --- harness-report (Loopy-Era 5축 점수 + 비용/efficiency 측정) ---
copy_file "$REPO_ROOT/skills/harness-report/SKILL.md" "$TARGET/skills/harness-report/SKILL.md"
for f in harness-report.py collect-cost.py dashboard.py; do
  copy_file "$REPO_ROOT/skills/harness-report/bin/$f" "$TARGET/skills/harness-report/bin/$f"
done

# --- comad-recall / comad-foresight (brain 활용 — ⚠️ comad-brain Neo4j 필요) ---
copy_file "$REPO_ROOT/skills/comad-recall/SKILL.md" "$TARGET/skills/comad-recall/SKILL.md"
copy_file "$REPO_ROOT/skills/comad-recall/bin/recall.sh" "$TARGET/skills/comad-recall/bin/recall.sh"
chmod +x "$TARGET/skills/comad-recall/bin/recall.sh"
copy_file "$REPO_ROOT/skills/comad-foresight/SKILL.md" "$TARGET/skills/comad-foresight/SKILL.md"
copy_file "$REPO_ROOT/skills/comad-foresight/config.json" "$TARGET/skills/comad-foresight/config.json"
copy_file "$REPO_ROOT/skills/comad-foresight/references/lenses.md" "$TARGET/skills/comad-foresight/references/lenses.md"
for f in cluster.sh digest.sh run.sh; do
  copy_file "$REPO_ROOT/skills/comad-foresight/bin/$f" "$TARGET/skills/comad-foresight/bin/$f"
  chmod +x "$TARGET/skills/comad-foresight/bin/$f"
done

# --- comad-sdd (Spec-Driven Development 루프 — SPEC→완료기준→PLAN→BUILD→VERIFY) ---
copy_file "$REPO_ROOT/skills/comad-sdd/SKILL.md" "$TARGET/skills/comad-sdd/SKILL.md"
copy_file "$REPO_ROOT/skills/comad-sdd/scripts/check-acceptance.sh" "$TARGET/skills/comad-sdd/scripts/check-acceptance.sh"
chmod +x "$TARGET/skills/comad-sdd/scripts/check-acceptance.sh"

# --- workflows (Dynamic Workflow templates) ---
#   adversarial-review.js (R2): N skeptics try to break the diff → .second-opinion.md
#   judge-panel.js        (R5): N strategy lenses → judged → synthesized recommendation
for f in adversarial-review.js judge-panel.js; do
  copy_file "$REPO_ROOT/workflows/$f" "$TARGET/workflows/$f"
done

# --- Codex AGENTS.md worker conventions (idempotent append to ~/.codex/AGENTS.md) ---
#   comad-parallel(품앗이)이 띄우는 Codex 워커가 qa-gate/destroy-check/T6-capture 를
#   기본값으로 통과하도록 CLAUDE.md 의 Codex-side 미러를 ~/.codex/AGENTS.md 에 주입.
CODEX_AGENTS="$HOME/.codex/AGENTS.md"
if [ -f "$REPO_ROOT/config/codex-agents-comad-conventions.md" ]; then
  mkdir -p "$HOME/.codex"
  if [ -f "$CODEX_AGENTS" ] && grep -q "COMAD-WORKER-CONVENTIONS-START" "$CODEX_AGENTS"; then
    log "preserved existing comad worker conventions in $CODEX_AGENTS (already present)"
  else
    cat "$REPO_ROOT/config/codex-agents-comad-conventions.md" >> "$CODEX_AGENTS"
    log "appended comad worker conventions to $CODEX_AGENTS"
  fi
fi

# --- config template (only if target doesn't exist — don't overwrite live state) ---
if [ ! -f "$TARGET/.comad/usage-gate.json" ]; then
  cp "$REPO_ROOT/config/usage-gate.json.template" "$TARGET/.comad/usage-gate.json"
  log "seeded $TARGET/.comad/usage-gate.json (enabled=false by default)"
else
  log "preserved existing $TARGET/.comad/usage-gate.json (edit manually if you want defaults)"
fi

# --- initial memory index ---
if command -v python3 >/dev/null 2>&1 && [ -f "$TARGET/skills/comad-memory/bin/sync.py" ]; then
  log "bootstrapping comad-memory FTS index…"
  (cd "$TARGET/skills/comad-memory/bin" && python3 sync.py || true)
fi

echo
log "✅ install complete."
echo
cat <<EOF
Next steps:

1. Wire hooks into ~/.claude/settings.json. Merge these into the "hooks" block
   (existing entries are preserved):

   "hooks": {
     "PreToolUse": [
       { "matcher": "Bash",
         "hooks": [{ "type": "command", "command": "$TARGET/hooks/pre-tool-use/destroy-gate.sh" }] },
       { "matcher": "Task",
         "hooks": [{ "type": "command", "command": "$TARGET/hooks/pre-tool-use/usage-gate.sh" }] }
     ],
     "Stop": [
       { "hooks": [{ "type": "command", "command": "$TARGET/hooks/stop/t6-capture.sh", "timeout": 8000 }] },
       { "hooks": [{ "type": "command", "command": "$TARGET/hooks/stop/adversarial-review-gate.sh", "timeout": 8000 }] }
     ]
   }

2. Add a T6 section to ~/.claude/CLAUDE.md — see README.md § CLAUDE.md T6.

3. Apply the Nexus-Sprint P7 patch (manual):
   see patches/nexus-sprint-stage5-p7.md

4. Smoke test:
   bash $TARGET/hooks/pre-tool-use/destroy-gate.sh <<< '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}'
   # should print "BLOCKED" and exit 2
EOF
