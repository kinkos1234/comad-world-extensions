---
name: harness-report
version: 0.1.0
description: |
  Loopy-Era 하네스의 5축 점수를 측정하고 ~/.claude/.comad/results.tsv 에 추세를
  남기는 스킬. "지금 우리가 좋아지고 있는가?"라는 질문에 답하는 단일 진실원.
  Trigger: "harness-report", "/harness-report", "하네스 점수", "시스템 점수",
  "results.tsv", "지금 점수", "/loopy:status", "/loopy:measure".
allowed-tools:
  - Bash
  - Read
---

# Harness Report — 5축 측정 + 추세

목적: 사이트의 "harness-report 72→75" 처럼, 시스템 자체 개선을 **수치로** 추적한다.
측정 없이는 자가개선이 회귀를 만들어도 모른다.

## 측정 5축

| 축 | 의미 | 측정 |
|---|---|---|
| **HARD coverage** | 차단 가능한 hook 수 / 사이트 목표 12 | `~/.claude/hooks/{pre-tool-use,stop}/*.py` count |
| **Pending throughput** | 분석 처리율 | processed / (processed + pending) |
| **Recurring detection** | 반복 패턴 발견 수 | feedback_*.md 중 Seen ≥ 2 |
| **Second-opinion** | 외부 검토 적용 | .second-opinion.md 존재 프로젝트 수 |
| **Evolve activity** | 자율 흡수 활동 | .comad/evolve/applied/ 항목 수 |

각 축은 0~1 정규화 후 가중치 적용 → composite score 0~100.

## 사용

```bash
python3 ~/.claude/skills/harness-report/bin/harness-report.py
```

기본: 측정 + results.tsv 에 한 줄 append + summary 출력.

옵션:
- `--read-only` → results.tsv 마지막 줄만 출력, append 안 함 (`/loopy:measure` 용)
- `--history N` → 최근 N행 출력
- `--json` → JSON 출력

## 출력 예시

```
Harness Report — 2026-04-30T14:30
HARD coverage      : 7/12  (58%)   30 * 0.58 = 17.5
Pending throughput : 67/88 (76%)   30 * 0.76 = 22.9
Recurring          : 2/10  (20%)   20 * 0.20 = 4.0
Second-opinion     : 1     active  10 * 1.0  = 10.0
Evolve activity    : 0     idle    10 * 0.0  = 0.0
─────────────────────────────────
Composite score    : 54.4 / 100

Trend (last 3 entries):
  2026-04-30T14:30  54.4
  (no prior entries)
```

## results.tsv 스키마

```
ts  hard_count  hard_target  pending_total  pending_processed  recurring  second_opinion  evolve_applied  evolve_rejected  score  tokens_24h  usd_24h  notes
```

탭 구분. 행은 append-only. 직접 편집 금지.
구 11컬럼 스키마는 실행 시 자동 마이그레이션(새 컬럼 빈칸 backfill).

## 비용 축 (2026-06-04 추가)

품질 composite(0~100)와 **분리**된 efficiency 지표. 비용은 품질이 아니므로 합산 안 함.

- `collect-cost.py` — 트랜스크립트(`~/.claude/projects/*/*.jsonl`)의 usage 를 24h 윈도우 집계.
  모델별 **notional list-price**(Max 정액 → 실청구 아님, 효율 상대지표). mtime 필터로 빠르게.
- `harness-report.py` 가 매 측정마다 `tokens_24h`·`usd_24h` 자동 기록 + summary cost 블록 출력.
- **efficiency = score / (tokens_24h / 1M)** = 토큰당 품질. 점수↑·토큰↓ = 개선.
- `/loopy:status`(=`--read-only`)·자율루프 측정에 자동 반영(검증: iter-1483).
- `dashboard.py [--rows N] [--open]` → 자립형 HTML(`~/.claude/.comad/reports/dashboard.html`), 무의존 인라인 SVG.

## 위치

- 스크립트: `~/.claude/skills/harness-report/bin/harness-report.py`
- 출력 TSV: `~/.claude/.comad/results.tsv`
- 베이스라인 행: 첫 실행 시 자동 생성, notes="baseline"

## 통합

- A/B 판정 (F4) 가 이 스크립트를 호출해 변경 전후 점수 비교
- /loopy:status 가 마지막 줄 표시
- /loopy:history 가 최근 N행 차트화
