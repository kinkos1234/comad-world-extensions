---
name: comad-foresight
version: 1.0.0
description: |
  brain hot-클러스터(ear 큐레이션 실재 기사)를 10-렌즈 전략 foresight 프레임워크
  (손자·스미스·탈레브·카너먼·메도우즈·데카르트·마키아벨리·클라우제비츠·헤겔·다윈)로
  재해석해 비자명 패턴·예측·실무 액션을 도출한다. eye 의 10렌즈 컨셉을 Claude 로 포팅한 것
  (Tier 2). eye 무거운 로컬-추출 파이프라인은 폐기 — 깨진 캐시·weak LLM 문제.
  Trigger: "/comad-foresight", "foresight", "전략 분석", "클러스터 분석", "렌즈 분석", "동향 예측".
allowed-tools:
  - Bash
  - Read
---

# comad-foresight — 10-렌즈 전략 Foresight

축적된 brain 지식을 **전략적 예측·통찰로 전환**(인지 루프). eye 의 핵심 가치(10렌즈
다관점 재해석)만 살리고, eye 의 broken 구현(로컬 qwen 추출 + stale 캐시)은 버렸다.

## 사용

```bash
# 1) 클러스터 조립 (brain hot-클러스터 자동 또는 지정)
bash ~/.claude/skills/comad-foresight/bin/cluster.sh                         # 최근 14일 hot 자동
bash ~/.claude/skills/comad-foresight/bin/cluster.sh "Claude Code,Codex,Gemini"  # 지정

# 2) Claude 가 references/lenses.md 프레임워크를 클러스터에 적용 → foresight 리포트
```

`references/lenses.md` = 10렌즈 37원리(eye lens_knowledge.py 포팅) + 산출 형식.

## 산출 (foresight 리포트)
1. 핵심 역학  2. 렌즈별 비자명 인사이트(각 렌즈 1개, 자명한 건 생략)
3. 교차 패턴(수렴 메타시그널)  4. 예측(신뢰도+근거)  5. 실무 액션

## 📐 측정 (Tier 2, 블라인드 A/B)

| 비교 | 결과 |
|---|---|
| eye 깨진 파이프라인 (run1) | ❌ 캐시 오염 → 마블 분석 garbage. 폐기 |
| **렌즈-foresight vs plain 분석** (run2) | ✅ **lift +1.375 (2/2승)** |

차별점(심사위원): 10렌즈 체계적 교차검증 + 놓친 행위자(예: CFO/조달) 발굴 + 확률보정 예측.
eye 대비: 빠름(~40s), 실재 추출(기사 자체, weak LLM 없음). eval: `comad-world/brain/utilization-eval/results-tier2-*.json`.

## Tier 3 · 통합 주간 인텔리전스 리포트
`run.sh` 는 두 파트를 하나로 묶는다:
- **Part 1 그래프 다이제스트** (`digest.sh`, 사실) — 이번 주 수집량·트렌딩 기술·신규 등장 토픽·예측 시그널(brain 그래프가 *학습한 것*)
- **Part 2 전략 Foresight** (해석) — 핫클러스터에 10렌즈 적용. 다이제스트의 신규토픽을 해석에 반영(예: "Dynamic Workflows 신규토픽"을 예측 근거로).

= 지각(ear)→기억(brain)→사실(digest)+해석(foresight)→산출(Discord)의 완전 루프.

## 자동화
**launchd `com.comad.foresight`** — 주간 월 09:00: digest + hot클러스터 foresight → 통합 리포트 → Discord(2000자 분할). dry_run=true 시작 → `config.json dry_run:false` 로 라이브.
산출: `~/.claude/.comad/foresight/foresight-<date>.md`. webhook = COMAD_CI_HEALER_WEBHOOK.

## eye 처리
eye(로컬 추출 파이프라인)는 **유지보수 중단 권고** — 캐시버그(`data/extraction/ontology.json` seed-키잉 안 됨) + weak qwen3.5:9b 추출. 컨셉은 이 스킬이 승계. 필요 시 eye 의 시뮬레이션(메타엣지·영향전파)만 별도 살릴 수 있으나 ROI 낮음.
