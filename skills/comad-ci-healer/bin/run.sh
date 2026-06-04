#!/usr/bin/env bash
# comad-ci-healer · run.sh — launchd 폴러 진입점.
# poll → 각 새 실패에 heal.sh 적용 → seen 기록. config dry_run 존중.
# 단일 인스턴스(mkdir 락). launchd 최소 환경 대응 위해 PATH 명시.
set -uo pipefail

export PATH="/Users/jhkim/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/Users/jhkim/.nvm/versions/node/v24.13.0/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$(python3 -c "import json,os;print(os.path.expanduser(json.load(open('$SKILL_DIR/config.json'))['state_dir']))")"
mkdir -p "$STATE_DIR/logs"
RUNLOG="$STATE_DIR/logs/run.log"
LOCK="$STATE_DIR/run.lock"

log() { echo "$(python3 -c 'import datetime;print(datetime.datetime.now(datetime.UTC).isoformat())') $*" >> "$RUNLOG"; }

# ── 단일 인스턴스 락 (macOS, flock 없음 → mkdir 원자성) ──────────
if ! mkdir "$LOCK" 2>/dev/null; then
  # 스테일 락(2h+) 자동 해제
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null && mkdir "$LOCK" 2>/dev/null || { log "lock busy"; exit 0; }
  else
    log "another run active, skip"; exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

log "=== poll start ==="
NEW_JSON="$(python3 "$SKILL_DIR/bin/poll.py" 2>>"$RUNLOG")"
COUNT="$(echo "$NEW_JSON" | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)"
log "new failures: $COUNT"

if [ "$COUNT" -gt 0 ]; then
  echo "$NEW_JSON" | python3 -c '
import json,sys
for r in json.load(sys.stdin):
    print(r["repo"], r["databaseId"])
' | while read -r REPO RID; do
    log "heal → $REPO#$RID"
    bash "$SKILL_DIR/bin/heal.sh" --repo "$REPO" --run-id "$RID" >>"$RUNLOG" 2>&1 || log "heal error $REPO#$RID"
  done
  # 처리 완료분 seen 기록(재처리 방지). heal 내부 attempts 가 재시도 거버넌스 담당.
  python3 "$SKILL_DIR/bin/poll.py" --commit >/dev/null 2>>"$RUNLOG"
fi
log "=== poll done ==="
