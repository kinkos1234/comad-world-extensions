#!/usr/bin/env python3
"""validate-qa-evidence — strict schema + cross-check + depth-profile validator.

Usage:
    validate-qa-evidence.py [path]

If path omitted, looks for .qa-evidence.json under git root (or CWD).

Exit codes:
    0 — valid AND verdict==PASS
    1 — valid but verdict != PASS (PENDING/PARTIAL/FAIL)
    2 — schema or cross-check violation (includes missing deep audits when
        depth profile is auto-detected or set to "deep")

DEPTH PROFILE
-------------
The validator infers a profile from `profile` field, scope/notes keywords,
or audit-key density. profile="deep" requires deeper evidence than smoke
testing — see DEEP_REQUIRED_AUDITS and the SKILL.md for the rationale.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

REQUIRED_TOP = ["schema_version", "generated_at", "project_root", "git_head",
                "scope", "verdict", "checks"]
ALLOWED_VERDICTS = {"PASS", "FAIL", "PARTIAL", "PENDING"}
ALLOWED_CHECK_STATUSES = {"PASS", "FAIL", "SKIP", "N/A"}
ALLOWED_PROFILES = {"smoke", "deep"}

# R2 — adversarial review (second_opinion) wiring.
# A substantial change should carry an adversarial review verdict. The check is
# recognized under any of these keys; its `verdict` must be APPROVED for a PASS.
# For deep profile its absence WARNS by default; set COMAD_SECOND_OPINION_REQUIRED=1
# to promote the warning to a hard error (same log-only→block maturity path the
# Stop gates use).
SECOND_OPINION_CANON = "second_opinion"
SECOND_OPINION_ALIASES = {"adversarial_review", "code_review", "second-opinion"}
SECOND_OPINION_VERDICTS = {"APPROVED", "REQUEST_CHANGES", "BLOCKS"}
SECOND_OPINION_REQUIRED = os.environ.get("COMAD_SECOND_OPINION_REQUIRED", "0") == "1"

QA_LEVELS = {
    "L0_api_contract":    "DTO/schema field mapping",
    "L1_ui_render":       "UI rendering (browser)",
    "L2_api_call":        "HTTP 200 + CORS",
    "L3_crud_roundtrip":  "Write → Read → Compare",
    "L4_console_errors":  "Browser console.error == 0",
    "L5_field_mapping":   "Frontend type ↔ backend field parity",
}

# Deep profile required audits — at least one entry per category, status
# in {PASS, SKIP (with reason), N/A}. Missing entries → schema violation.
# Each tuple: (canonical_key, accepted_aliases, category_description)
DEEP_REQUIRED = [
    ("audit.dependency_cve",
     {"audit.npm_audit", "audit.pip_audit", "audit.cargo_audit", "audit.cve"},
     "dependency CVE scan (npm audit / pip audit / equivalent)"),
    ("audit.data_integrity",
     {"audit.fk_integrity", "audit.orphan_check", "audit.referential_integrity"},
     "orphan / foreign-key / referential integrity"),
    ("audit.injection_probe",
     {"audit.xss_probe", "audit.nosql_injection", "audit.sqli_probe", "audit.input_safety"},
     "input safety: NoSQL/SQL/XSS injection probe"),
    ("audit.observability_verified",
     {"audit.sentry_capture", "audit.error_capture", "audit.logging_verified"},
     "observability — actually captured a test event (not just env presence)"),
    ("audit.performance_baseline",
     {"audit.lighthouse", "audit.latency_p95", "audit.bundle_size", "audit.load_test"},
     "performance — latency / lighthouse / bundle size baseline"),
]
# When DB is present (db_collections / mongo_collections / sql_tables in
# inventory), also require:
DEEP_REQUIRED_IF_DB = [
    ("audit.query_plan",
     {"audit.mongo_explain", "audit.index_hit", "audit.query_explain"},
     "DB query plan — explain() shows index hit, not COLLSCAN"),
]

# Heuristics to auto-detect deep profile (if `profile` field absent)
DEEP_KEYWORDS = re.compile(
    r"\b(production|live|deploy(?:ed)?|launch(?:ed)?|release|prod|"
    r"https://[\w.-]+\.(?:com|io|dev|app|net|fly\.dev|vercel\.app)|"
    r"flyctl|kubectl|docker compose up|terraform apply)\b",
    re.IGNORECASE,
)

# Shallow detail floor — if `details` is below this length while status=PASS
# AND key is an `audit.*` (i.e. claims to be an audit), warn.
SHALLOW_DETAILS_MIN = 40

# Deep profile floors
DEEP_MIN_ARTIFACTS = 5
DEEP_MIN_INVENTORY_DIMENSIONS = 4
DEEP_MIN_NOTES_LEN = 200


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


def detect_profile(data: dict) -> str:
    """Return 'smoke' or 'deep'. Explicit profile field wins."""
    p = data.get("profile")
    if p in ALLOWED_PROFILES:
        return p

    haystack = " ".join([
        data.get("scope") or "",
        data.get("notes") or "",
    ])
    if DEEP_KEYWORDS.search(haystack):
        return "deep"

    # Fallback: many audit.* keys → likely a deep audit
    audit_keys = [k for k in (data.get("checks") or {}) if k.startswith("audit.")]
    if len(audit_keys) >= 8:
        return "deep"

    return "smoke"


def find_check(checks: dict, canonical: str, aliases: set[str]) -> tuple[str, dict] | None:
    """Return (key, ck) if any of canonical/aliases present, else None."""
    candidates = [canonical, *aliases]
    for c in candidates:
        if c in checks and isinstance(checks[c], dict):
            return c, checks[c]
    return None


def has_db_inventory(inv: dict) -> bool:
    if not isinstance(inv, dict):
        return False
    for k in inv:
        if k.endswith("_total") and (
            "collection" in k or "table" in k or "mongo" in k.lower() or "db" in k
        ):
            return True
    return False


def validate(data: dict, path: pathlib.Path) -> tuple[list[str], list[str], str]:
    """Return (errors, warnings, profile)."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        errors.append("top-level value is not an object")
        return errors, warnings, "smoke"

    for k in REQUIRED_TOP:
        if k not in data:
            errors.append(f"missing required field: {k}")

    if "schema_version" in data and not isinstance(data["schema_version"], str):
        errors.append("schema_version must be a string")
    if "scope" in data:
        if not isinstance(data["scope"], str):
            errors.append("scope must be a string")
        elif not data["scope"].strip():
            errors.append("scope must not be empty")
    if "verdict" in data and data["verdict"] not in ALLOWED_VERDICTS:
        errors.append(f"verdict must be one of {sorted(ALLOWED_VERDICTS)} (got {data['verdict']!r})")

    if "profile" in data and data["profile"] not in ALLOWED_PROFILES:
        errors.append(f"profile must be one of {sorted(ALLOWED_PROFILES)} (got {data['profile']!r})")

    profile = detect_profile(data)

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
            errors.append(f"checks.{name}.status must be PASS|FAIL|SKIP|N/A (got {status!r})")

        if name == "browser_qa" or name == "L1_ui_render" or name == "L4_console_errors":
            if status == "PASS":
                ce = ck.get("console_errors", 0)
                if ce not in (0, None):
                    try:
                        if int(ce) != 0:
                            errors.append(f"checks.{name}.status=PASS requires console_errors=0")
                    except Exception:
                        errors.append(f"checks.{name}.console_errors must be int")
                if not ck.get("tool"):
                    warnings.append(f"checks.{name}.tool not specified")
                if name in ("browser_qa", "L1_ui_render") and (
                    not isinstance(ck.get("viewports"), list) or not ck.get("viewports")
                ):
                    warnings.append(f"checks.{name}.viewports missing or empty")

        if re.match(r"^L\d+_", name) and name not in QA_LEVELS:
            warnings.append(
                f"checks.{name}: L-prefix used but name not in reserved "
                f"set {sorted(QA_LEVELS.keys())}"
            )

        if "passed" in ck or "failed" in ck or "total" in ck:
            p = ck.get("passed", 0) or 0
            f = ck.get("failed", 0) or 0
            t = ck.get("total", None)
            if t is not None and p + f != t:
                errors.append(f"checks.{name}: passed({p})+failed({f}) != total({t})")

        # Shallow audit detection (deep profile only — smoke은 자유)
        if profile == "deep" and name.startswith("audit.") and status == "PASS":
            details = ck.get("details", "") or ""
            if len(details.strip()) < SHALLOW_DETAILS_MIN:
                warnings.append(
                    f"checks.{name}: shallow PASS — details under {SHALLOW_DETAILS_MIN} "
                    f"chars (got {len(details.strip())}). Provide concrete evidence "
                    f"(numbers, command output, file paths)."
                )

    # verdict ↔ checks consistency
    verdict = data.get("verdict")
    if verdict == "PASS":
        fail_checks = [n for n, ck in checks.items()
                       if isinstance(ck, dict) and ck.get("status") == "FAIL"]
        if fail_checks:
            errors.append(f"verdict=PASS but checks have FAIL status: {fail_checks}")

    # ── second_opinion (adversarial review) wiring [R2] ──
    so = find_check(checks, SECOND_OPINION_CANON, SECOND_OPINION_ALIASES)
    if so is not None:
        so_key, so_ck = so
        so_verdict = (so_ck.get("verdict") or "").upper()
        if so_verdict and so_verdict not in SECOND_OPINION_VERDICTS:
            errors.append(
                f"checks.{so_key}.verdict must be one of "
                f"{sorted(SECOND_OPINION_VERDICTS)} (got {so_ck.get('verdict')!r})"
            )
        if verdict == "PASS" and so_verdict != "APPROVED":
            errors.append(
                f"verdict=PASS requires checks.{so_key}.verdict=APPROVED "
                f"(got {so_verdict or 'empty'}) — adversarial review not approved."
            )
    else:
        msg = ("no second_opinion / adversarial-review check — a substantial "
               "change should record an adversarial review (verdict APPROVED). "
               "Run the adversarial-review Workflow or comad-second-opinion / "
               "codex challenge.")
        if profile == "deep" and SECOND_OPINION_REQUIRED:
            errors.append(msg)
        elif profile == "deep":
            warnings.append(msg)

    # inventory coverage
    inv = data.get("inventory") or {}
    inv_dimensions = 0
    if isinstance(inv, dict):
        seen_bases: set[str] = set()
        for k in inv:
            if k.endswith("_total"):
                seen_bases.add(k[:-6])
            elif k.endswith("_verified"):
                seen_bases.add(k[:-9])
        inv_dimensions = len(seen_bases)
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

    # ── DEEP PROFILE GATE ──────────────────────────────────────────────────
    if profile == "deep":
        required = list(DEEP_REQUIRED)
        if has_db_inventory(inv):
            required.extend(DEEP_REQUIRED_IF_DB)

        for canonical, aliases, desc in required:
            found = find_check(checks, canonical, aliases)
            if not found:
                errors.append(
                    f"deep profile requires '{canonical}' (or alias {sorted(aliases)}) "
                    f"— {desc}. Missing audit makes verdict=PASS misleading."
                )
                continue
            key, ck = found
            st = ck.get("status")
            if st == "FAIL":
                # already counted above, but reinforce
                pass
            elif st in ("SKIP", "N/A"):
                reason = ck.get("details", "") or ""
                if len(reason.strip()) < 30:
                    warnings.append(
                        f"checks.{key}: status={st} but no concrete reason in "
                        f"details (under 30 chars). State why this audit is "
                        f"genuinely not applicable to avoid suppression bias."
                    )

        # Artifacts minimum
        artifacts = data.get("artifacts") or []
        if not isinstance(artifacts, list):
            errors.append("artifacts must be a list")
        elif len(artifacts) < DEEP_MIN_ARTIFACTS:
            errors.append(
                f"deep profile requires >= {DEEP_MIN_ARTIFACTS} artifacts "
                f"(file paths to logs, screenshots, scripts, config). "
                f"Got {len(artifacts)}."
            )

        # Inventory dimensions minimum
        if inv_dimensions < DEEP_MIN_INVENTORY_DIMENSIONS:
            errors.append(
                f"deep profile requires >= {DEEP_MIN_INVENTORY_DIMENSIONS} "
                f"inventory dimensions (e.g. routes_total, workers_total, "
                f"server_actions_total, db_collections_total). Got {inv_dimensions}."
            )

        # Notes length minimum
        notes = data.get("notes") or ""
        if not isinstance(notes, str):
            errors.append("notes must be a string")
        elif len(notes.strip()) < DEEP_MIN_NOTES_LEN:
            warnings.append(
                f"notes shorter than {DEEP_MIN_NOTES_LEN} chars — deep audits "
                f"benefit from concrete narrative (deferred items, edge cases, "
                f"chaos scenarios skipped, etc.)."
            )

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

    return errors, warnings, profile


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

    errors, warnings, profile = validate(data, path)

    print(f"profile: {profile}")
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")

    if errors:
        print(f"\nvalidate-qa-evidence: {len(errors)} error(s), {len(warnings)} warning(s) — FAIL (profile={profile})")
        return 2

    verdict = data.get("verdict")
    if verdict == "PASS":
        print(f"\nvalidate-qa-evidence: schema OK, verdict=PASS — {len(warnings)} warning(s) (profile={profile})")
        return 0
    print(f"\nvalidate-qa-evidence: schema OK, verdict={verdict} (not yet PASS, profile={profile})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
