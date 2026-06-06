# Design DNA Corpus — 탑티어 미감 구조화 스펙

> "Aesthetic: Minimalist" 같은 **텍스트 지시**는 모델을 *초심자의 미니멀*로 이끈다.
> 대신 아래의 **구조화된 DNA**(구체적 토큰·아키타입·시그니처 디테일)를 통째로 주입하라.
> 각 아키타입은 실재 탑티어 제품의 미감을 역설계한 것. 프로젝트 도메인/톤에 맞는 1개를 골라 **전부** 프롬프트/생성 컨텍스트에 박는다.

선택 가이드:
- B2B SaaS·개발도구·대시보드·핀테크 → **A. Dark Product**
- 콘텐츠·프리미엄 브랜드·포트폴리오·문서 → **B. Light Editorial**
- 소비자앱·커뮤니티·웰니스·교육 → **C. Warm Consumer**
- 캠페인·런칭·크리에이터·스테이트먼트 → **D. Bold Statement**
- 데이터 밀집·어드민·내부도구 → **E. Dense Utility**

공통 원칙(모든 아키타입 위에 적용):
- **절제가 고급의 핵심**: 색 1개 액센트, 폰트 1~2종, 효과는 최소. 화려함 = 아마추어.
- **위계는 크기·무게·색이 아니라 "여백과 정렬"로 먼저 만든다.**
- **진짜처럼 보이게**: 실제 제품 UI 목업·실데이터 느낌 숫자·실제 회사명. 플레이스홀더 티 금지.
- **디테일이 고급을 만든다**: hairline border, 미세 그림자, optical 정렬, 일관된 radius.

---

## A. Dark Product (Linear · Vercel · Stripe · Raycast)

**DNA**: 거의 검정 캔버스 위 단색 절제 액센트. hairline로 구조를 그리고, 빛(glow)은 한 점에서만. 제품 자체가 주인공.

**Color**
- canvas `#08090c`~`#0b0d11` (순검정 아님, 살짝 푸른 먹). panel `#0e1014`.
- text `#f4f5f7` / muted `#8b909a` / faint `#565b65`.
- border: `rgba(255,255,255,.06~.08)` hairline. **절대 회색 선(#333) 쓰지 말 것** — 알파 화이트.
- accent: **단 1색**, 채도 절제(예 indigo `#8b9bff`, emerald `#5fcf80`, 또는 브랜드색). 액센트는 면적 5% 미만.
- 위험광: `radial-gradient(820px 460px at 68% -14%, accent .12, transparent)` — 화면 한 곳에서만, 은은하게.

**Type**: Inter / Geist. display 48~60px **weight 600**(800 금지, 무거우면 싸 보임), `letter-spacing:-.03em`, line-height 1.05. body 17~18px weight 450, muted색. eyebrow 12.5px.

**Spacing**: 8px 베이스. 섹션 96~120px. hero 상단 여백 후하게.

**Surface**: radius 9~14px. 미세 inner highlight (`box-shadow:0 -1px 0 rgba(255,255,255,.05) inset`). 큰 그림자는 accent 색으로 깔되 -40px 이상 blur, 낮은 alpha.

**Signature**: 좌측 또는 중앙 정렬 hero + **실제 제품 대시보드 목업**(브라우저 chrome·사이드바·KPI·SVG area차트). eyebrow는 fill 아닌 hairline pill + 작은 dot. 버튼은 radius 8~9px(pill 금지), primary=흰 배경/검은 글씨, secondary=ghost+hairline.

**Background detail**: 아주 흐린 64px grid(`rgba(255,255,255,.05)`)에 상단→하단 fade 마스크.

**Anti**: 풀스크린 무지개 그라데이션 · 그라데이션 텍스트 · 이모지 · pill 버튼 · 두꺼운 헤드라인 · 채도 높은 차트.

**Sources**: linear.app · vercel.com · stripe.com · raycast.com · resend.com

---

## B. Light Editorial (Apple · Notion · Things · Arc 문서)

**DNA**: 따뜻한 화이트 위 잉크 블랙 타이포가 주인공. 넓은 여백, 큰 타입, 극도의 절제. 색은 거의 무채.

**Color**: canvas `#fbfbf9`(순백 아닌 웜 페이퍼) / `#ffffff` 카드. text `#1a1a18` / muted `#6b6b66`. border `rgba(0,0,0,.08)`. accent 거의 안 씀(쓰면 잉크블루/딥그린 1색).

**Type**: 세리프 디스플레이(Newsreader·Fraunces·Tiempos) + 산세 본문(Inter), **또는** 산세 단일(SF/Inter) 큰 사이즈. display 56~80px weight 500~600 tracking -.02em. body 18~19px line-height 1.7. **타입 스케일 대비를 크게**(거대 헤드라인 ↔ 작은 본문).

**Spacing**: 넉넉한 baseline(1.7), 섹션 120~160px. 좌우 여백 후함(max-width 680~760 본문).

**Signature**: 비대칭·좌측정렬 본문, 큰 첫 문장, 절제된 1색 이미지/일러스트. 버튼은 텍스트링크 또는 미니멀 underline. 라인 구분자 hairline.

**Anti**: 다크모드 강제 · 카드 그림자 남발 · 채도 · 이모지 · 꽉 찬 레이아웃.

**Sources**: apple.com · notion.so · linear.app/method · stripe.com/press · readwise.io

---

## C. Warm Consumer (Airbnb · Duolingo(절제) · Headspace · Cron)

**DNA**: 친근하지만 유치하지 않게. 부드러운 곡선·따뜻한 1~2색·풍부한 여백. "귀엽다"가 아니라 "편안하다".

**Color**: canvas 웜 오프화이트 `#fdf9f3`. text `#2b2724`. accent 2색까지(코랄 `#f06a4d` + 딥틸 `#1f8a7a` 류) 채도 중간. 파스텔 남발 금지.

**Type**: 둥근 기하 산세(Poppins·Gilroy·General Sans) 헤드라인 + 가독 산세 본문. weight 대비 적당. display 44~56px.

**Surface**: radius 16~20px(큼·일관). 그림자 부드럽고 색조 있게(`accent .12`). 일러스트/이모지 대신 **커스텀 스팟 그래픽**.

**Signature**: 부드러운 카드, 친근한 카피, 1개의 따뜻한 hero 이미지/그래픽. 버튼 radius 12px 솔리드 accent.

**Anti**: 네온 · 무지개 · 이모지 떡칠 · 코믹산스류 · 과한 바운스 애니메이션.

**Sources**: airbnb.com · headspace.com · cron.com(now Notion Calendar) · oua.be · arc.net

---

## D. Bold Statement (Gumroad · Figma 캠페인 · Vercel ship · 브루탈리즘 절제판)

**DNA**: 큰 타이포·강한 대비·과감한 색면. 단 "정돈된 과감함" — 그리드는 엄격, 색은 2~3개로 한정.

**Color**: 고대비 베이스(검+1형광 또는 흰+1원색). accent 채도 높되 **면적·개수 엄격 제한**. 예: `#000` + `#ff4d00`, 또는 `#fff` + `#1500ff`.

**Type**: 굵은 그로테스크(Neue Haas·Archivo·Space Grotesk) display 72~120px weight 700~800 tracking -.04em. **이때만 두꺼운 헤드라인 허용**(컨셉이 statement라).

**Layout**: 엄격한 컬럼 그리드, 큰 색면 블록, 의도적 비대칭. 큰 숫자/라벨.

**Signature**: 한 화면 한 메시지. 강한 좌측정렬. 보더는 굵게(2px) 또는 없음. 버튼 사각/약간 radius, 솔리드.

**Anti**: 과감함을 핑계로 한 난잡함 · 색 5개+ · 정렬 깨짐 · 그라데이션 텍스트.

**Sources**: gumroad.com · figma.com/campaign · framer.com · vercel.com/ship

---

## E. Dense Utility (Linear 보드 · Retool · Bloomberg절제 · Height)

**DNA**: 정보 밀도가 미덕. 작은 타입·타이트 행·명확한 정렬·기능적 색. 화려함 0, 가독·스캔성 100.

**Color**: 다크 또는 라이트 중립. accent는 **상태색으로만**(성공/경고/위험/정보). 나머지 무채. border 빈번하되 hairline.

**Type**: 13~14px 본문(작게), 숫자는 tabular-nums + 약간 작은 mono 느낌. weight 450~550. 헤드라인도 절제(18~20px).

**Layout**: 촘촘한 테이블·리스트·칸반. 일관된 row height(28~36px). 좌측 사이드바 내비. 키보드-퍼스트 느낌.

**Signature**: 밀도 높되 숨 쉬는 정렬, 미세 zebra/hover, 상태 dot·badge(hairline). 빈 공간 최소.

**Anti**: 큰 카드 · 큰 여백 낭비 · 장식 아이콘 · 채도 · 둥근 거대 버튼.

**Sources**: linear.app(보드) · retool.com · height.app · plane.so · 터미널/IDE UI

---

## F. Studio Brand-Editorial (Plus X · contentformcontext · brenden · YNL · ordinarypeople · saworl)

> **사용자가 가장 자주 참조하는 핵심 미감** (한국 톱 디자인 스튜디오 포트폴리오). 2026-06-06 plus-ex 142개 작업 하베스트로 추출. swipe 코퍼스: `references/swipe/plusex/<slug>.png`.

**DNA**: 풀블리드 브랜드 케이스스터디. **하나의 강렬한 키비주얼/아이덴티티를 드라마틱하게 "리빌"** 하고(검은 화면에 크롬 로고 부상 등), 거대 확신형 타입과 실제 적용샷(폰목업·패키지·사이니지)으로 밀어붙인다. 카드 나열이 아니라 **작품 자체가 화면을 압도**.

**Color**: 프로젝트별로 다르나 공통 규율 — 절제된 배경(딥블랙·플럼·오프화이트) + **브랜드 1색을 강렬하게**. 대담하되 색 수는 2~3개로 한정. 채도는 목적적(브랜드색)일 때만 높음.

**Type**: **거대 디스플레이**(48~140px). 아웃라인 타입 ↔ 솔리드 혼용(plus-ex `ALL/BX/UX` 거대 아웃라인). 한글+영문 혼용 자연스럽게. 카테고리/라벨은 대문자 트래킹. 확신 있게 크게.

**Layout**: ① 풀블리드 히어로(단일 포컬) → ② 스크롤 케이스스터디(로고→컬러→타입→적용 순). 인덱스는 **masonry 그리드 + 거대 카테고리 타입 + 카운터**("142 eXperience"). 비대칭·대담한 스케일 점프.

**Surface**: 풀블리드 이미지가 주인공이라 카드·보더 최소. 실물 목업(디바이스·패키지·환경)으로 신뢰감. 미세 모션(호버 확대·패럴랙스·로고 리빌).

**Signature**: 아이덴티티 리빌 모먼트 · 실물 적용샷(추상 금지) · 거대 아웃라인 카테고리 타입 · 작품 카운터 · masonry 인덱스 · 한·영 타입 믹스.

**Anti**: 평범한 3컬럼 카드 그리드 · 작은 소심한 타입 · 추상 일러스트만(실물 없이) · 약한 중앙정렬 히어로 · 색 5개+.

**적용 시 주의**: 이 미감은 **이미지(실물 적용샷)가 핵심**이라, 콘텐츠가 빈약하면 공허해진다. 실제 제품 목업·스크린샷·실데이터를 반드시 채운다. SaaS/제품엔 A(Dark Product)와 섞어 — 풀블리드 확신형 히어로(F) + 제품 대시보드 목업(A).

**Sources**: plus-ex.com/experience(142작) · contentformcontext.com · brenden.kr/project · ynldesign.com · ordinarypeople.info/work · saworl.com
**Swipe**: `references/swipe/plusex/` (하베스트 — 프로젝트별 키비주얼 프레임)

---

## 사용 패턴 (생성 컨텍스트 주입 예)

```
[TASTE: Dark Product]
canvas #08090c, panel #0e1014, text #f4f5f7, muted #8b909a, border rgba(255,255,255,.07),
accent #8b9bff(면적<5%), 위험광 1점만. Inter 600 -0.03em 56px display / 450 18px body.
8px 리듬, 섹션96px, radius 9~14, hairline+inner-highlight surface.
필수: 실제 제품 대시보드 목업(브라우저chrome+사이드바+KPI+SVG area차트).
금지: 풀그라데이션·그라데이션텍스트·이모지·pill버튼·800두께·채도높은차트.
```

신규 레퍼런스 발견 시 해당 아키타입에 토큰/소스 추가(append-only). 새 아키타입이 필요하면 위 6항목 포맷으로 추가.
