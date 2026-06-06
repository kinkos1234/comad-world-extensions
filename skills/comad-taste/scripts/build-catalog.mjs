// swipe 코퍼스 → swipe-catalog.json (coarse 인덱스, 무비용).
// references/swipe/<studio>/*.png + catalog.tsv(slug→url) 를 합쳐 검색 가능한 JSON 생성.
// 세밀 태그(스타일/도메인)는 사전 부여 X — 에이전트가 런타임에 컨택트시트로 판단(swipe-search).
// usage: node build-catalog.mjs [swipeDir] [outJson]
import { readdirSync, readFileSync, writeFileSync, existsSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL = dirname(dirname(fileURLToPath(import.meta.url)));
const SW = process.argv[2] || join(SKILL, 'references/swipe');
const OUT = process.argv[3] || join(SW, 'swipe-catalog.json');

// 스튜디오별 메타 — 모두 아키타입 F(Studio Brand-Editorial)의 하위 결. 검색 필터용 desc.
const STUDIO = {
  plusex:   { site: 'plus-ex.com',          flavor: 'BX/UX 브랜드 케이스스터디 — 풀블리드 아이덴티티 리빌·실물 적용샷(폰목업·패키지·사이니지). 대기업 브랜드.' },
  ordinary: { site: 'ordinarypeople.info',  flavor: '문화/그래픽/에디토리얼 — 전시·출판·포스터·아이덴티티. 실험적 타이포·그리드.' },
  brenden:  { site: 'brenden.kr',           flavor: '브랜딩/모션 — 로고·아이덴티티 시스템·모션 그래픽. 미니멀·기하.' },
  ynl:      { site: 'ynldesign.com',        flavor: '브랜드/그래픽 디자인 스튜디오 — 아이덴티티·편집.' },
  cfc:      { site: 'contentformcontext.com',flavor: '그래픽/브랜드 — 전시(서울일러스트레이션페어 등)·공간·아이덴티티.' },
  saworl:   { site: 'saworl.com',           flavor: '공간/환경 그래픽·아트펜스·사이니지 프로젝트.' },
};

const entries = [];
const byStudio = {};
for (const studio of readdirSync(SW)) {
  const dir = join(SW, studio);
  if (!existsSync(dir) || !statSync(dir).isDirectory()) continue;
  // slug→url from catalog.tsv
  const urls = {};
  const tsv = join(dir, 'catalog.tsv');
  if (existsSync(tsv)) {
    for (const line of readFileSync(tsv, 'utf8').split('\n').slice(1)) {
      const [slug, , , url] = line.split('\t'); // plusex: slug file ok url ; urls: slug file url
      const parts = line.split('\t');
      const u = parts[parts.length - 1];
      if (slug && u && u.startsWith('http')) urls[slug] = u;
    }
  }
  const pngs = readdirSync(dir).filter(f => f.endsWith('.png'));
  byStudio[studio] = pngs.length;
  for (const f of pngs) {
    const slug = f.replace(/\.png$/, '');
    entries.push({
      studio,
      slug,
      file: `references/swipe/${studio}/${f}`,
      url: urls[slug] || `https://${STUDIO[studio]?.site || studio}`,
      flavor: STUDIO[studio]?.flavor || '',
    });
  }
}

const catalog = {
  generated_note: 'coarse 인덱스 — 세밀 태그 없음. swipe-search 로 후보→컨택트시트 생성 후 에이전트가 vision 판단.',
  archetype: 'F (Studio Brand-Editorial) — 전 항목',
  total: entries.length,
  byStudio,
  studios: STUDIO,
  entries,
};
writeFileSync(OUT, JSON.stringify(catalog, null, 1));
console.log(`swipe-catalog: ${entries.length} entries (${Object.entries(byStudio).map(([k, v]) => `${k}:${v}`).join(' ')}) → ${OUT}`);
