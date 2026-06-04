#!/usr/bin/env bash
# comad-recall · recall.sh
# brain(Neo4j) 에서 주제 지식팩을 뽑아 markdown 으로 출력.
# 세션/에이전트가 "brain 이 이 주제에 대해 아는 것"을 능동 컨텍스트로 주입하는 메커니즘(1a).
#
# 사용: recall.sh "mixture of experts"
set -uo pipefail

Q="${1:?usage: recall.sh \"<topic>\"}"
CONTAINER="${COMAD_BRAIN_CONTAINER:-comad-brain-neo4j}"
USER="${NEO4J_USER:-neo4j}"
PASS="${NEO4J_PASS:-knowledge2026}"
LIMIT_ART="${RECALL_ARTICLES:-8}"
LIMIT_CLAIM="${RECALL_CLAIMS:-10}"

cy() { docker exec "$CONTAINER" cypher-shell -u "$USER" -p "$PASS" --format plain "$1" 2>/dev/null; }

ql=$(printf '%s' "$Q" | tr '[:upper:]' '[:lower:]' | sed "s/'/\\\\'/g")

echo "# 🧠 brain recall — \"$Q\""
echo

# 1) 매칭 엔티티
echo "## 매칭 엔티티 (Technology/Topic)"
cy "MATCH (t) WHERE (t:Technology OR t:Topic) AND toLower(t.name) CONTAINS '$ql'
RETURN t.name AS name, labels(t)[0] AS type, COUNT{(t)--()} AS degree
ORDER BY degree DESC LIMIT 6" | sed 's/^/  /'
echo

# 2) 기술 계보 (관계)
echo "## 기술 계보·관계"
cy "MATCH (t)-[r]-(rel:Technology) WHERE (t:Technology OR t:Topic) AND toLower(t.name) CONTAINS '$ql'
AND type(r) IN ['ALTERNATIVE_TO','BUILT_ON','EVOLVED_FROM','OPTIMIZES','DEPENDS_ON','INFLUENCES','USES_TECHNOLOGY']
RETURN t.name AS src, type(r) AS rel, rel.name AS dst LIMIT 15" | sed 's/^/  /'
echo

# 3) 최근 관련 기사 — 실재 ear-큐레이션 출처(제목·날짜·URL·요약). 모델이 직접 읽고 추론할 대상.
echo "## 최근 관련 기사 (실재 출처 — 읽고 추론할 대상, 주장 아님)"
cy "MATCH (a:Article)-[:DISCUSSES]->(t) WHERE (t:Technology OR t:Topic) AND toLower(t.name) CONTAINS '$ql'
RETURN DISTINCT a.published_date AS date, a.title AS title, a.url AS url, left(a.summary,180) AS summary
ORDER BY date DESC LIMIT $LIMIT_ART" | sed 's/^/  /'
echo

# 4) 미검증 추출 주장 — 참고용(brain Claim 은 verified=FALSE, 단정 금지)
echo "## ⚠️ brain 추출 주장 (미검증 verified=FALSE — 단정 인용 금지, 탐색 힌트로만)"
cy "MATCH (c:Claim) WHERE any(e IN c.related_entities WHERE toLower(e) CONTAINS '$ql')
OPTIONAL MATCH (src:Article {uid: c.source_uid})
RETURN DISTINCT left(c.content,160) AS hint, src.url AS check_at
ORDER BY c.confidence DESC LIMIT 5" | sed 's/^/  /'
echo

echo "_사용 규칙: 위 '기사'는 실재 출처 — 인용·근거로 사용 가능. '추출 주장'은 미검증 — 사실로 단정 말고 '출처 확인 필요' 힌트로만._"
echo "_(source: comad-brain Neo4j · $(cy "MATCH (n) RETURN count(n)" | tail -1) nodes)_"
