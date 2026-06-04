#!/usr/bin/env bash
# comad-foresight · digest.sh
# brain 그래프의 "이번 주 학습한 것" 다이제스트 — 수집량·트렌딩·신규클러스터·예측 시그널.
# Tier 3 인텔리전스 리포트의 사실(fact) 섹션. (foresight=해석, digest=사실)
set -uo pipefail

CONTAINER="${COMAD_BRAIN_CONTAINER:-comad-brain-neo4j}"
PASS="${NEO4J_PASS:-knowledge2026}"
DAYS="${DIGEST_DAYS:-7}"
SINCE="$(python3 -c "import datetime;print((datetime.date.today()-datetime.timedelta(days=$DAYS)).isoformat())")"
cy() { docker exec "$CONTAINER" cypher-shell -u "$PASS" -u neo4j -p "$PASS" --format plain "$1" 2>/dev/null; }
cyq() { docker exec "$CONTAINER" cypher-shell -u neo4j -p "$PASS" --format plain "$1" 2>/dev/null; }

echo "# 🧠 brain 주간 그래프 다이제스트 (최근 ${DAYS}일, since ${SINCE})"
echo

NEW=$(cyq "MATCH (a:Article) WHERE a.published_date >= '$SINCE' RETURN count(*)" | tail -1)
TOTAL=$(cyq "MATCH (n) RETURN count(n)" | tail -1)
echo "**수집량**: 신규 기사 ${NEW}건 · 그래프 총 ${TOTAL} 노드"
echo

echo "## 트렌딩 기술 (이번 주 기사 밀도)"
cyq "MATCH (a:Article)-[:DISCUSSES]->(t:Technology) WHERE a.published_date >= '$SINCE'
RETURN t.name AS tech, count(DISTINCT a) AS articles ORDER BY articles DESC LIMIT 10" | sed 's/^/  /'
echo

echo "## 신규 등장 토픽 (이번 주 첫 논의)"
cyq "MATCH (a:Article)-[:DISCUSSES]->(t:Technology) WHERE a.published_date >= '$SINCE'
WITH t, count(DISTINCT a) AS recent
MATCH (a2:Article)-[:DISCUSSES]->(t) WITH t, recent, count(DISTINCT a2) AS total
WHERE total <= recent + 1 AND recent >= 2
RETURN t.name AS emerging_tech, recent AS this_week ORDER BY recent DESC LIMIT 8" | sed 's/^/  /'
echo

echo "## 예측 시그널 (이번 주 추출된 forward-looking claims, 미검증)"
cyq "MATCH (a:Article)-[:CLAIMS]->(c:Claim) WHERE c.claim_type='prediction' AND a.published_date >= '$SINCE'
RETURN DISTINCT left(c.content,160) AS prediction, a.url AS source ORDER BY c.confidence DESC LIMIT 6" | sed 's/^/  /'
echo
echo "_(미검증 추출 — 단정 금지, 신호로만. source: comad-brain)_"
