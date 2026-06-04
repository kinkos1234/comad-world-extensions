#!/usr/bin/env python3
"""harness-report — Loopy-Era 5-axis health score + results.tsv trend.

Measures the harness state and appends one row to ~/.claude/.comad/results.tsv.
Idempotent on the same minute (overwrites if last row's ts matches).

Usage:
    harness-report.py                 # measure + append + print summary
    harness-report.py --read-only     # print last row only
    harness-report.py --history 10    # print last N rows
    harness-report.py --json          # JSON output

Exit codes:
    0  measurement OK
    1  measurement OK but score regression vs previous row (>=2 points)
    2  failed to measure
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys

HOME = pathlib.Path(os.environ.get("HOME", "/"))
COMAD = HOME / ".claude" / ".comad"
TSV = COMAD / "results.tsv"
HOOK_PRE = HOME / ".claude" / "hooks" / "pre-tool-use"
HOOK_STOP = HOME / ".claude" / "hooks" / "stop"
PENDING = COMAD / "pending"
PROCESSED = COMAD / "_processed"
EVOLVE = COMAD / "evolve"
PROJECTS = HOME / ".claude" / "projects"

HARD_TARGET = 12  # site-defined target
COST_WINDOW_H = 24  # notional cost 집계 윈도우
COLUMNS = [
    "ts", "hard_count", "hard_target",
    "pending_total", "pending_processed",
    "recurring", "second_opinion",
    "evolve_applied", "evolve_rejected",
    "score", "tokens_24h", "usd_24h", "notes",
]


def count_hard_hooks() -> int:
    """Count Python hook files in pre-tool-use + stop dirs.

    Each .py corresponds to a hook capable of `exit 2` blocking. Shell wrappers
    are not counted separately (they delegate to .py)."""
    n = 0
    for d in (HOOK_PRE, HOOK_STOP):
        if d.exists():
            n += sum(1 for f in d.glob("*.py") if not f.name.startswith("_"))
    return n


def count_pending() -> tuple[int, int]:
    pending = sum(1 for _ in PENDING.glob("*.json")) if PENDING.exists() else 0
    processed = sum(1 for _ in PROCESSED.glob("*.json")) if PROCESSED.exists() else 0
    return pending + processed, processed


def count_recurring() -> int:
    """feedback_*.md files with Seen >= 2 occurrence."""
    pattern = re.compile(r"Seen\s+([2-9]|[1-9]\d+)\s*회")
    n = 0
    if not PROJECTS.exists():
        return 0
    for memdir in PROJECTS.glob("*/memory"):
        for md in memdir.glob("feedback_*.md"):
            try:
                if pattern.search(md.read_text(encoding="utf-8", errors="replace")):
                    n += 1
            except OSError:
                pass
    return n


def count_second_opinion() -> int:
    """Count projects (under ~/Programmer) that have a .second-opinion.md file."""
    base = HOME / "Programmer"
    if not base.exists():
        return 0
    try:
        out = subprocess.run(
            ["find", str(base), "-name", ".second-opinion.md",
             "-not", "-path", "*/node_modules/*",
             "-not", "-path", "*/.venv/*"],
            capture_output=True, text=True, timeout=10,
        )
        return sum(1 for line in out.stdout.splitlines() if line.strip())
    except (subprocess.TimeoutExpired, OSError):
        return 0


def count_evolve() -> tuple[int, int]:
    applied_dir = EVOLVE / "applied"
    rejected_dir = EVOLVE / "rejected"
    applied = sum(1 for _ in applied_dir.iterdir()) if applied_dir.exists() else 0
    rejected = sum(1 for _ in rejected_dir.iterdir()) if rejected_dir.exists() else 0
    return applied, rejected


def get_cost(hours: int = COST_WINDOW_H) -> tuple[int, float]:
    """collect-cost.py 호출 → (tokens_total, notional_usd). 실패 시 (0, 0.0).

    notional list-price (Max 구독은 정액 → 실제 청구 아님, 효율 추적용)."""
    script = pathlib.Path(__file__).parent / "collect-cost.py"
    try:
        out = subprocess.run(
            [sys.executable, str(script), "--hours", str(hours), "--json"],
            capture_output=True, text=True, timeout=30,
        )
        d = json.loads(out.stdout)
        return d["total"]["tokens_total"], round(d["total"]["usd"], 2)
    except Exception:
        return 0, 0.0


def composite_score(metrics: dict) -> float:
    """Weighted 0-100 composite.

    HARD coverage:      30 * (hard_count / hard_target) capped at 1.0
    Pending throughput: 30 * (processed / max(1, total))
    Recurring:          20 * min(1.0, recurring / 10)
    Second-opinion:     10 * (1 if >0 else 0)
    Evolve activity:    10 * min(1.0, applied / 5)
    """
    hard_pct = min(1.0, metrics["hard_count"] / metrics["hard_target"])
    total = max(1, metrics["pending_total"])
    pending_pct = metrics["pending_processed"] / total
    recurring_pct = min(1.0, metrics["recurring"] / 10)
    so_score = 1.0 if metrics["second_opinion"] > 0 else 0.0
    evolve_pct = min(1.0, metrics["evolve_applied"] / 5)
    return round(
        30 * hard_pct
        + 30 * pending_pct
        + 20 * recurring_pct
        + 10 * so_score
        + 10 * evolve_pct,
        1,
    )


def measure(notes: str = "") -> dict:
    pending_total, pending_processed = count_pending()
    evolve_applied, evolve_rejected = count_evolve()
    m = {
        "ts": datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%MZ"),
        "hard_count": count_hard_hooks(),
        "hard_target": HARD_TARGET,
        "pending_total": pending_total,
        "pending_processed": pending_processed,
        "recurring": count_recurring(),
        "second_opinion": count_second_opinion(),
        "evolve_applied": evolve_applied,
        "evolve_rejected": evolve_rejected,
        "notes": notes,
    }
    m["score"] = composite_score(m)  # 비용은 composite 에 미합산 (품질≠비용)
    tokens_24h, usd_24h = get_cost()
    m["tokens_24h"] = tokens_24h
    m["usd_24h"] = usd_24h
    return m


_NUM_INT = ("hard_count", "hard_target", "pending_total", "pending_processed",
            "recurring", "second_opinion", "evolve_applied", "evolve_rejected",
            "tokens_24h")
_NUM_FLOAT = ("score", "usd_24h")


def coerce_row(row: dict) -> dict:
    """TSV 행(전부 str)을 숫자 필드로 변환. 빈칸/오류는 0. render_summary 용."""
    out = dict(row)
    for k in _NUM_INT:
        try:
            out[k] = int(row.get(k) or 0)
        except (ValueError, TypeError):
            out[k] = 0
    for k in _NUM_FLOAT:
        try:
            out[k] = float(row.get(k) or 0)
        except (ValueError, TypeError):
            out[k] = 0.0
    return out


def read_tsv() -> list[dict]:
    if not TSV.exists():
        return []
    rows = []
    with TSV.open() as f:
        header = f.readline().rstrip("\n").split("\t")
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == len(header):
                rows.append(dict(zip(header, parts)))
    return rows


def migrate_tsv() -> None:
    """기존 헤더가 COLUMNS 와 다르면 새 컬럼을 ''(빈칸)로 backfill 해 재작성."""
    if not TSV.exists():
        return
    with TSV.open() as f:
        header = f.readline().rstrip("\n").split("\t")
    if header == COLUMNS:
        return
    old_rows = read_tsv()  # 옛 헤더 기준 dict 매핑
    with TSV.open("w") as f:
        f.write("\t".join(COLUMNS) + "\n")
        for r in old_rows:
            f.write("\t".join(str(r.get(c, "")) for c in COLUMNS) + "\n")


def append_tsv(metrics: dict) -> None:
    TSV.parent.mkdir(parents=True, exist_ok=True)
    new = not TSV.exists()
    if not new:
        migrate_tsv()  # 헤더 스키마 동기화 (하위호환)
    with TSV.open("a") as f:
        if new:
            f.write("\t".join(COLUMNS) + "\n")
        f.write("\t".join(str(metrics[c]) for c in COLUMNS) + "\n")


def render_summary(m: dict, prev: dict | None) -> str:
    lines = [
        f"Harness Report — {m['ts']}",
        f"  HARD coverage      : {m['hard_count']}/{m['hard_target']}  ({100*m['hard_count']/m['hard_target']:.0f}%)",
        f"  Pending throughput : {m['pending_processed']}/{m['pending_total']}  ({100*m['pending_processed']/max(1,m['pending_total']):.0f}%)",
        f"  Recurring (Seen≥2) : {m['recurring']}/10  ({100*min(1,m['recurring']/10):.0f}%)",
        f"  Second-opinion     : {m['second_opinion']} project(s)",
        f"  Evolve activity    : applied={m['evolve_applied']} rejected={m['evolve_rejected']}",
        f"  ─────────────────────────────────",
        f"  Composite score    : {m['score']:.1f} / 100",
    ]
    if prev:
        delta = m["score"] - float(prev["score"])
        arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "·")
        lines.append(f"  vs previous        : {arrow} {delta:+.1f} (was {prev['score']})")
    # 비용 블록 (composite 와 분리된 efficiency 지표)
    tok = int(m.get("tokens_24h") or 0)
    usd = float(m.get("usd_24h") or 0)
    if tok or usd:
        eff = m["score"] / (tok / 1_000_000) if tok else 0
        lines.append(f"  ─────────────────────────────────")
        lines.append(f"  Cost (24h, notional): {tok/1_000_000:.1f}M tok  ·  ${usd:,.2f}  (list-price, 정액구독≠실청구)")
        lines.append(f"  Efficiency          : {eff:.2f} score/Mtok")
        if prev and prev.get("usd_24h"):
            try:
                du = usd - float(prev["usd_24h"])
                a2 = "▲" if du > 0 else ("▼" if du < 0 else "·")
                lines.append(f"  vs prev cost        : {a2} ${du:+,.2f}")
            except (ValueError, TypeError):
                pass
    if m.get("notes"):
        lines.append(f"  notes              : {m['notes']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--read-only", action="store_true",
                    help="Print last row only; do not append.")
    ap.add_argument("--history", type=int, default=0,
                    help="Print last N rows then exit.")
    ap.add_argument("--json", action="store_true",
                    help="Emit JSON instead of text summary.")
    ap.add_argument("--notes", default="",
                    help="Note to attach to this row (e.g. 'baseline', 'after F1').")
    args = ap.parse_args()

    if args.history > 0:
        rows = read_tsv()
        for r in rows[-args.history:]:
            print(f"{r['ts']}\t{r['score']}\t{r.get('notes','')}")
        return 0

    if args.read_only:
        rows = read_tsv()
        if not rows:
            print("(no measurements yet)")
            return 0
        last = rows[-1]
        if args.json:
            print(json.dumps(last, indent=2))
        else:
            prev = coerce_row(rows[-2]) if len(rows) >= 2 else None
            print(render_summary(coerce_row(last), prev))
        return 0

    try:
        m = measure(args.notes)
    except Exception as e:
        print(f"measurement failed: {e}", file=sys.stderr)
        return 2

    prev_rows = read_tsv()
    prev = prev_rows[-1] if prev_rows else None
    append_tsv(m)

    if args.json:
        print(json.dumps(m, indent=2))
    else:
        print(render_summary(m, prev))

    if prev and float(prev["score"]) - m["score"] >= 2.0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
