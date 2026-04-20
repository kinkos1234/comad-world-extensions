# PreToolUse Hooks

Hooks wired into `~/.claude/settings.json` under `hooks.PreToolUse`.

## destroy-gate

**Matcher:** `Bash`
**Entry:** `destroy-gate.sh` → `destroy-gate.py` (v2, quote-aware)

Blocks a small set of catastrophic shell patterns unless the user drops an
approval flag. Patterns are matched after stripping quoted strings and heredoc
bodies, so scripts that merely mention a dangerous pattern in a string literal
are not blocked.

**Approve once (command-bound, preferred):**
```
touch ~/.claude/.comad/approvals/approve-destroy.<16-char-hash>
```
The hash is printed in the block message.

**Approve once (generic, fallback):**
```
touch ~/.claude/.comad/approvals/approve-destroy
```
This approves whatever destructive command comes next.

Blocked patterns:
- `rm -rf /`, `rm -rf ~`, `rm -rf $HOME`, `rm -rf .`, `rm -rf ..`
- `git push --force` / `-f` (but NOT `--force-with-lease`)
- `git reset --hard HEAD~…`, `git branch -D main/master/develop/production`
- `git clean -fd…`
- `DROP DATABASE`, `DROP SCHEMA`, `TRUNCATE DATABASE` (but NOT `DROP TABLE`)
- `kubectl delete namespace|ns|node`
- `docker system prune -a…`
- `mkfs.*`, `dd …of=/dev/sd…`, `> /dev/sd…`
- fork bombs, `chmod -R 777 /`, `chown -R … /`
- `shutdown -h`, `halt`, `init 0`

Incidents are appended to `~/.claude/.comad/pending/destroy-gate.jsonl`.

## usage-gate

**Matcher:** `Task`
**Entry:** `usage-gate.sh`
**State:** `~/.claude/.comad/usage-gate.json`

Blocks background agents (`comad-sleep`, `comad-ear`, `comad-evolve`,
`comad-brain`, `comad-photo`, `Explore`) when the Anthropic quota is under
pressure, so foreground work keeps its Opus budget.

**State semantics:**
- `enabled=false` (default) — hook is a no-op.
- `mode=force-downgrade` + `enabled=true` — block all background agent calls immediately.
- `mode=auto` + `enabled=true` — compare `current_5h_pct` / `current_7d_pct` against thresholds.

**Known gap:** nothing auto-updates `current_*_pct` yet. Until the refresher
lands (planned alongside `comad-evolve` cron), `mode=auto` is effectively a
no-op too. Use `force-downgrade` or manually edit the pct fields if you need
real defense now.

**Override once:** `touch ~/.claude/.comad/approvals/approve-usage-once`
