# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added (2026-06-04 — brain 활용 2종: comad-recall + comad-foresight)

comad-brain(축적만 되던 60K+ 노드 그래프)을 실제 작업 outcome 으로 전환. 모든 단계
블라인드 A/B + LLM 심사로 검증(activity 아닌 outcome lift). ⚠️ **comad-brain Neo4j 필요**.

- **`skills/comad-recall/`** — brain 을 "claim 오라클"이 아니라 **"출처 검색 인덱스"**로.
  `recall.sh` 가 주제의 매칭엔티티+기술계보+실재 ear-큐레이션 기사(제목·날짜·URL)를 지식팩으로
  추출. 핵심 발견: brain Claim 19,686개 **전부 verified=FALSE** → claim 주입은 outcome 악화
  (−0.31), 실재 Article 만 신뢰하니 **recency 질문 +3.12 lift**. 선택적 발화(최신/니치만).
- **`skills/comad-foresight/`** — brain hot클러스터를 **10렌즈 전략 foresight**(손자·스미스·탈레브
  ·카너먼·메도우즈·데카르트·마키아벨리·클라우제비츠·헤겔·다윈, eye `lens_knowledge.py` 포팅)로
  재해석. `cluster.sh`(hot클러스터 탐지) + `digest.sh`(주간 그래프 다이제스트) + `run.sh`(통합
  주간 인텔리전스 리포트 → Discord, launchd 주간). plain 분석 대비 **+1.375 lift**. comad-eye 의
  로컬-추출 파이프라인(캐시버그+weak LLM)은 폐기하고 컨셉만 승계.

### Added (2026-06-04 — harness-report 8번째 스킬: 5축 점수 + 비용/efficiency)

- **`skills/harness-report/`** — Loopy-Era 하네스 자가측정. `harness-report.py`가
  5축(HARD coverage·pending throughput·recurring·second-opinion·evolve) 0~100
  composite 를 `~/.claude/.comad/results.tsv` 에 append(구 11컬럼 → 13컬럼 자동
  마이그레이션). `collect-cost.py` 가 트랜스크립트 usage 24h 윈도우를 모델별
  notional list-price 로 집계(Max 정액 → 실청구 아님). **비용은 composite 에
  미합산** — efficiency = score/Mtok 별도 지표. `dashboard.py` 는 무의존 인라인
  SVG HTML 대시보드. `/loopy:status`·자율루프 측정에 자동 반영.

### Added (2026-06-04 — 상시 가동 에이전트 2종: CI 자가복구 + PR 리뷰어)

실리콘밸리 바이브코딩 강의(STEP03~04 "always-on agents")를 내재화. 둘 다 세션 밖
launchd 폴러로 동작하며 `dry_run` 가드 + repo allowlist 로 보호. 라이브 E2E 검증 완료.

- **`skills/comad-ci-healer/`** — GH Actions 실패 자가복구 상시 에이전트.
  `poll.py`(실패 run 수집+seen.json dedup) → `classify.py`(lint/test/build/deploy/flaky
  /unknown, IGNORECASE + Fly 인프라 패턴) → `heal.sh`(clone → headless `claude -p`
  `--dangerously-skip-permissions` → `ci-heal/<run-id>` 브랜치 → `gh pr create`) →
  `notify.sh`(Discord webhook[UA 헤더 필수] / queue). `run.sh` 가 launchd 진입점.
  성공 판정 = base 대비 새 커밋. [[feedback_ci_post_push]] 규칙을 세션 밖으로 승격.
  검증: comad-world PR 자동생성. webhook/plist 는 사용자 로컬 전용(repo 비포함).
- **`skills/comad-pr-review/`** — Autonomous 4-axis PR Reviewer.
  `review.sh`(codex 독립 2차 + headless claude 4축 채점 → `rubric.md` 출력계약 JSON) →
  `post.sh`(gh 인라인 코멘트 + 요약, headSha dedup, `post_min_severity` 게이트). `run.sh`
  폴러 + `templates/comad-pr-review.yml`(GH Actions opt-in, CLAUDE_CODE_OAUTH_TOKEN).
  검증: probe PR 에서 SQL injection(blocker)·ZeroDivision(major) 정확 탐지 + 인라인 게시.

### Added (2026-05-30 — R2 adversarial review + R5 judge-panel + decisions escalation)

- **`hooks/stop/adversarial-review-gate.{sh,py}`** (R2) — Stop hook that
  complements the claim-VALIDATORS: when a turn CLAIMS a *substantial* code
  change is done (≥3 code files, a sensitive path, or a substantial git diff)
  without a fresh `.second-opinion.md` verdict=APPROVED in the touched repo, it
  nags. WARN-ONLY by default; `COMAD_ADVERSARIAL_REVIEW_BLOCK=1` → exit 2.
  FAIL-OPEN.
- **`hooks/lib/`** (new shared-lib dir) —
  - `substantial_change.py` — git-diff/path heuristic (`is_substantial`,
    `classify_paths`) reused by gates / QA flows.
  - `decisions.py` — escalation queue (`~/.claude/.comad/decisions/`) so
    autonomous processes (loopy-era, nightly-audit) surface human *decisions*
    only (not raw logs). CLI `add|list|count|resolve` + `record_decision` /
    `pending` library API. Also imported by comad-world's `nightly-audit.sh`.
- **`workflows/`** (new dir — Dynamic Workflow templates) —
  - `adversarial-review.js` (R2) — N skeptics each break the diff via a distinct
    lens (correctness / security / edge), majority-vote a verdict, write
    `.second-opinion.md`. The default mechanism behind adversarial-review-gate.
  - `judge-panel.js` (R5) — N distinct strategy lenses generate approaches →
    parallel judges score → synthesize winner + grafted runner-up ideas. For
    wide-solution-space design / architecture / strategy decisions.
- **`comad-qa-evidence/bin/validate-qa-evidence.py`** — `checks.second_opinion`
  wiring so L4+ claims require an approved `.second-opinion.md`.
- **`install.sh`** — now installs `hooks/lib/`,
  `hooks/stop/adversarial-review-gate.{sh,py}`, and `workflows/*.js`;
  adversarial-review-gate added to the Stop wiring snippet.

### Changed (2026-05-30)

- Hook count 9 → **10** (adversarial-review-gate). Stop hooks 5 → **6**.

### Added (2026-04-25 — comad-parallel as 5th skill)

- **`comad-parallel`** — gptaku-plugins/pumasi v1.7.2 → ported to
  `~/.claude/skills/comad-parallel/` and re-engineered with 5 new comad
  integration commands:
  - `parallel.sh handoff` — emits a 7-section session handoff doc into
    `.comad/sessions/<ts>-parallel-<jobid>.md` after every parallel job.
    Auto-fills Summary / Relevant Files / Open Work; leaves TODO(claude)
    stubs for Key Decisions / Traps / Working Agreements.
    Default-on (env `COMAD_AUTO_HANDOFF=0` to disable).
  - `parallel.sh qa-gate` — verifies `.qa-evidence.json` (verdict=PASS) for
    each done task using `comad-qa-evidence/bin/validate-qa-evidence.py`
    (jq fallback). Opt-in via `COMAD_QA_EVIDENCE=1`.
  - `parallel.sh second-opinion-gate` — checks `.second-opinion.md`
    frontmatter verdict (APPROVED / REQUEST_CHANGES / BLOCKS). Verify-only,
    does not auto-spawn codex review. Opt-in via `COMAD_SECOND_OPINION=1`.
  - `parallel.sh destroy-check` — greps Codex worker output for 13
    destructive patterns (`rm -rf /|~|$HOME`, `git push --force`, `DROP
    DATABASE`, `mkfs.*`, fork bomb, etc). Opt-in via
    `COMAD_DESTROY_CHECK=1`. Sandbox-equivalent post-check since Codex runs
    out-of-process and Claude's pre-tool-use hooks don't apply.
  - ear-notify — POSTs a one-line summary to Discord webhook on job
    completion. Silent on failure. Opt-in via `COMAD_EAR_NOTIFY=1` +
    `DISCORD_WEBHOOK_URL`.
- **T6 self-evolve coupling** — `parallel` worker commits with `fix:`/`feat:`
  prefix are auto-captured by the existing `t6-capture.sh` Stop hook into
  `~/.claude/.comad/pending/`. No code changes needed; SKILL.md documents
  the convention.
- **`install.sh`** updated to copy 14 `comad-parallel/{scripts,references}/`
  files and chmod +x `parallel.sh` / `parallel-job.sh`.
- **`README.md`** updated: 4 skills → 5 skills, parallel row added to skill
  catalog table.

### Changed

- Skill count in README hero bullet: "스킬 4종" → "스킬 5종".

### Fixed

- (no functional fixes — additive release)

## [Tier 3] — 2026-04-20

- L0~L5 QA levels internalized into `comad-qa-evidence`
- `comad-second-opinion` skill added (codex CLI → subagent → self-adversarial
  3-step fallback)
- README rewritten for Tier 3 — 9 hooks documented (4 pre-tool-use + 5 stop)

## [Tier 2] — earlier 2026-04

- Hook additions: claim-done-gate, premature-completion-detector,
  numeric-claim-gate, inventory-gate, qa-gate-before-push (Tier 1+2)
- T6 self-evolve loop established (t6-capture.sh + comad-learn skill +
  comad-memory skill with SQLite FTS5 index)
- Approval-Gated Destruction (destroy-gate) hardened — sha256
  command-binding approvals, heredoc/literal stripping for false-positive
  immunity

## [Initial commit] — 2026-04-17

- Repo bootstrapped from `~/.claude/` curation. Goals: zero external
  service dependencies, Python stdlib + bash only, copy-based install,
  re-runnable safely.
