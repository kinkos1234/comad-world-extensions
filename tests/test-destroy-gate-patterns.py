#!/usr/bin/env python3
"""destroy-gate PATTERNS 양방향 회귀 테스트.

왜 있나: 부분문자열을 동일성으로 쓴 패턴이 정상 명령을 막았다 (2026-08-15,
`git push origin $(git rev-parse --abbrev-ref HEAD)` 가 "-ref " 때문에 `git push -f`
로 판정). 오탐이 쌓이면 사람이 가드를 무시하고 그 시점에 가드가 죽는다.
반대로 좁히다가 진짜 케이스를 놓치는 것도 같은 크기의 실패다 — 그래서 양방향으로 센다.

패턴을 좁히거나 넓힐 때마다 실행할 것:
    python3 ~/.claude/hooks/tests/test-destroy-gate-patterns.py

관련: memory/feedback_substring_match_false_positive.md
      rules/guard-scope-discipline.md
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import sys

# 기본은 라이브 게이트. pre-push 에서는 **푸시하려는 사본**을 검사해야 하므로
# DESTROY_GATE_PATH 로 대상을 바꿔 끼울 수 있게 둔다 (레포 사본 검증용).
GATE = pathlib.Path(
    os.environ.get("DESTROY_GATE_PATH")
    or (pathlib.Path(os.environ.get("HOME", "/")) / ".claude/hooks/pre-tool-use/destroy-gate.py")
)
if not GATE.exists():
    print(f"destroy-gate patterns: 대상 없음 ({GATE}) — skip", file=sys.stderr)
    raise SystemExit(0)

spec = importlib.util.spec_from_file_location("destroy_gate", GATE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# (command, should_block, why)
# 현재 게이트가 잡지 않는 것으로 **확인된** 케이스. 실패로 세지 않고 보고만 한다 —
# 패턴을 넓힐지는 사용자 승인 사항이라 테스트가 임의로 요구하지 않는다.
# (결정 큐 상신됨, 2026-08-16)
# 2026-08-16: --force-with-lease 갭은 사용자 승인으로 해소(패턴을 --force[-\\w]* 로 확장).
# 갭이 다시 생기면 여기에 적고 결정 큐로 올린다 — 테스트가 임의로 게이트 동작을 요구하지 않는다.
KNOWN_GAPS: list[tuple[str, str]] = []

# (command, should_block, why)
CASES: list[tuple[str, bool, str]] = [
    # --- 오탐 회귀: 정상 명령은 반드시 통과 ---
    ("git push origin $(git rev-parse --abbrev-ref HEAD)", False, "2026-08-15 실사고: --abbrev-ref 의 '-ref ' 가 -f 로 오독됐다"),
    ("git push origin main", False, "평범한 push"),
    ("git push --set-upstream origin feature/x", False, "긴 옵션 안의 f 조각"),
    ("git push origin HEAD --follow-tags", False, "--follow-tags 는 짧은 -f 가 아니다"),
    ("git rev-parse --abbrev-ref HEAD", False, "push 아님"),
    ("rm -rf ./node_modules", False, "상대 하위 경로는 대상 아님"),
    ("rm -rf build/", False, "빌드 산출물 삭제는 정상"),
    ('echo "example: rm -rf /"', False, "따옴표 안 문자열은 벗겨낸 뒤 판정"),
    ("git clean -n", False, "dry-run 은 파괴적이지 않다"),

    # --- 진짜 케이스는 반드시 차단 (좁히다 무력화하지 않았는지) ---
    ("git push -f origin main", True, "짧은 플래그 -f"),
    ("git push origin main -f", True, "후위 -f"),
    ("git push -uf origin main", True, "묶인 짧은 플래그"),
    ("git push --force origin main", True, "긴 옵션"),
    ("git push --force-with-lease origin main", True, "이름만 안전한 force — 원격 이력을 덮는 건 같다"),
    ("git push --force-if-includes origin main", True, "force 변형"),
    ("git push --force-with-lease=main:abc123 origin main", True, "값이 붙은 force 변형"),
    ("rm -rf /", True, "루트 삭제"),
    ("rm -rf ~/", True, "홈 삭제"),
    ("rm -rf $HOME", True, "홈 삭제 변수형"),
    ("git reset --hard origin/main", True, "원격 기준 하드 리셋"),
    ("git clean -fd", True, "추적 안 되는 파일 강제 삭제"),
    ("DROP DATABASE prod;", True, "DB 드롭"),
    ("kubectl delete namespace prod", True, "네임스페이스 삭제"),
]


def blocked(cmd: str) -> str | None:
    """차단이면 라벨, 아니면 None."""
    probe = mod.strip_strings(cmd) if hasattr(mod, "strip_strings") else cmd
    for pat, label in mod.PATTERNS:
        if re.search(pat, probe, flags=re.IGNORECASE):
            return label
    return None


def main() -> int:
    fails: list[str] = []
    for cmd, should_block, why in CASES:
        label = blocked(cmd)
        got = label is not None
        if got != should_block:
            verb = "차단됐어야 하는데 통과" if should_block else f"통과했어야 하는데 차단({label})"
            fails.append(f"  {cmd!r}\n    → {verb} · {why}")

    gaps = [(c, why) for c, why in KNOWN_GAPS if blocked(c) is None]
    closed = [(c, why) for c, why in KNOWN_GAPS if blocked(c) is not None]

    total = len(CASES)
    if fails:
        print(f"destroy-gate patterns: {total - len(fails)}/{total} ok, {len(fails)} FAIL\n")
        print("\n".join(fails))
        return 1
    print(f"destroy-gate patterns: {total}/{total} ok "
          f"(오탐 {sum(1 for _, b, _ in CASES if not b)} · 차단 {sum(1 for _, b, _ in CASES if b)})")
    for c, why in gaps:
        print(f"  KNOWN GAP (미차단): {c!r} — {why}")
    for c, _ in closed:
        print(f"  NOTE: 알려진 갭이 닫혔습니다 — {c!r}. KNOWN_GAPS 에서 CASES 로 옮기세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
