// Taste swipe-harvester (plus-ex 전용) — /experience SPA 의 각 프로젝트 히어로 프레임을
// 캡처해 references/swipe/plusex/<slug>.png 로 저장 + catalog.tsv 누적.
// plus-ex 는 해시 라우팅(#slug) SPA → 프로젝트별로 reload + 썸네일 클릭 후 상단 클립 캡처.
//
// usage: PW_BASE=<node_modules> node swipe-harvest-plusex.mjs <slugsFile> <outDir>
import { createRequire } from 'node:module';
import { readFileSync, mkdirSync, appendFileSync, existsSync } from 'node:fs';
const require = createRequire(process.env.PW_BASE + '/__a__.js');
const { chromium } = require('playwright');

const [, , slugsFile, outDir] = process.argv;
mkdirSync(outDir, { recursive: true });
const slugs = readFileSync(slugsFile, 'utf8').split('\n').map(s => s.trim()).filter(Boolean);
const catalog = outDir + '/catalog.tsv';
if (!existsSync(catalog)) appendFileSync(catalog, 'slug\tfile\tok\turl\n');

const browser = await chromium.launch();
let ok = 0, fail = 0;
for (const slug of slugs) {
  const out = `${outDir}/${slug}.png`;
  if (existsSync(out)) { ok++; continue; } // resume-safe
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const p = await ctx.newPage();
  try {
    await p.goto('https://www.plus-ex.com/experience', { waitUntil: 'networkidle', timeout: 60000 });
    await p.waitForTimeout(3000);
    const clicked = await p.evaluate((s) => {
      const a = document.querySelector(`a[href*="#${s}"]`);
      if (a) { a.click(); return true; } return false;
    }, slug);
    await p.waitForTimeout(3500);
    await p.evaluate(async () => { for (let y = 0; y < 3000; y += 700) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 140)); } window.scrollTo(0, 0); });
    await p.waitForTimeout(600);
    await p.screenshot({ path: out, clip: { x: 0, y: 0, width: 1440, height: 1700 } });
    appendFileSync(catalog, `${slug}\t${slug}.png\t${clicked ? 1 : 0}\t${p.url()}\n`);
    ok++;
    console.log(`[${ok + fail}/${slugs.length}] ${slug} ok`);
  } catch (e) {
    fail++;
    appendFileSync(catalog, `${slug}\t\t0\tERR:${e.message}\n`);
    console.error(`[${ok + fail}/${slugs.length}] ${slug} FAIL ${e.message}`);
  } finally {
    await ctx.close();
  }
}
await browser.close();
console.log(`DONE ok=${ok} fail=${fail} → ${outDir}`);
