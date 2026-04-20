#!/usr/bin/env bash
# t6-capture.sh — T6 자가진화 루프 1단계: fix:/feat: 커밋 포착
#
# Stop hook. Scans the current working directory's git log for commits whose
# subject starts with fix:/feat:/bugfix: and dumps them to
# ~/.claude/.comad/pending/{hash}.json for later analysis by /comad-learn.
#
# Non-invasive: silent on non-git dirs, skips already-captured commits.

set -uo pipefail

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

pending_dir="$HOME/.claude/.comad/pending"
mkdir -p "$pending_dir"

# Marker per-repo (avoid cross-repo collisions)
repo_tag="$(git rev-parse --show-toplevel 2>/dev/null | python3 -c "import sys,hashlib; print(hashlib.sha1(sys.stdin.read().strip().encode()).hexdigest()[:10])")"
marker="$pending_dir/.marker-$repo_tag"

if [ -f "$marker" ]; then
  since="$(cat "$marker")"
  if git cat-file -e "$since^{commit}" 2>/dev/null; then
    range="${since}..HEAD"
  else
    range="HEAD~10..HEAD"
  fi
else
  range="HEAD~5..HEAD"
fi

# Qualifying commits (macOS-compatible; no bash 4 mapfile)
commits="$(git log "$range" --pretty=format:'%H %s' 2>/dev/null \
  | grep -iE '^[a-f0-9]+ (fix|feat|bugfix)[:\(]' \
  | awk '{print $1}' || true)"
commit_count=0

for hash in $commits; do
  [ -z "$hash" ] && continue
  out_file="$pending_dir/${hash:0:12}.json"
  [ -f "$out_file" ] && continue
  commit_count=$((commit_count + 1))

  subject="$(git log -1 --format='%s' "$hash" 2>/dev/null || true)"
  body="$(git log -1 --format='%b' "$hash" 2>/dev/null || true)"
  diff_stat="$(git show --stat --no-color "$hash" 2>/dev/null | tail -20 || true)"
  diff_head="$(git show --no-color "$hash" 2>/dev/null | head -400 || true)"
  cwd="$(pwd)"

  python3 - "$hash" "$subject" "$body" "$diff_stat" "$diff_head" "$cwd" > "$out_file" <<'PY'
import json, sys, datetime
_, h, subject, body, diff_stat, diff_head, cwd = sys.argv
json.dump({
    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "commit": h,
    "subject": subject,
    "body": body,
    "diff_stat": diff_stat,
    "diff_head": diff_head[:8000],
    "repo": cwd,
    "status": "pending",
    "kind": "fix" if subject.lower().startswith(("fix", "bugfix")) else "feat",
}, sys.stdout, ensure_ascii=False, indent=2)
PY
done

git rev-parse HEAD > "$marker" 2>/dev/null || true

if [ "$commit_count" -gt 0 ]; then
  total="$(find "$pending_dir" -name '*.json' -not -name '.*' 2>/dev/null | wc -l | tr -d ' ')"
  [ "$total" -gt 0 ] && echo "hint: [T6] ${total} pending commit(s) ready for /comad-learn" >&2 || true
fi

exit 0
