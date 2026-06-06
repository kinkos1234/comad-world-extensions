# comad-world-extensions

코마드월드(`~/.claude/`) 위에 얹는 자가진화·안전·증명 레이어. Claude Code OAuth 사용자를 위한 로컬 전용 확장, 외부 서비스 의존성 없음.

설치하면 다음이 붙는다.

- **훅 10종** — pre-tool-use 4개(destruction / env-commit / push-QA / usage gate) + Stop 6개(t6-capture / claim-done / premature-completion / numeric-claim / inventory / **adversarial-review**). Stop 훅이 import하는 공유 라이브러리는 `hooks/lib/`(`decisions` · `substantial_change`).
- **스킬 12종** — `comad-learn`(T6 pending 분석) / `comad-memory`(SQLite FTS5 메모리 검색) / `comad-qa-evidence`(L0~L5 QA 증거) / `comad-second-opinion`(2차 리뷰 아티팩트) / `comad-parallel`(Codex CLI 병렬 외주 + 5종 comad 통합 게이트) / `comad-ci-healer`(GH Actions 실패 자가복구 상시 에이전트) / `comad-pr-review`(4축 Autonomous PR Reviewer) / `comad-sdd`(Spec-Driven Development 루프 — SPEC→완료기준→PLAN→BUILD→VERIFY 닫힌 루프) / `comad-taste`(Taste Layer — 레퍼런스×자기비평 디자인 퀄리티 상향, design-dna 코퍼스+anti-slop+렌더 하네스) / `harness-report`(5축 하네스 점수 + 비용/efficiency 측정) / `comad-recall`·`comad-foresight`(brain 활용 — ⚠️ **comad-brain Neo4j 필요**, 출처인덱스 + 10렌즈 foresight).
- **Codex AGENTS.md worker conventions** — `comad-parallel`(품앗이)이 띄우는 Codex 워커가 qa-gate/destroy-check/T6-capture 를 기본값으로 통과하도록 CLAUDE.md 의 Codex-side 미러를 `~/.codex/AGENTS.md` 에 멱등 주입(`config/codex-agents-comad-conventions.md`).
- **워크플로우 템플릿 2종** — `adversarial-review`(R2: N 회의론자가 diff를 깨려 시도 → `.second-opinion.md`) / `judge-panel`(R5: N 전략 렌즈 생성 → 병렬 심사 → 합성). `~/.claude/workflows/`에 설치, Claude Code Dynamic Workflow로 호출.
- **T6 자가진화 루프** — Stop hook이 `fix:/feat:/bugfix:` 커밋을 `.comad/pending/*.json`에 자동 포착 → `/comad-learn`이 `memory/feedback_*.md`로 승격, 2회+ 반복은 HARD 훅 후보로 승인 요청.
- **Approval-Gated Destruction** — `rm -rf /`, `git push --force`, `DROP DATABASE` 같은 재해급 명령을 sha256 커맨드-바인드 승인 없이는 `exit 2`로 차단. heredoc/문자열 리터럴 내부 패턴은 스트립 후 매칭해서 오탐 없음.
- **Proof-Driven QA** — 주장이 아닌 파일(`.qa-evidence.json` + `.second-opinion.md`)이 PASS의 증거. `git push` 전 Claude Code 훅이 schema + verdict를 검증. R2 `adversarial-review-gate`(Stop)는 "substantial 코드 변경 완료 주장 + 승인된 적대적 리뷰 부재"를 감지해 경고(기본 log-only).

설치는 복사 기반. 이 repo가 canonical이고 `install.sh`가 `~/.claude/` 로 복사본을 푼다. 외부 CLI 의존 없이 Python stdlib + bash만 사용.

## 설치

```bash
git clone https://github.com/kinkos1234/comad-world-extensions ~/Programmer/01-comad/comad-world-extensions
cd ~/Programmer/01-comad/comad-world-extensions
./install.sh
```

`install.sh`는 `~/.claude/hooks/{pre-tool-use,stop}/`, `~/.claude/skills/{comad-learn,comad-memory,comad-qa-evidence,comad-second-opinion,comad-parallel,comad-ci-healer,comad-pr-review,comad-sdd,comad-taste,harness-report,comad-recall,comad-foresight}/`, `~/.claude/.comad/` 디렉토리 트리를 세팅하고, `~/.codex/AGENTS.md` 에 comad worker conventions 를 멱등 append 한다. 기존 파일은 `.bak-<UTC>` 로 백업 후 덮어쓴다. 재실행 안전.

설치 후 두 가지 수동 작업:

1. `~/.claude/settings.json`의 `hooks` 블록에 10개 훅 등록 (install.sh 종료 시 스니펫 출력)
2. `~/.claude/CLAUDE.md`에 T6 섹션 추가 (아래 § CLAUDE.md T6)

## 훅 카탈로그

### pre-tool-use (4종)

| 훅 | 역할 | 트리거 | 승인 플래그 |
|---|---|---|---|
| `destroy-gate` | Approval-Gated Destruction | `rm -rf /`, `rm -rf ~/...`, `git push --force`, `DROP`, `truncate` 등 | `approve-destroy[.<hash>]` |
| `no-env-commit` | `.env`/credentials `git add` 차단 | `.env`, `credentials.json`, `*.pem` 등 staging | `approve-env-commit[.<hash>]` |
| `qa-gate-before-push` | `.qa-evidence.json` 있으면 `verdict=PASS` 강제 | `git push` | `approve-push-qa-skip[.<hash>]` |
| `usage-gate` | OAuth 5h/7d 쿼터 방어 (현재 dormant) | 배경 `Task` 호출 | `approve-usage-once` |

### stop (6종)

| 훅 | 역할 | 로그 |
|---|---|---|
| `t6-capture` | 세션 종료 시 현재 repo의 최근 `fix:/feat:/bugfix:` 커밋 포착 | `.comad/pending/*.json` |
| `claim-done-gate` | "모두 통과 / 92/92 PASS" 류 주장 + Bash 검증 없음 감지 | `.comad/pending/claim-done.jsonl` |
| `premature-completion-detector` | "수렴 달성" 조기 선언 감지 | `.comad/pending/premature-completion.jsonl` |
| `numeric-claim-gate` | "완벽/production-ready/100%" 절대 주장 vs 실제 evidence | `.comad/pending/numeric-claim.jsonl` |
| `inventory-gate` | coverage 주장 vs inventory cross-check | `.comad/pending/inventory-gate.jsonl` |
| `adversarial-review-gate` | substantial 코드 변경 "완료" 주장 + 승인된 `.second-opinion.md` 부재 감지 (R2) | `.comad/pending/adversarial-review.jsonl` |

Stop 훅은 기본 WARN-ONLY (exit 0 + 로그). 환경변수 `COMAD_*_BLOCK=1` 설정 시 exit 2로 승격.

> Stop/QA 훅이 import하는 공유 모듈은 `hooks/lib/`에 있다 — `substantial_change.py`(diff/경로 substantial heuristic) · `decisions.py`(자율 프로세스 결정 에스컬레이션 큐; comad-world `nightly-audit.sh`도 공유).

## 스킬 카탈로그

| 스킬 | 목적 | 핵심 바이너리 |
|---|---|---|
| `comad-learn` | T6 pending JSON → feedback memory 승격 + validator 2종 | `validate-pending.py`, `validate-feedback.py` |
| `comad-memory` | `~/.claude/projects/*/memory/*.md`의 SQLite FTS5 인덱스 | `sync.py`, `search.py`, `trace.py`, `refresh.py` |
| `comad-qa-evidence` | `.qa-evidence.json` 생성·검증 (L0~L5 지원) | `init-qa-evidence.py`, `validate-qa-evidence.py` |
| `comad-second-opinion` | `.second-opinion.md` 생성 가이드 + 검증기 | `validate-second-opinion.py` |
| `comad-parallel` | Codex CLI 병렬 외주 (Claude=PM, Codex×N=구현) + comad 5종 게이트 (handoff·qa-gate·second-opinion-gate·destroy-check·ear-notify) 통합 | `parallel.sh`, `parallel-job.js` (1500+ LOC) |
| `comad-ci-healer` | GH Actions 실패 → 분류 → headless claude 수정 → PR 자동생성 (세션 밖 launchd 폴러, allowlist+dry_run 가드) | `poll.py`, `classify.py`, `heal.sh`, `notify.sh`, `run.sh` |
| `comad-pr-review` | PR diff 4축(correctness·security·performance·convention) 자동 채점 → 인라인+요약 코멘트 (codex 독립 + headless claude, headSha dedup) | `review.sh`, `post.sh`, `run.sh` |
| `comad-sdd` | Spec-Driven Development 닫힌 루프 — SPEC(완료기준 체크리스트)→PLAN(역할 taxonomy 배정)→BUILD→VERIFY(AC별 evidence 대조, FAIL시 루프백)→CLOSE. show-me-the-prd(기획)와 autoplan(리뷰) 사이 갭. | `check-acceptance.sh` |
| `comad-taste` | Taste Layer — 디자인 생성 퀄리티 상향. "퀄리티≈레퍼런스×자기비평" 진단으로 ① design-dna 코퍼스(6 아키타입) 주입 ② generate→render→screenshot→critique(6축 루브릭+anti-slop)→regenerate 루프. swipe-harvester로 레퍼런스 자산화. | `render.sh`, `swipe-harvest-*.mjs` |
| `harness-report` | Loopy-Era 5축 하네스 점수 + 비용/efficiency(notional list-price, 품질 composite와 분리) 측정 → `results.tsv` 추세 + HTML 대시보드 | `harness-report.py`, `collect-cost.py`, `dashboard.py` |
| `comad-recall` ⚠️brain | comad-brain(Neo4j) 출처-인덱스 리콜 — 주제의 실재 기사·계보. recency 질문 +3.12 lift(측정) | `recall.sh` |
| `comad-foresight` ⚠️brain | brain hot클러스터 → 10렌즈 전략 foresight + 주간 통합 인텔리전스 리포트. plain 대비 +1.375(측정) | `cluster.sh`, `digest.sh`, `run.sh` |

## QA 레벨 (L0~L5)

`comad-qa-evidence`는 주장의 강도에 따른 증거 수준을 정의한다.

| 레벨 | 의미 | 최소 증거 |
|---|---|---|
| **L0** | 단순 의견, 리뷰 | 증거 없음 (bypass keyword 필수) |
| **L1** | "구현 완료" | 변경 diff 존재 |
| **L2** | "테스트 통과" | L1 + test 실행 로그 |
| **L3** | "전수 검증" | L2 + inventory + 모든 대상 pass 로그 |
| **L4** | "프로덕션 준비" | L3 + 2차 리뷰(`.second-opinion.md`) |
| **L5** | "재해 복구 검증" | L4 + 실제 프로덕션 rollout 기록 |

주장 등급이 올라갈수록 `qa-gate-before-push`와 `numeric-claim-gate`의 요구가 엄격해진다.

## 워크플로우

### QA 증거 (push 전)

```bash
cd <project>
python3 ~/.claude/skills/comad-qa-evidence/bin/init-qa-evidence.py --scope "feature X"
# ... 구현 + 테스트 ...
# .qa-evidence.json 의 checks{} 채우고 verdict=PASS 로 변경
python3 ~/.claude/skills/comad-qa-evidence/bin/validate-qa-evidence.py   # rc 0 → OK
git push   # qa-gate-before-push 훅이 verdict=PASS 검증 후 통과
```

### 2차 리뷰 (L4 이상)

1. codex CLI 가용: `codex exec --full-auto "Review this diff for ..." > /tmp/review.txt`
2. codex 부재: `Agent(volt-error-detective)` 또는 `Agent(general-purpose)`로 adversarial review
3. 결과를 프로젝트 루트 `.second-opinion.md`에 frontmatter + Scope/Findings/Verdict 구조로 저장
4. 검증: `python3 ~/.claude/skills/comad-second-opinion/bin/validate-second-opinion.py` → rc 0 = APPROVED
5. `.qa-evidence.json.checks.second_opinion` 에 `{status: PASS, artifact: ".second-opinion.md"}` 연결

### 적대적 리뷰 · 판정 패널 (Dynamic Workflows)

`~/.claude/workflows/`의 두 템플릿은 Claude Code Dynamic Workflow 엔진(`Workflow` 도구)으로 호출한다. headless `claude -p` cron에서는 직접 호출 불가 — 에이전트 opt-in 기능.

- **`adversarial-review`** — 기존 변경을 *검증*. N명의 회의론자가 각기 다른 렌즈(correctness / security / edge)로 diff를 깨려 시도 → 과반 투표로 verdict → `.second-opinion.md` 작성. `adversarial-review-gate` 훅이 요구하는 아티팩트를 생성하는 기본 경로.
  - args: `{ repo?, target?, panel? }` (기본 panel=3)
- **`judge-panel`** — 해답 공간이 넓은 문제에 옵션을 *생성*. N개의 distinct 전략 렌즈(mvp-first / risk-first / user-first / long-game)가 독립 접근안 생성 → 기준별 병렬 심사 → 승자 + 차점안 아이디어 graft 합성. 설계·아키텍처·전략 결정용.
  - args: `{ problem, strategies?, panel?, criteria? }`

### Destroy-gate 승인 플로우

1. Claude가 위험 명령 시도 → 훅이 차단 + 커맨드 sha256 해시 출력
2. 사용자 승인: `touch ~/.claude/.comad/approvals/approve-destroy.<hash>`
3. Claude 재시도 → 승인 소모 → 통과 (다른 명령은 해시가 다르므로 여전히 차단)

Fallback (공용 1회): `touch ~/.claude/.comad/approvals/approve-destroy` — 다음 들어오는 아무 위험 명령이나 통과시킨다.

### 메모리 검색

```bash
cd ~/.claude/skills/comad-memory/bin
python3 sync.py                                 # 인덱스 갱신
python3 search.py "discord" --type=feedback
python3 trace.py <fact_id>                      # 원본 md 경로 역추적
```

## CLAUDE.md T6

설치 후 `~/.claude/CLAUDE.md`에 아래 섹션을 붙인다. 기존 Comad Voice 워크플로우(T0/T4/T5)와 호환.

```markdown
## T6. 자가진화 루프 (Self-Evolve)

**자동 포착:** Stop hook이 매 세션 종료 시 현재 git 저장소의 최근 `fix:/feat:/bugfix:` 커밋을 `~/.claude/.comad/pending/*.json`에 덤프. 사용자 개입 없음.

**감지 키워드:** "학습", "comad-learn", "자가진화", "배워줘", "pending 분석"

1. `Skill(skill: "comad-learn")` 호출 — pending/*.json 분석
2. 판정 기준 통과한 커밋만 `memory/feedback_{topic}.md`로 승격 (append-only)
3. 같은 topic이 2회 이상 관찰되면 해당 메모리 파일에 "HARD 훅 후보" 섹션 추가 + 사용자 승인 요청
4. 처리한 pending은 `_processed/`, 거부는 `_rejected/`로 이동

**Approval-Gated Destruction 연동:** 2회+ 반복된 패턴 중 `rm`, `git reset`, `DROP` 계열이 탐지되면 destroy-gate 패턴 리스트에 추가 제안.
```

## 진화 히스토리

| 티어 | 주요 내용 |
|---|---|
| **Tier 1** | destroy-gate + usage-gate + t6-capture + comad-learn/memory (92-case 매트릭스) |
| **Tier 2** | no-env-commit + qa-gate-before-push + claim-done-gate + premature-completion + numeric-claim + inventory-gate (포괄 증명 가드) |
| **Tier 3** | L0~L5 QA 레벨 + comad-qa-evidence + comad-second-opinion (주장→증거 전환) |

## 검증

| 종류 | 결과 |
|---|---|
| 합성 매트릭스 134 cases | 134/134 pass |
| 직접 스크립트 invoke | 전부 정확 exit code |
| 새 세션 라이브 dispatch (2026-04-20) | destroy-gate / qa-gate-before-push / t6-capture 모두 정상 fire |

**주의:** 훅 수정 직후 같은 세션에서 라이브 검증은 Claude Code 디스패처 캐시 이슈로 신뢰 불가. 반드시 새 세션 smoke test(`rm -rf ~/nonexistent-test`)부터 재검증.

## 의존성

- `python3` (3.10+ 권장, sqlite3 stdlib 사용)
- `bash` (macOS 기본 3.2 호환)
- `git` (t6-capture가 `git log` / `git rev-parse` 사용)

외부 패키지 의존성 없음. `pip install` 불필요. codex CLI는 2차 리뷰 시 선택적 가용 경로.

## 레이아웃

```text
hooks/
  pre-tool-use/
    destroy-gate.{sh,py}           # Approval-Gated Destruction
    no-env-commit.{sh,py}          # .env / credentials 차단
    qa-gate-before-push.{sh,py}    # push 전 .qa-evidence.json PASS 강제
    usage-gate.sh                  # OAuth quota defender (dormant)
    README.md                      # 훅 동작 레퍼런스
  stop/
    t6-capture.sh                  # fix:/feat: 커밋 → .comad/pending/
    claim-done-gate.{sh,py}        # 검증 없는 완료 주장 감지
    premature-completion-detector.{sh,py}
    numeric-claim-gate.{sh,py}
    inventory-gate.{sh,py}
    adversarial-review-gate.{sh,py} # R2: substantial 변경 완료 주장 + 적대적 리뷰 부재
  lib/
    substantial_change.py          # diff/경로 substantial heuristic (공유)
    decisions.py                   # 자율 프로세스 결정 에스컬레이션 큐 (공유)

skills/
  comad-learn/         SKILL.md + validate-{pending,feedback}.py
  comad-memory/        SKILL.md + {lib,sync,search,trace,refresh}.py
  comad-qa-evidence/   SKILL.md + {init,validate}-qa-evidence.py
  comad-second-opinion/ SKILL.md + validate-second-opinion.py

workflows/
  adversarial-review.js            # R2: N 회의론자 → .second-opinion.md
  judge-panel.js                   # R5: N 전략 렌즈 → 심사 → 합성

config/
  usage-gate.json.template

patches/
  nexus-sprint-stage5-p7.md
```

## 라이선스

MIT. 개인 사용 또는 fork 환영.
