---
name: comad-memory
version: 0.1.0
description: |
  코마드 전용 메모리 인덱스. ~/.claude/projects/*/memory/*.md를 SQLite FTS5로
  인덱싱하고, 빠른 전문 검색 + type 필터를 제공. 파일이 단일 진실, DB는 캐시.
  Phase 2에서 sqlite-vec 임베딩 추가 가능.
  Trigger: "/comad-memory", "메모리 검색", "메모리 동기화", "memory search",
  "memory sync", "기억 찾아줘".
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
---

# Comad Memory — Custom Memory Index (v0.1, FTS5)

hugh-kim의 memory-bank MCP를 통째로 들여오는 대신, 기존 코마드 메모리 레이아웃에 얇은
SQLite 인덱스를 얹은 **파일 우선** 설계. md 파일이 항상 단일 진실. DB는 언제든 `sync`로 복구.

## 레이아웃

```
~/.claude/projects/{proj-slug}/memory/
  MEMORY.md                      # 기존 인덱스 (수동 편집 가능)
  {type}_{topic}.md              # 기존 개별 메모리 (frontmatter 포함)

~/.claude/.comad/memory/         # (신규, 캐시 전용)
  facts.sqlite                   # FTS5 인덱스
  sync.log                       # 마지막 sync 이력
```

## DB 스키마 (FTS5)

```sql
CREATE VIRTUAL TABLE facts USING fts5(
  fact_id UNINDEXED,   -- hash(path + heading)
  project UNINDEXED,   -- ~/.claude/projects/{proj-slug}
  file_path UNINDEXED,
  type,                -- user | feedback | project | reference (frontmatter)
  name,                -- frontmatter name
  description,         -- frontmatter description
  body,                -- 본문 전체
  mtime UNINDEXED,
  tokenize='unicode61 remove_diacritics 2'
);
```

## 제공 도구 (3종, 축약)

| 도구 | 사용 케이스 |
|------|-------------|
| `comad-memory sync` | 파일 변경 후 인덱스 재구성 (incremental, mtime 기반) |
| `comad-memory search <query> [--type=feedback] [--project=...] [--limit=N]` | FTS5 전문 검색 |
| `comad-memory trace <fact_id>` | fact_id → 원본 md 파일 경로 + 본문 반환 |

## 사용 지점

1. **comad-sleep (dream 트리거)** — 메모리 정리 후 `comad-memory sync` 호출
2. **SessionStart 훅** — "dream" 힌트와 나란히 "최근 인덱스: N facts across M files" 요약
3. **comad-evolve Phase 1** — `comad-memory search "반복" --type=feedback`로 로컬 피드백 마이닝
4. **수동 조회** — 사용자가 "언제 인프라 제약 얘기했지?"처럼 물을 때 `search` 직접 호출

## 작동 원칙

- **파일 우선**: md가 단일 진실. DB는 캐시 — 날려도 `sync`로 복구
- **Append-only 지향**: md 파일 수정은 기존 섹션 추가만. DB는 자동 upsert
- **Incremental**: mtime > last_sync 파일만 재인덱싱
- **분리**: comad-world ≠ 다른 프로젝트. 인덱스는 모든 프로젝트를 커버하되 project 필드로 구분

## Phase 2 (이후 승격 시)

의존성 설치 최소화를 위해 MVP는 FTS5만. 의미 검색이 필요하면:
- `pip install sqlite-vec sentence-transformers`
- `vec.sqlite`에 ko-sroberta-multitask 384차원 임베딩 저장
- `search --semantic`으로 활성화

승격 조건: FTS5로 "못 찾는" 케이스가 반복 관찰되고, 사용자가 명시적으로 요청할 때.

## 실행 스크립트

`bin/sync.py`, `bin/search.py`, `bin/trace.py` — 모두 Python 3 stdlib + sqlite3만 사용.

## Safety

- 절대 `~/.claude/projects/*/memory/*.md`를 수정하지 않음 (read-only)
- DB 파일만 쓴다 (`~/.claude/.comad/memory/facts.sqlite`)
- 동일 fact_id 충돌 시 덮어쓰기 (mtime 기준 최신)
- 빈 파일 / 깨진 frontmatter는 스킵 + sync.log에 기록

## 스코프

- **In**: `~/.claude/projects/*/memory/*.md` 전체 (multi-project), 인덱스 DB
- **Out**: 소스 코드 인덱싱, 세션 transcript, 외부 문서 (RAG 범위 확장은 Phase 3)
