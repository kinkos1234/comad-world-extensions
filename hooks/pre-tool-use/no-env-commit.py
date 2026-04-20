#!/usr/bin/env python3
"""no-env-commit hook — blocks ``git add`` / ``git stage`` of sensitive files.

PreToolUse[Bash]. Intercepts ``git add``-like invocations, enumerates the
files that *would* be staged (resolving wildcards via ``git add --dry-run``
where safe), and blocks if any match a sensitive pattern.

Exit codes:
  0 → allow
  2 → deny (stderr shown to the model)

Bypass (one-shot, command-hash-bound):
  touch ~/.claude/.comad/approvals/approve-env-commit.<hash>

Or generic:
  touch ~/.claude/.comad/approvals/approve-env-commit
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

# Sensitive patterns — applied to file paths (unix-style, no leading ./).
SENSITIVE_PATTERNS = [
    (r"(^|/)\.env$", ".env"),
    (r"(^|/)\.env\.(?!example$|sample$|template$|dist$|defaults$)[A-Za-z0-9_.-]+$", ".env.<env>"),
    (r"(^|/)settings\.local\.json$", "settings.local.json"),
    (r"\.(key|pem|p12|pfx)$", "private key"),
    (r"(^|/)id_(rsa|ed25519|ecdsa|dsa)(\.pub)?$", "SSH key"),
    (r"(^|/)credentials\.json$", "credentials.json"),
    (r"(^|/)secrets?\.(json|ya?ml|env)$", "secrets.*"),
    (r"(^|/)\.aws/credentials$", "AWS credentials"),
    (r"(^|/)\.netrc$", ".netrc"),
    (r"(^|/)\.npmrc$", ".npmrc (may contain token)"),
    (r"(^|/)\.pypirc$", ".pypirc"),
    (r"\.token$", "*.token"),
    (r"(^|/)access\.json$", "access.json"),
    (r"(^|/)service-account.*\.json$", "GCP service account"),
    (r"\.gpg$", "*.gpg"),
    (r"(^|/)firebase-admin.*\.json$", "firebase admin sdk"),
]


def cmd_hash(cmd: str) -> str:
    return hashlib.sha256(cmd.encode("utf-8", errors="replace")).hexdigest()[:16]


def is_git_add(cmd: str) -> bool:
    """True if the command invokes git add or git stage (possibly chained)."""
    # Split on command separators, then look for git add / stage at the start
    # of each subcommand. This catches `cd foo && git add .`, `git add x;`,
    # `sudo git add x`, etc.
    parts = re.split(r"[;&|]|&&|\|\|", cmd)
    for part in parts:
        tokens = shlex.split(part.strip(), posix=True) if part.strip() else []
        if not tokens:
            continue
        # skip leading env/sudo-style prefix
        i = 0
        while i < len(tokens) and (
            tokens[i] in {"sudo", "env"}
            or "=" in tokens[i]
            or tokens[i].startswith("-")
        ):
            i += 1
        if i + 1 >= len(tokens):
            continue
        if tokens[i] == "git" and tokens[i + 1] in {"add", "stage"}:
            return True
    return False


# Flags that expand to "all modified/untracked files". We pass these through
# to `git add --dry-run` so it enumerates the actual files that would be
# staged. Other flags (like --verbose) are dropped.
EXPANSION_FLAGS = {"-A", "--all", "-u", "--update", "-p", "--patch", "--ignore-removal"}


def extract_add_args(cmd: str) -> list[str]:
    """Return the non-option arguments passed to ``git add`` / ``git stage``,
    plus any expansion flags (``-A`` / ``--all`` / ``-u``). Other flags are
    dropped so the dry-run sees a clean argument list."""
    args: list[str] = []
    parts = re.split(r"[;&|]|&&|\|\|", cmd)
    for part in parts:
        try:
            tokens = shlex.split(part.strip(), posix=True)
        except ValueError:
            continue
        if not tokens:
            continue
        for i, t in enumerate(tokens[:-1]):
            if t == "git" and tokens[i + 1] in {"add", "stage"}:
                for arg in tokens[i + 2 :]:
                    if arg in {"&&", "||", ";", "|"}:
                        break
                    if arg == "--":
                        continue
                    if arg.startswith("-"):
                        if arg in EXPANSION_FLAGS:
                            args.append(arg)
                        # drop other flags (e.g. --verbose)
                        continue
                    args.append(arg)
                break
    return args


def find_cd_prefix(cmd: str) -> str | None:
    """If command starts with `cd X && ...`, return X. Used as best-effort
    cwd hint for running git dry-run."""
    m = re.match(r"\s*cd\s+([^\s;&|]+)\s*(?:&&|;)", cmd)
    if m:
        return m.group(1).strip("'\"")
    return None


def resolve_files(args: list[str], cwd: pathlib.Path) -> list[str]:
    """Resolve potentially wildcard/directory/flag args into the actual files
    that would be staged. Uses ``git add --dry-run --ignore-errors`` which
    prints ``add '<path>'`` lines without modifying the index.

    Returns a list of repo-relative paths. Falls back to the raw literal path
    args if the dry-run fails or produces no hits."""
    if not args:
        return []

    # Separate expansion flags (pass without --) from path args (pass after --)
    flags = [a for a in args if a in EXPANSION_FLAGS]
    paths = [a for a in args if a not in EXPANSION_FLAGS]
    cmdline = ["git", "add", "--dry-run", "--ignore-errors"] + flags
    if paths:
        cmdline += ["--"] + paths

    try:
        proc = subprocess.run(
            cmdline, cwd=str(cwd), capture_output=True, text=True, timeout=10
        )
    except Exception:
        return [p for p in paths]

    files: list[str] = []
    for line in proc.stdout.splitlines():
        m = re.match(r"^add '(.+)'$", line.strip())
        if m:
            files.append(m.group(1))
    if not files:
        # dry-run produced nothing (possibly all skipped). Fall back to raw paths.
        return [p for p in paths]
    return files


def match_sensitive(path: str) -> tuple[str, str] | None:
    """Return (matched_regex, human_label) or None."""
    for pat, label in SENSITIVE_PATTERNS:
        if re.search(pat, path):
            return pat, label
    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0

    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return 0
    if not is_git_add(cmd):
        return 0

    # Determine cwd: try cd-prefix, else use process cwd
    cd = find_cd_prefix(cmd)
    cwd = pathlib.Path(cd).expanduser().resolve() if cd else pathlib.Path.cwd()
    if not cwd.exists():
        cwd = pathlib.Path.cwd()

    args = extract_add_args(cmd)
    files = resolve_files(args, cwd)

    hits: list[tuple[str, str]] = []  # (file, label)
    for f in files:
        m = match_sensitive(f)
        if m:
            hits.append((f, m[1]))

    if not hits:
        return 0

    h = cmd_hash(cmd)

    # Approval bypasses
    APPROVE_DIR.mkdir(parents=True, exist_ok=True)
    specific_flag = APPROVE_DIR / f"approve-env-commit.{h}"
    generic_flag = APPROVE_DIR / "approve-env-commit"
    if specific_flag.exists():
        specific_flag.unlink()
        sys.stderr.write(
            f"no-env-commit: command-bound approval consumed ({h}) — staging {len(hits)} sensitive file(s)\n"
        )
        return 0
    if generic_flag.exists():
        generic_flag.unlink()
        sys.stderr.write("no-env-commit: generic approval consumed\n")
        return 0

    # Log
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    import datetime
    with (LOG_DIR / "no-env-commit.jsonl").open("a") as fp:
        fp.write(
            json.dumps(
                {
                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "cmd_hash": h,
                    "command": cmd,
                    "hits": hits,
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    lines = "\n".join(f"  • {f}  ← {label}" for f, label in hits)
    sys.stderr.write(f"""🔐 no-env-commit: BLOCKED (credentials/secrets about to enter git)

Command   : {cmd}
Sensitive files detected:
{lines}
Cmd hash  : {h}

Fix options:
  (a) Remove the sensitive files from the add list
  (b) Add them to .gitignore
  (c) If this is a template / fixture / deliberate, approve once (exact cmd):
        touch ~/.claude/.comad/approvals/approve-env-commit.{h}
  (d) Generic one-shot (any next 'git add'):
        touch ~/.claude/.comad/approvals/approve-env-commit

False positive? Edit ~/.claude/hooks/pre-tool-use/no-env-commit.py SENSITIVE_PATTERNS.
Incident logged at ~/.claude/.comad/pending/no-env-commit.jsonl
""")
    return 2


if __name__ == "__main__":
    sys.exit(main())
