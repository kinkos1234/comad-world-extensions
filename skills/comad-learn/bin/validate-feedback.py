#!/usr/bin/env python3
"""Post-validator for /comad-learn-generated feedback memories.

Verifies that newly-written feedback_*.md files follow the template so the
LLM's output remains structurally consistent. Exit 1 on any violation; the
skill should re-generate failing files.

Usage:
    validate-feedback.py <file1.md> [file2.md ...]
    validate-feedback.py --all       # check every feedback_*.md under projects
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

HOME = pathlib.Path(os.environ["HOME"])
PROJECTS = HOME / ".claude" / "projects"

REQUIRED_FRONTMATTER = ["name", "description", "type"]

# Strict mode — for files written by /comad-learn (enforces the full T6 template).
STRICT_BODY_MARKERS = [
    r"^## 원칙\s*$",
    r"\*\*Why:\*\*",
    r"\*\*How to apply:\*\*",
    r"^## 관찰 이력\s*$",
    r"^## HARD 훅 후보\s*$",
]

# Lenient mode — for pre-existing / grandfathered memories (--all audit).
# Only requires frontmatter + non-empty body.
LENIENT_MIN_BODY_LEN = 40


def parse_frontmatter(text: str) -> tuple[dict, str]:
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


def count_seen(body: str) -> int:
    """Count `Seen N회` bullets in the 관찰 이력 section."""
    return len(re.findall(r"^\s*-\s*Seen\s+(\d+)?\s*회", body, flags=re.MULTILINE))


def validate(path: pathlib.Path, strict: bool = True) -> list[str]:
    issues: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return [f"read error: {e}"]

    fm, body = parse_frontmatter(text)
    if not fm:
        issues.append("missing or malformed frontmatter")
    for k in REQUIRED_FRONTMATTER:
        if k not in fm:
            issues.append(f"frontmatter missing: {k}")
    if fm.get("type") and fm["type"] != "feedback":
        issues.append(f"frontmatter type must be 'feedback' (got {fm['type']!r})")

    if strict:
        for pat in STRICT_BODY_MARKERS:
            if not re.search(pat, body, flags=re.MULTILINE):
                issues.append(f"body missing section: {pat}")

        # HARD hook candidate gating rule — only enforced in strict mode
        seen = count_seen(body)
        hard_section_idx = body.find("## HARD 훅 후보")
        if hard_section_idx >= 0:
            hard_body = body[hard_section_idx:]
            has_actual_candidate = "승인 요청" in hard_body or "제안 위치" in hard_body
            if has_actual_candidate and seen < 2:
                issues.append(
                    f"HARD 훅 후보가 있는데 Seen={seen} (<2) — 2회 이상 관찰되기 전에 승격 금지"
                )
    else:
        # Lenient: just require non-empty body
        if len(body.strip()) < LENIENT_MIN_BODY_LEN:
            issues.append(f"body too short (<{LENIENT_MIN_BODY_LEN} chars)")

    return issues


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run_all = "--all" in sys.argv
    # --all implies lenient (grandfather pre-existing files). Per-file mode is
    # strict by default — that is the mode /comad-learn uses post-write.
    strict = not run_all
    if "--strict" in sys.argv:
        strict = True
    if "--lenient" in sys.argv:
        strict = False

    if run_all:
        paths = list(PROJECTS.glob("*/memory/feedback_*.md"))
    else:
        paths = [pathlib.Path(a) for a in args]

    if not paths:
        print("usage: validate-feedback.py <file1.md> [file2.md ...] | --all", file=sys.stderr)
        return 2

    bad = 0
    for p in paths:
        issues = validate(p, strict=strict)
        if issues:
            bad += 1
            print(f"INVALID {p}:")
            for i in issues:
                print(f"  - {i}")
        else:
            print(f"OK       {p.name}")

    mode = "strict" if strict else "lenient"
    print(f"\nvalidate-feedback [{mode}]: {len(paths) - bad}/{len(paths)} pass")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
