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

## L0~L5 QA 레벨 (Tier 3 확장, 선택적)

체크 키에 `L<digit>_` 접두어를 쓰면 validator가 의미를 인식한다. 프로젝트
타입에 따라 적용 불가한 레벨은 `"status": "N/A"` 로 선언 — FAIL로 치지
않고 verdict=PASS에 지장 없음.

| 키 | 의미 | 전제 |
|----|------|------|
| `L0_api_contract` | DTO/스키마 필드 매핑 검증 | API 있는 프로젝트 |
| `L1_ui_render` | UI 렌더링 + 스크린샷 + viewport | 브라우저 필요 |
| `L2_api_call` | curl 200 응답 + CORS 헤더 | HTTP API |
| `L3_crud_roundtrip` | Write → Read → Compare | 영속 상태 있는 시스템 |
| `L4_console_errors` | 브라우저 console.error == 0 | 브라우저 필요 |
| `L5_field_mapping` | frontend type ↔ backend response 일치 | FE+BE 양쪽 있는 프로젝트 |

**Status enum**: `PASS | FAIL | SKIP | N/A`
- `N/A` = 이 프로젝트 타입에 해당 레벨 적용 안 됨. verdict=PASS와 호환.
- `SKIP` = 이번 세션에서 일부러 건너뜀. verdict=PASS와 호환하지만 coverage
  수치가 빠졌다는 기록이 남음.

**L1 / L4 (브라우저 필요) 추가 필드:**
- `tool`: "chrome-devtools-protocol | cdp | playwright | manual | ..."
- `viewports`: ["1280x720", "375x812"] (L1만)
- `console_errors`: 정수 (L4 PASS 시 반드시 0)

**예시 (웹 프로젝트):**
```json
"checks": {
  "L0_api_contract":   {"status": "PASS", "command": "python3 verify-dto.py"},
  "L1_ui_render":      {"status": "PASS", "tool": "cdp",
                        "viewports": ["1280x720","375x812"], "console_errors": 0},
  "L2_api_call":       {"status": "PASS", "command": "curl -sI"},
  "L3_crud_roundtrip": {"status": "PASS"},
  "L4_console_errors": {"status": "PASS", "tool": "cdp", "console_errors": 0},
  "L5_field_mapping":  {"status": "PASS", "details": "generated types match response"}
}
```

**예시 (CLI 라이브러리):**
```json
"checks": {
  "L0_api_contract":   {"status": "N/A"},
  "L1_ui_render":      {"status": "N/A"},
  "L2_api_call":       {"status": "N/A"},
  "L3_crud_roundtrip": {"status": "N/A"},
  "L4_console_errors": {"status": "N/A"},
  "L5_field_mapping":  {"status": "N/A"},
  "unit_tests":        {"status": "PASS", "passed": 47, "failed": 0, "total": 47}
}
```

validator는 `L\d+_` 접두어를 쓰되 위 6개 외 이름을 쓰면 경고를 낸다 (오타
방지). "L9_something" 같은 자유 이름은 `custom.*`로 표현 권장.

## Depth Profile (smoke vs deep) — schema_version 2

표면 검증 (build/lint/HTTP 200) 만 통과해도 PASS 받는 약점을 막기 위해
**profile** 필드 도입. 프로덕션·실서비스에 영향이 있는 변경은 자동으로
"deep" 으로 추정되어 더 엄격한 audits 가 강제된다.

### 어떤 변경에 무엇을 고르나 (2026-08-15 명문화)

**원칙: 증거는 레포의 것이 아니라 이번 푸시의 것이다.** `profile` 은 레포 성격이 아니라
**이번에 밀어 넣는 변경**이 무엇인지로 고른다. 그래서 매번 `scope`·`git_head` 를 갱신하고
`profile` 을 **명시**한다 (추정에 맡기지 않는다).

| 이번 변경이… | profile | 요구되는 증거 |
|---|---|---|
| 문서·주석·가이드 페이지 | `smoke` | 렌더/링크가 깨지지 않았다는 확인 |
| 훅·스크립트·CI 설정 등 사용자 런타임 밖 | `smoke` | 구문 검사 + **통과 케이스와 실패 케이스 양쪽** 재현 |
| 테스트·픽스처만 | `smoke` | 테스트 실행 결과 |
| 사용자 경로에 닿는 기능(UI·API·워커) | `smoke` + 해당 영역 실측 | 브라우저 QA(콘솔 0)·실요청·실렌더 |
| 배포·마이그레이션·인증/권한·의존성 교체·외부 노출 | `deep` | audit 6종 + artifacts |

**판정기·가드를 고칠 때는 `smoke` 라도 실패 케이스 재현이 필수다.** 통과만 확인하고 내보내면
"좁히다가 무력화된 가드"를 배포하게 된다 (`rules/guard-scope-discipline`).

### 낡은 증거가 만드는 두 가지 사고

1. **엉뚱한 프로파일로 판정된다** — 4개월 전 전체 시스템 QA 스냅샷이 남아 있어, 셸 스크립트
   2파일 푸시에 CVE 스캔·주입 프로브를 요구하며 막았다 (comad-world, 2026-08-15).
2. **더 위험한 쪽 — 그냥 통과시킨다.** 낡은 파일이 `smoke` + `verdict=PASS` 였다면 오늘 푸시는
   **아무 검증 없이 게이트를 통과**했을 것이다. 게이트가 있는데도 무증거 푸시가 된다.

그래서 `git_head` 가 현재 HEAD 와 다르면 validator 가 경고한다. **그 경고를 보면 증거를 다시
쓰는 게 맞다** — 무시하고 넘기면 2번이 된다.

### 자동 추정 규칙 (validator)

`profile` 필드 명시 안 했을 때:
1. `scope` 또는 `notes` 에 `production`, `live`, `deploy`, `launch`,
   `release`, `prod`, 또는 production URL (`https://*.fly.dev` 등),
   `flyctl`, `kubectl`, `docker compose up`, `terraform apply` 매칭 → **deep**
2. `audit.*` 키가 8개 이상 → **deep**
3. 그 외 → **smoke** (현 default)

명시는 init 시:
```bash
init-qa-evidence.py --profile deep --scope "production launch QA"
```

### Deep profile 필수 audits (6 + 1)

각 카테고리에서 **canonical key 또는 alias 중 하나** 가 있어야 함. status 는
`PASS|SKIP|N/A` 모두 허용 (단 SKIP/N/A 는 `details` 에 30자 이상의 사유 필요).

| canonical key | 의미 | 실행 예시 |
|---|---|---|
| `audit.dependency_cve` | 의존성 CVE | `npm audit` / `pip audit` / `cargo audit` |
| `audit.data_integrity` | foreign key / orphan / referential | `db.collection.aggregate` 로 orphan 검색 |
| `audit.injection_probe` | NoSQL/SQL/XSS | 검색 input 에 `$ne`, `<script>` 등 던져 차단 확인 |
| `audit.observability_verified` | error 캡처 **실측** | 일부러 throw → Sentry/CloudWatch 콘솔 1건 확인 |
| `audit.performance_baseline` | latency / lighthouse / bundle | curl latency p95, lighthouse, `next build` analyze |
| `audit.query_plan` (DB 있는 경우) | DB explain | `db.collection.find().explain('executionStats')` |

aliases 도 인정:
- `audit.npm_audit`, `audit.pip_audit` → dependency_cve
- `audit.fk_integrity`, `audit.orphan_check` → data_integrity
- `audit.xss_probe`, `audit.nosql_injection` → injection_probe
- `audit.sentry_capture`, `audit.error_capture` → observability_verified
- `audit.lighthouse`, `audit.latency_p95`, `audit.bundle_size` → performance_baseline
- `audit.mongo_explain`, `audit.index_hit` → query_plan

### Shallow audit 감지

deep profile 에서 `audit.*` 의 status=PASS 인데 `details` 가 40자 미만이면
**warning**. "PASS" 한 줄로 박지 말고 구체 증거 (수치, 명령 출력, 파일 경로) 명시.

### Artifacts / Inventory 최소

deep profile:
- `artifacts` >= **5** (스크린샷, 로그, 스크립트, config 파일 경로 등)
- `inventory` 차원 >= **4** (예: routes / workers / server_actions / collections)
- `notes` >= **200자** (warning, hard fail 아님)

### 자동 검증 못 한 영역 (사용자 인터랙티브 필수)

자동화 어려운 audits 도 명시 — 그래야 verdict=PASS 의 "신뢰 범위" 가 명확:
- **OAuth 흐름** — 사용자 토큰 필요. 자동 PASS 못 하면 `status="SKIP"` + 사유
- **결제/인앱** — 별도 sandbox
- **chaos engineering** — 외부 서비스 down 시뮬레이션

### deep template seed (init `--profile deep`)

```json
"checks": {
  "build": {"status": "PENDING", "command": "<runtime build command>"},
  "audit.dependency_cve": {"status": "PENDING", "command": "<npm audit | pip audit | ...>"},
  "audit.data_integrity": {"status": "PENDING", "details": "<orphan/FK/referential check>"},
  "audit.injection_probe": {"status": "PENDING", "details": "<NoSQL/SQL/XSS probes attempted>"},
  "audit.observability_verified": {"status": "PENDING", "details": "<actually triggered an event and saw it in dashboard>"},
  "audit.performance_baseline": {"status": "PENDING", "details": "<latency p50/p95 or lighthouse score or bundle size>"},
  "audit.query_plan": {"status": "PENDING", "details": "<DB explain showing index hit, not COLLSCAN>"}
}
```

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
