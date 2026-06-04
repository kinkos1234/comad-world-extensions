#!/usr/bin/env bash
# comad-pr-review · review.sh
# PR diff 를 codex(독립) + headless claude(4축 루브릭)로 채점 → 리포트.
# 2a: 리포트만 생성(.comad/reports/review/PR-<n>.md). 포스팅은 post.sh(2b).
#
# 사용: review.sh --repo OWNER/REPO --pr 12 [--post]
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG="${SKILL_DIR}/config.json"
cfg() { python3 -c "import json,sys;print(json.load(open('$CFG'))$1)"; }

REPO="" ; PR="" ; DO_POST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2;;
    --pr) PR="$2"; shift 2;;
    --post) DO_POST=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[ -n "$REPO" ] && [ -n "$PR" ] || { echo "need --repo and --pr" >&2; exit 2; }

REPORT_DIR="$(python3 -c "import os;print(os.path.expanduser('$(cfg "['report_dir']")'))")"
STATE_DIR="$(python3 -c "import os;print(os.path.expanduser('$(cfg "['state_dir']")'))")"
MAX_DIFF="$(cfg "['max_diff_bytes']")"
mkdir -p "$REPORT_DIR" "$STATE_DIR"
REPORT="${REPORT_DIR}/PR-${PR}.md"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

echo "[review] $REPO #$PR — fetching diff…"
META=$(gh pr view "$PR" --repo "$REPO" --json title,author,additions,deletions,changedFiles,url 2>/dev/null)
TITLE=$(echo "$META" | python3 -c "import json,sys;print(json.load(sys.stdin).get('title',''))")
URL=$(echo "$META" | python3 -c "import json,sys;print(json.load(sys.stdin).get('url',''))")
gh pr diff "$PR" --repo "$REPO" > "$WORK/diff.patch" 2>/dev/null
DIFF_BYTES=$(wc -c < "$WORK/diff.patch" | tr -d ' ')
TRUNCATED="no"
if [ "$DIFF_BYTES" -gt "$MAX_DIFF" ]; then
  head -c "$MAX_DIFF" "$WORK/diff.patch" > "$WORK/diff.trunc" && mv "$WORK/diff.trunc" "$WORK/diff.patch"
  TRUNCATED="yes (${DIFF_BYTES}B→${MAX_DIFF}B)"
fi

# ── codex 독립 리뷰 (적대적 2차 의견) ──────────────────────────
echo "[review] codex independent pass…"
CODEX_OUT="$WORK/codex.txt"
# codex exec 는 stdin open 시 블록 → < /dev/null 필수 (feedback_codex_exec_stdin)
codex exec --full-auto "다음 git diff 를 적대적으로 리뷰해라. 실제 버그·보안·성능 문제만 간결히 bullet 로. 추측 금지.

$(cat "$WORK/diff.patch")" < /dev/null > "$CODEX_OUT" 2>/dev/null || echo "(codex 실행 실패/미가용 — 토큰 만료 시 'codex login' 필요)" > "$CODEX_OUT"

# ── headless claude 4축 채점 ──────────────────────────────────
echo "[review] claude 4-axis scoring…"
RUBRIC=$(cat "$SKILL_DIR/rubric.md")
PROMPT="$RUBRIC

---
리뷰 대상 PR: ${REPO} #${PR} — ${TITLE}
diff(truncated=${TRUNCATED}):
\`\`\`diff
$(cat "$WORK/diff.patch")
\`\`\`

codex 독립 리뷰(2차 의견, 참고용):
$(cat "$CODEX_OUT")

위 루브릭의 '출력 계약'대로 4축 채점 JSON 만 출력해라. 다른 설명 없이 \`\`\`json 블록 하나."
CLAUDE_OUT="$WORK/claude.txt"
claude -p "$PROMPT" < /dev/null > "$CLAUDE_OUT" 2>&1 || true

# JSON 추출
python3 - "$CLAUDE_OUT" "$WORK/findings.json" <<'PY'
import json, re, sys
raw = open(sys.argv[1]).read()
m = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.S) or re.search(r"(\{.*\})", raw, re.S)
try:
    data = json.loads(m.group(1)) if m else {}
except Exception:
    data = {}
data.setdefault("verdict", "comment")
data.setdefault("summary", "(파싱 실패 — 원문 로그 확인)")
data.setdefault("findings", [])
json.dump(data, open(sys.argv[2], "w"), ensure_ascii=False, indent=2)
PY

# ── 리포트 렌더 ────────────────────────────────────────────────
python3 - "$WORK/findings.json" "$REPORT" "$REPO" "$PR" "$TITLE" "$URL" "$TRUNCATED" "$CODEX_OUT" <<'PY'
import json, sys, datetime
fj, report, repo, pr, title, url, trunc, codexf = sys.argv[1:9]
d = json.load(open(fj))
sev_order = {"blocker":0,"major":1,"minor":2,"nit":3}
icons = {"blocker":"🔴","major":"🟠","minor":"🟡","nit":"⚪"}
fs = sorted(d["findings"], key=lambda f: sev_order.get(f.get("severity","nit"),9))
counts = {}
for f in fs: counts[f.get("severity","nit")] = counts.get(f.get("severity","nit"),0)+1
badge = " · ".join(f"{icons.get(k,'')}{k}:{v}" for k,v in sorted(counts.items(), key=lambda x:sev_order.get(x[0],9))) or "발견 없음"
L = []
L.append(f"# PR Review — {repo} #{pr}")
L.append(f"> {title}\n> {url}\n> diff truncated: {trunc}\n")
L.append(f"**Verdict:** `{d['verdict']}`  ·  {badge}\n")
L.append(f"**총평:** {d['summary']}\n")
if fs:
    L.append("## Findings\n")
    for f in fs:
        loc = f.get("file","?")
        if f.get("line"): loc += f":{f['line']}"
        L.append(f"### {icons.get(f.get('severity'),'')} [{f.get('severity','?')}/{f.get('axis','?')}] {f.get('title','')}")
        L.append(f"`{loc}`\n")
        L.append(f"{f.get('detail','')}\n")
        if f.get("suggestion"): L.append(f"**제안:** {f['suggestion']}\n")
else:
    L.append("발견된 이슈 없음. ✅\n")
L.append("\n---\n## codex 독립 리뷰 원문\n")
L.append("```\n" + open(codexf).read().strip()[:3000] + "\n```\n")
open(report,"w").write("\n".join(L))
print(report)
PY

echo "[review] report → $REPORT"
echo "── verdict & counts ──"
python3 -c "import json;d=json.load(open('$WORK/findings.json'));print('verdict:',d['verdict']);print('findings:',len(d['findings']))"

if [ "$DO_POST" -eq 1 ]; then
  echo "[review] --post 지정됨 → post.sh 호출 (2b)"
  bash "$SKILL_DIR/bin/post.sh" --repo "$REPO" --pr "$PR" --findings "$WORK/findings.json" 2>&1 || echo "[review] post.sh 미구현/실패"
fi
