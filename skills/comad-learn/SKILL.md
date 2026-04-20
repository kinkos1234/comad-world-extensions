---
name: comad-learn
version: 0.1.0
description: |
  T6 자가진화 루프의 분석 단계. Stop hook이 ~/.claude/.comad/pending/에 포착한
  fix:/feat: 커밋들을 읽어서 반복되는 실수 패턴을 추출하고, memory/feedback_*.md로
  승격하거나 2회 이상 반복된 패턴은 exit 2 훅 후보로 승인 요청한다.
  Trigger: "comad-learn", "배워줘", "/comad-learn", "자가학습", "pending 분석",
  "실수 패턴 정리".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# Comad Learn — T6 Self-Evolution Analysis

Claude가 직접 실행하는 스킬. `pending/*.json`을 훑어서 가치 있는 패턴만 메모리로 승격한다.

## 입력

- `~/.claude/.comad/pending/*.json` — Stop hook이 포착한 fix:/feat: 커밋 raw 데이터
  - 필드: `commit`, `subject`, `body`, `diff_stat`, `diff_head`, `repo`, `kind`, `status`
- `~/.claude/projects/*/memory/feedback_*.md` — 기존 피드백 메모리 (반복 감지용)

## 출력

- `memory/feedback_{topic}.md` — 신규 승격 또는 기존 업데이트
- `~/.claude/rules/*.md` — 2회+ 반복 패턴은 HARD 차단 규칙 제안서
- `~/.claude/.comad/pending/_processed/{hash}.json` — 처리 완료 기록 (삭제하지 말고 이동)
- `~/.claude/.comad/pending/_rejected/{hash}.json` — 학습 가치 없음 판정

## 판정 기준 (하나라도 만족 못하면 REJECT)

1. **명시적 실수 수정인가?** `subject`가 `fix:` 또는 `bugfix:`로 시작하거나,
   `feat:`이라도 본문에 "regression", "edge case", "was broken" 같은 재발 방지 언급
2. **일반화 가능한 교훈인가?** 특정 프로젝트 로직 버그가 아니라, 다른 맥락에서
   반복될 수 있는 패턴인가? (예: "누락된 `await`", "잘못된 경로 슬래시", "인증 미체크")
3. **관찰 가능한 증거가 있나?** `diff_head`에 제거/추가된 코드가 교훈과 연결되는가?

## 프로세스

1. **Pre-validator 먼저 실행** — `python3 ~/.claude/skills/comad-learn/bin/validate-pending.py --move-invalid`
   - schema 위반 파일은 자동으로 `_invalid/`로 이동 → LLM 분석에서 자연 제외
   - exit 1이면 위반 파일 목록이 stdout에 표시됨. 그래도 계속 진행 (나머지 유효 파일만 처리)
2. `ls ~/.claude/.comad/pending/*.json`로 **유효** 파일 목록 확보
3. 각 파일에 대해:
   - `subject`, `body`, `diff_head` 읽기
   - 위 3개 판정 기준 통과하면 topic 추출 (예: `missing-await`, `path-slash`, `auth-missing`)
   - 같은 topic의 `memory/feedback_*.md`가 이미 있는지 확인
     - 있음 → 기존 파일에 `## Seen N회 @ {commit short} — {one-line}` 추가
       - 기존 `Seen`이 2회 이상이면 **HARD 훅 후보** 섹션에 제안 추가
     - 없음 → 신규 `feedback_{topic}.md` 작성 (frontmatter 포함)
3. 처리한 pending json은 `_processed/`로 이동
4. REJECT된 json은 `_rejected/`로 이동 (이유 주석)
5. MEMORY.md 인덱스에 신규 항목 한 줄 추가

## feedback 파일 템플릿

```markdown
---
name: {{topic}}
description: {{one-line}}
type: feedback
---

## 원칙
{{한 문장 규칙}}

**Why:** {{이유 — 어떤 커밋에서 어떤 증상이었는지}}
**How to apply:** {{어떤 맥락에서 이 규칙이 적용되는지}}

## 관찰 이력
- Seen 1회 @ {{commit}} ({{repo short}}) — {{증상/수정 요약}}

## HARD 훅 후보
- 해당 없음 (Seen < 2)
```

2회째 관찰되면 위 마지막 섹션을 업데이트:
```markdown
## HARD 훅 후보
- **승인 요청**: `grep -qE '{{pattern}}'` 감지 시 exit 2
  - 제안 위치: `~/.claude/hooks/pre-tool-use/{{topic}}-gate.sh`
  - 근거: 이 실수가 2회 이상 반복됨 ({{commit1}}, {{commit2}})
```

## Discord 리포트

실행 종료 시 Discord 채널에 요약 전송:
```
🧠 Comad Learn 완료
• 처리: {{N}}건
• 승격: {{N}}건 (memory/feedback_*.md)
• 반복 감지: {{N}}건 (HARD 훅 후보)
• Reject: {{N}}건
```

## Post-validation (필수)

새로 작성하거나 업데이트한 `feedback_*.md`에 대해 반드시 실행:
```bash
python3 ~/.claude/skills/comad-learn/bin/validate-feedback.py <file.md> [...]
```
exit 1이면 템플릿 준수 실패. 해당 파일을 기준에 맞춰 재작성한다.

검증 항목:
- frontmatter: `name`, `description`, `type: feedback`
- 본문: `## 원칙`, `**Why:**`, `**How to apply:**`, `## 관찰 이력`, `## HARD 훅 후보`
- HARD 훅 후보 섹션이 실제 승인 요청을 담으려면 `Seen ≥ 2`여야 함

## Safety

- 기존 `feedback_*.md`는 **append 만** (기존 섹션 덮어쓰기 금지)
- 신규 HARD 훅은 **제안만** 하고 실제 파일 생성은 사용자 승인 후
- pending 원본은 삭제 금지, `_processed/` 또는 `_rejected/`로만 이동

## 스코프

- **In**: `~/.claude/.comad/pending/*.json`, `~/.claude/projects/*/memory/feedback_*.md`, MEMORY.md
- **Out**: 소스 코드 수정, 다른 프로젝트 레포 변경, 실제 훅 파일 자동 생성
