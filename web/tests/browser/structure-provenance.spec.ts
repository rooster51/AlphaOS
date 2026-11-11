import {readFileSync} from 'node:fs';
import {expect,test,type Page} from '@playwright/test';

const fixture=JSON.parse(readFileSync('tests/fixtures/structure-provenance-parity.json','utf8'));
const bridge=(research:unknown)=>({json:{research,verified_for_trading:false,source:'alphaos_research_structure_api'}});

async function fill(page:Page, request:typeof fixture.single.SPY.request) {
  await page.locator('#structure-symbol').selectOption(request.symbol);
  await page.locator('#structure-expiration').fill(request.expiration);
  await page.locator('#structure-as-of').fill(request.as_of);
  await page.locator('#structure-spot').fill(String(request.spot));
  await page.locator('#structure-side').selectOption(request.credit>0?'credit':'debit');
  await page.locator('#structure-price').fill(String(Math.abs(request.credit)));
  await page.locator('#structure-fees').fill(String(request.fees));
  const mode=page.getByRole('checkbox',{name:'Validate against a verified archive snapshot'});
  await mode.setChecked(Boolean(request.market_data));
  if(request.market_data) {
    await page.locator('#structure-snapshot-id').fill(request.market_data.snapshot_id);
    await page.locator('#structure-snapshot-hash').fill(request.market_data.archive_sha256);
  }
  while(await page.locator('[id^="leg-type-"]').count()<request.legs.length)
    await page.getByRole('button',{name:'Add leg',exact:true}).click();
  while(await page.locator('[id^="leg-type-"]').count()>request.legs.length)
    await page.getByRole('button',{name:'Remove leg',exact:true}).last().click();
  for(let i=0;i<request.legs.length;i++) {
    const leg=request.legs[i];
    await page.locator(`#leg-type-${i}`).selectOption(leg.type);
    await page.locator(`#leg-action-${i}`).selectOption(leg.qty>0?'Buy':'Sell');
    await page.locator(`#leg-strike-${i}`).fill(String(leg.strike));
    await page.locator(`#leg-quantity-${i}`).fill(String(Math.abs(leg.qty)));
    if(request.market_data) await page.locator(`#leg-contract-${i}`).fill(leg.contract);
  }
}

test('archive-backed SPY/QQQ research and mixed comparison display quote provenance',async({page})=>{
  const singles:unknown[]=[];
  await page.route('**/api/research/structure',async route=>{
    const request=route.request().postDataJSON();singles.push(request);
    expect(request).toEqual(fixture.single[request.symbol].request);
    await route.fulfill(bridge(fixture.single[request.symbol]));
  });
  await page.route('**/api/research/structures/compare',async route=>{
    expect(route.request().postDataJSON()).toEqual(fixture.comparison.request);
    await route.fulfill(bridge(fixture.comparison));
  });
  await page.goto('/structures');await page.waitForLoadState('networkidle');
  for(const symbol of ['SPY','QQQ']) {
    // The comparison fixture uses a QQQ outright, the single fixture a spread.
    await fill(page,fixture.single[symbol].request);
    await page.getByRole('button',{name:'Research this structure',exact:true}).click();
    await expect(page.getByText(/Verified archive observations; not executable fills/)).toBeVisible();
    await expect(page.getByText(new RegExp(fixture.single[symbol].request.legs[0].contract))).toBeVisible();
    await expect(page.getByText(/oldest quote age 180.0s/).first()).toBeVisible();
  }
  for(const request of fixture.comparison.request.structures) {
    await fill(page,request);
    await page.getByRole('button',{name:'Save for comparison',exact:true}).click();
  }
  await page.locator('#structure-thesis').fill(fixture.comparison.request.thesis ?? '');
  await page.getByRole('button',{name:'Compare saved structures (3)',exact:true}).click();
  await expect(page.getByText('Candidate 1 quote provenance')).toBeVisible();
  await expect(page.getByText('Candidate 2 quote provenance')).toBeVisible();
  await expect(page.getByText('Hypothetical scenario — no verified market quote provenance.')).toBeVisible();
  expect(singles).toHaveLength(2);
});

test('snapshot rollover stays an explicit error',async({page})=>{
  await page.route('**/api/research/structure',route=>route.fulfill({status:502,json:{status:'unavailable',code:'archive_snapshot_mismatch'}}));
  await page.goto('/structures');await page.waitForLoadState('networkidle');
  await fill(page,fixture.single.SPY.request);
  await page.getByRole('button',{name:'Research this structure',exact:true}).click();
  await expect(page.getByText(/archive snapshot changed or its checksum does not match/)).toBeVisible();
  await expect(page.getByText(/Verified archive observations; not executable fills/)).toHaveCount(0);
});
