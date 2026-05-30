# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
