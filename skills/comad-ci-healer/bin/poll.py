#!/usr/bin/env python3
"""comad-ci-healer · poll.py

allowlist repo 들의 GH Actions 실패 run 을 수집하고 seen.json 으로 dedup 한다.
dry-run 기본: 새 실패를 JSON 으로 출력만 하고 seen 에 기록 안 함.
--commit 시 seen.json 에 기록(= 처리 착수 표시).

사용:
  python3 poll.py                 # 새 실패 목록 JSON 출력 (dedup, 비기록)
  python3 poll.py --commit        # 출력 + seen.json 기록
  python3 poll.py --repo OWNER/R  # 특정 repo 만
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config.json"


def load_config():
    cfg = json.loads(CONFIG_PATH.read_text())
    cfg["state_dir"] = os.path.expanduser(cfg["state_dir"])
    return cfg


def gh_json(args):
    """gh 호출 후 JSON 파싱. 실패 시 빈 리스트."""
    try:
        out = subprocess.run(
            ["gh", *args],
            capture_output=True, text=True, timeout=60,
        )
        if out.returncode != 0:
            print(f"[poll] gh error: {out.stderr.strip()}", file=sys.stderr)
            return []
        return json.loads(out.stdout or "[]")
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"[poll] {type(e).__name__}: {e}", file=sys.stderr)
        return []


def list_failures(repo, limit):
    fields = "databaseId,headBranch,workflowName,conclusion,headSha,createdAt,url,event"
    runs = gh_json([
        "run", "list", "--repo", repo,
        "--status", "failure", "--limit", str(limit),
        "--json", fields,
    ])
    for r in runs:
        r["repo"] = repo
        r["key"] = f"{repo}#{r['databaseId']}"
    return runs


def load_seen(state_dir):
    p = Path(state_dir) / "seen.json"
    if p.exists():
        return set(json.loads(p.read_text()))
    return set()


def save_seen(state_dir, seen):
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    p = Path(state_dir) / "seen.json"
    p.write_text(json.dumps(sorted(seen), indent=0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="seen.json 에 기록")
    ap.add_argument("--repo", help="특정 repo 만 (OWNER/REPO)")
    args = ap.parse_args()

    cfg = load_config()
    repos = [args.repo] if args.repo else cfg["repos"]
    seen = load_seen(cfg["state_dir"])

    new = []
    for repo in repos:
        for run in list_failures(repo, cfg["poll_limit"]):
            if run["key"] not in seen:
                new.append(run)

    print(json.dumps(new, indent=2, ensure_ascii=False))

    if args.commit and new:
        for run in new:
            seen.add(run["key"])
        save_seen(cfg["state_dir"], seen)
        print(f"\n[poll] {len(new)} run(s) marked seen.", file=sys.stderr)
    else:
        print(f"\n[poll] {len(new)} new failure(s) (dry-run, not committed).",
              file=sys.stderr)


if __name__ == "__main__":
    main()
