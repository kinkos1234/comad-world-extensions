---
name: comad-sdd
description: Spec-Driven Development 루프 스킬. show-me-the-prd(기획)와 autoplan(리뷰) 사이의 빈 골격을 채운다 — 기능 하나를 Spec → 완료기준(acceptance criteria) → Plan → Build → Verify(완료기준 대조) 의 닫힌 루프로 끌고 간다. 각 완료기준을 검증 가능한 체크(test/gate/관찰)에 1:1 매핑해서 "다 됐다"를 증거로 증명. comad 역할 taxonomy·qa-evidence·adr·handoff 와 연동. 트리거 — 한국어 "/comad-sdd, SDD, 스펙 기반 개발, 스펙 작성해줘, 완료기준 정의, spec 만들어줘, 이 기능 스펙부터, 명세 작성"; 영어 "comad-sdd, spec-driven, write a spec, acceptance criteria, SDD loop, spec first". 단발 버그수정·1~2스텝 작업엔 트리거 안 함(오버헤드) — 새 기능/0→1 MVP/1→10 확장처럼 완료기준이 여러 개일 때만.
---

# comad-sdd — Spec-Driven Development 루프

> 패스트캠퍼스 하네스 강의(SDD: Spec.md → Plan.md → 완료기준 → test-loop)의 comad-native 구현.
> comad 스택 갭 메우기: show-me-the-prd(인터뷰 기획)는 **무엇을 만들지**, autoplan(CEO/eng 리뷰)은 **계획이 탄탄한지**를 다룬다. 그 사이 **"명세 → 검증가능한 완료기준 → 구현 → 완료기준 대조"** 의 닫힌 루프가 비어 있었다. 이 스킬이 그 루프다.

## 핵심 원칙

**완료기준(acceptance criteria)이 먼저다. 그리고 모든 완료기준은 검증 가능해야 한다.**

- 검증 불가능한 완료기준은 완료기준이 아니다 ("잘 동작한다" ❌ → "POST /login 200 + Set-Cookie 헤더 존재" ✅).
- 각 완료기준 ↔ 검증 수단(unit test / 게이트 명령 / 브라우저 관찰)을 1:1 매핑.
- "구현 끝"의 정의 = **모든 완료기준이 PASS 증거를 가짐**. 코드가 컴파일되는 것 ≠ 완료.
- [[feedback_web_deploy_live_check]] · [[reference_comad_qa_evidence]] 와 같은 철학: 주장 금지, 증거 강제.

## 산출물 위치

```
<git-root>/.comad/sdd/<feature-slug>/
├── spec.md      # WHAT + WHY + 완료기준(체크리스트)
├── plan.md      # HOW: 단계·파일·역할배정·리스크
└── evidence.md  # 완료기준별 검증 결과 (Build 후 채움)
```

## 5단계 루프

### S1. SPEC (무엇을·왜)
`spec.md` 작성. 섹션 고정:
```markdown
# Spec: <기능명>
## 목적 (Why) — 사용자/비즈니스 문제 한 문단
## 범위 (Scope) — In / Out 명시 (Out 도 적는다)
## 완료기준 (Acceptance Criteria)
- [ ] AC1: <검증 가능한 단언> → 검증수단: <test/gate/관찰>
- [ ] AC2: ...
## 비범위·가정 (Assumptions) — 모호한 결정의 기본 해석
```
- 모호하면 show-me-the-prd 로 먼저 기획 인터뷰를 돌리고 그 산출을 Spec 으로 정제.
- AC 는 3~7개 권장. 1~2개면 이 스킬 불필요(직접 구현). 10개+면 기능 분할.

### S2. PLAN (어떻게)
`plan.md` 작성. [[reference_comad_role_taxonomy]] 의 역할로 단계 배정:
```markdown
# Plan: <기능명>
## 단계 (역할 매핑)
1. [SCOUT] <탐색할 것> — agentType Explore
2. [PLANNER] <설계할 것>
3. [WORKER] <구현 단위> — direct / Workflow worktree / comad-parallel(Codex)
4. [VERIFIER] <검증> — 각 AC 대조
## 건드릴 파일
## 리스크 / 롤백
```
- 구현 메커니즘 선택은 [[reference_comad_orchestration_routing]] "누가 코드를 쓰나" 로 결정.
- 계획이 큰 결정을 포함하면 autoplan(CEO/eng/design 리뷰)을 여기서 한 번 통과시킨다.
- 아키텍처 결정이 발생하면 `/adr` 로 ADR 남기고 plan.md 에서 (ADR-NNNN) 링크.

### S3. BUILD (구현)
plan.md 의 단계대로 실행. 역할별 정규 프롬프트는 role_taxonomy 참조.
- 대량·독립 모듈 → comad-parallel(Codex). Claude-품질·고통합 → Workflow worktree 또는 direct.
- WORKER 는 시그니처 고정·스텁 금지·tsc→build→test 직접 통과 (AGENTS.md 컨벤션).

### S4. VERIFY (완료기준 대조) — 루프의 핵심
`evidence.md` 에 **AC 별로** 검증 결과를 채운다:
```markdown
# Evidence: <기능명>
- AC1: ✅ PASS — `npm test -- auth.spec` 12/12, 로그 첨부
- AC2: ✅ PASS — curl 200 + Set-Cookie 확인
- AC3: ❌ FAIL — <원인> → S3 로 되돌림
```
- 하나라도 FAIL → S3(또는 S1 재정의)로 **루프백**. 전부 PASS 여야 종료.
- 가능하면 `.qa-evidence.json` 도 생성(comad-qa-evidence) → push 게이트와 연동.
- 검증은 적대적으로: VERIFIER 역할(codex review / adversarial-review WF)로 "AC 가 정말 충족됐나" refute 시도.

### S5. CLOSE (종료)
- spec.md 의 완료기준 체크박스 전부 `[x]`.
- `/handoff`(T5)로 세션 핸드오프 — Relevant Files 에 `.comad/sdd/<slug>/` 포함.
- 커밋은 `feat:`/`fix:` 프리픽스 (T6 캡처 연동).

## 빠른 시작
```
/comad-sdd <기능명>
→ S1 spec.md 초안 생성 → 사용자 완료기준 확인 → S2~S5 진행
```

## 안 쓰는 경우
- 단발 버그수정, 1~2스텝, 완료기준 1개 이하 → 직접 구현이 빠름.
- 순수 탐색/리서치 → deep-research / Explore.
- UI 미세조정 → design-review.

## 검증 헬퍼
`scripts/check-acceptance.sh <feature-slug>` — spec.md 의 미체크 AC 개수와 evidence.md 의 FAIL 개수를 세서 종료 가능 여부 판정 (둘 다 0 이어야 통과).

## 관련
- [[reference_comad_role_taxonomy]] · [[reference_comad_orchestration_routing]] · [[reference_comad_qa_evidence]] · [[reference_comad_verification_gates]] · [[feedback_handoff_template]] · [[feedback_web_deploy_live_check]]
