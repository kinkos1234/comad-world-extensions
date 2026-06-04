#!/usr/bin/env python3
"""comad-ci-healer · classify.py

실패한 run 의 로그를 받아 카테고리로 분류한다.
카테고리: lint | test | build | deploy | flaky | unknown

사용:
  python3 classify.py --repo OWNER/R --run-id 123456
  python3 classify.py --log-file /path/to/log.txt   # 로컬 로그 직접 분류
출력: JSON {category, signals[], summary, log_excerpt}
"""
import argparse
import json
import re
import subprocess
import sys

# (category, [정규식 시그널]) — 위에서부터 우선. test 가 lint 보다 우선순위 낮음에 주의.
SIGNATURES = [
    ("deploy", [
        r"\bflyctl\b.*\berror", r"deploy(ment)? failed", r"failed to deploy",
        r"vercel.*error", r"release command failed",
        # Fly 인프라성 배포 실패 (health-check timeout 등)
        r"timeout reached waiting for health checks",
        r"unrecoverable error", r"failed to get vm",
        r"api\.machines\.dev", r"smoke check(s)? failed",
        r"machine .* failed to (start|reach)",
    ]),
    ("lint", [
        r"eslint", r"--max-warnings", r"\bprettier\b", r"ruff\b", r"\bflake8\b",
        r"\bblack\b.*would reformat", r"lint(ing)? (error|failed)",
        r"\bwarning\b.*\bproblems?\b",
    ]),
    ("build", [
        r"\btsc\b.*error TS\d+", r"error TS\d+", r"type error",
        r"build failed", r"webpack.*error", r"Module not found",
        r"Cannot find module", r"compilation failed", r"next build.*failed",
        r"syntax error near", r"unexpected (token|end of file)",
        r"line \d+: syntax error", r"shellcheck",
    ]),
    ("test", [
        r"\bjest\b", r"\bvitest\b", r"\bpytest\b", r"\d+ (failed|failing)",
        r"Tests:.*failed", r"AssertionError", r"expect\(", r"test(s)? failed",
    ]),
    ("flaky", [
        r"ETIMEDOUT", r"ECONNRESET", r"socket hang up", r"network.*timeout",
        r"rate limit", r"503 Service", r"runner.*lost communication",
        r"context deadline exceeded", r"i/o timeout",
        r"TLS handshake timeout", r"connection reset by peer",
        r"net/http: request canceled",
    ]),
]


def fetch_log(repo, run_id):
    try:
        out = subprocess.run(
            ["gh", "run", "view", str(run_id), "--repo", repo, "--log-failed"],
            capture_output=True, text=True, timeout=120,
        )
        if out.returncode != 0:
            # --log-failed 가 비면 전체 로그 시도
            out = subprocess.run(
                ["gh", "run", "view", str(run_id), "--repo", repo, "--log"],
                capture_output=True, text=True, timeout=120,
            )
        return out.stdout
    except subprocess.TimeoutExpired:
        return ""


def classify(log):
    # 대소문자 무시 매칭 (로그를 소문자화하면 TS/ETIMEDOUT/TLS 등 대문자 패턴이 안 맞음)
    matched = []
    for category, patterns in SIGNATURES:
        hits = [p for p in patterns if re.search(p, log, re.IGNORECASE)]
        if hits:
            matched.append((category, hits))

    if not matched:
        category, signals = "unknown", []
    else:
        # 가장 많은 시그널이 잡힌 카테고리 우선, 동률이면 SIGNATURES 순서
        matched.sort(key=lambda m: -len(m[1]))
        category, signals = matched[0][0], matched[0][1]

    # 로그 발췌: error/failed 가 처음 등장하는 부분 주변
    excerpt = ""
    m = re.search(r"(?im)^.*(error|failed|✗|×).*$", log)
    if m:
        start = max(0, m.start() - 200)
        excerpt = log[start:m.end() + 600].strip()

    return {
        "category": category,
        "signals": signals,
        "all_matches": [c for c, _ in matched],
        "summary": f"{category} 실패 (시그널 {len(signals)}개)",
        "log_excerpt": excerpt[:1200],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo")
    ap.add_argument("--run-id")
    ap.add_argument("--log-file")
    args = ap.parse_args()

    if args.log_file:
        log = open(args.log_file).read()
    elif args.repo and args.run_id:
        log = fetch_log(args.repo, args.run_id)
    else:
        print("--repo+--run-id 또는 --log-file 필요", file=sys.stderr)
        sys.exit(2)

    if not log.strip():
        print(json.dumps({"category": "unknown", "signals": [],
                          "summary": "로그 비어있음", "log_excerpt": ""},
                         ensure_ascii=False))
        return

    print(json.dumps(classify(log), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
