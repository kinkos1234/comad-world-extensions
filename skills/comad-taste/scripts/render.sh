#!/usr/bin/env bash
# Taste Layer 렌더 래퍼 — playwright 위치를 찾아 PW_BASE 로 넘기고 render.mjs 실행.
# usage: render.sh <htmlPath> <outPng> [w] [h] [fullPage]
#   ex) render.sh /tmp/x/v1.html /tmp/x/v1.png 1440 980
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# playwright 가진 node_modules 의 "부모 dir" 후보 (gstack 우선 — chromium 이미 설치됨).
PW_BASE=""
for cand in \
  "$HOME/.claude/skills/gstack" \
  "$HOME/.claude/skills/comad-motion" \
  "$SKILL_DIR"; do
  if [ -d "$cand/node_modules/playwright" ]; then PW_BASE="$cand"; break; fi
done
if [ -z "$PW_BASE" ]; then
  echo "::error:: playwright 미발견. gstack 설치 필요 (~/.claude/skills/gstack, npx playwright install chromium)." >&2
  exit 1
fi

PW_BASE="$PW_BASE/node_modules" node "$SKILL_DIR/scripts/render.mjs" "$@"
