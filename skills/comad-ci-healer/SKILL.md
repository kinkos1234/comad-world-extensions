---
name: comad-ci-healer
version: 0.1.0
description: |
  GH Actions 실패를 세션 밖에서 자동 감지·분석·복구하는 상시 에이전트.
  실패 run → 로그 분류 → 수정 브랜치 → PR 자동생성 → 재검증 → Discord 알림.
  feedback_ci_post_push 규칙(--max-warnings=0, actions 버전)을 세션 밖으로 승격.
  Trigger: "ci-healer", "/comad-ci-healer", "CI 자가복구", "CI 힐러", "빌드 실패 자동수정".
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# comad-ci-healer — CI/CD 자가복구 에이전트

강의 STEP03 [프로젝트4] CI/CD 통합 에이전트의 내재화. `feedback_ci_post_push`가
"세션 안에서 push 후 확인+수정"이었다면, 이건 **세션 밖 상시 폴러**가 한다.

## 파이프라인

```
poll.py        실패 run 수집 + seen.json dedup
  ↓
classify.py    로그 → {lint|test|build|deploy|flaky|unknown}
  ↓
heal.sh        worktree → headless claude -p → 수정 → ci-heal/<run-id> 브랜치 → PR   [1b]
  ↓
notify.sh      Discord webhook 알림 (성공/에스컬레이션)                              [1b]
```

## 카테고리별 정책 (config.json)

| 카테고리 | 동작 |
|---|---|
| lint, build | 자동수정 시도 (`auto_fix_categories`) |
| flaky | 재실행만 (`rerun_only_categories`) |
| test | 자동수정 시도하되 보수적 (회귀 위험) |
| deploy, unknown | 인간 에스컬레이션 (`escalate_categories`) |

## 안전 가드

- `repos` allowlist 밖은 무시
- 수정은 항상 `ci-heal/<run-id>` 브랜치 + PR. **main 직접 push 금지**
- `max_attempts`(기본 2) 초과 → Discord 에스컬레이션, 자동수정 중단
- headless run 에도 destroy-gate / qa-gate-before-push 적용
- `dry_run: true` 면 PR 안 내고 계획만

## 수동 사용

```bash
cd ~/.claude/skills/comad-ci-healer
python3 bin/poll.py                          # 새 실패 목록 (dry-run)
python3 bin/classify.py --repo OWNER/R --run-id 123
# 1b 이후:
# bash bin/heal.sh --repo OWNER/R --run-id 123
```

## 상태

- `~/.claude/.comad/ci-healer/seen.json` — 처리한 run-id (dedup)
- `~/.claude/.comad/ci-healer/attempts.json` — run 별 시도 횟수
- `~/.claude/.comad/ci-healer/logs/` — 복구 로그

## 자동화 (1c)

launchd `com.comad.ci-healer.plist` 15분 주기 → `poll.py --commit | heal`.
reference_comad_cron 에 등록.

## 빌드 상태

- [x] 1a: 스캐폴드 + poll.py + classify.py (dry-run)
- [x] 1b: heal.sh (라우팅 + headless 오케스트레이션, dry-run 가드) + notify.sh (webhook/queue)
- [x] 1c: 통제 라이브 E2E 성공(comad-world PR#5) + run.sh 폴러 + launchd 등록(dry_run 유지)

## 운영 전환

- 현재 **dry_run=true** — 폴러가 관측+에스컬레이션 알림만, 자동 PR 안 냄.
- 완전 자율: `config.json` `dry_run:false` → lint/build/test 실패 자동 PR 생성.
- 알림: `export COMAD_CI_HEALER_WEBHOOK=<discord webhook>` 설정 시 Discord 직접 POST(없으면 notify-queue.jsonl).
- launchd: `launchctl {load,unload} ~/Library/LaunchAgents/com.comad.ci-healer.plist` (15분 주기).
