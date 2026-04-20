---
name: comad-qa-evidence
version: 0.1.0
description: |
  QA 증거 파일(.qa-evidence.json) 생성·검증 스킬. Claude가 "QA 통과"를 주장하기
  전에 프로젝트 루트에 구조화된 증거 파일을 작성하고, validate-qa-evidence.py로
  자체 검증한다. #4 qa-gate-before-push.sh가 이 파일 + verdict=PASS를 `git push`
  이전 단계에서 강제한다.
  Trigger: "qa 증거", "qa-evidence", "/comad-qa-evidence", "QA 증거 파일",
  "QA 결과 기록", "증거 파일 생성".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# Comad QA Evidence

Claude가 QA 결과를 **구조화된 파일**로 기록하도록 강제한다. "테스트 통과"라는 문장
대신 `.qa-evidence.json` 의 `verdict`, `checks.*.status`, `inventory` 수치가 진실의
근거가 된다. `qa-gate-before-push.sh` 와 짝을 이뤄 push 단계에서 강제된다.

## 언제 사용하는가

다음 중 하나라도 해당하면 **QA 결과 주장 전에 반드시 증거 파일을 생성**한다.

- 사용자에게 "테스트 통과", "QA OK", "빌드 성공" 중 어느 것이든 보고할 때
- `git push` 직전 (다음 단계 #4 훅이 강제)
- 다음 세션에 "지난번 QA 결과" 주장하려 할 때

## 파일 위치

프로젝트 루트에 `.qa-evidence.json` (하나만). 여러 피처를 동시 검증하면 `scope`
필드로 구분한다.

## 도구 3종

### 1) init — 템플릿 생성

```bash
python3 ~/.claude/skills/comad-qa-evidence/bin/init-qa-evidence.py
```

기본 동작:
- CWD의 git 루트로 이동(또는 CWD)
- `.qa-evidence.json` 없으면 기본 스켈레톤 작성
- `generated_at`, `project_root`, `git_head` 자동 채움
- `verdict`는 항상 `"PENDING"`으로 시작 — Claude가 각 check 실행 후 채우고 마지막에 `PASS`로 승격

인자: `--scope "기능 X 검증"` (선택). `--force`로 기존 파일 덮어쓰기.

### 2) validate — 스키마 + 내부 일관성 검증

```bash
python3 ~/.claude/skills/comad-qa-evidence/bin/validate-qa-evidence.py [path]
```

기본 대상: `.qa-evidence.json` in CWD git root. 종료 코드:
- 0 — valid + verdict==PASS
- 1 — valid이지만 verdict!=PASS (PENDING/FAIL/PARTIAL)
- 2 — schema 또는 cross-check 위반

cross-check:
- `verdict=PASS`면 모든 `checks.*.status`가 `PASS|SKIP` (하나라도 FAIL이면 불일치)
- `inventory.*_total >= *_verified`
- `checks.browser_qa.status=PASS`면 `console_errors=0`
- 적어도 하나의 `checks` 엔트리 필수 (빈 checks 금지)

### 3) skill 호출 (Claude가 직접)

사용자가 "QA 돌려서 기록해줘" / "증거 파일 만들어줘" 요청하면:
1. `init-qa-evidence.py` 실행
2. 각 check를 순서대로 실행:
   - build → `checks.build`
   - typecheck → `checks.typecheck`
   - tests → `checks.unit_tests`
   - (web) browser_qa
   - (audit) 매트릭스 테스트
3. 결과를 파일에 기록 (Edit 도구)
4. `validate-qa-evidence.py` 실행 → exit 0이면 PASS 확정
5. 사용자에게 파일 경로 + `verdict` 보고

## 스키마 상세

```json
{
  "schema_version": "1",
  "generated_at": "ISO 8601",
  "project_root": "/abs/path",
  "git_head": "short hash",
  "scope": "한 줄 설명",
  "verdict": "PASS | FAIL | PARTIAL | PENDING",
  "checks": {
    "<name>": {
      "status": "PASS | FAIL | SKIP",
      "command": "실행한 명령 (선택)",
      "exit_code": 0,
      "passed": 92,
      "failed": 0,
      "total": 92,
      "details": "자유 텍스트"
    }
  },
  "inventory": {
    "api_endpoints_total": 7,
    "api_endpoints_verified": 7
  },
  "artifacts": ["logs/test.log", "/tmp/qa-screenshot-1.png"],
  "notes": "컨텍스트/제약/알려진 한계"
}
```

**예약된 check 키 (일관성 위해 권장):**
- `build`, `typecheck`, `lint`
- `unit_tests`, `integration_tests`, `e2e_tests`
- `browser_qa` — 추가 필드: `tool`, `viewports[]`, `console_errors`
- `audit` — 커스텀 감사(매트릭스, fuzz 등)
- `custom.<anything>` — 프로젝트 특유

## PASS 조건 체크리스트

`verdict: "PASS"`로 승격 전에 확인:

- [ ] 적어도 하나의 `checks` 엔트리 실행됨
- [ ] 모든 `checks.*.status`가 `PASS` 또는 `SKIP` (FAIL 0건)
- [ ] `inventory`가 있다면 coverage 완전 (`total == verified`)
- [ ] `scope`가 비어있지 않음
- [ ] `git_head`가 실제 현재 HEAD와 일치

## 나쁜 패턴 (감지되면 validator가 FAIL)

| 패턴 | 이유 |
|------|------|
| `verdict=PASS` + `checks.*.status=FAIL` | 거짓 승격 |
| `checks: {}` 빈 객체 | 검증 없이 PASS 선언 |
| `browser_qa.status=PASS` + `console_errors>0` | 브라우저 에러 무시 |
| `inventory.api_endpoints_verified > *_total` | 수치 불일치 |
| `scope=""` | 무엇을 검증했는지 불명 |

## Safety

- 이 스킬은 파일 생성/검증만 한다. 테스트 자체를 돌리지는 않는다 — Claude가
  각 체크를 실제 실행해야 한다
- `.qa-evidence.json`은 `.gitignore`에 추가할지 프로젝트마다 결정 (증거를
  tracked에 남길 수도, 빌드 artifact로 볼 수도)

## 스코프

- **In**: `.qa-evidence.json` 생성·검증, 스키마 enforcement
- **Out**: 실제 테스트 실행, 브라우저 자동화, CI 연동 (별도 스킬/도구)
