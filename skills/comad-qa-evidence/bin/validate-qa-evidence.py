#!/usr/bin/env python3
"""validate-qa-evidence — strict schema + cross-check validator.

Usage:
    validate-qa-evidence.py [path]

If path omitted, looks for .qa-evidence.json under git root (or CWD).

Exit codes:
    0 — valid AND verdict==PASS
    1 — valid but verdict != PASS (PENDING/PARTIAL/FAIL)
    2 — schema or cross-check violation
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REQUIRED_TOP = ["schema_version", "generated_at", "project_root", "git_head",
                "scope", "verdict", "checks"]
ALLOWED_VERDICTS = {"PASS", "FAIL", "PARTIAL", "PENDING"}
# N/A — level not applicable to this project type (e.g., L1/L4 on a CLI-only
# tool). Treated as pass-equivalent for verdict consistency.
ALLOWED_CHECK_STATUSES = {"PASS", "FAIL", "SKIP", "N/A"}

# L0~L5 QA levels (Tier 3 extension). Reserved prefixes; check names starting
# with these imply the semantic below. Having them is optional — projects opt
# in per level.
QA_LEVELS = {
    "L0_api_contract":    "DTO/schema field mapping",
    "L1_ui_render":       "UI rendering (browser)",
    "L2_api_call":        "HTTP 200 + CORS",
    "L3_crud_roundtrip":  "Write → Read → Compare",
    "L4_console_errors":  "Browser console.error == 0",
    "L5_field_mapping":   "Frontend type ↔ backend field parity",
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


def validate(data: dict, path: pathlib.Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). errors means schema/cross-check violation (exit 2)."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        errors.append("top-level value is not an object")
        return errors, warnings

    for k in REQUIRED_TOP:
        if k not in data:
            errors.append(f"missing required field: {k}")

    # Types
    if "schema_version" in data and not isinstance(data["schema_version"], str):
        errors.append("schema_version must be a string")
    if "scope" in data:
        if not isinstance(data["scope"], str):
            errors.append("scope must be a string")
        elif not data["scope"].strip():
            errors.append("scope must not be empty")
    if "verdict" in data:
        if data["verdict"] not in ALLOWED_VERDICTS:
            errors.append(f"verdict must be one of {sorted(ALLOWED_VERDICTS)} (got {data['verdict']!r})")

    checks = data.get("checks")
    if not isinstance(checks, dict):
        errors.append("checks must be an object")
        checks = {}
    elif not checks:
        errors.append("checks must not be empty")

    # Per-check validation
    for name, ck in checks.items():
        if not isinstance(ck, dict):
            errors.append(f"checks.{name} must be an object")
            continue
        status = ck.get("status")
        if status not in ALLOWED_CHECK_STATUSES:
            errors.append(f"checks.{name}.status must be PASS|FAIL|SKIP (got {status!r})")

        if name == "browser_qa" or name == "L1_ui_render" or name == "L4_console_errors":
            if status == "PASS":
                if ck.get("console_errors", 0) not in (0, None):
                    try:
                        if int(ck.get("console_errors", 0)) != 0:
                            errors.append(f"checks.{name}.status=PASS requires console_errors=0")
                    except Exception:
                        errors.append(f"checks.{name}.console_errors must be int")
                if not ck.get("tool"):
                    warnings.append(f"checks.{name}.tool not specified")
                if name in ("browser_qa", "L1_ui_render") and (
                    not isinstance(ck.get("viewports"), list) or not ck.get("viewports")
                ):
                    warnings.append(f"checks.{name}.viewports missing or empty")

        # L* prefix consistency — if the key starts with L<digit>_ ensure it
        # maps to a known reserved name (warn only).
        import re as _re
        if _re.match(r"^L\d+_", name) and name not in QA_LEVELS:
            warnings.append(
                f"checks.{name}: L-prefix used but name not in reserved "
                f"set {sorted(QA_LEVELS.keys())}"
            )

        # tests-like shape sanity
        if "passed" in ck or "failed" in ck or "total" in ck:
            p = ck.get("passed", 0) or 0
            f = ck.get("failed", 0) or 0
            t = ck.get("total", None)
            if t is not None and p + f != t:
                errors.append(f"checks.{name}: passed({p})+failed({f}) != total({t})")

    # verdict ↔ checks consistency. N/A is pass-equivalent (level doesn't apply
    # to this project type); only FAIL blocks a PASS verdict.
    verdict = data.get("verdict")
    if verdict == "PASS":
        fail_checks = [n for n, ck in checks.items()
                       if isinstance(ck, dict) and ck.get("status") == "FAIL"]
        if fail_checks:
            errors.append(
                f"verdict=PASS but checks have FAIL status: {fail_checks}"
            )

    # inventory coverage
    inv = data.get("inventory") or {}
    if isinstance(inv, dict):
        seen_bases: set[str] = set()
        for k in inv:
            if k.endswith("_total"):
                seen_bases.add(k[:-6])
            elif k.endswith("_verified"):
                seen_bases.add(k[:-9])
        for base in seen_bases:
            total = inv.get(f"{base}_total")
            verified = inv.get(f"{base}_verified")
            if total is None or verified is None:
                warnings.append(f"inventory.{base}: missing _total or _verified pair")
                continue
            try:
                t = int(total); v = int(verified)
            except Exception:
                errors.append(f"inventory.{base}: _total/_verified must be ints")
                continue
            if v > t:
                errors.append(f"inventory.{base}: verified({v}) > total({t})")
            if verdict == "PASS" and v < t:
                errors.append(f"inventory.{base}: verdict=PASS but coverage {v}/{t} incomplete")

    # git_head sanity
    head = data.get("git_head")
    if head:
        try:
            out = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(path.parent), capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0 and out.stdout.strip():
                current = out.stdout.strip()
                if not current.startswith(head) and not head.startswith(current):
                    warnings.append(f"git_head={head} but current HEAD={current} (evidence may be stale)")
        except Exception:
            pass

    return errors, warnings


def main() -> int:
    if len(sys.argv) > 2:
        print("usage: validate-qa-evidence.py [path]", file=sys.stderr)
        return 2

    if len(sys.argv) == 2:
        path = pathlib.Path(sys.argv[1])
    else:
        root = git_root(pathlib.Path.cwd())
        path = root / ".qa-evidence.json"

    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 2

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"error: cannot parse JSON: {e}", file=sys.stderr)
        return 2

    errors, warnings = validate(data, path)

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")

    if errors:
        print(f"\nvalidate-qa-evidence: {len(errors)} error(s), {len(warnings)} warning(s) — FAIL")
        return 2

    verdict = data.get("verdict")
    if verdict == "PASS":
        print(f"\nvalidate-qa-evidence: schema OK, verdict=PASS — {len(warnings)} warning(s)")
        return 0
    print(f"\nvalidate-qa-evidence: schema OK, verdict={verdict} (not yet PASS)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
