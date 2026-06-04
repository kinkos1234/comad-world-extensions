#!/usr/bin/env bash
# comad-ci-healer · notify.sh
# Discord 알림. 웹훅(env COMAD_CI_HEALER_WEBHOOK) 있으면 POST,
# 없으면 notify-queue.jsonl 에 적재(인터랙티브 세션/Stop 훅이 drain).
#
# 사용: notify.sh "<message>"
set -euo pipefail

MSG="${1:?usage: notify.sh <message>}"
STATE_DIR="${HOME}/.claude/.comad/ci-healer"
mkdir -p "$STATE_DIR"
QUEUE="${STATE_DIR}/notify-queue.jsonl"

# webhook env 는 config 의 notify_webhook_env 키가 가리키는 변수명
WEBHOOK_VAR="$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/skills/comad-ci-healer/config.json')))['notify_webhook_env'])" 2>/dev/null || echo COMAD_CI_HEALER_WEBHOOK)"
WEBHOOK="${!WEBHOOK_VAR:-}"

TS="$(python3 -c 'import datetime;print(datetime.datetime.now(datetime.UTC).isoformat())')"

if [ -n "$WEBHOOK" ]; then
  # Discord webhook 페이로드 (content 2000자 cap)
  python3 - "$WEBHOOK" "$MSG" <<'PY'
import json, sys, urllib.request
webhook, msg = sys.argv[1], sys.argv[2]
data = json.dumps({"content": ("🔧 [ci-healer] " + msg)[:1990]}).encode()
# Discord 는 User-Agent 없는 요청을 403 차단 → UA 필수
req = urllib.request.Request(webhook, data=data, headers={
    "Content-Type": "application/json",
    "User-Agent": "comad-ci-healer/0.1 (+https://github.com/kinkos1234)",
})
try:
    urllib.request.urlopen(req, timeout=15)
    print("[notify] webhook sent")
except Exception as e:
    print(f"[notify] webhook FAILED: {e}", file=sys.stderr)
    sys.exit(1)
PY
else
  python3 -c "import json,sys; print(json.dumps({'ts':sys.argv[1],'msg':sys.argv[2]},ensure_ascii=False))" "$TS" "$MSG" >> "$QUEUE"
  echo "[notify] queued (no webhook): $QUEUE"
fi
