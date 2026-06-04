#!/usr/bin/env python3
"""harness-report · dashboard.py

results.tsv → 자립형 HTML 대시보드(점수 추세 + notional 비용 + efficiency).
comad-infographic 의존 없음(인라인 SVG). 출력 ~/.claude/.comad/reports/dashboard.html

사용: python3 dashboard.py [--rows 40] [--open]
"""
import argparse
import os
import pathlib
import webbrowser

TSV = pathlib.Path(os.path.expanduser("~/.claude/.comad/results.tsv"))
OUT = pathlib.Path(os.path.expanduser("~/.claude/.comad/reports/dashboard.html"))


def load(rows_n):
    if not TSV.exists():
        return []
    lines = TSV.read_text().splitlines()
    header = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        p = ln.split("\t")
        if len(p) == len(header):
            rows.append(dict(zip(header, p)))
    return rows[-rows_n:]


def num(v, f=float, d=0):
    try:
        return f(v) if v not in (None, "") else d
    except (ValueError, TypeError):
        return d


def sparkline(vals, w=720, h=120, color="#4f8cff", fill=True):
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    n = len(vals)
    pts = [(i * w / max(1, n - 1), h - (v - lo) / rng * (h - 16) - 8) for i, v in enumerate(vals)]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    area = ""
    if fill:
        area = f'<path d="{path} L{w},{h} L0,{h} Z" fill="{color}" opacity="0.12"/>'
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{color}"/>' for x, y in pts[-1:])
    return f'<svg viewBox="0 0 {w} {h}" width="100%" preserveAspectRatio="none">{area}<path d="{path}" fill="none" stroke="{color}" stroke-width="2"/>{dots}</svg>'


def bars(vals, w=720, h=120, color="#ff9f43"):
    if not vals:
        return ""
    hi = max(vals) or 1
    n = len(vals)
    bw = w / n * 0.7
    gap = w / n
    rects = ""
    for i, v in enumerate(vals):
        bh = v / hi * (h - 12)
        rects += f'<rect x="{i*gap+gap*0.15:.1f}" y="{h-bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{color}" opacity="0.8" rx="1"/>'
    return f'<svg viewBox="0 0 {w} {h}" width="100%" preserveAspectRatio="none">{rects}</svg>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=40)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    rows = load(args.rows)
    if not rows:
        print("no data")
        return

    scores = [num(r.get("score")) for r in rows]
    cost_rows = [r for r in rows if num(r.get("usd_24h")) > 0]
    usds = [num(r.get("usd_24h")) for r in cost_rows]
    last = rows[-1]
    score = num(last.get("score"))
    usd = num(last.get("usd_24h"))
    tok = num(last.get("tokens_24h"), int)
    eff = score / (tok / 1_000_000) if tok else 0
    first_score = scores[0] if scores else 0
    delta = score - first_score

    html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Comad Harness Dashboard</title>
<style>
:root{{--bg:#0f1115;--card:#181b22;--mut:#8b93a7;--fg:#e8ecf4;--ac:#4f8cff;--wn:#ff9f43}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Pretendard,sans-serif;padding:32px}}
h1{{font-size:20px;margin:0 0 4px}}.sub{{color:var(--mut);font-size:12px;margin-bottom:24px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}}
.kpi{{background:var(--card);border-radius:12px;padding:18px}}
.kpi .v{{font-size:28px;font-weight:700}}.kpi .l{{color:var(--mut);font-size:12px;margin-top:4px}}
.card{{background:var(--card);border-radius:12px;padding:20px;margin-bottom:20px}}
.card h2{{font-size:13px;color:var(--mut);margin:0 0 12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}}
.up{{color:#46d39a}}.down{{color:#ff6b6b}}.note{{color:var(--mut);font-size:11px;margin-top:8px}}
</style></head><body>
<h1>Comad Harness Dashboard</h1>
<div class="sub">최근 {len(rows)}회 측정 · {last.get('ts','')} · 비용은 notional list-price(정액구독≠실청구)</div>
<div class="grid">
<div class="kpi"><div class="v">{score:.1f}</div><div class="l">Composite Score / 100 <span class="{'up' if delta>=0 else 'down'}">{delta:+.1f}</span></div></div>
<div class="kpi"><div class="v">{tok/1_000_000:.1f}M</div><div class="l">Tokens (24h)</div></div>
<div class="kpi"><div class="v">${usd:,.0f}</div><div class="l">Notional Cost (24h)</div></div>
<div class="kpi"><div class="v">{eff:.2f}</div><div class="l">Efficiency (score/Mtok)</div></div>
</div>
<div class="card"><h2>Composite Score — 추세</h2>{sparkline(scores)}</div>
<div class="card"><h2>Notional Cost (24h, $) — 추세</h2>{bars(usds) if usds else '<div class="note">비용 데이터 누적 중(첫 측정 이후부터 기록)</div>'}</div>
<div class="note">생성: harness-report/dashboard.py · 단일 진실원 results.tsv</div>
</body></html>"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    print(f"dashboard → {OUT}")
    if args.open:
        webbrowser.open(f"file://{OUT}")


if __name__ == "__main__":
    main()
