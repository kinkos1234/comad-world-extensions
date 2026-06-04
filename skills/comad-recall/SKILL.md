---
name: comad-recall
version: 1.0.0
description: |
  comad-brain(Neo4j 지식그래프) 을 "출처 검색 인덱스"로 활용하는 능동 리콜.
  한 주제의 실재 ear-큐레이션 기사(제목·날짜·URL) + 기술 계보를 지식팩으로 뽑아
  세션/에이전트에 주입한다. 축적만 되던 brain 을 실제 작업 컨텍스트로 전환(Tier 1).
  Trigger: "/comad-recall", "brain 검색", "brain에 뭐 있어", "최근 동향 brain", "지식 리콜".
allowed-tools:
  - Bash
  - Read
---

# comad-recall — brain 출처 인덱스 리콜

comad-brain(74K+ 노드 Neo4j)을 **claim 오라클이 아니라 "최신 실재 출처로 가는 인덱스"**로 쓴다.
3런 A/B 측정으로 검증된 설계(아래 § 측정).

## 사용

```bash
bash ~/.claude/skills/comad-recall/bin/recall.sh "<주제>"
```

출력 지식팩:
1. **매칭 엔티티** (Technology/Topic + degree)
2. **기술 계보** (ALTERNATIVE_TO/BUILT_ON/EVOLVED_FROM 등 관계)
3. **최근 관련 기사** — ear 큐레이션 **실재 출처**(제목·날짜·URL·요약). ← 핵심 가치
4. **⚠️ brain 추출 주장** — `verified=FALSE` 미검증. 단정 금지, 탐색 힌트로만.

## 🎯 선택적 발화 규칙 (측정으로 도출 — 중요)

**brain 리콜은 아래일 때만 호출**:
- ✅ **최신 동향 / 최근 출시 / 2026 신모델·신기법** 질문 (측정 lift **+3.12**)
- ✅ 니치·프로젝트 특화 주제 (모델 학습데이터에 약한)
- ✅ "최근", "요즘", "올해", "신규" 같은 recency 신호

**호출하지 말 것**:
- ❌ **타임리스 기초** (well-known 알고리즘·언어 패턴) — 모델이 이미 강함, lift ~0(+0.25), 노이즈만 추가
- ❌ 일반 코딩·개념 설명 (asyncio 패턴, SQL 튜닝 등)

## 사용 규칙 (주입 후)
- '최근 관련 기사'의 제목·URL은 **실재** — 인용·근거로 사용 가능(제목+URL 명시).
- '추출 주장'은 **미검증** — "사실"로 단정 말고 "출처 확인 필요" 힌트로만.
- brain 출처 + 자체지식을 자연스럽게 통합.

## 📐 측정 결과 (N=10 블라인드 A/B, LLM 심사)

| 단계 | lift | 비고 |
|---|---|---|
| run1 claim 주입(무인용) | +0.06 | flat — 미검증 claim 의심받음 |
| run2 claim+출처 | **−0.31** | 악화 — 인용이 fabrication 의심 자초 |
| **run3+4 출처-인덱스(현재)** | **+1.83** (8/10승) | ✅ recency 질문 **+3.12**, timeless +0.25 |

근본 발견: brain Claim 19,686개 **전부 verified=FALSE**(검증 파이프라인 휴면) → claim 레이어는 신뢰 불가, 실재 Article 만 신뢰. eval 데이터: `comad-world/brain/utilization-eval/results-tier1-*.json`.

## 후속 (별도)
- **brain 검증 파이프라인 부활**(0/19686 verified) — claim 레이어를 쓸 수 있게 만드는 brain 본체 개선.
- Tier 2/3 에서 이 recall 을 자동 발화(ear 클러스터 → eye)로 확장.
