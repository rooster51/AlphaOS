import { expect,test } from '@playwright/test';
import { readFileSync } from 'node:fs';
const fixtures=JSON.parse(readFileSync('tests/fixtures/multi-strategy-live.json','utf8'));
for(const width of [390,1440]){
  test(`comparison uses selected contracts and invalidates changed constraints at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:900});
    const requests:Record<string,unknown>[]=[];
    const calls=fixtures[0].chain.calls;
    const puts=fixtures[1].chain.puts;
    await page.route('**/api/options?*',async route=>{
      if(route.request().method()==='GET')return route.fulfill({json:{source:'Public',retrieved_at:'2026-11-05T15:00:00Z',max_quote_age_seconds:30,
        chain:{calls:calls.map((row:any)=>({...row,status:'fresh'})),puts:puts.map((row:any)=>({...row,status:'fresh'}))}}});
      const payload=route.request().postDataJSON();requests.push(payload);
      return route.fulfill({json:{scenarios:payload.scenarios.map((selection:any)=>fixtures.find((item:any)=>item.request.strategy===selection.strategy).result)}});
    });
    await page.goto('/options');await page.waitForLoadState('networkidle');
    expect(requests).toHaveLength(0);
    await page.getByLabel('Expiration',{exact:true}).fill('2026-11-06');
    await page.getByRole('button',{name:'Refresh chain'}).click();
    const workbench=page.getByRole('region',{name:'Strategy Comparison Workbench'});
    await expect(workbench).toBeVisible();
    await page.getByLabel('Workbench Buy call',{exact:true}).selectOption(calls[0].contract);
    await page.getByRole('button',{name:'Add scenario to comparison'}).click();
    await page.getByLabel('Strategy',{exact:true}).selectOption('long_put');
    await page.getByLabel('Workbench Buy put',{exact:true}).selectOption(puts[0].contract);
    await page.getByRole('button',{name:'Add scenario to comparison'}).click();
    expect(requests).toHaveLength(0);
    await page.getByRole('button',{name:'Evaluate comparison'}).click();
    const table=page.getByRole('table',{name:'Strategy comparison',exact:true});
    await expect(table).toContainText('$300.65');await expect(table).toContainText('Unlimited');
    await expect(table.getByText('Eligible for analysis',{exact:true})).toHaveCount(2);
    expect(requests).toHaveLength(1);
    expect(requests[0].scenarios).toEqual(fixtures.slice(0,2).map((item:any)=>item.request));
    await page.getByLabel('Comparison sort',{exact:true}).selectOption('profit');
    expect(requests).toHaveLength(1);
    await page.getByText('Scenario 1 · evidence, assumptions and terminal payoff',{exact:true}).click();
    await expect(page.getByRole('table',{name:'Scenario 1 terminal payoff',exact:true})).toBeVisible();
    await page.getByLabel('max loss',{exact:true}).fill('100');
    await expect(table).toHaveCount(0);
    await page.getByLabel('Symbol',{exact:true}).selectOption('QQQ');
    await expect(workbench).toHaveCount(0);
    expect(requests).toHaveLength(1);
  });
}
