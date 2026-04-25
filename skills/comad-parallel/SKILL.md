---
name: comad-parallel
description: Parallel coding orchestration — Claude takes the PM/architect role, Codex CLI instances act as parallel outsource developers. Auto-triggers when 3+ independent modules need concurrent implementation. Distributes subtasks to Codex, then Claude reviews and integrates. Korean triggers — "/pumasi", "/comad-parallel", "품앗이로 만들어줘", "품앗이 켜줘", "codex 외주로", "codex한테 시켜", "코덱스 병렬로", "코덱스한테 맡겨". English triggers — "pumasi", "parallel with codex", "delegate to codex", "codex outsource", "parallel code generation", "codex workers".
credits: ported from gptaku-plugins/pumasi v1.7.2 (internalized into comad-world). 경로만 CLAUDE_PLUGIN_ROOT → $HOME/.claude/skills/comad-parallel 로 치환.
---

# 품앗이 (Pumasi) — Codex 병렬 외주 개발

> 품앗이: 서로 협력하며 일을 나눠 하는 한국 전통 방식
> Claude = 설계/감독 | Codex × N = 병렬 구현자

## 개념

```
┌─────────────────────────────────────────────────────────┐
│              Claude Code (설계/감독/PM)                   │
│  1. 요구사항 분석 → 기획 → 독립 서브태스크 분해           │
│  2. 시그니처 + 요구사항 + 게이트 작성                     │
│  3. parallel.sh 실행 → Codex 병렬 스폰                     │
│  4. 게이트 검증 → 통합                                   │
└─────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
  ┌──────────┐     ┌──────────┐     ┌──────────┐
  │ Codex #1 │     │ Codex #2 │     │ Codex #3 │
  │ 시그니처  │     │ 시그니처  │     │ 시그니처  │
  │ 기반 구현 │     │ 기반 구현 │     │ 기반 구현 │
  └──────────┘     └──────────┘     └──────────┘
        │                 │                 │
        └─────────────────┴─────────────────┘
                          │
                          ▼
              게이트 검증 → 통합 → 완성
```

## 핵심 가치

**품앗이의 존재 이유는 "Claude가 코드를 짜지 않는 것"이다.**

| 가치 | 설명 |
|------|------|
| Claude 토큰 절약 | Claude는 설계만, 구현은 Codex가 담당 |
| 속도 향상 | N개 모듈을 Codex가 병렬로 동시 구현 |
| 검증 최적화 | 동적 게이트(bash, 토큰 0)로 자동 검증 |

**전제 조건**: Codex가 **실제 구현**을 해야 한다. Claude가 코드를 다 짜고 Codex에게 복사만 시키면 토큰 절약 효과 = 0.

---

## 안티패턴 및 역할 분리

> **instruction 작성 전 반드시 Read**:
> - `${HOME}/.claude/skills/comad-parallel/references/anti-patterns.md` — 복붙형 instruction 절대 금지 규칙
> - `${HOME}/.claude/skills/comad-parallel/references/role-separation.md` — Claude vs Codex 역할 경계, 경계선 예시

**핵심 원칙 요약**: Claude는 시그니처+요구사항만 작성. 코드 본문(body)은 절대 작성 금지. 강한 게이트(tsc/build/test)로 검증.

---

## 트리거 조건

```
명시적 트리거:
- "/pumasi [작업]"
- "품앗이로 [작업]해줘"
- "품앗이 켜줘"
- "codex 외주로 [작업]"
- "codex한테 [작업] 시켜"

자동 감지 (대규모 코딩 요청 시):
- 4개 이상의 독립 파일/모듈 동시 작성 요청
- "전체 [기능] 구현해줘" + 규모가 큰 경우
- 여러 컴포넌트/서비스를 한 번에 만들어야 할 때
```

### 작업 규모별 분기 (중요)

| 규모 | 권장 방식 | 이유 |
|------|----------|------|
| 태스크 1~2개 | **Claude 직접 코딩** | 품앗이 오버헤드가 더 큼 |
| 태스크 3~4개 | **품앗이 사용 가능** | 병렬 이득이 오버헤드와 비슷 |
| 태스크 5개+ | **품앗이 강력 권장** | 병렬 이득이 확실히 큼 |

**또한 다음 경우에는 품앗이를 사용하지 않는다:**
- 기존 코드 수정/버그 수정 (컨텍스트 주입이 과도해짐)
- 단일 파일 작업 (병렬 이점 없음)
- 게이트를 만들 수 없는 작업 (UI 미세 조정 등)

### /batch와의 관계

품앗이와 `/batch`는 목적이 다르다. 상호 보완적이며, 대체 관계가 아니다.

| | 품앗이 (Pumasi) | /batch |
|--|----------------|--------|
| **목적** | 독립 모듈 N개 동시 구현 (Greenfield) | 동일 패턴을 N개 파일에 반복 적용 (Brownfield) |
| **워커** | Codex CLI (Codex 토큰) | Claude 에이전트 (Claude 토큰) |
| **격리** | 동일 워킹 디렉토리 | git worktree별 완전 격리 |
| **적합한 작업** | 인증 + DB + API 각각 만들기 | jest→vitest 마이그레이션, CSS→Tailwind 변환 |

### 품앗이 모드 진입 시 Claude의 행동 변화

```
일반 모드:          품앗이 모드:
Claude가 직접 코딩  Claude가 시그니처+요구사항 작성
                   → parallel.sh 실행 → Codex가 구현
                   → 게이트 자동 검증 → 통합
```

---

## 7단계 워크플로우

### Phase 0: 기획 (Claude as PM)

사용자 요청을 분석하여 **완성도 있는 기획안**을 작성. 기획 체크리스트 통과 후 사용자 승인을 받는다.

**기획 체크리스트** (태스크 분해 전 반드시 확인):

```
□ 이 앱/기능의 핵심 사용 시나리오는?
□ 경쟁 제품/일반적 기대치 대비 빠진 기능은?
□ 데이터 모델에 필요한 필드가 충분한가?
□ UX 관점: 검색, 정렬, 필터, 벌크 작업이 필요한가?
□ 비기능 요구사항: 반응형, 다크모드, 접근성은?
□ 태스크 수가 4개 이상인가? (아니면 Claude 직접 코딩)
```

**데이터 모델 설계 원칙**: 타입/인터페이스는 Claude가 설계. 구현 로직은 Codex가 작성.

### Phase 1: 분석 (Claude)

요청을 받으면 **독립적으로 병렬 실행 가능한** 서브태스크로 분해.

**좋은 서브태스크 조건**:
- 다른 서브태스크 완료를 기다리지 않아도 됨
- 명확한 입출력(시그니처) 정의 가능
- Codex 혼자 구현 가능한 범위
- 파일/기능 경계가 명확함

### Phase 2: 설정 (Claude)

`parallel.config.yaml`의 `tasks:` 섹션을 수정.

> **instruction 작성 전 반드시 Read**:
> - `${HOME}/.claude/skills/comad-parallel/references/codex-guide.md` — Codex 특성, DO/DON'T 규칙, 라이브러리 대체 방지
> - `${HOME}/.claude/skills/comad-parallel/references/instruction-templates.md` — 템플릿, 좋은/나쁜 예시, 자기 점검 체크리스트
> - `${HOME}/.claude/skills/comad-parallel/references/tech-stack.md` — 2025-2026 기준 모던 스택 추천표

**instruction 작성 시 반드시 지킬 것:**
1. 시그니처와 요구사항만 작성 (코드 본문 작성 금지)
2. 강한 게이트 설정 (tsc/build/test 중심)
3. 제약사항 명확히 (라이브러리, 스타일, 금지사항)

### Phase 3: 실행 (Claude → Bash)

```bash
${HOME}/.claude/skills/comad-parallel/scripts/parallel.sh start "프로젝트 개요: [간단한 설명]"
```

### Phase 4: 모니터링 (Claude)

```bash
${HOME}/.claude/skills/comad-parallel/scripts/parallel.sh wait [JOB_DIR]
```

### Phase 5: 게이트 검증 + 선택적 코드 리뷰 (Claude)

```bash
${HOME}/.claude/skills/comad-parallel/scripts/parallel.sh results [JOB_DIR]
```

**4단계 검증 프로세스:**

```
Step 0: 의존성 확인 (게이트 실행 전 필수)
  └── node_modules가 없으면: cd [프로젝트] && npm install --silent
  └── tsc/build/test 게이트는 의존성 설치 후에만 유효

Step 1: 자동 게이트 실행 (bash, 토큰 0)
  └── tsc --noEmit → npm run build → npm test → grep 확인

Step 2: 결과 판정
  ├── 전부 통과 → Codex 보고서만 읽기 (토큰 소량)
  └── 실패 있음 → 실패한 게이트 관련 코드만 읽기 (토큰 최소화)

Step 3: 서브태스크 간 인터페이스 확인
  └── 타입/import 경로 등 교차 검증
```

### Phase 5.5: 코드 정리 (선택적, /simplify 활용)

> 게이트가 모두 통과했지만 코드 품질을 한 단계 높이고 싶을 때 사용.

**조건**: Phase 5 게이트 전부 PASS + 태스크 3개 이상일 때 권장

```
Phase 5 게이트 PASS → /simplify 실행 → 게이트 재실행 → Phase 6 통합
```

### Phase 6: 통합 및 수정 (Claude 판단 + Codex 재위임)

**수정이 필요한 경우**: Claude가 직접 고치지 않고 Codex에 재위임.

```
Claude가 하는 일: "뭘 고칠지" 결정 (자연어 수정 지시)
Codex가 하는 일: 실제 수정 실행
```

**수정이 필요 없는 경우**: 서브태스크 간 연결만 확인 후 정리.

```bash
${HOME}/.claude/skills/comad-parallel/scripts/parallel.sh clean [JOB_DIR]
```

> **실행 예시 참고**: `${HOME}/.claude/skills/comad-parallel/references/examples.md`

---

## 커맨드 레퍼런스

```bash
# 시작
parallel.sh start [--config path] "프로젝트 컨텍스트"
parallel.sh start --json "컨텍스트"

# 상태 확인
parallel.sh status [JOB_DIR]          # JSON
parallel.sh status --text [JOB_DIR]   # 한 줄 요약
parallel.sh status --checklist [JOB_DIR]

# 대기
parallel.sh wait [JOB_DIR]

# 결과
parallel.sh results [JOB_DIR]
parallel.sh results --json [JOB_DIR]

# comad 통합 — handoff (Phase 1.1)
parallel.sh handoff [--out PATH] [--json] [JOB_DIR]
# 7-section 핸드오프 doc 생성 (Summary/Key Decisions/Traps/Working Agreements/Relevant Files/Open Work/Prompt for New Chat)
# 출력 위치 우선순위: --out > $COMAD_SESSION_DIR > <git-root>/.comad/sessions/ > ~/.claude/.comad/sessions/
# Summary, Relevant Files, Open Work 는 members[].report.files_created/state 에서 자동 채움
# 나머지 3 섹션은 TODO(claude) stub — 사용자/Claude 가 직접 enrich
# `parallel.sh run-all` 끝에 자동 발화 (env COMAD_AUTO_HANDOFF=0 으로 비활성)

# comad 통합 — qa-evidence gate (Phase 1.2)
parallel.sh qa-gate [--json] [JOB_DIR]
# 각 done task 의 cwd 에서 `.qa-evidence.json` 존재 + verdict=PASS 검증
# comad-qa-evidence/bin/validate-qa-evidence.py 있으면 사용 (schema + verdict 둘 다 검증), 없으면 jq fallback
# 결과는 members/<task>/qa-evidence.json 에 저장, blocking 1+ 면 exit 1
# `run-all` 흐름: env COMAD_QA_EVIDENCE=1 설정 시 results 후 자동 호출 → handoff 가 결과 반영
# Codex worker 가 산출 코드에 .qa-evidence.json 안 만들면 missing 으로 표시됨 → handoff Open Work 에 명시

# comad 통합 — second-opinion gate (Phase 1.3)
parallel.sh second-opinion-gate [--json] [JOB_DIR]
# 각 done task 의 cwd 에서 `.second-opinion.md` frontmatter 의 verdict 검증 (verify mode)
# verdict: APPROVED → passed, REQUEST_CHANGES/BLOCKS → failed, 파일 없음 → missing
# 실행 X (자동 codex review 안 함) — Claude/사용자가 별도로 comad-second-opinion 스킬 호출해서 작성
# 결과는 members/<task>/second-opinion.json, blocking 1+ 면 exit 1
# `run-all` 흐름: env COMAD_SECOND_OPINION=1 설정 시 qa-gate 후 자동 호출 → handoff 반영
# missing 시 handoff Open Work 에 "/comad-second-opinion 실행" 안내 자동 삽입

# comad 통합 — destroy-check (Phase 2.2)
parallel.sh destroy-check [--json] [JOB_DIR]
# Codex worker 의 output.txt 에서 destructive 패턴 grep (사후 검사 — Codex 는 별도
# 프로세스라 Claude 의 pre-tool-use hook 적용 불가).
# 차단 패턴: rm -rf /|~|$HOME, git push --force, git reset --hard ref, git branch -D protected,
#   git clean -fd, DROP DATABASE/SCHEMA, TRUNCATE DATABASE, kubectl delete ns/node,
#   docker system prune -a, mkfs.*, fork bomb (총 13종)
# 결과는 members/<task>/destroy-check.json, blocking 1+ 면 exit 1
# `run-all` 흐름: env COMAD_DESTROY_CHECK=1 설정 시 second-opinion-gate 후 자동 호출

# T6 학습 연계 (Phase 2.1) — 코드 변경 없음, 동작 조건만 명시
# `~/.claude/hooks/stop/t6-capture.sh` 는 Claude 세션 종료 시 git log 의 fix:/feat: 커밋 자동 포착.
# parallel worker 가 산출 변경을 git commit (with prefix `fix:` or `feat:`) 하면 다음 Claude
# 세션 종료에서 ~/.claude/.comad/pending/ 에 자동 덤프 → /comad-learn 으로 학습 가능.
# 권장: parallel task instruction 에 "When done, create a git commit with prefix fix:/feat:" 명시.

# ear 알림 (Phase 2.3) — opt-in
# env COMAD_EAR_NOTIFY=1 + DISCORD_WEBHOOK_URL 모두 설정 시 cmdRunAll 끝에 한 줄 요약 POST.
# 실패 silent (stderr 만 한 줄). curl 의존.

# 관리
parallel.sh stop [JOB_DIR]
parallel.sh clean [JOB_DIR]
```

---

## 파일 구조

```
${HOME}/.claude/skills/comad-parallel/
├── SKILL.md                    # 이 문서
├── parallel.config.yaml        # 작업 목록 (매 실행 전 수정)
├── references/
│   ├── anti-patterns.md        # 복붙형 instruction 절대 금지
│   ├── role-separation.md      # Claude vs Codex 역할 경계
│   ├── codex-guide.md          # Codex 특성 + instruction 규칙
│   ├── instruction-templates.md # instruction 템플릿 + 좋은/나쁜 예시
│   ├── tech-stack.md           # 모던 기술스택 추천표
│   └── examples.md             # 실행 예시 (Todo 앱, 인증 시스템)
└── scripts/
    ├── parallel.sh               # 진입점
    ├── parallel-job.sh           # Node.js 래퍼
    ├── parallel-job.js           # 오케스트레이터
    └── parallel-job-worker.js    # Codex 워커 (detached)
```

---

## 주의사항

**순서 의존성 처리**:
태스크 간 의존성이 있으면 **라운드**로 분리:
```
Round 1: 공유 타입/유틸리티 (3개 병렬)
Round 2: Round 1 결과 사용하는 태스크 (2개 병렬)
Round 3: 최종 통합 (Claude 직접)
```

**Codex CLI 필요**:
```bash
command -v codex  # 설치 확인
# 없으면: npm install -g @openai/codex
```
