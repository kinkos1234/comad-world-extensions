#!/usr/bin/env python3
"""usage-gate refresher — aggregates Claude Code session transcripts into
5h/7d token usage percentages.

Usage:
    python3 refresh.py                        # update state file
    python3 refresh.py --plan=max             # tier: free | pro | max | max20x
    python3 refresh.py --plan-5h=500000 --plan-7d=5000000
    python3 refresh.py --dry-run              # print, don't write

Data source: ~/.claude/projects/*/*.jsonl   (per-session transcript streams)
             each assistant message has `.message.usage` with input_tokens,
             cache_creation_input_tokens, cache_read_input_tokens, output_tokens
Target:      ~/.claude/.comad/usage-gate.json

Plan limits are estimates — Anthropic does not publish OAuth quota
ceilings. Pin after observing an actual quota hit.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import sys

HOME = pathlib.Path(os.environ["HOME"])
TRANSCRIPTS_ROOT = HOME / ".claude" / "projects"
STATE_FILE = HOME / ".claude" / ".comad" / "usage-gate.json"

PLANS = {
    "free":   {"_5h":    200_000, "_7d":   1_500_000},
    "pro":    {"_5h":  1_000_000, "_7d":   8_000_000},
    "max":    {"_5h":  5_000_000, "_7d":  40_000_000},
    "max20x": {"_5h": 20_000_000, "_7d": 160_000_000},
}
DEFAULT_PLAN = "max"

# Token-accounting mode:
#   "billed"    = input_tokens + output_tokens + cache_creation_input_tokens
#                 Excludes cache_read — already-cached reads are billed at 10%
#                 and don't press against the same quota envelope.
#   "all"       = superset including cache_read (paranoid overcount)
DEFAULT_ACCOUNTING = "billed"


def parse_args(argv: list[str]) -> dict:
    opts = {"plan": DEFAULT_PLAN, "dry": False, "p5": None, "p7": None,
            "accounting": DEFAULT_ACCOUNTING}
    for tok in argv[1:]:
        if tok == "--dry-run":
            opts["dry"] = True
        elif tok.startswith("--plan="):
            opts["plan"] = tok.split("=", 1)[1]
        elif tok.startswith("--plan-5h="):
            opts["p5"] = int(tok.split("=", 1)[1])
        elif tok.startswith("--plan-7d="):
            opts["p7"] = int(tok.split("=", 1)[1])
        elif tok.startswith("--accounting="):
            opts["accounting"] = tok.split("=", 1)[1]
    return opts


def token_cost(usage: dict, accounting: str) -> int:
    inp = int(usage.get("input_tokens", 0) or 0)
    out = int(usage.get("output_tokens", 0) or 0)
    cc = int(usage.get("cache_creation_input_tokens", 0) or 0)
    cr = int(usage.get("cache_read_input_tokens", 0) or 0)
    if accounting == "all":
        return inp + out + cc + cr
    # default: billed (excludes cache_read)
    return inp + out + cc


def parse_ts(val: str | None) -> datetime.datetime | None:
    if not val:
        return None
    try:
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"
        dt = datetime.datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        return None


def iter_usage_events(accounting: str) -> list[tuple[datetime.datetime, int]]:
    """Walk all transcript JSONL files, yield (ts, token_count) per assistant
    message with usage metadata. Token count depends on ``accounting``."""
    out: list[tuple[datetime.datetime, int]] = []
    if not TRANSCRIPTS_ROOT.exists():
        return out
    for f in TRANSCRIPTS_ROOT.glob("*/*.jsonl"):
        try:
            with f.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    ts = parse_ts(d.get("timestamp"))
                    if ts is None:
                        continue
                    msg = d.get("message") or {}
                    u = msg.get("usage") or {}
                    if not u:
                        continue
                    tokens = token_cost(u, accounting)
                    if tokens > 0:
                        out.append((ts, tokens))
        except Exception:
            continue
    return out


def main() -> int:
    opts = parse_args(sys.argv)
    now = datetime.datetime.now(datetime.timezone.utc)
    five_ago = now - datetime.timedelta(hours=5)
    seven_ago = now - datetime.timedelta(days=7)

    p5 = opts["p5"] or PLANS.get(opts["plan"], PLANS[DEFAULT_PLAN])["_5h"]
    p7 = opts["p7"] or PLANS.get(opts["plan"], PLANS[DEFAULT_PLAN])["_7d"]

    events = iter_usage_events(opts["accounting"])
    total_5h = sum(tokens for ts, tokens in events if ts >= five_ago)
    total_7d = sum(tokens for ts, tokens in events if ts >= seven_ago)

    pct5h = min(round(total_5h / p5 * 100, 1), 100.0) if p5 else 0.0
    pct7d = min(round(total_7d / p7 * 100, 1), 100.0) if p7 else 0.0

    payload = {
        "ts": now.isoformat(timespec="seconds"),
        "plan": opts["plan"],
        "plan_5h_limit": p5,
        "plan_7d_limit": p7,
        "total_5h_tokens": total_5h,
        "total_7d_tokens": total_7d,
        "current_5h_pct": pct5h,
        "current_7d_pct": pct7d,
        "events_counted": len(events),
        "accounting": opts["accounting"],
    }

    if opts["dry"]:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if not STATE_FILE.exists():
        print(f"error: {STATE_FILE} not found — usage-gate not installed?", file=sys.stderr)
        return 1

    state = json.loads(STATE_FILE.read_text())
    state["current_5h_pct"] = pct5h
    state["current_7d_pct"] = pct7d
    state["last_check"] = now.isoformat(timespec="seconds")
    state["_last_refresh_meta"] = {
        "plan": opts["plan"],
        "plan_5h_limit": p5,
        "plan_7d_limit": p7,
        "total_5h_tokens": total_5h,
        "total_7d_tokens": total_7d,
        "events_counted": len(events),
    }
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")

    print(
        f"usage-gate refreshed: 5h={pct5h}% ({total_5h:,} tok of {p5:,}) "
        f"7d={pct7d}% ({total_7d:,} tok of {p7:,}) plan={opts['plan']} "
        f"events={len(events)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
