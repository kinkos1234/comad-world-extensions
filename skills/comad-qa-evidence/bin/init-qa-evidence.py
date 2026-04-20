#!/usr/bin/env python3
"""init-qa-evidence — generate a template .qa-evidence.json in CWD.

Usage:
    init-qa-evidence.py [--scope "description"] [--force] [--path PATH]

Auto-fills: generated_at, project_root, git_head. Leaves checks={} and
verdict=PENDING for Claude to populate.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys


def git_root(start: pathlib.Path) -> pathlib.Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start), capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return pathlib.Path(out.stdout.strip())
    except Exception:
        pass
    return start


def git_head(root: pathlib.Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return ""


def build_template(root: pathlib.Path, scope: str) -> dict:
    return {
        "schema_version": "1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "project_root": str(root),
        "git_head": git_head(root),
        "scope": scope or "",
        "verdict": "PENDING",
        "checks": {},
        "inventory": {},
        "artifacts": [],
        "notes": "",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate .qa-evidence.json template")
    ap.add_argument("--scope", default="")
    ap.add_argument("--force", action="store_true", help="overwrite existing file")
    ap.add_argument("--path", default=None, help="write to this path instead of <git_root>/.qa-evidence.json")
    args = ap.parse_args()

    cwd = pathlib.Path.cwd()
    root = git_root(cwd)
    target = pathlib.Path(args.path) if args.path else (root / ".qa-evidence.json")

    if target.exists() and not args.force:
        print(f"error: {target} already exists (use --force to overwrite)", file=sys.stderr)
        return 1

    data = build_template(root, args.scope)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {target}")
    print(f"  project_root={data['project_root']} git_head={data['git_head'] or '(no git)'}")
    print("  verdict=PENDING — populate checks{} then set verdict=PASS and run validate-qa-evidence.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
