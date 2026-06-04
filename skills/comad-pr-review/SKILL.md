---
name: comad-pr-review
version: 0.1.0
description: |
  PR diff 를 4축(correctness·security·performance·convention)으로 자동 채점하는
  Autonomous PR Reviewer. codex 독립 리뷰 + headless claude 루브릭 채점을 묶어
  구조화된 리포트 + (2b)인라인 코멘트로 산출. /code-review ultra 의 self-launch 가능 버전.
  Trigger: "comad-pr-review", "/comad-pr-review", "PR 리뷰", "PR 자동리뷰", "PR 채점".
allowed-tools:
  - Bash
  - Read
---

# comad-pr-review — Autonomous PR Reviewer

강의 STEP03 [프로젝트2] Autonomous PR Reviewer 의 내재화. 흩어져 있던
codex / comad-second-opinion / review 스킬을 **단일 4축 리뷰어**로 패키징.

## 파이프라인

```
review.sh   gh pr diff → codex 독립리뷰(2차) + headless claude 4축 채점
  ↓
            findings.json → 리포트 .comad/reports/review/PR-<n>.md
  ↓
post.sh     verdict + post_min_severity 이상 finding → gh 인라인 코멘트 + 요약   [2b]
```

## 4축 (rubric.md)
correctness · security · performance · convention. 심각도 blocker/major/minor/nit.
상세 기준·출력계약은 `rubric.md`.

## 트리거 (점진)
- (a) 수동 `bash bin/review.sh --repo OWNER/R --pr N` — secret 불필요, 먼저 구축
- (b) launchd 폴러 — `gh pr list` 신규/갱신 PR 감지 [2c]
- (c) GH Actions `comad-pr-review.yml` opt-in per repo [2c]

## 재활용
- `codex` — 적대적 독립 리뷰
- `review` 스킬 — SQL safety / LLM trust boundary 패턴 (rubric 흡수)
- ci-healer 의 notify/clone/allowlist 자산

## 안전
- `dry_run: true` 면 포스팅 안 함(리포트만)
- diff `max_diff_bytes` 초과 시 truncate(리포트에 명시)
- codex 미가용 시 claude 단독으로 진행(graceful)

## 빌드 상태
- [x] 2a: rubric.md + review.sh (codex + claude 4축, 리포트만)
- [x] 2b: post.sh (gh 인라인 코멘트 + 요약 + headSha dedup)
- [x] 2c: run.sh 폴러 + launchd(com.comad.pr-review, 20분) + GH Actions 템플릿

## 운영
- 현재 dry_run=true(리포트만). `config.json dry_run:false` → 인라인+요약 포스팅.
- 수동: `bash bin/review.sh --repo R --pr N [--post]`
- codex 2차 패스는 `codex login` 토큰 유효 시 자동 활성(만료 시 claude 단독)
