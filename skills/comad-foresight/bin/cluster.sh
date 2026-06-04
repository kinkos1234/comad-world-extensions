#!/usr/bin/env bash
# comad-foresight · cluster.sh
# brain(Neo4j)에서 hot 클러스터를 탐지하거나 지정 토픽의 최근 기사팩을 조립한다.
# 출력 = foresight 분석 대상 클러스터(실재 기사 제목·날짜·URL·요약).
#
# 사용:
#   cluster.sh                      # 최근 14일 hot Technology 클러스터 자동 탐지 후 조립
#   cluster.sh "Claude Code,Codex,GPT-5.5,Gemini"   # 지정 엔티티들로 클러스터 조립
set -uo pipefail

CONTAINER="${COMAD_BRAIN_CONTAINER:-comad-brain-neo4j}"
PASS="${NEO4J_PASS:-knowledge2026}"
SINCE="${CLUSTER_SINCE:-$(python3 -c 'import datetime;print((datetime.date.today()-datetime.timedelta(days=14)).isoformat())')}"
cy() { docker exec "$CONTAINER" cypher-shell -u neo4j -p "$PASS" --format plain "$1" 2>/dev/null; }

ENTITIES="${1:-}"
if [ -z "$ENTITIES" ]; then
  # hot 클러스터 자동: 최근 SINCE 이후 기사 많은 Technology top
  echo "## 자동 탐지된 hot 클러스터 (최근 14일 기사 밀도순)" >&2
  TOP=$(cy "MATCH (a:Article)-[:DISCUSSES]->(t:Technology) WHERE a.published_date >= '$SINCE'
RETURN t.name AS tech, count(DISTINCT a) AS c ORDER BY c DESC LIMIT 8" | tail -n +2)
  echo "$TOP" >&2
  ENTITIES=$(echo "$TOP" | head -6 | sed 's/, [0-9]*$//' | tr -d '"' | paste -sd, -)
fi

# 엔티티 리스트 → cypher IN 절
IN=$(python3 -c "import sys;print(','.join(repr(x.strip()) for x in sys.argv[1].split(',') if x.strip()))" "$ENTITIES")

echo "# 클러스터: $ENTITIES — 최근 동향 (since $SINCE)"
echo
cy "MATCH (a:Article)-[:DISCUSSES]->(t:Technology)
WHERE t.name IN [$IN] AND a.published_date >= '$SINCE'
RETURN DISTINCT a.published_date AS d, a.title AS title, a.url AS url, left(coalesce(a.summary,''),260) AS summary
ORDER BY d DESC LIMIT 25" | sed 's/^/• /'
echo
echo "_(source: comad-brain · 클러스터 엔티티: $ENTITIES)_"
