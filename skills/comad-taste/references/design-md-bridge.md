# DESIGN.md ↔ design-dna 브릿지 (gstack ↔ comad 스택 통합)

> 문제 (2026-07-10 진단): comad 에 디자인 스택이 2개 공존 — **gstack**(design-consultation 이 쓰는 DESIGN.md·design 바이너리·browse) 과 **comad**(design-dna·render.sh·swipe). 서로 참조가 없어 brand-factory 등 실제 파이프라인이 comad 미감 레이어를 우회했다.
> 해법: DESIGN.md 를 **인터페이스**로 삼는다. 이 문서가 매핑의 단일 진실원. (gstack 스킬 파일은 서드파티 — 수정해도 gstack-upgrade 시 소실되므로 브릿지 로직을 그쪽에 두지 않는다.)

## 방향 1 — DESIGN.md 를 **소비**할 때 (comad-taste S0)

프로젝트에 DESIGN.md 가 있으면:

| DESIGN.md 필드 | design-dna 처리 |
|---|---|
| 색 팔레트 (brand/accent/neutral) | 아키타입의 색 토큰을 **오버라이드** — 브랜드색이 항상 이긴다 |
| 타이포 (display/body 폰트) | 아키타입 타입 토큰 오버라이드. 단 **사이즈·무게·트래킹 규율은 아키타입 것 유지** (예: A 는 800 금지) |
| 톤/무드 형용사 | 아키타입 **선택**의 입력 (아래 매핑표) |
| 금지사항 | 아키타입 anti 목록에 **합집합**으로 추가 |
| (없는 필드: spacing·surface·signature·모션) | 아키타입 스펙이 그대로 채운다 — DESIGN.md 는 색·타입 위주라 구조 미감은 design-dna 가 보완 |

**원칙: DESIGN.md = 브랜드 아이덴티티(색·폰트·톤), design-dna = 구조 미감(위계·여백·surface·signature·anti·모션). 충돌 시 아이덴티티는 DESIGN.md, 규율은 design-dna.**

## 방향 2 — DESIGN.md 를 **생성**할 때 (design-consultation 실행 전후)

design-consultation(gstack) 을 호출해 DESIGN.md 를 만들 때:
1. **호출 전**: 프로젝트 도메인으로 아키타입 1개를 선택하고, 그 스펙(색 방향·타입 규율·spacing·anti)을 consultation 의 컨텍스트에 제안 입력으로 함께 넘긴다.
2. **호출 후**: 산출된 DESIGN.md 끝에 아래 스탬프를 append 한다 (이후 세션이 브릿지를 인식):

```markdown
<!-- comad-taste bridge -->
## Comad Taste Layer
- archetype: <A~F 중 선택> (see ~/.claude/skills/comad-taste/references/design-dna.md)
- 시각 산출물 생성 시 comad-taste 5단계 루프(S0 주입 → S2 렌더 → S3 6축 채점 → 24/30 게이트) 적용
- motion: design-dna MOTION DNA <아키타입> 행 준수
```

## 톤 → 아키타입 매핑표

| DESIGN.md 톤/도메인 | 아키타입 |
|---|---|
| 미니멀·고급 / B2B SaaS·개발도구·핀테크 | A. Dark Product |
| 콘텐츠·프리미엄·포트폴리오·문서 | B. Light Editorial |
| 친근·발랄 / 소비자앱·웰니스·교육 | C. Warm Consumer |
| 트렌디·힙 / 캠페인·런칭·크리에이터 | D. Bold Statement |
| 어드민·내부도구·데이터 밀집 | E. Dense Utility |
| 브랜드 케이스스터디·에이전시급 쇼케이스 | F. Studio Brand-Editorial |

## 소비자 목록 (이 브릿지를 쓰는 곳)

- **comad-brand-factory** Step 2 STRATEGY — DESIGN.md 생성 시 방향 2 적용, 이후 모든 ASSET 프롬프트에 아키타입 토큰 포함
- **comad-taste** S0 — 방향 1 적용
- gstack design-shotgun/design-html 산출물 — comad-taste S2~S5 로 채점 (gstack 쪽 수정 없이 산출물 단계에서 게이트)
