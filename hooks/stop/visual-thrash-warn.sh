#!/usr/bin/env bash
# visual-thrash-warn — 시각 재구성 스래싱 경고 (SIGNAL ONLY, 항상 exit 0)
#
# 세션 저장소에 24h 내 "시각 정합" fix 커밋이 2회 이상 쌓이면 접근 전환 신호를 출력.
# CSS 도형 근사를 반복 수정하는 대신 목업 색상 마스킹 픽셀 추출로 전환하라는 힌트.
#
# 근거: feedback_mock_asset_extraction — sig-slot SOLD OUT 리본 4차 재구성
#       (749a08e3 → f08a53c5 → 97847ab0 → 7b9f9cd6, 해결은 a5b25ebb 에셋 추출)
# 결정: 20260705T002111-stop-hook-fix-4 (2026-07-08 사용자 일괄 승인, 경고형)

N=$(git log --since='24 hours ago' --pretty=%s 2>/dev/null \
  | grep -cE '^fix:.*(목업|리본|mockup|정합|재현|리디자인)') || N=0

if [ "${N:-0}" -ge 2 ]; then
  echo "🎨 시각 재구성 스래싱 감지 — 24h 내 시각 정합 fix ${N}회. CSS 근사 반복을 중단하고 목업 색상 마스킹 픽셀 추출로 전환하세요 (feedback_mock_asset_extraction, 반복 2회 초과 = 접근 전환 신호)."
fi
exit 0
