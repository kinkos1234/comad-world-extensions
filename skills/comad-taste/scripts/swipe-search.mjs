// swipe-search — 작업 미감/도메인 쿼리로 레퍼런스 후보를 추려 "컨택트시트 몽타주" 1장 생성.
// 에이전트가 몽타주를 Read 로 한눈에 스캔→관련작 선별→해당 풀이미지 주입. (런타임 vision 판단)
//
// usage: PW_BASE=<nm> node swipe-search.mjs [--studio S] [--q "keywords"] [--n 24] [--out montage.png] [--cols 4]
//   예) --q "dark fintech dashboard" --n 24   /  --studio plusex --n 30
// 출력: montage.png + STDOUT 에 매칭 리스트(타일 번호→studio/slug/url) — 에이전트가 타일↔출처 매핑.
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(process.env.PW_BASE + '/__a__.js');
const { chromium } = require('playwright');

const SKILL = dirname(dirname(fileURLToPath(import.meta.url)));
const SW = join(SKILL, 'references/swipe');
const cat = JSON.parse(readFileSync(join(SW, 'swipe-catalog.json'), 'utf8'));

const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i >= 0 ? process.argv[i + 1] : d; };
const studio = arg('studio', '');
const q = (arg('q', '') || '').toLowerCase().split(/\s+/).filter(Boolean);
const n = parseInt(arg('n', '24'), 10);
const cols = parseInt(arg('cols', '4'), 10);
const out = arg('out', '/tmp/swipe-montage.png');

// 필터: studio (있으면) + 키워드(slug/url/flavor 부분일치) 점수. 없으면 스튜디오 라운드로빈 샘플.
let pool = cat.entries.filter(e => !studio || e.studio === studio);
if (q.length) {
  pool = pool.map(e => {
    const hay = (e.slug + ' ' + e.url + ' ' + e.flavor + ' ' + e.studio).toLowerCase();
    return { e, score: q.reduce((s, w) => s + (hay.includes(w) ? 1 : 0), 0) };
  }).filter(x => x.score > 0).sort((a, b) => b.score - a.score).map(x => x.e);
}
// 키워드 매칭이 적으면(또는 없으면) 스튜디오 고르게 샘플로 채움
if (pool.length < n) {
  const seen = new Set(pool.map(e => e.file));
  const rest = cat.entries.filter(e => (!studio || e.studio === studio) && !seen.has(e.file));
  // 스튜디오 라운드로빈
  const byS = {}; rest.forEach(e => (byS[e.studio] ??= []).push(e));
  const ks = Object.keys(byS); let i = 0;
  while (pool.length < n && ks.some(k => byS[k].length)) {
    const k = ks[i++ % ks.length]; if (byS[k].length) pool.push(byS[k].shift());
  }
}
const picked = pool.slice(0, n);

// 컨택트시트 HTML
const tiles = picked.map((e, i) => `
  <div class="t"><div class="im" style="background-image:url('file://${join(SKILL, e.file)}')"></div>
  <div class="cap"><b>${i + 1}</b> ${e.studio}/${e.slug}</div></div>`).join('');
const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@500;600&display=swap');
*{margin:0;box-sizing:border-box}body{font-family:Inter,sans-serif;background:#0c0c0f;padding:18px}
.hd{color:#cfd2d6;font-size:13px;font-weight:600;margin-bottom:14px}
.hd span{color:#8b909a;font-weight:500}
.g{display:grid;grid-template-columns:repeat(${cols},1fr);gap:12px}
.t{border:1px solid rgba(255,255,255,.1);border-radius:8px;overflow:hidden;background:#15161a}
.im{width:100%;aspect-ratio:16/10;background-size:cover;background-position:top center}
.cap{font-size:10.5px;color:#9aa0aa;padding:5px 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cap b{color:#ff8a3a;margin-right:3px}
</style></head><body>
<div class="hd">comad-taste swipe — ${picked.length} refs ${studio ? `· studio=${studio}` : ''} ${q.length ? `· q="${q.join(' ')}"` : ''} <span>(타일 번호로 풀이미지 식별)</span></div>
<div class="g">${tiles}</div></body></html>`;
const tmpHtml = out.replace(/\.png$/, '.html');
writeFileSync(tmpHtml, html);

const rows = Math.ceil(picked.length / cols);
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: cols * 300 + 60, height: rows * 210 + 80 }, deviceScaleFactor: 1 });
await p.goto('file://' + tmpHtml, { waitUntil: 'networkidle', timeout: 30000 });
await p.waitForTimeout(500);
await p.screenshot({ path: out, fullPage: true });
await b.close();

console.log(`montage: ${out} (${picked.length} refs, ${cols}cols)`);
console.log('타일↔출처:');
picked.forEach((e, i) => console.log(`  ${i + 1}\t${e.studio}/${e.slug}\t${join(SKILL, e.file)}\t${e.url}`));
