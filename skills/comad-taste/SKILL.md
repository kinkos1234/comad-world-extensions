---
name: comad-taste
description: AI 디자인 생성 퀄리티를 탑티어(인간 디자이너·상위 바이브코더) 수준으로 끌어올리는 공통 "Taste Layer". 핵심 진단 — 생성 퀄리티 ≈ (주입한 레퍼런스의 질) × (자기비평 반복 깊이)이며 모델 성능이 아니다. 그래서 ① design-dna 코퍼스(구조화 미감 스펙)를 텍스트지시 대신 통째로 주입하고 ② generate→render→screenshot→critique(6축 루브릭+anti-slop)→regenerate 자기비평 루프를 돌린다. UI/HTML/랜딩/컴포넌트/카드 등 시각 산출물 생성 시 design-shotgun·design-html·comad-brand-factory·comad-image·comad-app-prototype·comad-infographic 앞단에 끼우는 레이어. 트리거 — 한국어 "taste, 테이스트, 디자인 퀄리티, 고급스럽게, AI티 없애, 탑티어 디자인, 레퍼런스 주입, 자기비평 디자인, 디자인 끌어올려, 세련되게 만들어, 퀄리티 높여"; 영어 "taste layer, design quality, make it premium, top-tier design, anti-slop, less generic, elevate the design, reference-driven design". 단순 와이어프레임·기능 우선 프로토타입엔 트리거 안 함(미감 불필요할 때 오버헤드).
---

# comad-taste — Taste Layer

> **퀄리티 ≈ (레퍼런스의 질) × (자기비평 깊이).** 모델이 아니라 이 두 입력이 갭의 근원.
> PoC 검증(2026-06-06): 동일 제품·카피·도구로 제네릭 1-shot vs (레퍼런스+자기비평) → "AI 티" ↔ "탑티어 SaaS" 수준 차이.

## 언제 쓰나
시각 산출물의 **미감 수준**이 중요할 때, 생성 스킬 앞단에 끼운다:
- design-shotgun(variant) · design-html(프로덕션 HTML) · comad-app-prototype · comad-infographic · comad-brand-factory(납품 게이트) · comad-image(프롬프트에 DNA 주입)
- 직접 앱/랜딩을 바이브코딩할 때도 (CLAUDE.md 디자인 규칙으로)

**안 쓰는 경우**: 기능검증용 와이어프레임, 내부 임시 UI, 미감 무관 작업 → 오버헤드.

## 5단계 루프

### S0. TASTE SELECT — 레퍼런스 DNA 선택·주입
1. `references/design-dna.md` 에서 프로젝트 도메인/톤에 맞는 **아키타입 1개** 선택 (A.Dark Product / B.Light Editorial / C.Warm Consumer / D.Bold Statement / E.Dense Utility).
2. 그 아키타입의 **전체 스펙(색·타입·spacing·surface·signature·anti)을 통째로** 생성 컨텍스트/프롬프트에 박는다. "Minimalist" 같은 추상 텍스트 금지 — 구체 토큰.
3. 프로젝트에 DESIGN.md 있으면 토큰을 그쪽 우선으로 오버라이드(브랜드색 등).

### S1. GENERATE v1
선택 DNA + `references/anti-slop.md` 회피규칙을 적용해 산출물(HTML/React/이미지프롬프트) 생성.
- 실콘텐츠·실숫자·고유명사 사용(플레이스홀더 금지). 제품 UI면 **실제 목업**(브라우저 chrome·사이드바·KPI·SVG차트) 포함.

### S2. RENDER & SEE — 결과를 실제로 본다 (핵심)
HTML/UI는 반드시 렌더해서 스크린샷을 **Read 로 본다**. 안 보면 자기비평 불가.
```bash
bash ~/.claude/skills/comad-taste/scripts/render.sh <html> <out.png> 1440 980
# 그 다음 Read 도구로 out.png 를 본다.
```
- 이미지 생성(comad-image)은 산출 PNG를 그대로 Read.
- 풀페이지면 5번째 인자 `1`.

### S3. CRITIQUE — 6축 채점 + anti-slop 스캔
스크린샷을 보고:
1. `references/taste-rubric.md` 6축 각 0~5 채점 + 한 줄 근거.
2. `references/anti-slop.md` 즉시탈락 항목 스캔.
3. "이걸 Linear/Stripe 옆에 두면 어디서 티 나나?" **구체 결함 3가지** 명시.
> 추상적 "더 다듬자"(X). "헤드라인 800→600, 막대차트→area, 중앙정렬→좌측"(O).

### S4. REGENERATE
S3의 구체 결함을 고친 v2 생성 → S2~S3 재수행.
- **통과 기준**: 합계 ≥24/30 AND 모든 축 ≥3 AND 즉시탈락 0.
- **최대 3라운드**. 3라운드 후 미달이면 사용자에게 "여기까지 + 막힌 축" 보고(무한루프 금지).

### S5. GATE & DELIVER
통과한 산출물만 납품/통합. 점수 로그를 남긴다:
```
v1: 색4 타입3 공간3 표면3 신뢰2 차별3 = 18/30 → 신뢰·공간 타깃
v2: 색4 타입4 공간4 표면4 신뢰4 차별4 = 24/30 → 통과
```
- comad-brand-factory 연동: QA 게이트(qa-checklist) **다음**에 taste-gate로 호출 → 미달 asset 재생성.

## 다른 스킬과의 관계
- **comad-qa-evidence**(기능: 동작하나) · **design-review**(시각 일관성: 정렬·간격 버그) 와 **별개·보완**. Taste Layer 는 "**좋아 보이나**"(미적 수준).
- **adversarial-review/verification-gate 철학의 디자인판**: anti-slop을 적대적으로 refute("이거 generic 아닌가?").
- **design-shotgun**: variant N개 생성 → 각각 S2~S3 채점 → top만 노출(자동 큐레이션).

## 파일
```
~/.claude/skills/comad-taste/
├── SKILL.md
├── references/
│   ├── design-dna.md      # 미감 코퍼스 5 아키타입 (append-only, 신규 레퍼런스 추가)
│   ├── anti-slop.md       # generic-AI 탐지 체크리스트
│   └── taste-rubric.md    # 6축 채점 기준
└── scripts/
    ├── render.sh          # playwright 해소 래퍼
    └── render.mjs         # HTML → PNG @2x 스크린샷
```

## 코퍼스 성장
새 탑티어 레퍼런스를 보면 `design-dna.md` 해당 아키타입에 토큰/소스 **append**. 우리 best 산출물도 역설계해 추가. 코퍼스가 자랄수록 생성 품질이 복리로 오른다.
