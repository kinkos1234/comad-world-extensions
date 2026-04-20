#!/usr/bin/env python3
"""claim-done-gate hook — detects verification-flavored completion claims in
the current assistant turn and logs them when no verification command was run.

Stop hook. Reads the session transcript (path provided by Claude Code via
stdin payload or $CLAUDE_TRANSCRIPT_PATH), finds the last assistant turn,
scans it for specific verification claims ("92/92 PASS", "모두 통과", "all
tests pass", ...), and cross-references with Bash tool invocations in the
same turn.

Mode: WARN-ONLY (exit 0 + log to ~/.claude/.comad/pending/claim-done.jsonl).
To escalate to blocking (exit 2 forcing Claude to continue), set the env
var COMAD_CLAIM_DONE_BLOCK=1.

Bypass keywords (if present anywhere in this turn's assistant text, the
check is skipped for that turn):
  "검증 없이 판단", "검증 없이", "LGTM", "tests skipped", "no verification",
  "구현만", "증거 없음 명시"
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import sys

HOME = pathlib.Path(os.environ.get("HOME", "/"))
LOG_DIR = HOME / ".claude" / ".comad" / "pending"
BLOCK_MODE = os.environ.get("COMAD_CLAIM_DONE_BLOCK", "") == "1"

# Verification-flavored claim patterns — deliberately narrower than generic
# "완료" to avoid false positives on conversational summaries.
CLAIM_PATTERNS = [
    r"\b\d+\s*/\s*\d+\s+(?:PASS|passed|통과)\b",
    r"모두\s*(?:PASS|passed|통과)",
    r"전부\s*(?:PASS|passed|통과|성공)",
    r"100\s*%\s*(?:통과|PASS|성공|완료)",
    r"전수\s*검증\s*(?:완료|통과)",
    r"\ball\s+(?:tests?|checks?)\s+(?:pass|passed|passing)\b",
    r"\btests?\s+(?:all\s+)?pass(?:ed|ing)?\b",
    r"every(?:thing)?\s+pass",
]

# Commands that count as "I actually verified something" in the same turn.
VERIFICATION_CMD_PATTERNS = [
    r"\btest\b",
    r"\bpytest\b",
    r"\btsc\b",
    r"\bmake\b",
    r"\bnpm\s+(?:test|run)\b",
    r"\bcargo\s+test\b",
    r"\bgo\s+test\b",
    r"\blint\b",
    r"\bcheck\b",
    r"\bverify\b",
    r"\baudit\b",
    r"\bcurl\b",
    r"\bpy_compile\b",
    r"\bpython3?\s+.*\.py\b",
    r"\bbash\s+.*\.sh\b",
    r"\.sh(?:\s|$)",
    r"\bgrep\b.*PASS",
    r"\bgrep\b.*(?:FAIL|ok)",
    r"\bbuild\b",
    r"\bexpect-cli\b",
    r"\bweb-qa-tester\b",
]

BYPASS_KEYWORDS = [
    "검증 없이 판단",
    "검증 없이",
    "LGTM",
    "tests skipped",
    "no verification",
    "구현만",
    "증거 없음 명시",
]

def resolve_transcript_path(stdin_json: dict) -> pathlib.Path | None:
    # Priority: explicit transcript_path → env var → session_id resolution
    tp = stdin_json.get("transcript_path")
    if tp and pathlib.Path(tp).exists():
        return pathlib.Path(tp)

    env_tp = os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    if env_tp and pathlib.Path(env_tp).exists():
        return pathlib.Path(env_tp)

    sid = stdin_json.get("session_id") or os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        # Scan ~/.claude/projects/*/<session_id>.jsonl
        for f in (HOME / ".claude" / "projects").glob(f"*/{sid}.jsonl"):
            return f
    return None


def find_last_user_idx(lines: list[str]) -> int:
    """Return the index of the most recent *real* user message (not tool_result)."""
    for i in range(len(lines) - 1, -1, -1):
        try:
            d = json.loads(lines[i])
        except Exception:
            continue
        if d.get("type") != "user":
            continue
        msg = d.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return i
        if isinstance(content, list):
            if any(c.get("type") != "tool_result" for c in content):
                return i
    return -1


def collect_turn(lines: list[str], start_idx: int) -> tuple[str, list[str]]:
    """Collect claim-text + Bash commands from lines after ``start_idx``.

    Claim-text aggregates:
      - assistant ``content[].text`` blocks (classic prose)
      - assistant ``content[].tool_use.input.text`` (MCP reply tools like
        discord/slack — where user-facing claims actually land in a tool-
        centric workflow)

    Bash commands capture assistant ``content[].tool_use.name == "Bash"``
    ``input.command`` values, used for verification evidence.
    """
    texts: list[str] = []
    bash_cmds: list[str] = []
    for line in lines[start_idx + 1 :]:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("type") != "assistant":
            continue
        msg = d.get("message") or {}
        for c in msg.get("content") or []:
            ct = c.get("type")
            if ct == "text":
                texts.append(c.get("text") or "")
            elif ct == "tool_use":
                name = c.get("name", "")
                inp = c.get("input") or {}
                if name == "Bash":
                    bash_cmds.append(inp.get("command") or "")
                # Scan `input.text` on any tool — most MCP reply-style tools
                # carry their user-visible string in a `text` field. Bash uses
                # `command` and Write uses `content`, so they don't collide.
                maybe_text = inp.get("text")
                if isinstance(maybe_text, str) and maybe_text:
                    texts.append(maybe_text)
    return "\n".join(texts), bash_cmds


def has_any(patterns: list[str], haystack: str, flags: int = re.IGNORECASE) -> list[str]:
    hits = []
    for p in patterns:
        if re.search(p, haystack, flags):
            hits.append(p)
    return hits


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}

    transcript = resolve_transcript_path(payload)
    if transcript is None:
        return 0  # can't inspect, fail-open

    try:
        lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return 0

    last_user = find_last_user_idx(lines)
    if last_user < 0:
        return 0
    text, bash_cmds = collect_turn(lines, last_user)
    if not text:
        return 0

    # Bypass if explicit
    if any(kw in text for kw in BYPASS_KEYWORDS):
        return 0

    claim_hits = has_any(CLAIM_PATTERNS, text)
    if not claim_hits:
        return 0

    verification_hits: list[str] = []
    for cmd in bash_cmds:
        hits = has_any(VERIFICATION_CMD_PATTERNS, cmd)
        if hits:
            verification_hits.extend(hits)

    if verification_hits:
        return 0  # claim accompanied by at least one verification command

    # Log the event
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "session_id": payload.get("session_id"),
        "transcript": str(transcript),
        "claim_patterns_matched": claim_hits,
        "bash_cmd_count": len(bash_cmds),
        "sample_text": text[-500:],
    }
    with (LOG_DIR / "claim-done.jsonl").open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    msg = (
        "⚠️  claim-done-gate: verification-flavored claim detected without a "
        "verifying Bash command in this turn.\n"
        f"   claims  : {claim_hits}\n"
        f"   bash_cmds: {len(bash_cmds)} (none matched verification patterns)\n"
        "   If this is real verification, run a test/build/audit command or use a "
        "bypass keyword like 'LGTM' or '검증 없이 판단'.\n"
        f"   Logged to {LOG_DIR}/claim-done.jsonl\n"
    )
    sys.stderr.write(msg)

    if BLOCK_MODE:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

# --- debug stub: unconditional invocation breadcrumb (temporary) ---
