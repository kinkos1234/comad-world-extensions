#!/usr/bin/env python3
"""premature-completion-detector — catches early "converged / loop done" claims.

Stop hook, sibling to claim-done-gate. Scans the current assistant turn for
loop-completion language ("수렴 달성", "converged", "iteration complete") and
warns if no measurement command ran in the same turn to justify it.

Mode: WARN-ONLY by default. Set COMAD_PREMATURE_BLOCK=1 to exit 2.

Bypass keywords in turn text (all skipped):
    "조기 종료 의도", "manual stop", "user requested stop", "수렴 전 종료"
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
BLOCK_MODE = os.environ.get("COMAD_PREMATURE_BLOCK", "") == "1"

CONVERGENCE_PATTERNS = [
    r"수렴\s*(?:달성|완료|성공|된|됨|했|확인)",
    r"(?:loop|iteration|라운드|반복)\s*(?:종료|완료|수렴|성공)",
    r"(?:converged|convergence\s+reached|loop\s+complete)",
    r"모든\s*조건\s*만족",
    r"이번\s*라운드에서\s*완료",
    r"최종\s*(?:수렴|convergence)",
    r"stable\s+state\s+reached",
    r"더\s*이상\s*개선(?:\s*여지)?\s*없",
]

# Evidence: commands that would actually measure "are we converged?"
MEASUREMENT_CMD_PATTERNS = [
    r"\btest\b",
    r"\bpytest\b",
    r"\bharness-report\b",
    r"\bscore\b",
    r"\bbench(?:mark)?\b",
    r"\bmeasure\b",
    r"\bdiff\b",
    r"\bgit\s+log\b",
    r"\bgit\s+diff\b",
    r"\bgrep\b.*(?:pass|fail|score|ok|metric)",
    r"\bwc\b",
    r"\bpython3?\s+.*\.py\b",
    r"\bbash\s+.*\.sh\b",
    r"\.sh(?:\s|$)",
    r"\bcurl\b",
    r"\bnpm\s+(?:test|run)\b",
]

BYPASS_KEYWORDS = [
    "조기 종료 의도",
    "manual stop",
    "user requested stop",
    "수렴 전 종료",
]


def resolve_transcript_path(stdin_json: dict) -> pathlib.Path | None:
    tp = stdin_json.get("transcript_path")
    if tp and pathlib.Path(tp).exists():
        return pathlib.Path(tp)
    env_tp = os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    if env_tp and pathlib.Path(env_tp).exists():
        return pathlib.Path(env_tp)
    sid = stdin_json.get("session_id") or os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        for f in (HOME / ".claude" / "projects").glob(f"*/{sid}.jsonl"):
            return f
    return None


def find_last_user_idx(lines: list[str]) -> int:
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
    """See claim-done-gate.py::collect_turn — same scope (assistant text +
    MCP tool_use.input.text for user-visible claims)."""
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
                maybe_text = inp.get("text")
                if isinstance(maybe_text, str) and maybe_text:
                    texts.append(maybe_text)
    return "\n".join(texts), bash_cmds


def hits(patterns: list[str], text: str) -> list[str]:
    return [p for p in patterns if re.search(p, text, re.IGNORECASE)]


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}
    transcript = resolve_transcript_path(payload)
    if transcript is None:
        return 0
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
    if any(kw in text for kw in BYPASS_KEYWORDS):
        return 0

    claim_hits = hits(CONVERGENCE_PATTERNS, text)
    if not claim_hits:
        return 0

    measurement_hits: list[str] = []
    for cmd in bash_cmds:
        m = hits(MEASUREMENT_CMD_PATTERNS, cmd)
        if m:
            measurement_hits.extend(m)
    if measurement_hits:
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "premature-completion.jsonl").open("a") as f:
        f.write(
            json.dumps(
                {
                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "session_id": payload.get("session_id"),
                    "transcript": str(transcript),
                    "claims": claim_hits,
                    "bash_cmd_count": len(bash_cmds),
                    "sample_text": text[-500:],
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    sys.stderr.write(
        "⚠️  premature-completion-detector: convergence claim without measurement.\n"
        f"   claims : {claim_hits}\n"
        f"   bash_cmds: {len(bash_cmds)} (none matched measurement patterns)\n"
        "   If the loop truly converged, run a metric/test/diff command and re-state.\n"
        "   Bypass phrase: '조기 종료 의도' / 'manual stop'.\n"
        f"   Logged to {LOG_DIR}/premature-completion.jsonl\n"
    )
    return 2 if BLOCK_MODE else 0


if __name__ == "__main__":
    sys.exit(main())
