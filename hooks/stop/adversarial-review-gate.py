#!/usr/bin/env python3
"""adversarial-review-gate — R2: adversarial review by default for substantial code.

Stop hook. Complements the claim-VALIDATORS (claim-done / numeric-claim /
inventory / harsh-critic): those catch over-claiming TEXT. This one asks a
different question — when a turn CLAIMS a substantial code change is done/ready,
was it adversarially reviewed? (i.e. did anyone try to *break* it?)

Trigger (all three):
  1. turn text contains a completion/ship claim
  2. the turn itself made a substantial code change
     (>= 3 code files edited, OR a sensitive path, OR git diff is substantial)
  3. no fresh `.second-opinion.md` with verdict=APPROVED in the touched repo

Action: WARN-ONLY by default (logs to pending/adversarial-review.jsonl).
Set COMAD_ADVERSARIAL_REVIEW_BLOCK=1 to exit 2 (block) — same maturity path as
claim-done-gate's deploy/live gate.

To run the review: the `adversarial-review` Workflow template (N skeptics try to
break the diff → verdict) writes `.second-opinion.md`; or use comad-second-opinion
/ codex challenge. Bypass for genuine WIP via a bypass keyword (see below).

FAIL-OPEN: any error returns 0.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
try:
    from substantial_change import classify_paths, repo_root, is_substantial
except Exception:  # fail-open if lib missing
    def classify_paths(paths):  # type: ignore
        return [], False

    def repo_root(start=None):  # type: ignore
        return None

    def is_substantial(cwd=None):  # type: ignore
        return False, {}

HOME = pathlib.Path(os.environ.get("HOME", "/"))
LOG_DIR = HOME / ".claude" / ".comad" / "pending"
BLOCK_MODE = os.environ.get("COMAD_ADVERSARIAL_REVIEW_BLOCK", "0") != "0"

COMPLETION_PATTERNS = [
    r"구현\s*(?:완료|끝|했(?:어|습니다|다|음))",
    r"(?:기능|feature)\s*(?:완성|완료)",
    r"완성\s*(?:했|됐|됨|입니다|!)",
    r"다\s*(?:만들었|구현했|짰)",
    r"배포\s*(?:완료|했|준비\s*완료)",
    r"머지\s*(?:하면|준비|가능|해도\s*되)",
    r"\bready\s+to\s+(?:merge|ship|deploy|land)\b",
    r"\b(?:ship\s+it|good\s+to\s+(?:merge|ship|go))\b",
    r"\bdone\s+(?:implementing|building)\b",
    r"구현이?\s*끝났",
    r"\b(?:feature|기능)\s*(?:is\s+)?complete\b",
    r"완전\s*동작",
]

# If the turn is explicitly WIP / defers review, do not nag.
BYPASS_KEYWORDS = [
    "WIP", "초안", "draft", "리뷰 예정", "리뷰 전", "리뷰 받을",
    "second opinion", "second-opinion", "adversarial review", "적대적 리뷰",
    "리뷰 돌릴", "리뷰 돌려", "검토 예정", "아직 미완", "검증 없이 판단",
]

VERDICT_OK = {"APPROVED"}


def resolve_transcript_path(stdin_json: dict) -> pathlib.Path | None:
    tp = stdin_json.get("transcript_path")
    if tp and pathlib.Path(tp).exists():
        return pathlib.Path(tp)
    env_tp = os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    if env_tp and pathlib.Path(env_tp).exists():
        return pathlib.Path(env_tp)
    sid = stdin_json.get("session_id") or os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        for f in (HOME / ".claude" / "projects").glob(f"*/{sid}.jsonl"):
            return f
    return None


def find_last_user_idx(lines: list[str]) -> int:
    for i in range(len(lines) - 1, -1, -1):
        try:
            d = json.loads(lines[i])
        except Exception:
            continue
        if d.get("type") != "user":
            continue
        msg = d.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return i
        if isinstance(content, list):
            if any(c.get("type") != "tool_result" for c in content):
                return i
    return -1


def collect_turn(lines: list[str], start_idx: int) -> tuple[str, list[str]]:
    """Return (assistant_text, edited_file_paths) for the turn."""
    texts: list[str] = []
    files: list[str] = []
    for line in lines[start_idx + 1:]:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("type") != "assistant":
            continue
        msg = d.get("message") or {}
        for c in msg.get("content") or []:
            ct = c.get("type")
            if ct == "text":
                texts.append(c.get("text") or "")
            elif ct == "tool_use":
                if c.get("name") in ("Write", "Edit", "NotebookEdit"):
                    fp = (c.get("input") or {}).get("file_path")
                    if isinstance(fp, str) and fp:
                        files.append(fp)
    return "\n".join(texts), files


def read_verdict(repo: pathlib.Path) -> str | None:
    f = repo / ".second-opinion.md"
    if not f.exists():
        return None
    try:
        text = f.read_text(encoding="utf-8", errors="replace")[:4000]
    except Exception:
        return None
    m = re.search(r"^\s*verdict:\s*([A-Za-z_]+)", text, re.MULTILINE)
    if not m:
        m = re.search(r"VERDICT:\s*([A-Za-z_]+)", text)
    return m.group(1).strip().upper() if m else None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}
    transcript = resolve_transcript_path(payload)
    if transcript is None:
        return 0
    try:
        lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return 0
    last_user = find_last_user_idx(lines)
    if last_user < 0:
        return 0

    text, edited = collect_turn(lines, last_user)
    if not text:
        return 0
    if any(kw.lower() in text.lower() for kw in BYPASS_KEYWORDS):
        return 0
    if not any(re.search(p, text, re.IGNORECASE) for p in COMPLETION_PATTERNS):
        return 0  # no completion claim → nothing to gate

    code_files, sensitive = classify_paths(edited)
    # Substantial if the turn edited many code files / a sensitive path, OR the
    # repo diff is substantial. Need at least one code file edited this turn so
    # the gate is anchored to actual work (cwd-independent).
    if not code_files:
        return 0
    repo = repo_root(str(pathlib.Path(code_files[0]).parent))
    git_substantial = False
    if repo is not None:
        git_substantial, _ = is_substantial(str(repo))
    substantial = sensitive or len(code_files) >= 3 or git_substantial
    if not substantial:
        return 0

    if repo is None:
        return 0  # cannot locate review artifact reliably
    verdict = read_verdict(repo)
    if verdict in VERDICT_OK:
        return 0  # adversarial review present & approved → pass

    # ── nag (log-only by default) ──
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LOG_DIR / "adversarial-review.jsonl").open("a") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "session_id": payload.get("session_id"),
                "repo": str(repo),
                "code_files": code_files[:20],
                "sensitive": sensitive,
                "verdict_found": verdict,
                "sample_text": text[-500:],
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass

    sys.stderr.write(
        "⚠️  adversarial-review-gate: substantial code change claimed done "
        "without an approved adversarial review.\n"
        f"   repo        : {repo}\n"
        f"   code files  : {len(code_files)}"
        f"{' (sensitive path!)' if sensitive else ''}\n"
        f"   .second-opinion.md verdict: {verdict or 'MISSING'}\n"
        "   → Run the `adversarial-review` Workflow (N skeptics try to break the "
        "diff) or comad-second-opinion / codex challenge, then re-state.\n"
        "   Genuine WIP? add a bypass keyword (WIP / 초안 / '리뷰 예정').\n"
        f"   Logged to {LOG_DIR}/adversarial-review.jsonl\n"
    )
    return 2 if BLOCK_MODE else 0


if __name__ == "__main__":
    sys.exit(main())
