// 제네릭 swipe-harvester — full URL 리스트의 각 페이지 상단(히어로)을 캡처.
// 정적 라우팅(brenden /project/<slug>, ordinary /work/<slug> 등)용.
// usage: PW_BASE=<nm> node swipe-harvest-urls.mjs <urlsFile> <outDir>
import { createRequire } from 'node:module';
import { readFileSync, mkdirSync, appendFileSync, existsSync } from 'node:fs';
const require = createRequire(process.env.PW_BASE + '/__a__.js');
const { chromium } = require('playwright');
const [,, urlsFile, outDir] = process.argv;
mkdirSync(outDir, { recursive:true });
const urls = readFileSync(urlsFile,'utf8').split('\n').map(s=>s.trim()).filter(Boolean);
const cat = outDir+'/catalog.tsv';
if(!existsSync(cat)) appendFileSync(cat,'slug\tfile\turl\n');
const b = await chromium.launch();
let ok=0,fail=0;
for(const url of urls){
  const slug = url.replace(/\/$/,'').split('/').pop().replace(/[^a-zA-Z0-9_-]/g,'_').slice(0,50);
  const out = `${outDir}/${slug}.png`;
  if(existsSync(out)){ok++;continue;}
  const ctx = await b.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1});
  const p = await ctx.newPage();
  try{
    // 'load' + 고정대기 — JS-heavy 스튜디오 SPA 는 networkidle 가 안 가라앉아 timeout 나므로
    // 'load'(DOM+리소스) 후 고정대기 + 스크롤로 lazy 로드 트리거. (PW_WAIT env 로 대기 조정)
    const wait = parseInt(process.env.PW_WAIT || '3500', 10);
    await p.goto(url,{waitUntil:'load',timeout:Number(process.env.PW_TIMEOUT||'70000')});
    await p.waitForTimeout(wait);
    await p.evaluate(async()=>{for(let y=0;y<3000;y+=600){window.scrollTo(0,y);await new Promise(r=>setTimeout(r,160));}window.scrollTo(0,0);});
    await p.waitForTimeout(800);
    await p.screenshot({path:out,clip:{x:0,y:0,width:1440,height:1600}});
    appendFileSync(cat,`${slug}\t${slug}.png\t${url}\n`); ok++;
    console.log(`[${ok+fail}/${urls.length}] ${slug}`);
  }catch(e){fail++;appendFileSync(cat,`${slug}\t\tERR:${e.message}\n`);console.error(`[${ok+fail}/${urls.length}] ${slug} FAIL`);}
  finally{await ctx.close();}
}
await b.close();
console.log(`DONE ok=${ok} fail=${fail}`);
