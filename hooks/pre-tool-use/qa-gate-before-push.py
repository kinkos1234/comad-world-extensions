#!/usr/bin/env python3
"""qa-gate-before-push — require a valid .qa-evidence.json before ``git push``.

PreToolUse[Bash]. Opt-in by design:

- Repo has NO .qa-evidence.json → gate dormant, push allowed.
- Repo HAS .qa-evidence.json → run validate-qa-evidence.py. Push only
  allowed if validator returns exit 0 (schema OK + verdict=PASS).
- COMAD_QA_REQUIRED=1 in env → force gate active even without the file;
  pushes blocked until Claude (or the user) initializes + populates.

Non-push bash invocations are ignored. Remote-delete pushes
(``git push --delete …`` or ``git push origin :branch``) are exempt.

Bypass (one-shot):
  touch ~/.claude/.comad/approvals/approve-push-qa-skip.<cmd_hash>
  touch ~/.claude/.comad/approvals/approve-push-qa-skip             # generic
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys

HOME = pathlib.Path(os.environ.get("HOME", "/"))
APPROVE_DIR = HOME / ".claude" / ".comad" / "approvals"
LOG_DIR = HOME / ".claude" / ".comad" / "pending"

VALIDATOR = HOME / ".claude" / "skills" / "comad-qa-evidence" / "bin" / "validate-qa-evidence.py"


def cmd_hash(cmd: str) -> str:
    return hashlib.sha256(cmd.encode("utf-8", errors="replace")).hexdigest()[:16]


def find_cd_prefix(cmd: str) -> str | None:
    m = re.match(r"\s*cd\s+([^\s;&|]+)\s*(?:&&|;)", cmd)
    if m:
        return m.group(1).strip("'\"")
    return None


def is_push(tokens: list[str]) -> bool:
    """True if tokens represent `git push`. tokens start with git-like prefix."""
    i = 0
    while i < len(tokens) and (tokens[i] in {"sudo", "env"} or "=" in tokens[i]):
        i += 1
    return (
        i + 1 < len(tokens)
        and tokens[i] == "git"
        and tokens[i + 1] == "push"
    )


def find_push_segment(cmd: str) -> list[str] | None:
    """Return the tokens of the first `git push` segment, or None."""
    parts = re.split(r"[;&|]|&&|\|\|", cmd)
    for part in parts:
        try:
            tokens = shlex.split(part.strip(), posix=True)
        except ValueError:
            continue
        if not tokens:
            continue
        if is_push(tokens):
            return tokens
    return None


def is_delete_push(tokens: list[str]) -> bool:
    """Detect remote-delete patterns that don't need QA:
        git push --delete origin branch
        git push origin :branch
        git push origin +:branch  (force-with-lease variant)"""
    # find the two relevant tokens after 'push'
    try:
        idx = tokens.index("push")
    except ValueError:
        return False
    rest = tokens[idx + 1 :]
    if any(t == "--delete" or t == "-d" for t in rest):
        return True
    # refspec starting with ":" means delete
    for t in rest:
        if t.startswith(":") or t.startswith("+:"):
            return True
    return False


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


def run_validator(evidence_path: pathlib.Path) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["python3", str(VALIDATOR), str(evidence_path)],
            capture_output=True, text=True, timeout=15,
        )
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 99, f"validator crashed: {e}"


def emit_block(msg: str, cmd: str, h: str) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    import datetime
    with (LOG_DIR / "qa-gate-before-push.jsonl").open("a") as fp:
        fp.write(
            json.dumps(
                {
                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "cmd_hash": h,
                    "command": cmd,
                    "reason": msg.splitlines()[0],
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    sys.stderr.write(f"""🚦 qa-gate-before-push: BLOCKED

{msg}

Command   : {cmd}
Cmd hash  : {h}

Options:
  (a) Populate .qa-evidence.json and run validate-qa-evidence.py → verdict=PASS
  (b) Approve THIS push only (exact command):
        touch ~/.claude/.comad/approvals/approve-push-qa-skip.{h}
  (c) Generic one-shot bypass:
        touch ~/.claude/.comad/approvals/approve-push-qa-skip
  (d) Disable gate for this repo: delete .qa-evidence.json
        (ONLY if the repo genuinely doesn't need QA gating)

False positive? Edit ~/.claude/hooks/pre-tool-use/qa-gate-before-push.py
Incident logged at ~/.claude/.comad/pending/qa-gate-before-push.jsonl
""")
    return 2


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0

    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return 0

    tokens = find_push_segment(cmd)
    if tokens is None:
        return 0  # not a git push

    if is_delete_push(tokens):
        return 0  # remote deletes don't need QA

    # Resolve cwd (cd prefix wins, else process cwd)
    cd = find_cd_prefix(cmd)
    cwd = pathlib.Path(cd).expanduser().resolve() if cd else pathlib.Path.cwd()
    if not cwd.exists():
        cwd = pathlib.Path.cwd()

    root = git_root(cwd)
    if root is None:
        return 0  # not in a git repo, nothing to gate

    evidence = root / ".qa-evidence.json"
    forced = os.environ.get("COMAD_QA_REQUIRED") == "1"

    if not evidence.exists() and not forced:
        return 0  # opt-in gate dormant for this repo

    h = cmd_hash(cmd)

    # Approval bypass
    APPROVE_DIR.mkdir(parents=True, exist_ok=True)
    specific = APPROVE_DIR / f"approve-push-qa-skip.{h}"
    generic = APPROVE_DIR / "approve-push-qa-skip"
    if specific.exists():
        specific.unlink()
        sys.stderr.write(f"qa-gate-before-push: command-bound approval consumed ({h})\n")
        return 0
    if generic.exists():
        generic.unlink()
        sys.stderr.write("qa-gate-before-push: generic approval consumed\n")
        return 0

    if not evidence.exists() and forced:
        return emit_block(
            f"COMAD_QA_REQUIRED=1 but {evidence} missing.\n"
            f"Run: python3 ~/.claude/skills/comad-qa-evidence/bin/init-qa-evidence.py",
            cmd, h,
        )

    rc, report = run_validator(evidence)
    if rc == 0:
        return 0  # valid + verdict=PASS → allow

    if rc == 1:
        reason = (
            f".qa-evidence.json found but verdict is not PASS yet.\n"
            f"Validator output:\n{report}"
        )
    elif rc == 2:
        reason = (
            f".qa-evidence.json has schema/cross-check violations.\n"
            f"Validator output:\n{report}"
        )
    else:
        reason = f"validate-qa-evidence.py failed (rc={rc}):\n{report}"

    return emit_block(reason, cmd, h)


if __name__ == "__main__":
    sys.exit(main())
