#!/usr/bin/env python3
"""decisions — escalation channel for autonomous processes (R3).

Philosophy: autonomous work (loopy-era, nightly-audit, evolve) does the work and
self-verifies; it surfaces to the human ONLY items that need judgment — a
*decision*, not raw output or routine logs. Those land in a queue:

    ~/.claude/.comad/decisions/<utc>-<slug>.json      (pending)
    ~/.claude/.comad/decisions/_resolved/...          (after resolve)

Surfaced at SessionStart (count + titles). FAIL-OPEN for library callers.

CLI:
    decisions.py add --source S --title T [--detail D] [--urgency low|normal|high]
                     [--option O]...            (repeatable)
    decisions.py list [--json]
    decisions.py count
    decisions.py resolve <id> [--note N]

Library:
    record_decision(source, title, detail="", options=None, urgency="normal") -> str|None
    pending() -> list[dict]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys

HOME = pathlib.Path(os.environ.get("HOME", "/"))
DECISIONS_DIR = HOME / ".claude" / ".comad" / "decisions"
RESOLVED_DIR = DECISIONS_DIR / "_resolved"
URGENCY = {"low", "normal", "high"}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:40] or "decision")


def record_decision(source: str, title: str, detail: str = "",
                    options=None, urgency: str = "normal") -> str | None:
    """Append a decision to the queue. Returns the decision id, or None on error.
    De-dupes on (source, title): an identical pending decision is not re-added."""
    try:
        DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
        if urgency not in URGENCY:
            urgency = "normal"
        # de-dup: same source+title already pending?
        sig = hashlib.sha1(f"{source}\x00{title}".encode()).hexdigest()[:10]
        for f in DECISIONS_DIR.glob("*.json"):
            try:
                if json.loads(f.read_text()).get("sig") == sig:
                    return f.stem  # already queued
            except Exception:
                continue
        now = datetime.datetime.now(datetime.timezone.utc)
        did = f"{now.strftime('%Y%m%dT%H%M%S')}-{_slug(title)}"
        rec = {
            "id": did,
            "sig": sig,
            "source": source,
            "title": title,
            "detail": detail,
            "options": list(options or []),
            "urgency": urgency,
            "created_at": now.isoformat(timespec="seconds"),
        }
        (DECISIONS_DIR / f"{did}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2))
        return did
    except Exception:
        return None


def pending() -> list[dict]:
    out: list[dict] = []
    try:
        for f in sorted(DECISIONS_DIR.glob("*.json")):
            try:
                out.append(json.loads(f.read_text()))
            except Exception:
                continue
    except Exception:
        pass
    # high urgency first, then oldest first
    rank = {"high": 0, "normal": 1, "low": 2}
    out.sort(key=lambda d: (rank.get(d.get("urgency"), 1), d.get("created_at", "")))
    return out


def resolve(did: str, note: str = "") -> bool:
    try:
        src = DECISIONS_DIR / f"{did}.json"
        if not src.exists():
            # allow id without .json or partial match
            matches = list(DECISIONS_DIR.glob(f"{did}*.json"))
            if not matches:
                return False
            src = matches[0]
        RESOLVED_DIR.mkdir(parents=True, exist_ok=True)
        rec = json.loads(src.read_text())
        rec["resolved_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        rec["resolution_note"] = note
        (RESOLVED_DIR / src.name).write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        src.unlink()
        return True
    except Exception:
        return False


def _cli() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--source", required=True)
    a.add_argument("--title", required=True)
    a.add_argument("--detail", default="")
    a.add_argument("--urgency", default="normal", choices=sorted(URGENCY))
    a.add_argument("--option", action="append", default=[], dest="options")
    sub.add_parser("count")
    li = sub.add_parser("list")
    li.add_argument("--json", action="store_true")
    r = sub.add_parser("resolve")
    r.add_argument("id")
    r.add_argument("--note", default="")
    args = ap.parse_args()

    if args.cmd == "add":
        did = record_decision(args.source, args.title, args.detail, args.options, args.urgency)
        print(did or "(error)")
        return 0 if did else 1
    if args.cmd == "count":
        print(len(pending()))
        return 0
    if args.cmd == "list":
        items = pending()
        if args.json:
            print(json.dumps(items, ensure_ascii=False, indent=2))
        else:
            for d in items:
                mark = {"high": "🔴", "normal": "🟡", "low": "⚪"}.get(d.get("urgency"), "🟡")
                print(f"{mark} [{d.get('source')}] {d.get('title')}  ({d.get('id')})")
        return 0
    if args.cmd == "resolve":
        ok = resolve(args.id, args.note)
        print("resolved" if ok else "not found")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
