// Taste Layer 렌더 하네스 — HTML 파일을 headless Chromium 으로 렌더해 PNG 스크린샷.
// 자기비평(CRITIQUE) 루프가 생성 결과를 "실제로 보게" 하는 핵심 도구.
//
// playwright 해소: ESM bare import 는 이 파일 위치 기준이라 외부 node_modules 를 못 찾는다.
// → render.sh 가 PW_BASE(=playwright 가진 node_modules 의 부모 dir)를 env 로 넘기고,
//   createRequire 로 그 위치에서 require('playwright') 한다. (심볼릭 불필요.)
//
// usage: PW_BASE=<dir> node render.mjs <htmlPath> <outPng> [width=1440] [height=900] [fullPage=0]
import { createRequire } from 'node:module';

const base = process.env.PW_BASE;
if (!base) { console.error('PW_BASE env 미설정 — render.sh 로 실행하세요.'); process.exit(2); }
const require = createRequire(base + '/__anchor__.js');
const { chromium } = require('playwright');

const [, , htmlPath, outPath, w = '1440', h = '900', fullPage = '0'] = process.argv;
if (!htmlPath || !outPath) {
  console.error('usage: PW_BASE=<dir> node render.mjs <htmlPath> <outPng> [w] [h] [fullPage]');
  process.exit(2);
}

const browser = await chromium.launch();
try {
  const page = await browser.newPage({
    viewport: { width: parseInt(w, 10), height: parseInt(h, 10) },
    deviceScaleFactor: 2, // retina — 디테일(hairline·미세그림자) 검수 위해 2x
  });
  const url = htmlPath.startsWith('http') ? htmlPath : 'file://' + htmlPath;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(450); // 폰트·전환 안정화
  await page.screenshot({ path: outPath, fullPage: fullPage === '1' });
  console.log('rendered', outPath, `(${w}x${h}${fullPage === '1' ? ' fullPage' : ''} @2x)`);
} finally {
  await browser.close();
}
