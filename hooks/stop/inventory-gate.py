#!/usr/bin/env python3
"""inventory-gate — coverage-claim cross-check against .qa-evidence.json.

Stop hook. When the current assistant turn contains a "full coverage"
style claim ("7/7 처리", "N개 전부 구현", "전수 검증 완료"), look for the
git-root `.qa-evidence.json`. If its `inventory` field has any
`*_verified < *_total` bucket, warn — the coverage claim doesn't match
ground truth.

Opt-in: fires only when `.qa-evidence.json` exists AND has non-empty
`inventory`. Absent file / empty inventory / fully-covered inventory → allow.

Distinct from:
- claim-done-gate (#2): test verification claims ("92/92 PASS")
- numeric-claim-gate (#6): absolute "완벽", "production-ready" claims
- qa-gate-before-push (#4): hard gate on `git push` itself

Mode: WARN-ONLY. Set COMAD_INVENTORY_BLOCK=1 for exit 2.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import subprocess
import sys

HOME = pathlib.Path(os.environ.get("HOME", "/"))
LOG_DIR = HOME / ".claude" / ".comad" / "pending"
BLOCK_MODE = os.environ.get("COMAD_INVENTORY_BLOCK", "") == "1"

# Coverage claim patterns. Intentionally avoid matching test-result claims
# (those are claim-done-gate's turf) via a trailing negative lookahead for
# PASS/passed/통과 on the N/N form.
COVERAGE_PATTERNS = [
    r"\b\d+\s*/\s*\d+\b(?!\s+(?:PASS|passed|통과|FAIL|failed))",
    r"\d+\s*개.*\s*(?:모두|전부)\s*(?:구현|처리|완료|검증|커버)",
    r"전수\s*(?:검증|조사|확인|테스트)\s*(?:완료|통과)",
    r"모든\s+\w+\s*(?:검증|처리|커버|구현)",
    r"\ball\s+(?:endpoints?|entities|items?|cases?)\s+(?:covered|verified|implemented)",
]

BYPASS_KEYWORDS = [
    "LGTM",
    "검증 없이 판단",
    "스펙 불명",
    "부분 커버 명시",
    "partial coverage",
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


def collect_turn(lines: list[str], start_idx: int) -> tuple[str, str]:
    """Return (claim_text, cwd_hint). cwd_hint = latest `cwd` field seen on
    any assistant entry in the turn (Claude Code writes this). Fallback: """
    texts: list[str] = []
    cwd = ""
    for line in lines[start_idx + 1 :]:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("type") != "assistant":
            continue
        if isinstance(d.get("cwd"), str):
            cwd = d["cwd"]
        msg = d.get("message") or {}
        for c in msg.get("content") or []:
            ct = c.get("type")
            if ct == "text":
                texts.append(c.get("text") or "")
            elif ct == "tool_use":
                inp = c.get("input") or {}
                t = inp.get("text")
                if isinstance(t, str) and t:
                    texts.append(t)
    return "\n".join(texts), cwd


def git_root(start: pathlib.Path) -> pathlib.Path | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start), capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return pathlib.Path(out.stdout.strip())
    except Exception:
        pass
    return None


def analyze_inventory(inv: dict) -> list[tuple[str, int, int]]:
    """Return list of (bucket_name, total, verified) for each paired entry.
    Filters out pairs where either side is missing or non-integer."""
    bases: dict[str, dict] = {}
    for key, val in inv.items():
        if key.endswith("_total"):
            bases.setdefault(key[:-6], {})["total"] = val
        elif key.endswith("_verified"):
            bases.setdefault(key[:-9], {})["verified"] = val
    out: list[tuple[str, int, int]] = []
    for base, pair in bases.items():
        try:
            t = int(pair.get("total"))
            v = int(pair.get("verified"))
            out.append((base, t, v))
        except Exception:
            continue
    return out


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
    text, cwd_hint = collect_turn(lines, last_user)
    if not text:
        return 0
    if any(kw in text for kw in BYPASS_KEYWORDS):
        return 0

    # Coverage claim?
    hits = [p for p in COVERAGE_PATTERNS if re.search(p, text, re.IGNORECASE)]
    if not hits:
        return 0

    # Resolve cwd
    start = pathlib.Path(cwd_hint) if cwd_hint and pathlib.Path(cwd_hint).exists() else pathlib.Path.cwd()
    root = git_root(start)
    if root is None:
        return 0  # not in a git repo — can't cross-check

    evidence = root / ".qa-evidence.json"
    if not evidence.exists():
        return 0  # opt-in: this repo doesn't use qa-evidence

    try:
        data = json.loads(evidence.read_text(encoding="utf-8"))
    except Exception:
        return 0  # malformed evidence — qa-gate-before-push will handle

    inv = data.get("inventory") or {}
    buckets = analyze_inventory(inv)
    if not buckets:
        return 0  # no inventory to compare against

    incomplete = [(b, t, v) for b, t, v in buckets if v < t]
    if not incomplete:
        return 0  # all buckets fully covered — claim is consistent

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "inventory-gate.jsonl").open("a") as f:
        f.write(
            json.dumps(
                {
                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "session_id": payload.get("session_id"),
                    "transcript": str(transcript),
                    "evidence_file": str(evidence),
                    "claim_patterns": hits,
                    "incomplete_buckets": [
                        {"bucket": b, "total": t, "verified": v}
                        for b, t, v in incomplete
                    ],
                    "sample_text": text[-500:],
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    lines_msg = "\n".join(f"   - {b}: verified {v}/{t}" for b, t, v in incomplete)
    sys.stderr.write(
        "⚠️  inventory-gate: coverage claim vs .qa-evidence.json inventory mismatch.\n"
        f"   Claim pattern hits: {hits}\n"
        f"   Evidence file : {evidence}\n"
        "   Incomplete buckets:\n"
        f"{lines_msg}\n"
        "   Either finish verifying each bucket (set *_verified == *_total) "
        "or soften the claim / add 'partial coverage' / 'LGTM' bypass keyword.\n"
        f"   Logged to {LOG_DIR}/inventory-gate.jsonl\n"
    )
    return 2 if BLOCK_MODE else 0


if __name__ == "__main__":
    sys.exit(main())
