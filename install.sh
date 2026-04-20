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

mkdir -p "$TARGET/hooks/pre-tool-use" "$TARGET/hooks/stop" \
         "$TARGET/skills/comad-learn/bin" "$TARGET/skills/comad-memory/bin" \
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
for f in destroy-gate.sh destroy-gate.py usage-gate.sh no-env-commit.sh no-env-commit.py README.md; do
  copy_file "$REPO_ROOT/hooks/pre-tool-use/$f" "$TARGET/hooks/pre-tool-use/$f"
done
copy_file "$REPO_ROOT/hooks/stop/t6-capture.sh" "$TARGET/hooks/stop/t6-capture.sh" \
         "$TARGET/hooks/stop/claim-done-gate.sh" \
         "$TARGET/hooks/stop/claim-done-gate.py"
copy_file "$REPO_ROOT/hooks/stop/claim-done-gate.sh" "$TARGET/hooks/stop/claim-done-gate.sh"
copy_file "$REPO_ROOT/hooks/stop/claim-done-gate.py" "$TARGET/hooks/stop/claim-done-gate.py"

chmod +x "$TARGET/hooks/pre-tool-use/destroy-gate.sh" \
         "$TARGET/hooks/pre-tool-use/destroy-gate.py" \
         "$TARGET/hooks/pre-tool-use/usage-gate.sh" \
         "$TARGET/hooks/pre-tool-use/no-env-commit.sh" \
         "$TARGET/hooks/pre-tool-use/no-env-commit.py" \
         "$TARGET/hooks/stop/t6-capture.sh"

# --- skills ---
for f in SKILL.md; do
  copy_file "$REPO_ROOT/skills/comad-learn/$f" "$TARGET/skills/comad-learn/$f"
  copy_file "$REPO_ROOT/skills/comad-memory/$f" "$TARGET/skills/comad-memory/$f"
done
for f in validate-pending.py validate-feedback.py; do
  copy_file "$REPO_ROOT/skills/comad-learn/bin/$f" "$TARGET/skills/comad-learn/bin/$f"
done
for f in lib.py sync.py search.py trace.py refresh.py; do
  copy_file "$REPO_ROOT/skills/comad-memory/bin/$f" "$TARGET/skills/comad-memory/bin/$f"
done

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
       { "hooks": [{ "type": "command", "command": "$TARGET/hooks/stop/t6-capture.sh", "timeout": 8000 }] }
     ]
   }

2. Add a T6 section to ~/.claude/CLAUDE.md — see README.md § CLAUDE.md T6.

3. Apply the Nexus-Sprint P7 patch (manual):
   see patches/nexus-sprint-stage5-p7.md

4. Smoke test:
   bash $TARGET/hooks/pre-tool-use/destroy-gate.sh <<< '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}'
   # should print "BLOCKED" and exit 2
EOF
