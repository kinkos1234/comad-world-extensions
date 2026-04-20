#!/usr/bin/env bash
# usage-gate.sh — Anthropic quota guard.
#
# PreToolUse[Task]. When 5h / 7d usage breaches thresholds (or `mode =
# force-downgrade`), BLOCK calls to heavyweight background agents so the
# foreground operator keeps its Opus budget. The user can override once via
# the approval flag.
#
# State file: ~/.claude/.comad/usage-gate.json
# Bypass    : touch ~/.claude/.comad/approvals/approve-usage-once

set -uo pipefail

state_file="$HOME/.claude/.comad/usage-gate.json"
approve_flag="$HOME/.claude/.comad/approvals/approve-usage-once"

# State missing → gate disabled, allow
[ -f "$state_file" ] || exit 0

input="$(cat)"

# One-shot approval bypass
if [ -f "$approve_flag" ]; then
  rm -f "$approve_flag"
  printf 'usage-gate: one-shot approval consumed\n' >&2
  exit 0
fi

decision="$(printf '%s' "$input" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    tool_name  = data.get('tool_name', '')
    tool_input = data.get('tool_input', {})

    if tool_name != 'Task':
        print('ALLOW|||')
        sys.exit(0)

    state = json.load(open('$state_file'))
    if not state.get('enabled', False):
        print('ALLOW|||')
        sys.exit(0)

    sub   = tool_input.get('subagent_type', '')
    pct5  = state.get('current_5h_pct', 0)
    pct7  = state.get('current_7d_pct', 0)
    t5    = state.get('threshold_5h_pct', 80)
    t7    = state.get('threshold_7d_pct', 90)
    mode  = state.get('mode', 'auto')
    downgrade_agents = state.get('downgrade_agents', [])

    trigger = (mode == 'force-downgrade') or pct5 >= t5 or pct7 >= t7
    if not trigger:
        print('ALLOW|||')
        sys.exit(0)

    if sub in downgrade_agents:
        reason = f'mode={mode} 5h={pct5}/{t5}% 7d={pct7}/{t7}%'
        print(f'BLOCK|||{sub}|||{reason}')
    else:
        print('ALLOW|||')
except Exception:
    print('ALLOW|||')
")"

action="${decision%%|||*}"
[ "$action" = "ALLOW" ] && exit 0

rest="${decision#*|||}"
sub="${rest%%|||*}"
reason="${rest#*|||}"

cat <<EOF >&2
⏸️  usage-gate: BLOCKED background agent (quota protection)

Agent : $sub
State : $reason

Why: the foreground operator needs Opus headroom. Background curation/QA/
memory work is deferred until the quota window rolls over.

To dispatch this call anyway (single use):
  touch ~/.claude/.comad/approvals/approve-usage-once

To disable entirely or edit thresholds:
  $HOME/.claude/.comad/usage-gate.json   (set "enabled": false)

To refresh measured usage:
  /usage-gate refresh   (or let comad-evolve cron do it)
EOF
exit 2
