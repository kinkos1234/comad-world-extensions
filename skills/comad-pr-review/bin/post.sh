#!/usr/bin/env bash
# comad-pr-review · post.sh (2b)
# findings.json → gh 인라인 리뷰 코멘트(가능한 것) + 요약 코멘트. dedup(headSha).
#
# 사용: post.sh --repo OWNER/REPO --pr N --findings /path/findings.json
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG="${SKILL_DIR}/config.json"
cfg() { python3 -c "import json,sys;print(json.load(open('$CFG'))$1)"; }

REPO="" ; PR="" ; FINDINGS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2;;
    --pr) PR="$2"; shift 2;;
    --findings) FINDINGS="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[ -n "$REPO" ] && [ -n "$PR" ] && [ -n "$FINDINGS" ] || { echo "need --repo --pr --findings" >&2; exit 2; }

DRY_RUN="$(cfg "['dry_run']")"
MIN_SEV="$(cfg "['post_min_severity']")"
STATE_DIR="$(python3 -c "import os;print(os.path.expanduser('$(cfg "['state_dir']")'))")"
mkdir -p "$STATE_DIR"
POSTED="$STATE_DIR/posted.json"

HEAD_SHA=$(gh pr view "$PR" --repo "$REPO" --json headRefOid -q .headRefOid)
PKEY="${REPO}#${PR}#${HEAD_SHA}"

# dedup: 같은 headSha 이미 포스팅했으면 skip
ALREADY=$(python3 -c "import json,os;f='$POSTED';d=json.load(open(f)) if os.path.exists(f) else [];print('1' if '$PKEY' in d else '0')")
if [ "$ALREADY" = "1" ]; then
  echo "[post] $PKEY 이미 포스팅됨 — skip(dedup)"; exit 0
fi

if [ "$DRY_RUN" = "True" ]; then
  echo "[post] dry_run=true → 포스팅 안 함. (대상: $REPO #$PR @ ${HEAD_SHA:0:7})"
  python3 -c "import json;d=json.load(open('$FINDINGS'));print('  would post:', sum(1 for f in d['findings'] if {'blocker':0,'major':1,'minor':2,'nit':3}.get(f.get('severity','nit'),9) <= {'blocker':0,'major':1,'minor':2,'nit':3}['$MIN_SEV']),'inline +1 summary')"
  exit 0
fi

# ── 인라인 코멘트(개별 POST, 실패 시 skip) + 요약 ──────────────
python3 - "$FINDINGS" "$REPO" "$PR" "$HEAD_SHA" "$MIN_SEV" <<'PY'
import json, subprocess, sys
findings_f, repo, pr, sha, min_sev = sys.argv[1:6]
order = {"blocker":0,"major":1,"minor":2,"nit":3}
icons = {"blocker":"🔴","major":"🟠","minor":"🟡","nit":"⚪"}
d = json.load(open(findings_f))
thresh = order.get(min_sev, 1)
owner, name = repo.split("/")

posted_inline, failed_inline = 0, []
for f in d["findings"]:
    if order.get(f.get("severity","nit"),9) > thresh:
        continue
    path, line = f.get("file"), f.get("line")
    body = f"{icons.get(f.get('severity'),'')} **[{f.get('severity')}/{f.get('axis')}] {f.get('title')}**\n\n{f.get('detail','')}"
    if f.get("suggestion"):
        body += f"\n\n**제안:** {f['suggestion']}"
    body += "\n\n<sub>🤖 comad-pr-review</sub>"
    if not (path and line):
        failed_inline.append(f); continue
    # 개별 인라인 리뷰 코멘트 (diff 밖 line 이면 422 → skip)
    p = subprocess.run([
        "gh","api",f"repos/{owner}/{name}/pulls/{pr}/comments","-X","POST",
        "-f",f"body={body}","-f",f"commit_id={sha}","-f",f"path={path}",
        "-F",f"line={int(line)}","-f","side=RIGHT",
    ], capture_output=True, text=True)
    if p.returncode == 0:
        posted_inline += 1
    else:
        failed_inline.append(f)

# 요약 코멘트 (항상)
badge_counts = {}
for f in d["findings"]:
    badge_counts[f.get("severity","nit")] = badge_counts.get(f.get("severity","nit"),0)+1
badge = " · ".join(f"{icons.get(k,'')}{k}:{v}" for k,v in sorted(badge_counts.items(), key=lambda x:order.get(x[0],9))) or "발견 없음"
lines = [f"## 🤖 comad-pr-review — `{d['verdict']}`", "", f"{badge}", "", d.get("summary",""), ""]
if failed_inline:
    lines.append("### 인라인 위치 밖 / 추가 발견")
    for f in failed_inline:
        loc = f.get("file","?") + (f":{f['line']}" if f.get("line") else "")
        lines.append(f"- {icons.get(f.get('severity'),'')} **[{f.get('severity')}/{f.get('axis')}]** `{loc}` — {f.get('title')}")
    lines.append("")
lines.append(f"<sub>인라인 {posted_inline}건 게시 · post_min_severity=`{min_sev}` · 머지 전 인간 확인 권장</sub>")
lines.append("<!-- comad-pr-review-summary -->")
summary = "\n".join(lines)

p = subprocess.run(["gh","pr","comment",pr,"--repo",repo,"--body",summary],
                   capture_output=True, text=True)
print(f"[post] inline={posted_inline} fallback={len(failed_inline)} summary_rc={p.returncode}")
if p.returncode != 0:
    print(p.stderr[:300], file=sys.stderr)
PY

# dedup 기록
python3 -c "import json,os;f='$POSTED';d=json.load(open(f)) if os.path.exists(f) else [];d.append('$PKEY');json.dump(d,open(f,'w'),indent=0)"
echo "[post] done → $PKEY 기록"
