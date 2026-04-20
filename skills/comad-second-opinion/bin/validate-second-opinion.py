#!/usr/bin/env python3
"""validate-second-opinion — schema validator for `.second-opinion.md`.

Usage:
    validate-second-opinion.py [path]

If path omitted, looks for .second-opinion.md under git root (or CWD).

Exit codes:
    0 — valid AND verdict==APPROVED
    1 — valid but verdict != APPROVED (REQUEST_CHANGES / BLOCKS)
    2 — schema / content violation
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

REQUIRED_FM = ["schema_version", "generated_at", "reviewer", "git_head",
               "topic", "verdict"]
ALLOWED_VERDICTS = {"APPROVED", "REQUEST_CHANGES", "BLOCKS"}
REQUIRED_SECTIONS = [
    r"^##\s*Scope\b",
    r"^##\s*Findings\b",
    r"^##\s*Verdict",
]
MIN_BODY_CHARS = 200


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


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    fm: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, body


def validate(text: str, repo: pathlib.Path) -> tuple[list[str], list[str], str]:
    errors: list[str] = []
    warnings: list[str] = []
    fm, body = parse_frontmatter(text)

    if not fm:
        errors.append("missing or malformed frontmatter")
        return errors, warnings, ""

    for k in REQUIRED_FM:
        if k not in fm:
            errors.append(f"frontmatter missing: {k}")

    verdict = fm.get("verdict", "")
    if verdict not in ALLOWED_VERDICTS:
        errors.append(
            f"verdict must be one of {sorted(ALLOWED_VERDICTS)} (got {verdict!r})"
        )

    topic = fm.get("topic", "")
    if topic and len(topic.strip()) < 5:
        warnings.append("topic is very short — add context")
    if not topic:
        errors.append("frontmatter topic is required and non-empty")

    # git_head staleness check
    head = fm.get("git_head", "")
    if head:
        try:
            out = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(repo), capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0:
                current = out.stdout.strip()
                if current and not (current.startswith(head) or head.startswith(current)):
                    errors.append(
                        f"git_head={head} but current HEAD={current} — review "
                        f"is stale; re-review the current diff"
                    )
        except Exception:
            pass

    if len(body.strip()) < MIN_BODY_CHARS:
        errors.append(
            f"body too short ({len(body.strip())} < {MIN_BODY_CHARS} chars) — "
            f"substantive review expected"
        )

    for pat in REQUIRED_SECTIONS:
        if not re.search(pat, body, flags=re.MULTILINE):
            errors.append(f"body missing required section: {pat}")

    return errors, warnings, verdict


def main() -> int:
    if len(sys.argv) > 2:
        print("usage: validate-second-opinion.py [path]", file=sys.stderr)
        return 2

    if len(sys.argv) == 2:
        path = pathlib.Path(sys.argv[1])
        repo = git_root(path.parent if path.is_file() else path)
    else:
        repo = git_root(pathlib.Path.cwd())
        path = repo / ".second-opinion.md"

    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 2

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return 2

    errors, warnings, verdict = validate(text, repo)

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")

    if errors:
        print(f"\nvalidate-second-opinion: {len(errors)} error(s), "
              f"{len(warnings)} warning(s) — FAIL")
        return 2

    if verdict == "APPROVED":
        print(f"\nvalidate-second-opinion: schema OK, verdict=APPROVED — "
              f"{len(warnings)} warning(s)")
        return 0

    print(f"\nvalidate-second-opinion: schema OK, verdict={verdict} (not APPROVED)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
