---
name: comad-second-opinion
version: 0.1.0
description: |
  2차 리뷰(second opinion) 산출물 `.second-opinion.md` 생성·검증 스킬.
  Claude가 구현을 끝낸 후 다른 관점(codex CLI → Claude Code 서브에이전트
  → self-adversarial)으로 검토한 결과를 프로젝트 루트에 구조화된 파일로
  남긴다. `.qa-evidence.json.checks.second_opinion`에 연결해서 QA 게이트와
  통합된다.
  Trigger: "second opinion", "2차 리뷰", "/comad-second-opinion", "독립 검토",
  "adversarial review", "리뷰 받아줘".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Agent
---

# Comad Second Opinion

**목적:** "나 혼자 검토해서 괜찮아 보임"을 배제. 다른 관점(외부 CLI 또는
서브에이전트)이 실제로 diff/산출물을 봤다는 증거를 `.second-opinion.md`로
남기고, QA 증거 파일에 연결한다.

## 3단계 폴백 체인

**1순위: `codex` CLI** — `codex --version`이 성공하면 사용.
```bash
cd <project>
git diff HEAD~1 HEAD > /tmp/diff.patch
codex exec --full-auto -C <project> \
  "Review the attached diff for correctness, security, edge cases. \
   End with a single line: VERDICT: APPROVED | REQUEST_CHANGES | BLOCKS." \
  < /tmp/diff.patch > /tmp/codex-review.txt
```

**2순위: Claude Code 서브에이전트** — codex 없으면 `Agent` 도구로 spawn.
```
Agent(
  subagent_type="volt-error-detective",
  description="Adversarial review of recent diff",
  prompt="""
  독립 검토자로서 방금 완료된 작업의 diff를 검토하십시오.
  ...
  마지막 한 줄에 VERDICT: APPROVED | REQUEST_CHANGES | BLOCKS
  """
)
```

사용 가능한 reviewer 서브에이전트(`~/.claude/agents/`):
- `volt-error-detective` — 에러/버그 근본 원인 관점
- `volt-security-auditor` — 보안 관점
- `nexus-reviewer` — 일반 코드 리뷰
- `volt-refactoring-specialist` — 코드 품질/중복 관점
- `volt-performance-engineer` — 성능 관점

작업 성격에 따라 선택. 여러 관점 필요하면 병렬로 Agent 2~3회 호출 후 결과
합치기.

**3순위 (fallback): self-adversarial** — codex도 서브에이전트도 부적절한
상황(예: 즉흥 스크립트, 간단한 커밋). Claude 본인이 "adversarial reviewer"
persona로 동일 diff를 비판적으로 검토. 편향 리스크 명시.

## 파일 포맷 (`.second-opinion.md`)

```markdown
---
schema_version: "1"
generated_at: 2026-04-20T08:00:00Z
reviewer: codex | subagent:<name> | self-adversarial
git_head: abc1234
topic: "한 줄 설명 — 검토 대상 요약"
verdict: APPROVED | REQUEST_CHANGES | BLOCKS
---

# Second Opinion Review

## Scope
[검토한 파일/디프 범위]

## Findings
- [이슈 1 — severity: LOW/MEDIUM/HIGH/CRITICAL]
- [이슈 2]

## Recommendations
- [개선 권고]

## Verdict: <APPROVED | REQUEST_CHANGES | BLOCKS>
이유: [한 줄]
```

## 프로세스 (Claude 직접 실행)

1. 구현 완료 + `.qa-evidence.json`이 있는 상태에서 사용자가 2차 리뷰 요청
2. `command -v codex` 체크 → codex 있으면 1순위 경로
3. 없으면 작업 성격에 맞는 reviewer 서브에이전트를 `Agent` 도구로 spawn
4. 결과를 `.second-opinion.md`로 저장 (위 스키마 준수)
5. `validate-second-opinion.py` 실행 → 스키마 통과 확인
6. `.qa-evidence.json.checks.second_opinion` 에 status 기록:
   ```json
   "second_opinion": {
     "status": "PASS",
     "reviewer": "codex",
     "file": ".second-opinion.md",
     "verdict": "APPROVED"
   }
   ```
   verdict이 `REQUEST_CHANGES`면 status=FAIL, `BLOCKS`면 status=FAIL로 기록.
7. validate-qa-evidence.py 재실행 → verdict=PASS 승격 가능

## 언제 사용

- 사용자가 "2차 리뷰 받고 push" 요청 시
- 보안 민감 변경 (auth, crypto, SQL, 권한)
- 외부 API와의 계약 변경
- 프로덕션 deploy 직전
- 대규모 리팩토링 후

## 언제 쓰지 말 것

- 단순 오타/문서 수정
- 한 파일 한 줄짜리 수정
- 실험적 브랜치 (main/production 아닌)
- PRB(Pre-Release Build) 아닌 로컬 개발 중간 커밋

## 검증

`validate-second-opinion.py <file.md>` — 스키마 준수 확인:
- frontmatter: schema_version, generated_at, reviewer, git_head, topic, verdict
- git_head가 현재 HEAD와 일치 (stale 리뷰 방지)
- verdict ∈ {APPROVED, REQUEST_CHANGES, BLOCKS}
- 본문 최소 200자
- Scope / Findings / Verdict 섹션 존재

Exit codes:
- 0 — valid + verdict=APPROVED
- 1 — valid but verdict ≠ APPROVED
- 2 — schema violation

## Safety

- 리뷰 결과는 항상 파일로 저장 (휘발성 대화 안 됨)
- git_head 검증으로 stale 리뷰(이전 커밋에 대한 리뷰) 차단
- self-adversarial 모드는 편향 리스크 있으므로 crit한 변경에는 금지

## Scope

- **In**: `.second-opinion.md` 생성·검증, reviewer 선택 가이드
- **Out**: 실제 리뷰 수행(Claude가 Agent/Bash로), 자동 PR 코멘트 (별개)
