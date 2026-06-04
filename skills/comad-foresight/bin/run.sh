#!/usr/bin/env bash
# comad-foresight · run.sh — launchd 주간 진입점.
# hot 클러스터 탐지 → headless claude(10렌즈 적용) → foresight 리포트 → Discord.
# config dry_run 존중. 단일 인스턴스 락.
set -uo pipefail

export PATH="/Users/jhkim/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/Users/jhkim/.nvm/versions/node/v24.13.0/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG="$SKILL_DIR/config.json"
cfg() { python3 -c "import json,sys;print(json.load(open('$CFG'))$1)"; }
LENSES="$SKILL_DIR/references/lenses.md"
CLUSTER_SH="$SKILL_DIR/bin/cluster.sh"
DIGEST_SH="$SKILL_DIR/bin/digest.sh"

DRY_RUN="$(cfg "['dry_run']")"
ENTITIES="$(cfg "['cluster_entities']")"
REPORT_DIR="$(python3 -c "import os;print(os.path.expanduser('$(cfg "['report_dir']")'))")"
MIN_ART="$(cfg "['min_articles']")"
mkdir -p "$REPORT_DIR/logs"
RUNLOG="$REPORT_DIR/logs/run.log"
LOCK="$REPORT_DIR/run.lock"
STAMP="$(python3 -c 'import datetime;print(datetime.date.today().isoformat())')"
WEBHOOK_VAR="$(cfg "['notify_webhook_env']")"
WEBHOOK="${!WEBHOOK_VAR:-}"

log() { echo "$(python3 -c 'import datetime;print(datetime.datetime.now(datetime.UTC).isoformat())') $*" >> "$RUNLOG"; }

if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +180 2>/dev/null)" ]; then rmdir "$LOCK" 2>/dev/null && mkdir "$LOCK" 2>/dev/null || exit 0; else log "locked, skip"; exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

log "=== foresight 시작 (dry_run=$DRY_RUN) ==="
PACK="$REPORT_DIR/cluster-$STAMP.md"
bash "$CLUSTER_SH" "$ENTITIES" > "$PACK" 2>>"$RUNLOG"
NART=$(grep -cE '"[0-9]{4}-[0-9]{2}-[0-9]{2}"' "$PACK" 2>/dev/null) || NART=0
[ -z "$NART" ] && NART=0
log "클러스터 기사 ${NART}개"
if [ "$NART" -lt "$MIN_ART" ]; then log "기사 부족(<${MIN_ART}), 종료"; exit 0; fi

# Tier 3: 그래프 다이제스트(사실) — foresight 앞에 붙는 Part 1
DIGEST="$REPORT_DIR/digest-$STAMP.md"
bash "$DIGEST_SH" > "$DIGEST" 2>>"$RUNLOG" || true
log "다이제스트 생성"

REPORT="$REPORT_DIR/foresight-$STAMP.md"
PROMPT="아래 자료를 읽어라.
[10-렌즈 프레임워크]
$(cat "$LENSES")

[이번 주 brain 그래프 다이제스트 — 트렌딩·신규 토픽 (해석에 참고)]
$(cat "$DIGEST")

[분석할 핫 클러스터 — brain 큐레이션 실재 기사]
$(cat "$PACK")

프레임워크의 '산출 형식'대로 전략 foresight 리포트를 작성하라. 다이제스트의 트렌딩·신규토픽을 해석에 반영. 자명한 요약 금지, 각 렌즈는 그 렌즈 아니면 안 보이는 비자명 통찰만, 예측은 신뢰도+근거, 출처(기사 제목/URL) 명시. 450단어 이내. 출력은 리포트 본문만."

log "headless claude foresight 생성 중…"
FORESIGHT="$REPORT_DIR/_foresight-body-$STAMP.md"
claude -p "$PROMPT" --dangerously-skip-permissions < /dev/null > "$FORESIGHT" 2>>"$RUNLOG" || { log "claude 실패"; exit 1; }

# Tier 3 통합 인텔리전스 리포트 = 다이제스트(사실) + foresight(해석)
{
  echo "# 📡 주간 인텔리전스 리포트 — $STAMP"
  echo
  echo "> brain(74K+ 노드) 그래프 다이제스트 + 핫클러스터 10렌즈 전략 foresight"
  echo
  echo "---"
  echo "## Part 1 · 그래프 다이제스트 (이번 주 사실)"
  echo
  tail -n +2 "$DIGEST"
  echo
  echo "---"
  echo "## Part 2 · 전략 Foresight (10렌즈 해석)"
  echo
  cat "$FORESIGHT"
} > "$REPORT"
rm -f "$FORESIGHT"
log "통합 인텔리전스 리포트 → $REPORT ($(wc -l < "$REPORT") 줄)"

# Discord 전송
if [ "$DRY_RUN" = "True" ]; then
  log "dry_run=true → Discord 전송 안 함 (리포트만 저장)"
  echo "[dry-run] foresight 리포트 저장됨: $REPORT"
  exit 0
fi
if [ -z "$WEBHOOK" ]; then log "webhook 없음, 큐만"; echo "no webhook"; exit 0; fi
# 2000자 단위 분할 전송
python3 - "$WEBHOOK" "$REPORT" "$STAMP" <<'PY'
import json,sys,urllib.request
wh,rep,stamp=sys.argv[1],sys.argv[2],sys.argv[3]
body=open(rep).read()
header=f"🔮 **comad-foresight — {stamp}** (brain hot클러스터 10렌즈 분석)\n\n"
chunks=[]; cur=header
for line in body.splitlines(keepends=True):
    if len(cur)+len(line)>1900: chunks.append(cur); cur=""
    cur+=line
if cur.strip(): chunks.append(cur)
for c in chunks:
    data=json.dumps({"content":c[:1990]}).encode()
    req=urllib.request.Request(wh,data=data,headers={"Content-Type":"application/json","User-Agent":"comad-foresight/1.0"})
    try: urllib.request.urlopen(req,timeout=15)
    except Exception as e: print(f"send fail: {e}",file=sys.stderr)
print(f"sent {len(chunks)} chunk(s)")
PY
log "Discord 전송 완료"
