#!/usr/bin/env bash
# comad-sdd 종료 게이트: 모든 완료기준(AC)이 충족됐는지 판정.
# 통과 조건: spec.md 의 미체크 체크박스 0개 AND evidence.md 의 FAIL 0개.
# usage: check-acceptance.sh <feature-slug> [--root <git-root>]
set -euo pipefail

slug="${1:-}"
[ -z "$slug" ] && { echo "usage: check-acceptance.sh <feature-slug> [--root <dir>]" >&2; exit 2; }
shift || true

root=""
if [ "${1:-}" = "--root" ]; then root="${2:-}"; fi
if [ -z "$root" ]; then
  root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi

dir="$root/.comad/sdd/$slug"
spec="$dir/spec.md"
evidence="$dir/evidence.md"

[ -f "$spec" ] || { echo "FAIL: spec.md not found at $spec" >&2; exit 1; }

# 미체크 완료기준 = "- [ ]" 패턴
unchecked=$(grep -cE '^\s*-\s*\[ \]' "$spec" 2>/dev/null || true)
unchecked=${unchecked:-0}

# evidence.md 의 FAIL 마커 (이모지 ❌ 또는 단어 FAIL)
fails=0
if [ -f "$evidence" ]; then
  fails=$(grep -cE '❌|\bFAIL\b' "$evidence" 2>/dev/null || true)
  fails=${fails:-0}
else
  echo "WARN: evidence.md not found — VERIFY(S4) 미실행으로 간주" >&2
fi

echo "feature=$slug  unchecked_AC=$unchecked  evidence_FAIL=$fails"

if [ "$unchecked" -eq 0 ] && [ "$fails" -eq 0 ] && [ -f "$evidence" ]; then
  echo "PASS — 모든 완료기준 충족, 종료(S5) 가능"
  exit 0
fi
echo "BLOCKED — S3/S4 로 루프백 필요 (미체크 AC=$unchecked, FAIL=$fails)"
exit 1
