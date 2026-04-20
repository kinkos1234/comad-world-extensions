#!/usr/bin/env python3
"""Pre-validator for T6 pending commits.

Reads ~/.claude/.comad/pending/*.json produced by t6-capture.sh and verifies
that each file has the minimum information /comad-learn needs to reason about
the commit. Files that fail schema are moved to pending/_invalid/ so they
don't poison the LLM analysis step.

Usage:
    validate-pending.py                # check all pending
    validate-pending.py --quiet        # only print failures
    validate-pending.py --move-invalid # move bad files to _invalid/
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys

HOME = pathlib.Path(os.environ["HOME"])
PENDING = HOME / ".claude" / ".comad" / "pending"
INVALID = PENDING / "_invalid"

REQUIRED_KEYS = ["ts", "commit", "subject", "diff_head", "repo", "status", "kind"]
KIND_ENUM = {"fix", "feat"}


def validate(path: pathlib.Path) -> tuple[bool, list[str]]:
    """Return (valid, issues)."""
    issues: list[str] = []

    # Skip non-pending files (marker, log lines, etc.)
    if path.name.startswith(".") or path.name.startswith("_"):
        return True, []
    if path.suffix != ".json":
        return True, []
    # Skip the destroy-gate jsonl logs that live next to pending
    if path.name == "destroy-gate.jsonl":
        return True, []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, [f"invalid JSON: {e}"]
    except Exception as e:
        return False, [f"read error: {e}"]

    if not isinstance(data, dict):
        return False, ["top-level not an object"]

    for key in REQUIRED_KEYS:
        if key not in data:
            issues.append(f"missing key: {key}")
        elif not isinstance(data[key], str):
            issues.append(f"key {key} not a string")

    if data.get("kind") not in KIND_ENUM:
        issues.append(f"kind '{data.get('kind')}' not in {sorted(KIND_ENUM)}")

    subject = data.get("subject", "")
    if subject and not any(
        subject.lower().startswith(p) for p in ("fix", "feat", "bugfix")
    ):
        issues.append("subject doesn't start with fix:/feat:/bugfix:")

    diff_head = data.get("diff_head", "")
    if len(diff_head) < 20:
        issues.append("diff_head too short (<20 chars) — capture may be incomplete")

    return not issues, issues


def main() -> int:
    quiet = "--quiet" in sys.argv
    move = "--move-invalid" in sys.argv

    if not PENDING.exists():
        if not quiet:
            print(f"no pending dir at {PENDING}", file=sys.stderr)
        return 0

    ok = 0
    bad = 0
    for path in sorted(PENDING.glob("*.json")):
        valid, issues = validate(path)
        if valid:
            ok += 1
            continue
        bad += 1
        print(f"INVALID {path.name}:")
        for issue in issues:
            print(f"  - {issue}")
        if move:
            INVALID.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(INVALID / path.name))
            print(f"  → moved to _invalid/")

    if not quiet:
        print(f"\nvalidate-pending: {ok} ok, {bad} invalid")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
