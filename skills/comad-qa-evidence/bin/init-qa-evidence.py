#!/usr/bin/env python3
"""init-qa-evidence — generate a template .qa-evidence.json in CWD.

Usage:
    init-qa-evidence.py [--scope "description"] [--profile {smoke,deep}]
                        [--force] [--path PATH]

Auto-fills: generated_at, project_root, git_head. Leaves checks={} (smoke)
or seeded with PENDING placeholders (deep) for Claude to populate.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import subprocess
import sys

PROFILES = ("smoke", "deep")

# Deep profile seed — placeholder PENDING entries to remind Claude what to
# populate. Claude must change status to PASS|FAIL|SKIP|N/A after running
# the actual check, and fill `details` with concrete evidence.
DEEP_SEED_CHECKS = {
    "build":              {"status": "PENDING", "command": "<runtime build command>"},
    "typecheck":          {"status": "PENDING", "command": "<typecheck command>"},
    "lint":               {"status": "PENDING", "command": "<lint command>"},
    "unit_tests":         {"status": "PENDING", "command": "<test command>", "passed": 0, "failed": 0, "total": 0},
    "integration_tests":  {"status": "PENDING", "command": "<integration command>"},
    "L1_ui_render":       {"status": "PENDING", "tool": "<playwright|cdp|manual>", "viewports": [], "console_errors": 0},
    "L2_api_call":        {"status": "PENDING", "command": "<curl ...>"},
    "L3_crud_roundtrip":  {"status": "PENDING"},
    "L4_console_errors":  {"status": "PENDING", "tool": "<browser>", "console_errors": 0},
    "audit.dependency_cve":         {"status": "PENDING", "command": "<npm audit | pip audit | ...>"},
    "audit.data_integrity":         {"status": "PENDING", "details": "<orphan/FK/referential check>"},
    "audit.injection_probe":        {"status": "PENDING", "details": "<NoSQL/SQL/XSS probes attempted>"},
    "audit.observability_verified": {"status": "PENDING", "details": "<actually triggered an event and saw it in dashboard>"},
    "audit.performance_baseline":   {"status": "PENDING", "details": "<latency p50/p95 or lighthouse score or bundle size>"},
    "audit.query_plan":             {"status": "PENDING", "details": "<DB explain showing index hit, not COLLSCAN>"},
    "second_opinion":               {"status": "PENDING", "verdict": "", "reviewer": "<adversarial-review workflow | codex challenge | comad-second-opinion>", "details": "<what was adversarially challenged; what survived>"},
}

DEEP_SEED_INVENTORY = {
    "routes_total": 0,
    "routes_verified": 0,
    "workers_total": 0,
    "workers_verified": 0,
    "server_actions_total": 0,
    "server_actions_verified": 0,
    "db_collections_total": 0,
    "db_collections_verified": 0,
}


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


def build_template(root: pathlib.Path, scope: str, profile: str) -> dict:
    base = {
        "schema_version": "2",
        "profile": profile,
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
    if profile == "deep":
        base["checks"] = dict(DEEP_SEED_CHECKS)
        base["inventory"] = dict(DEEP_SEED_INVENTORY)
        base["notes"] = (
            "[Deep profile seeded] Replace PENDING with PASS/FAIL/SKIP/N/A "
            "after each audit. Provide concrete evidence in `details` "
            "(numbers, command output, file paths). Inventory dimensions "
            "must reflect actual project surface — extend/replace as needed."
        )
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate .qa-evidence.json template")
    ap.add_argument("--scope", default="")
    ap.add_argument("--profile", choices=PROFILES, default="smoke")
    ap.add_argument("--force", action="store_true", help="overwrite existing file")
    ap.add_argument("--path", default=None,
                    help="write to this path instead of <git_root>/.qa-evidence.json")
    args = ap.parse_args()

    cwd = pathlib.Path.cwd()
    root = git_root(cwd)
    target = pathlib.Path(args.path) if args.path else (root / ".qa-evidence.json")

    if target.exists() and not args.force:
        print(f"error: {target} already exists (use --force to overwrite)", file=sys.stderr)
        return 1

    data = build_template(root, args.scope, args.profile)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {target}")
    print(f"  project_root={data['project_root']} git_head={data['git_head'] or '(no git)'}")
    print(f"  profile={args.profile}")
    if args.profile == "deep":
        print(f"  seeded {len(DEEP_SEED_CHECKS)} PENDING checks + "
              f"{len(DEEP_SEED_INVENTORY)//2} inventory dimensions")
    print("  verdict=PENDING — populate then set verdict=PASS and run validate-qa-evidence.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
