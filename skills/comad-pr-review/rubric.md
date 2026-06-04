# comad-pr-review 루브릭 — 4축 × 심각도

PR diff 를 아래 4축으로 독립 채점한다. 각 발견(finding)은 file·line·severity·축·근거·제안수정을 갖는다.
plan-eng-review(아키텍처/엣지케이스) + codex(적대적) + review 스킬(SQL/LLM trust boundary) 기준 흡수.

## 축

### 1. correctness (심각도/정확성)
- 로직 버그, off-by-one, 잘못된 조건/부정
- 처리 안 된 엣지케이스(빈 입력, null, 경계값)
- 레이스 컨디션, 비동기 누락 await, 부분 실패
- 데이터 손실/손상 위험(파괴적 마이그레이션, 미가드 삭제)
- 조건부 부작용(early return 후 side effect 누락) — review 스킬 패턴

### 2. security (보안)
- injection(SQL/command/template), SSRF, path traversal
- authz/authn 경계 누락, IDOR
- 시크릿 노출(하드코딩 키, 로그 유출, NEXT_PUBLIC_* 민감정보)
- LLM trust boundary(사용자 입력→프롬프트 직주입, 도구 호출 무검증) — review 스킬 패턴
- 의존성 신규 추가 시 공급망 위험

### 3. performance (성능)
- N+1 쿼리, 무한정(unbounded) 쿼리/페치
- 동기 블로킹 in async, 불필요한 직렬화
- 메모리 누수, 대용량 in-memory 적재
- 번들 크기 급증, 무거운 dep 정적 import(→ dynamic import 권장)
- 캐시 무효화 누락 / 과도

### 4. convention (컨벤션/유지보수)
- 네이밍·스타일 불일치(주변 코드 대비)
- 테스트 커버리지 누락(신규 로직에 테스트 없음)
- 데드코드, 중복, 과도한 복잡도
- 에러 핸들링/로깅 부재
- lint 경고(이 레포 기준 --max-warnings=0)

## 심각도

| severity | 의미 | 게이트 |
|---|---|---|
| **blocker** | 머지 시 프로덕션 사고/데이터 손실/보안 침해 | 머지 차단 권고 |
| **major** | 명백한 버그/위험, 머지 전 수정 권고 | 포스팅 기본 임계(post_min_severity) |
| **minor** | 개선 권장, 차단 안 함 | 리포트만 |
| **nit** | 취향/스타일 | 리포트만 |

## 출력 계약 (review.sh 가 파싱)

headless claude 는 정확히 아래 JSON 을 ```json 블록으로 출력:

```json
{
  "verdict": "approve | comment | request_changes",
  "summary": "1-2문장 총평",
  "findings": [
    {"axis":"correctness","severity":"major","file":"src/x.ts","line":42,
     "title":"짧은 제목","detail":"근거","suggestion":"제안 수정"}
  ]
}
```

발견 없으면 findings: [] + verdict: approve. 추정/불확실은 severity 를 낮추고 detail 에 "불확실" 명시.
