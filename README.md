# comad-world-extensions

코마드월드(~/.claude) 위에 얹는 자가진화·안전·메모리 레이어. Claude Code OAuth 사용자를 위한 로컬 전용 확장. 설치하면 다음이 붙는다.

- **destroy-gate** — Approval-Gated Destruction 훅. `rm -rf /`, `git push --force`, `DROP DATABASE` 같은 재해급 명령을 sha256 커맨드-바인드 승인 없이는 `exit 2`로 차단. 문자열 리터럴/heredoc 내부의 위험 패턴은 스트립 후 매칭해서 오탐 없음.
- **usage-gate** — OAuth 5h/7d 쿼터를 로컬 transcript에서 실측(`input + output + cache_creation`)하여 임계치 초과 시 배경 에이전트 호출을 블록. 전경 오퍼레이터의 Opus 예산을 보전.
- **T6 자가진화 루프** — Stop hook이 `fix:/feat:/bugfix:` 커밋을 자동 포착(`.comad/pending/*.json`) → `/comad-learn`이 `memory/feedback_*.md`로 승격 + 2회+ 반복된 패턴은 HARD 훅 후보로 제안.
- **comad-memory** — `~/.claude/projects/*/memory/*.md`를 SQLite FTS5로 인덱싱. 파일이 단일 진실, DB는 캐시. `sync / search / trace / refresh` 4개 도구.
- **comad-learn validator 2종** — pending JSON schema, feedback 템플릿(strict/lenient dual-mode).

설치는 복사 기반. 원본은 이 repo가 canonical, `~/.claude/` 에는 install.sh가 복사본을 넣는다.

## 설치

```bash
git clone https://github.com/kinkos1234/comad-world-extensions ~/Programmer/01-comad/comad-world-extensions
cd ~/Programmer/01-comad/comad-world-extensions
./install.sh
```

`install.sh`는 `~/.claude/hooks/`, `~/.claude/skills/{comad-learn,comad-memory}/`, `~/.claude/.comad/usage-gate.json`(없을 때만)을 설치하고, 초기 FTS 인덱스를 bootstrap한다. 기존 파일은 `.bak-<UTC>` 로 백업 후 덮어쓴다.

설치 후 두 가지 수동 작업:
1. `~/.claude/settings.json` 의 `hooks` 블록에 3개 훅 등록 (install.sh 종료 시 스니펫 출력)
2. `~/.claude/CLAUDE.md` 에 T6 섹션 추가 (아래 § CLAUDE.md T6)

## 레이아웃

```
hooks/
  pre-tool-use/
    destroy-gate.sh      # Claude Code PreToolUse[Bash] entrypoint (delegates to .py)
    destroy-gate.py      # quote/heredoc-aware blocker, sha256 command-bound approval
    usage-gate.sh        # PreToolUse[Task] quota defender (reads usage-gate.json)
    README.md            # hook behavior reference
  stop/
    t6-capture.sh        # Stop hook — dumps fix:/feat: commits to .comad/pending/

skills/
  comad-learn/
    SKILL.md
    bin/validate-pending.py
    bin/validate-feedback.py
  comad-memory/
    SKILL.md
    bin/{lib,sync,search,trace,refresh}.py

config/
  usage-gate.json.template  # seed config (enabled=false by default)

patches/
  nexus-sprint-stage5-p7.md # gstack nexus-sprint Stage 5 P7 loop — manual apply
```

## 의존성

- `python3` (3.10+ 권장, sqlite3 stdlib 사용)
- `bash` (macOS 기본 3.2 호환 — mapfile 사용 안 함)
- `git` (t6-capture가 `git log`/`git rev-parse` 사용)

외부 패키지 의존성 없음. `pip install` 필요 없음.

## CLAUDE.md T6

설치 후 `~/.claude/CLAUDE.md`에 아래 섹션을 붙인다. 기존 Comad Voice 워크플로우(T0/T4/T5)와 호환.

```markdown
## T6. 자가진화 루프 (Self-Evolve)

**자동 포착:** Stop hook이 매 세션 종료 시 현재 git 저장소의 최근 `fix:/feat:/bugfix:` 커밋을 `~/.claude/.comad/pending/*.json`에 덤프. 사용자 개입 없음.

**감지 키워드:** "학습", "comad-learn", "자가진화", "배워줘", "pending 분석"

1. `Skill(skill: "comad-learn")` 호출 — pending/*.json 분석
2. 판정 기준 통과한 커밋만 `memory/feedback_{topic}.md`로 승격 (append-only)
3. 같은 topic이 2회 이상 관찰되면 해당 메모리 파일에 "HARD 훅 후보" 섹션 추가 + 사용자 승인 요청
4. 처리한 pending은 `_processed/`, 거부는 `_rejected/`로 이동 (원본 삭제 금지)

**Approval-Gated Destruction 훅과의 연동:** 2회+ 반복 패턴 중 `rm`, `git reset`, `DROP` 계열이 탐지되면 destroy-gate 패턴 리스트에 추가 제안.
```

## 사용

### destroy-gate 승인 플로우

1. Claude가 위험 명령 시도 → 훅이 차단 + 명령 해시 출력
2. 사용자가 승인: `touch ~/.claude/.comad/approvals/approve-destroy.<hash>`
3. Claude 재시도 → 승인 소모 → 통과
4. 다른 위험 명령은 해시가 다르므로 여전히 차단

Fallback(공용 1회): `touch ~/.claude/.comad/approvals/approve-destroy` — 다음에 들어오는 아무 위험 명령이나 통과시킨다.

### usage-gate 활성화

기본은 `enabled=false`. 활성화 시:

```bash
# 수동 강제 (쿼터 무관, 항상 배경 에이전트 블록)
python3 -c "import json,pathlib; p=pathlib.Path('~/.claude/.comad/usage-gate.json').expanduser(); d=json.load(open(p)); d['enabled']=True; d['mode']='force-downgrade'; open(p,'w').write(json.dumps(d, indent=2, ensure_ascii=False)+'\n')"

# 또는 auto 모드 (실측 기반, 10분마다 refresh 필요)
python3 ~/.claude/skills/comad-memory/bin/refresh.py
```

`refresh.py`를 launchd/cron으로 10분마다 돌리면 `current_5h_pct / current_7d_pct` 가 지속 갱신된다. OAuth 구독이라 API 비용 $0.

### comad-memory 검색

```bash
cd ~/.claude/skills/comad-memory/bin
python3 sync.py                            # 인덱스 갱신
python3 search.py "discord" --type=feedback
python3 search.py "인프라" --limit=3
python3 trace.py <fact_id>                 # 원본 md 경로 역추적
```

## 검증

92/92 end-to-end 감사 통과 (2026-04-20). 카테고리:
- C1 destroy-gate robustness · C2 quote/heredoc stripping · C3 usage-gate state machine
- C4 t6-capture (non-git/detached/empty/dup) · C5-6 comad-memory sync/search/edge cases
- C7 skill/agent 파일 무결성 · C8 nexus-sprint P7 참조 무결성 · C9 settings.json backup
- C10 sqlite 동시성

## 라이선스

MIT. 개인 사용 또는 fork 환영.
