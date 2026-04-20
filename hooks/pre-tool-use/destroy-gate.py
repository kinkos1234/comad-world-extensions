#!/usr/bin/env python3
"""destroy-gate hook — v2.

Improvements over v1 (shell):
- Strip single/double-quoted string contents before pattern matching, so a
  command like `echo "example: rm -rf /"` no longer false-blocks.
- Approval flag is command-bound by default: the hook computes sha256(cmd)[:16]
  and shows the user the exact filename to touch. A generic legacy flag still
  works but is now advertised as the fallback, not the primary path.
- Patterns are anchored with \b word boundaries for better precision.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import re
import sys

HOME = pathlib.Path(os.environ.get("HOME", "/"))
APPROVE_DIR = HOME / ".claude" / ".comad" / "approvals"
LOG_DIR = HOME / ".claude" / ".comad" / "pending"

# Terminator after a path/target — anything that isn't a path-continuation
# character counts as "end of that arg". Captures `/`, end-of-line, `)`, `;`,
# `&`, `|`, whitespace, and so on.
_END = r"(?![A-Za-z0-9/._-])"

# (pattern, human-readable label)
PATTERNS: list[tuple[str, str]] = [
    (r"\brm\s+-[rRfFd]+\s+/" + _END, "rm -rf /"),
    (r"\brm\s+-[rRfFd]+\s+/\*", "rm -rf /*"),
    (r"\brm\s+-[rRfFd]+\s+~" + _END, "rm -rf ~"),
    (r"\brm\s+-[rRfFd]+\s+~/", "rm -rf ~/..."),
    (r"\brm\s+-[rRfFd]+\s+\$HOME", "rm -rf $HOME"),
    (r"\brm\s+-[rRfFd]+\s+\.\.?" + _END, "rm -rf . / .."),
    (r"\bgit\s+push\s+[^;&|]*--force(\s|$)", "git push --force"),
    (r"\bgit\s+push\s+[^;&|]*-[^\s-]*f(\s|$)", "git push -f"),
    (r"\bgit\s+reset\s+--hard\s+(HEAD~|origin/|upstream/)", "git reset --hard ref"),
    (r"\bgit\s+branch\s+-D\s+(main|master|develop|production)", "git branch -D protected"),
    (r"\bgit\s+clean\s+-fd", "git clean -fd"),
    (r"\bDROP\s+(DATABASE|SCHEMA)\b", "DROP DATABASE/SCHEMA"),
    (r"\bTRUNCATE\s+DATABASE\b", "TRUNCATE DATABASE"),
    (r"\bkubectl\s+delete\s+(namespace|ns|node)\b", "kubectl delete ns/node"),
    (r"\bdocker\s+system\s+prune\s+[^;&|]*-a", "docker system prune -a"),
    (r"\bmkfs\.[a-z0-9]+", "mkfs.*"),
    (r"\bdd\s+[^;&|]*of=/dev/(sd|nvme|disk|hd)", "dd → raw disk"),
    (r":\s*\(\s*\)\s*\{\s*:", "fork bomb"),
    (r"\bchmod\s+-R\s+(777|000)\s+/", "chmod -R 777 /"),
    (r"\bchown\s+-R\s+[^\s]+\s+/" + _END, "chown -R /"),
    (r">\s*/dev/sd", "write to /dev/sd*"),
    (r"\bshutdown\s+-h\b", "shutdown -h"),
    (r"\bhalt" + _END, "halt"),
    (r"\binit\s+0" + _END, "init 0"),
]


def strip_strings(cmd: str) -> str:
    """Replace quoted string contents and heredoc bodies with placeholders so
    patterns match only on executable command text.

    - Heredocs (``<< EOF ... EOF``, ``<<-'EOF' ... EOF``) are collapsed to a
      single placeholder token, preserving the redirection operator.
    - Single-quoted strings: contents replaced (POSIX has no escapes inside
      single quotes, so this is safe).
    - Double-quoted strings: contents replaced, with minimal escape awareness
      (``\"`` does not end the string).
    """
    # Heredocs — greedy but line-anchored
    def heredoc_sub(m: re.Match[str]) -> str:
        prefix = m.group("prefix")
        return f"{prefix} __HEREDOC__\n"

    cmd = re.sub(
        r"(?P<prefix><<-?\s*['\"]?(?P<delim>[A-Za-z_][A-Za-z0-9_]*)['\"]?)"
        r"[^\n]*\n"
        r".*?"
        r"\n\s*(?P=delim)\s*(?:\n|$)",
        heredoc_sub,
        cmd,
        flags=re.DOTALL,
    )

    # Single-quoted strings (no nested escapes in POSIX)
    cmd = re.sub(r"'[^']*'", "__SQUOTED__", cmd)

    # Double-quoted strings — allow \" escape
    cmd = re.sub(r'"(?:\\.|[^"\\])*"', "__DQUOTED__", cmd, flags=re.DOTALL)

    return cmd


def cmd_hash(cmd: str) -> str:
    return hashlib.sha256(cmd.encode("utf-8", errors="replace")).hexdigest()[:16]


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0  # can't parse → fail-open

    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return 0

    cleaned = strip_strings(cmd)

    matched_label = None
    for pat, label in PATTERNS:
        if re.search(pat, cleaned, flags=re.MULTILINE):
            matched_label = label
            break

    if matched_label is None:
        return 0

    h = cmd_hash(cmd)

    APPROVE_DIR.mkdir(parents=True, exist_ok=True)
    specific_flag = APPROVE_DIR / f"approve-destroy.{h}"
    generic_flag = APPROVE_DIR / "approve-destroy"

    if specific_flag.exists():
        specific_flag.unlink()
        sys.stderr.write(
            f"destroy-gate: command-bound approval consumed ({h} / {matched_label})\n"
        )
        return 0
    if generic_flag.exists():
        generic_flag.unlink()
        sys.stderr.write(
            f"destroy-gate: generic approval consumed ({matched_label})\n"
        )
        return 0

    # Log event
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "destroy-gate.jsonl").open("a") as f:
        f.write(
            json.dumps(
                {
                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "cmd_hash": h,
                    "pattern": matched_label,
                    "command": cmd,
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    msg = f"""🛑 destroy-gate: BLOCKED (Approval-Gated Destruction)

Command     : {cmd}
Pattern     : {matched_label}
Cmd hash    : {h}

To approve THIS specific command (exact match, single use — preferred):
  touch ~/.claude/.comad/approvals/approve-destroy.{h}

To approve ANY next destructive command (broad, single use — fallback):
  touch ~/.claude/.comad/approvals/approve-destroy

Either flag is auto-removed on consumption. If this is a false positive, edit:
  ~/.claude/hooks/pre-tool-use/destroy-gate.py

Incident logged at ~/.claude/.comad/pending/destroy-gate.jsonl
"""
    sys.stderr.write(msg)
    return 2


if __name__ == "__main__":
    sys.exit(main())
