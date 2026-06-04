#!/usr/bin/env bash
# comad-pr-review · run.sh — launchd 폴러 진입점.
# allowlist repo 의 열린 PR 을 headSha dedup → 신규/갱신만 review.sh --post.
# config dry_run 존중(true 면 리포트만). 단일 인스턴스 락.
set -uo pipefail

export PATH="/Users/jhkim/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/Users/jhkim/.nvm/versions/node/v24.13.0/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG="$SKILL_DIR/config.json"
STATE_DIR="$(python3 -c "import json,os;print(os.path.expanduser(json.load(open('$CFG'))['state_dir']))")"
mkdir -p "$STATE_DIR/logs"
RUNLOG="$STATE_DIR/logs/run.log"
LOCK="$STATE_DIR/run.lock"
REVIEWED="$STATE_DIR/reviewed.json"

log() { echo "$(python3 -c 'import datetime;print(datetime.datetime.now(datetime.UTC).isoformat())') $*" >> "$RUNLOG"; }

if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null && mkdir "$LOCK" 2>/dev/null || { log "lock busy"; exit 0; }
  else
    log "another run active, skip"; exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

REPOS=$(python3 -c "import json;print(' '.join(json.load(open('$CFG'))['repos']))")
log "=== pr-review poll start ==="
for REPO in $REPOS; do
  PRS=$(gh pr list --repo "$REPO" --state open --json number,headRefOid -q '.[] | "\(.number) \(.headRefOid)"' 2>>"$RUNLOG")
  [ -z "$PRS" ] && continue
  echo "$PRS" | while read -r NUM SHA; do
    PKEY="${REPO}#${NUM}#${SHA}"
    SEEN=$(python3 -c "import json,os;f='$REVIEWED';d=json.load(open(f)) if os.path.exists(f) else [];print('1' if '$PKEY' in d else '0')")
    [ "$SEEN" = "1" ] && continue
    log "review → $REPO #$NUM @ ${SHA:0:7}"
    bash "$SKILL_DIR/bin/review.sh" --repo "$REPO" --pr "$NUM" --post >>"$RUNLOG" 2>&1 || log "review error $REPO#$NUM"
    python3 -c "import json,os;f='$REVIEWED';d=json.load(open(f)) if os.path.exists(f) else [];d.append('$PKEY');json.dump(d[-500:],open(f,'w'),indent=0)"
  done
done
log "=== pr-review poll done ==="
