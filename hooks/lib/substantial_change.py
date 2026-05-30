#!/usr/bin/env python3
"""substantial_change — shared heuristic: is a change 'substantial' enough to
warrant adversarial review?

Used by adversarial-review-gate (and reusable by other gates / qa flows).
Two entry points:

  is_substantial(cwd)        — git-diff based (working tree vs HEAD, else last
                               commit). Returns (bool, info).
  classify_paths(paths)      — given a list of file paths (e.g. the files a turn
                               edited), returns (code_paths, sensitive_bool).

Design rules (this runs inside a global Stop hook):
  * FAIL-OPEN — any error returns "not substantial" / empty, never raises.
  * FAST — git calls have a 5s timeout; no network.

Heuristic floors (tunable):
  substantial if  sensitive-path  OR  >= CODE_FILES_FLOOR code files
                  OR  (>= 1 code file AND >= NET_LINES_FLOOR net lines)
"""
from __future__ import annotations

import os
import pathlib
import subprocess

CODE_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java",
    ".rb", ".sh", ".bash", ".zsh", ".sql", ".c", ".cc", ".cpp", ".h", ".hpp",
    ".swift", ".kt", ".php", ".vue", ".svelte", ".scala", ".cs", ".clj", ".ex",
    ".exs", ".lua", ".pl", ".dart", ".m", ".mm",
}
# code-ish paths that should NOT count (generated / vendored / minified)
SKIP_PATH_SUBSTR = (
    "node_modules/", ".venv/", "venv/", "vendor/", "dist/", "build/", ".next/",
    "__pycache__/", ".min.", "/migrations/", ".generated.",
)
# substring match → always substantial (security/prod surface)
SENSITIVE_SUBSTR = (
    "auth", "security", "secret", "crypto", "login", "password", "passwd",
    "token", "payment", "billing", "prod", "credential", "/admin", "session",
    "permission", "rbac",
)
NET_LINES_FLOOR = 40
CODE_FILES_FLOOR = 3


def _git(args: list[str], cwd) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(cwd),
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout
    except Exception:
        pass
    return ""


def repo_root(start=None) -> pathlib.Path | None:
    start = start or os.getcwd()
    out = _git(["rev-parse", "--show-toplevel"], start)
    return pathlib.Path(out.strip()) if out.strip() else None


def is_code_path(path: str) -> bool:
    low = path.lower()
    if any(s in low for s in SKIP_PATH_SUBSTR):
        return False
    return pathlib.PurePath(path).suffix.lower() in CODE_EXT


def is_sensitive_path(path: str) -> bool:
    return any(s in path.lower() for s in SENSITIVE_SUBSTR)


def classify_paths(paths) -> tuple[list[str], bool]:
    """Return (code_paths, any_sensitive) from an arbitrary path list."""
    code: list[str] = []
    sensitive = False
    for p in paths or []:
        if not isinstance(p, str) or not p:
            continue
        if not is_code_path(p):
            continue
        code.append(p)
        if is_sensitive_path(p):
            sensitive = True
    return code, sensitive


def _numstat(root) -> list[tuple[int, int, str]]:
    raw = _git(["diff", "--numstat", "HEAD"], root)
    if not raw.strip():
        raw = _git(["diff", "--numstat", "HEAD~1", "HEAD"], root)
    rows: list[tuple[int, int, str]] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, d, path = parts
        try:
            added = 0 if a == "-" else int(a)
            deleted = 0 if d == "-" else int(d)
        except ValueError:
            added = deleted = 0
        rows.append((added, deleted, path))
    return rows


def is_substantial(cwd=None) -> tuple[bool, dict]:
    root = repo_root(cwd)
    if root is None:
        return False, {"reason": "not a git repo"}
    code: list[str] = []
    sensitive = False
    net = 0
    for added, deleted, path in _numstat(root):
        if not is_code_path(path):
            continue
        code.append(path)
        net += added + deleted
        if is_sensitive_path(path):
            sensitive = True
    substantial = bool(
        sensitive
        or len(code) >= CODE_FILES_FLOOR
        or (len(code) >= 1 and net >= NET_LINES_FLOOR)
    )
    reason = []
    if sensitive:
        reason.append("sensitive-path")
    if len(code) >= CODE_FILES_FLOOR:
        reason.append(f"{len(code)} code files")
    if net >= NET_LINES_FLOOR:
        reason.append(f"{net} net lines")
    return substantial, {
        "root": str(root),
        "code_files": code[:20],
        "code_file_count": len(code),
        "net_lines": net,
        "sensitive": sensitive,
        "reason": ", ".join(reason) or "below thresholds",
    }


if __name__ == "__main__":
    import json
    import sys
    ok, info = is_substantial(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps({"substantial": ok, **info}, ensure_ascii=False, indent=2))
