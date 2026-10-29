import { chromium } from '@playwright/test';
import fs from 'node:fs';
import assert from 'node:assert/strict';
// Explicit live audit; never included in the fixture-based automated test suite.
const audit=JSON.parse(fs.readFileSync(process.argv[2] ?? '../diagnostics/spy-qqq-validation.json','utf8'));
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const base='https://codex-cloudflare-workers-alphaos-web.rfroux95.workers.dev';
const result={errors:[],market:[],structures:[],navigation:[]};
page.on('pageerror',e=>result.errors.push(e.message));
for(const symbol of ['SPY','QQQ']){
 const pending=page.waitForResponse(r=>r.url().endsWith('/api/research/market')&&r.request().method()==='POST');
 await page.goto(`${base}/market?symbol=${symbol}`);const r=await pending;const b=await r.json();
 result.market.push({symbol,status:r.status(),source:b.source,code:b.code,request_id:r.headers()['x-alphaos-request-id'],hasMain:await page.getByRole('main').isVisible()});
}
await page.goto(`${base}/structures`);await page.waitForLoadState('networkidle');
for(const [symbol,horizon,family] of [['SPY','weekly','call_debit_spread'],['QQQ','long_dated','long_call']]){
 const c=audit.symbols[symbol].horizons[horizon].cases[family].request;
 await page.locator('#structure-symbol').selectOption(c.symbol);
 for(const [id,value] of [['expiration',c.expiration],['as-of',c.as_of],['spot',c.spot],['price',Math.abs(c.credit).toFixed(8)],['fees',c.fees]]) await page.locator(`#structure-${id}`).fill(String(value));
 await page.locator('#structure-side').selectOption(c.credit>0?'credit':'debit');
 const existing=await page.locator('[id^="leg-type-"]').count();
 for(let n=existing;n<c.legs.length;n++)await page.getByRole('button',{name:'Add leg',exact:true}).click();
 // The single-option case follows a two-leg case; remove the last displayed leg.
 while(await page.locator('[id^="leg-type-"]').count()>c.legs.length) await page.getByRole('button',{name:/Remove leg/}).last().click();
 for(let n=0;n<c.legs.length;n++){let leg=c.legs[n];await page.locator(`#leg-type-${n}`).selectOption(leg.type);await page.locator(`#leg-action-${n}`).selectOption(leg.qty>0?'Buy':'Sell');await page.locator(`#leg-strike-${n}`).fill(String(leg.strike));await page.locator(`#leg-quantity-${n}`).fill(String(Math.abs(leg.qty)));}
 const p=page.waitForResponse(r=>r.url().endsWith('/api/research/structure'));
 await page.getByRole('button',{name:'Research this structure',exact:true}).click();const r=await p;const b=await r.json();
 result.structures.push({symbol,horizon,status:r.status(),source:b.source,family:b.research?.research?.strategy_family,integrityWarning:await page.getByText(/integrity/i).count(),code:b.code});
 await page.getByRole('button',{name:'Save for comparison',exact:true}).click();
}
const compare=page.waitForResponse(r=>r.url().endsWith('/api/research/structures/compare'));
await page.getByRole('button',{name:'Compare saved structures (2)',exact:true}).click();const cr=await compare;result.compare={status:cr.status(),source:(await cr.json()).source};
for(const [label,path] of [['Market Research','/market'],['Strategy Explorer','/strategies'],['Structure Lab','/structures'],['Session Review','/session'],['Trade Journal','/journal'],['Portfolio Risk','/risk'],['Settings','/settings'],['Dashboard','/dashboard']]){
 await page.getByRole('navigation',{name:'Primary navigation'}).getByRole('link',{name:label}).click();await page.waitForURL(`**${path}`);result.navigation.push(path);
}
await page.setViewportSize({width:390,height:844});await page.goto(`${base}/dashboard`);await page.waitForLoadState('networkidle');
await page.locator('button[aria-controls="mobile-primary-navigation"]').click();
await page.getByRole('navigation',{name:'Primary navigation'}).getByRole('link',{name:'Structure Lab',exact:true}).click();await page.waitForURL('**/structures');
result.mobile={path:new URL(page.url()).pathname,closed:await page.locator('button[aria-controls="mobile-primary-navigation"]').getAttribute('aria-expanded')==='false'};
fs.writeFileSync('../diagnostics/live-browser.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));await browser.close();
assert.deepEqual(result.errors, [], 'Live browser page errors');
assert.ok(result.market.every(r=>r.status===200 && r.source==='alphaos_research_api'), 'Market requests must reach real research');
assert.ok(result.structures.every(r=>r.status===200 && r.source==='alphaos_research_structure_api' && r.integrityWarning===0), 'Structure responses must pass integrity checks');
assert.equal(result.compare.status,200);
assert.equal(result.mobile.closed,true);
