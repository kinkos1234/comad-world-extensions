#!/usr/bin/env python3
"""harness-report · collect-cost.py

Claude Code 트랜스크립트(~/.claude/projects/*/*.jsonl)의 usage 를 윈도우 집계.
Max 구독은 정액이라 비용은 **notional list-price**(효율 추적용 상대지표). 실제 청구 아님.

사용:
  python3 collect-cost.py            # 최근 24h, 사람용 요약
  python3 collect-cost.py --hours 24 --json
"""
import argparse
import datetime as dt
import glob
import json
import os

# per-million-token notional USD (2026 list price 근사; 정확 청구 아님). prefix 매칭.
PRICING = {
    "opus":   {"in": 15.0, "out": 75.0, "cache_w": 18.75, "cache_r": 1.50},
    "sonnet": {"in": 3.0,  "out": 15.0, "cache_w": 3.75,  "cache_r": 0.30},
    "haiku":  {"in": 1.0,  "out": 5.0,  "cache_w": 1.25,  "cache_r": 0.10},
}
PROJECTS = os.path.expanduser("~/.claude/projects")


def price_for(model):
    m = (model or "").lower()
    for k, v in PRICING.items():
        if k in m:
            return v, k
    return PRICING["opus"], "opus?"  # 미상은 opus 로 보수적 추정


def parse_ts(s):
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def collect(hours):
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=hours)
    cutoff_epoch = cutoff.timestamp()

    agg = {}  # model_key → token sums
    files = glob.glob(os.path.join(PROJECTS, "*", "*.jsonl"))
    scanned = 0
    for fp in files:
        try:
            if os.path.getmtime(fp) < cutoff_epoch - 3600:  # mtime 필터(1h 버퍼)
                continue
        except OSError:
            continue
        scanned += 1
        try:
            with open(fp, errors="ignore") as f:
                for line in f:
                    if '"usage"' not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    ts = parse_ts(o.get("timestamp", ""))
                    if not ts or ts < cutoff:
                        continue
                    msg = o.get("message") or {}
                    u = msg.get("usage") or {}
                    if not u:
                        continue
                    _, key = price_for(msg.get("model"))
                    a = agg.setdefault(key, {"in": 0, "out": 0, "cache_w": 0,
                                             "cache_r": 0, "msgs": 0})
                    a["in"] += u.get("input_tokens", 0)
                    a["out"] += u.get("output_tokens", 0)
                    a["cache_w"] += u.get("cache_creation_input_tokens", 0)
                    a["cache_r"] += u.get("cache_read_input_tokens", 0)
                    a["msgs"] += 1
        except OSError:
            continue

    # 비용 계산
    total = {"in": 0, "out": 0, "cache_w": 0, "cache_r": 0, "msgs": 0, "usd": 0.0}
    by_model = {}
    for key, a in agg.items():
        p = PRICING.get(key.rstrip("?"), PRICING["opus"])
        usd = (a["in"] * p["in"] + a["out"] * p["out"]
               + a["cache_w"] * p["cache_w"] + a["cache_r"] * p["cache_r"]) / 1_000_000
        by_model[key] = {**a, "usd": round(usd, 3)}
        for k in ("in", "out", "cache_w", "cache_r", "msgs"):
            total[k] += a[k]
        total["usd"] += usd
    total["usd"] = round(total["usd"], 2)
    total["tokens_total"] = total["in"] + total["out"] + total["cache_w"] + total["cache_r"]
    return {"hours": hours, "files_scanned": scanned, "total": total, "by_model": by_model}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = collect(args.hours)

    if args.json:
        print(json.dumps(r, ensure_ascii=False))
        return

    t = r["total"]
    print(f"Cost (notional list-price) — 최근 {args.hours:g}h  ({r['files_scanned']} 세션 스캔)")
    print(f"  input        : {t['in']:>12,}")
    print(f"  output       : {t['out']:>12,}")
    print(f"  cache write  : {t['cache_w']:>12,}")
    print(f"  cache read   : {t['cache_r']:>12,}")
    print(f"  ─────────────────────────────")
    print(f"  tokens total : {t['tokens_total']:>12,}  ({t['msgs']} msgs)")
    print(f"  notional USD : ${t['usd']:>11,.2f}")
    if r["by_model"]:
        print("  by model:")
        for k, a in sorted(r["by_model"].items(), key=lambda x: -x[1]["usd"]):
            print(f"    {k:<8} ${a['usd']:>8,.2f}  ({a['in']+a['out']+a['cache_w']+a['cache_r']:,} tok)")


if __name__ == "__main__":
    main()
