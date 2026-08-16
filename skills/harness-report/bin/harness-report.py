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
import time
import sys

HOME = pathlib.Path(os.environ.get("HOME", "/"))
COMAD = HOME / ".claude" / ".comad"
TSV = COMAD / "results.tsv"
HOOK_PRE = HOME / ".claude" / "hooks" / "pre-tool-use"
HOOK_STOP = HOME / ".claude" / "hooks" / "stop"
PENDING = COMAD / "pending"
# T6 파이프라인(comad-learn)은 pending/ 아래로 옮긴다 — 처리분 _processed/, 기각분 _rejected/.
# 예전 상수는 COMAD/"_processed" 를 가리켰는데 그 디렉터리는 2026-04-25 이후 안 쓰인다.
# 그 탓에 pending_processed 가 3개월간 67 고정이었고 composite score 의 throughput 축이
# 통째로 틀린 값을 쓰고 있었다 (2026-08-02 발견).
PROCESSED = COMAD / "pending" / "_processed"
REJECTED = COMAD / "pending" / "_rejected"
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
    # R6 outcome 지표 (2026-06-11) — 프로세스 점수와 달리 "산출물이 좋아졌나"의
    # 프록시. composite 에 미합산 (게이트 아님, 4주+ 베이스라인 후 추세 판독용).
    "fix_ratio", "ci_first_pass",
    # 2026-08-16 v2 — score 는 이제 결과 중심(composite_score_v2). 활동량 점수는 score_v1 에
    # 계속 기록해 4,500행 추세를 끊지 않는다. health 는 활동량 pass/fail.
    "unbacked_claims", "score_v1", "health",
]

# R6 outcome 지표 대상 (로컬 git, gh 레포). 둘 다 soft-fail.
OUTCOME_LOCAL_REPOS = [
    HOME / "Programmer/01-comad/comad-world",
    HOME / "Programmer/03-web/one-k-web",
    HOME / "Programmer/03-web/VidGuide",
    HOME / "Programmer/03-web/unispa",
]
OUTCOME_GH_REPOS = [
    "kinkos1234/one-k-web", "kinkos1234/thegongsi",
    "kinkos1234/VidGuide", "kinkos1234/comad-world",
]
OUTCOME_CACHE = COMAD / "outcome-cache.json"
OUTCOME_CACHE_TTL_S = 6 * 3600  # 30분 tick 마다 git/gh 를 두드리지 않도록 6h 캐시


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
    """(전체 포착 신호, 처리 완료 수).

    기각(_rejected)도 "사람이 판단을 끝낸 것"이라 처리에 포함한다. 빼두면 승격되지
    않은 신호가 영원히 미처리로 남아 throughput 이 실제보다 낮게 나온다.
    """
    pending = sum(1 for _ in PENDING.glob("*.json")) if PENDING.exists() else 0
    processed = sum(1 for _ in PROCESSED.glob("*.json")) if PROCESSED.exists() else 0
    rejected = sum(1 for _ in REJECTED.glob("*.json")) if REJECTED.exists() else 0
    handled = processed + rejected
    return pending + handled, handled


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


def count_unbacked_claims(days: int = 7) -> int:
    """최근 `days` 일 동안 자기검증 훅이 잡은 **근거 없는 주장** 건수 (낮을수록 좋음).

    왜 이 지표인가: 처음엔 "최근 30일 새 재발 패턴 수"를 쓰려 했는데, 그 값은 주간
    자가학습이 메모리를 **일괄 승격**할 때 한꺼번에 뛴다(2026-08-15: 하루에 15건).
    사건 수가 아니라 배치 일정에 흔들리는 값은 계기로 쓸 수 없다.
    대신 stop 훅들이 남기는 per-incident 로그를 센다 — "모두 통과했다"는 주장에 검증이
    없었다(claim-done) · 수치를 근거 없이 단정했다(numeric-claim) · 수렴을 조기 선언했다
    (premature-completion). 이건 하네스가 줄이려는 행동 그 자체다.
    """
    cutoff = time.time() - days * 86400
    total = 0
    for name in ("claim-done", "numeric-claim", "premature-completion"):
        path = COMAD / "pending" / f"{name}.jsonl"
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                raw = rec.get("ts") or rec.get("at") or ""
                try:
                    when = datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                except ValueError:
                    continue
                if when.timestamp() >= cutoff:
                    total += 1
        except OSError:
            pass
    return total


def count_second_opinion() -> int:
    """Count projects (under ~/Programmer) that have a .second-opinion.md file.

    2026-08-16 수정 — 이 축이 4개월간 사실상 항상 0 이었다. 원인은 "안 썼다"가 아니라
    **측정이 실패하고 있었다**: 전체 트리 find 가 10초 타임아웃을 넘겨(콜드 캐시에서 재현,
    3회 연속 10.0s 클립) except 절이 그걸 0 으로 눌러 담았다. 실패와 0 을 구분 못 하니
    10점짜리 축이 조용히 죽었고, 그 결과 composite 상한이 90.0 으로 고정돼 정지 임계 92 를
    구조적으로 도달 불가능하게 만들었다. (빈 결과를 성공으로 읽지 말 것 — rules/sync-integrity)

    고친 것 두 가지:
      1) 탐색 범위 축소 — 이 파일은 프로젝트 루트에만 놓이므로 maxdepth 4 면 충분하다.
         무거운 디렉터리는 prune 으로 아예 들어가지 않는다(-not -path 는 순회 후 제외라 느리다).
      2) 실패를 0 으로 흘리지 않는다 — 타임아웃이면 예외를 올린다. 이 레포의 기존 원칙과 같다
         ("측정 실패를 0점으로 흘리면 루프가 영원히 안 멈춘다", loopy-era 05-verify-initial).
    """
    base = HOME / "Programmer"
    if not base.exists():
        return 0
    out = subprocess.run(
        ["find", str(base), "-maxdepth", "4",
         "(", "-name", "node_modules", "-o", "-name", ".git", "-o", "-name", ".venv",
         "-o", "-name", "dist", "-o", "-name", "build", ")", "-prune", "-o",
         "-name", ".second-opinion.md", "-print"],
        capture_output=True, text=True, timeout=30,
    )
    return sum(1 for line in out.stdout.splitlines() if line.strip())


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


def outcome_metrics() -> tuple[str, str]:
    """R6 outcome 프록시 2종. 반환은 문자열 — '' = 데이터 없음 (0 과 구분).

    fix_ratio:    최근 7일 주요 레포 커밋 중 fix:/bugfix: 비율 (낮을수록 좋음)
    ci_first_pass: 최근 GH Actions run 중 1차 시도 성공 비율 (높을수록 좋음)
    """
    # 6h 캐시 (30분 tick 부하 방지)
    try:
        cache = json.loads(OUTCOME_CACHE.read_text())
        age = datetime.datetime.now(datetime.timezone.utc).timestamp() - cache["ts"]
        if age < OUTCOME_CACHE_TTL_S:
            return cache["fix_ratio"], cache["ci_first_pass"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        pass

    fix_n = total_n = 0
    for repo in OUTCOME_LOCAL_REPOS:
        if not (repo / ".git").exists():
            continue
        try:
            out = subprocess.run(
                ["git", "-C", str(repo), "log", "--since=7 days ago", "--pretty=%s"],
                capture_output=True, text=True, timeout=15)
            for subj in out.stdout.splitlines():
                total_n += 1
                if re.match(r"^(fix|bugfix)\b", subj.strip(), re.IGNORECASE):
                    fix_n += 1
        except (subprocess.TimeoutExpired, OSError):
            pass
    fix_ratio = f"{fix_n / total_n:.3f}" if total_n else ""

    first_pass = completed = 0
    for gh_repo in OUTCOME_GH_REPOS:
        try:
            out = subprocess.run(
                ["gh", "api", f"repos/{gh_repo}/actions/runs?per_page=20",
                 "--jq", "[.workflow_runs[] | select(.status==\"completed\") | {c: .conclusion, a: .run_attempt}]"],
                capture_output=True, text=True, timeout=20)
            for run in json.loads(out.stdout or "[]"):
                completed += 1
                if run.get("c") == "success" and run.get("a") == 1:
                    first_pass += 1
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
            pass
    ci_first = f"{first_pass / completed:.3f}" if completed else ""

    try:
        OUTCOME_CACHE.write_text(json.dumps({
            "ts": datetime.datetime.now(datetime.timezone.utc).timestamp(),
            "fix_ratio": fix_ratio, "ci_first_pass": ci_first,
            "detail": {"fix_n": fix_n, "total_commits": total_n,
                       "first_pass": first_pass, "completed_runs": completed},
        }))
    except OSError:
        pass
    return fix_ratio, ci_first


def _band(value: float, best: float, worst: float, points: float) -> float:
    """best 이상(또는 이하)이면 만점, worst 를 넘으면 0, 사이는 선형."""
    if best == worst:
        return points if value == best else 0.0
    if best < worst:                      # 낮을수록 좋음
        if value <= best: return points
        if value >= worst: return 0.0
        return points * (worst - value) / (worst - best)
    if value >= best: return points       # 높을수록 좋음
    if value <= worst: return 0.0
    return points * (value - worst) / (best - worst)


# v2 임계 — 전부 조정 가능한 판단값이다. 근거는 2026-08-16 실측:
#   fix_ratio 는 0.40(평시) ~ 0.75(수정 몰린 날) 사이에서 실제로 움직였다.
#   ci_first_pass 는 0.986~0.99 로 이미 높다 — 0.95 를 바닥이 아니라 만점선으로 둔다.
V2_BANDS = {
    # 최근 7일 근거 없는 주장 건수: 0건 만점, 30건 이상 0점 (2026-08-16 실측 23건)
    "unbacked_claims": (0.0, 30.0, 40.0),
    "fix_ratio":       (0.20, 0.60, 30.0),  # 낮을수록 좋음
    "ci_first_pass":   (0.95, 0.70, 30.0),  # 높을수록 좋음
}


def composite_score_v2(metrics: dict) -> tuple[float, str]:
    """결과 중심 0-100 점수. 반환 (score, note).

    왜 바꿨나 (2026-08-16): v1 5축은 전부 **활동량 카운터**였고 2026-08 기준 전 축이 만점
    (100.0)이라 변별력이 0 이었다. 게다가 second_opinion 축은 4개월간 측정 실패를 0 으로
    눌러 담고 있어 상한이 90.0 으로 묶여 있었고, 그게 "정지 임계 92 를 못 넘는 정체"로
    보였다. 계기가 고장 나 있었던 것이지 개선이 소진된 게 아니었다.

    v2 는 "돌아가고 있나"(활동량)를 점수에서 빼고 "결과가 좋아졌나"만 센다.
    활동량은 health() 가 pass/fail 로 따로 본다 — 멈추면 그건 점수가 아니라 장애다.

    측정 불가 축은 **0점으로 흘리지 않는다.** 가용 축만으로 정규화하고 note 에 partial 을
    남긴다 — 실패를 낮은 점수로 바꾸면 "고장났는데 열심히 한 것"처럼 보인다.
    """
    got, avail, missing = 0.0, 0.0, []
    for key, (best, worst, pts) in V2_BANDS.items():
        raw = metrics.get(key)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            missing.append(key)
            continue
        got += _band(val, best, worst, pts)
        avail += pts
    if avail == 0:
        return 0.0, "measure-failed:all"
    score = round(got * 100.0 / avail, 1)
    return score, ("partial:" + ",".join(missing) if missing else "")


def health(metrics: dict) -> tuple[bool, str]:
    """활동량 = 점수가 아니라 헬스체크. 멈춰 있으면 장애로 본다."""
    fails = []
    if metrics["hard_count"] < metrics["hard_target"]:
        fails.append(f"hard {metrics['hard_count']}/{metrics['hard_target']}")
    total = max(1, metrics["pending_total"])
    if metrics["pending_processed"] / total < 0.9:
        fails.append(f"pending {metrics['pending_processed']}/{total}")
    if metrics["evolve_applied"] <= 0:
        fails.append("evolve 0")
    return (not fails), ("ok" if not fails else "; ".join(fails))


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
    m["unbacked_claims"] = count_unbacked_claims(7)
    m["score_v1"] = composite_score(m)   # 옛 활동량 점수 — 추세 연속성 위해 계속 기록만 한다
    m["fix_ratio"], m["ci_first_pass"] = outcome_metrics()  # v2 가 쓰므로 먼저 잰다
    v2, v2note = composite_score_v2(m)
    m["score"] = v2                      # 루프가 읽는 값 = v2 (결과 중심)
    ok, hnote = health(m)
    m["health"] = "ok" if ok else hnote
    if v2note or not ok:
        m["notes"] = " · ".join(x for x in (notes, v2note, ("" if ok else "health:" + hnote)) if x)
    tokens_24h, usd_24h = get_cost()
    m["tokens_24h"] = tokens_24h
    m["usd_24h"] = usd_24h
    return m


_NUM_INT = ("hard_count", "hard_target", "pending_total", "pending_processed",
            "recurring", "second_opinion", "evolve_applied", "evolve_rejected",
            "tokens_24h", "unbacked_claims")
_NUM_FLOAT = ("score", "usd_24h", "score_v1")


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
    # v2 (2026-08-16) — 점수는 **결과**만 센다. 활동량은 아래 health 줄에 pass/fail 로.
    ub = m.get("unbacked_claims")
    lines = [
        f"Harness Report — {m['ts']}",
        f"  근거 없는 주장(7일) : {ub}건  → {_band(float(ub), *V2_BANDS['unbacked_claims']):.1f}/40"
        if ub is not None else "  근거 없는 주장(7일) : (측정 실패)",
        f"  fix_ratio (↓좋음)  : {m.get('fix_ratio') or '—'}"
        + (f"  → {_band(float(m['fix_ratio']), *V2_BANDS['fix_ratio']):.1f}/30" if m.get("fix_ratio") else ""),
        f"  ci_first_pass(↑좋음): {m.get('ci_first_pass') or '—'}"
        + (f"  → {_band(float(m['ci_first_pass']), *V2_BANDS['ci_first_pass']):.1f}/30" if m.get("ci_first_pass") else ""),
        f"  ─────────────────────────────────",
        f"  Score (v2, 결과)   : {m['score']:.1f} / 100",
        f"  health (활동량)    : {m.get('health','?')}"
        f"   [hard {m['hard_count']}/{m['hard_target']} · pending {m['pending_processed']}/{m['pending_total']}"
        f" · evolve {m['evolve_applied']} · 2nd-op {m['second_opinion']}]",
        f"  (참고) v1 활동량 점수: {m.get('score_v1','—')} — 5축 전부 포화라 변별력이 없어 2026-08-16 에 점수에서 내렸다",
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
    # R6 outcome 블록 (composite 와 분리 — "산출물이 좋아졌나" 추세용)
    fr, cf = m.get("fix_ratio") or "", m.get("ci_first_pass") or ""
    if fr or cf:
        lines.append(f"  ─────────────────────────────────")
        lines.append(f"  Outcome (R6, 비게이트): fix_ratio={fr or 'n/a'} (7d, ↓좋음)  ·  ci_first_pass={cf or 'n/a'} (↑좋음)")
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

    # v1→v2 전환 행은 회귀가 아니다 — 척도가 바뀐 것이라 비교 자체가 성립하지 않는다.
    # 이전 행에 score_v1 컬럼이 없으면(= v2 이전 기록) 회귀 판정을 건너뛴다.
    if prev and not prev.get("score_v1"):
        return 0
    if prev and float(prev["score"]) - m["score"] >= 2.0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
