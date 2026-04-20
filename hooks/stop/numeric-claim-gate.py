#!/usr/bin/env python3
"""numeric-claim-gate — catches unqualified "absolute" / "perfect" claims.

Stop hook. Complementary to claim-done-gate (which is test-result-specific).
This one catches broader unsupported absolutism — "완벽하게", "production-
ready", "모든 엣지 케이스", "fully tested", "남은 문제 없음" — when the
turn shows no tangible action (no Bash, fewer than 2 Edit/Write).

Mode: WARN-ONLY by default. Set COMAD_NUMERIC_CLAIM_BLOCK=1 to exit 2.

Bypass keywords in turn text:
    "LGTM", "검증 없이 판단", "스펙 불명", "best effort", "tentatively"
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
BLOCK_MODE = os.environ.get("COMAD_NUMERIC_CLAIM_BLOCK", "") == "1"

CLAIM_PATTERNS = [
    r"완벽하게\s*(?:처리|구현|동작|작동|완료|해결)",
    r"완벽히\s*(?:처리|구현|동작|작동|완료|해결)",
    r"\bperfectly\s+(?:works?|implemented|handled|done)\b",
    r"production[-\s]?ready",
    r"프로덕션\s*(?:준비|레디|대응)\s*완료",
    r"모든\s*(?:엣지\s*케이스|edge\s*cases?|시나리오|side\s*cases?)\s*(?:처리|커버|대응)",
    r"\ball\s+edge\s+cases?\s+(?:covered|handled)",
    r"\bfully\s+(?:tested|covered|implemented|working|operational)",
    r"\d+\s*개.*\s*전부\s+(?:구현|처리|완료|해결|검증)",
    r"남은\s*(?:문제|버그|bug|이슈|issues?)\s*(?:없|zero|0건)",
    r"\bno\s+known\s+(?:bugs?|issues?|problems?)\b",
    r"everything\s+(?:works|is\s+working|is\s+(?:done|complete))",
    r"완벽한\s*(?:구현|동작|해결)",
    r"\b100\s*%\s*(?:working|perfect|complete|correct)\b",
    r"전수\s*(?:조사|확인)\s*완료",
]

BYPASS_KEYWORDS = [
    "LGTM",
    "검증 없이 판단",
    "스펙 불명",
    "best effort",
    "tentatively",
    "추정",
    "근사치",
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


def collect_turn(lines: list[str], start_idx: int) -> tuple[str, int, int]:
    """Collect claim-text + tool invocation counts.

    Returns (claim_text, bash_cmd_count, edit_write_count).
    """
    texts: list[str] = []
    bash_ct = 0
    write_ct = 0
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
                    bash_ct += 1
                elif name in ("Write", "Edit", "NotebookEdit"):
                    write_ct += 1
                maybe = inp.get("text")
                if isinstance(maybe, str) and maybe:
                    texts.append(maybe)
    return "\n".join(texts), bash_ct, write_ct


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
    text, bash_ct, write_ct = collect_turn(lines, last_user)
    if not text:
        return 0
    if any(kw in text for kw in BYPASS_KEYWORDS):
        return 0

    claim_hits = hits(CLAIM_PATTERNS, text)
    if not claim_hits:
        return 0

    # Evidence threshold: any Bash OR >=2 Edit/Write
    has_evidence = bash_ct >= 1 or write_ct >= 2
    if has_evidence:
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "numeric-claim.jsonl").open("a") as f:
        f.write(
            json.dumps(
                {
                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "session_id": payload.get("session_id"),
                    "transcript": str(transcript),
                    "claims": claim_hits,
                    "bash_ct": bash_ct,
                    "write_ct": write_ct,
                    "sample_text": text[-500:],
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    sys.stderr.write(
        "⚠️  numeric-claim-gate: absolute/perfect claim with no tangible action.\n"
        f"   claims : {claim_hits}\n"
        f"   bash={bash_ct}, edit/write={write_ct} — evidence threshold missed "
        "(need ≥1 Bash or ≥2 Edit/Write).\n"
        "   If the turn was purely review/discussion, add a bypass keyword "
        "('LGTM', '검증 없이 판단', '근사치') or soften the claim.\n"
        f"   Logged to {LOG_DIR}/numeric-claim.jsonl\n"
    )
    return 2 if BLOCK_MODE else 0


if __name__ == "__main__":
    sys.exit(main())
