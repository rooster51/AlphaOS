import {expect,test} from '@playwright/test';
import {password} from '../auth-fixture.mjs';

test.describe('Worker password login',()=>{
  test.skip(process.env.ALPHAOS_TEST_WORKERS!=='true','Authentication is scoped to Cloudflare, not the existing Render website');
  test.use({storageState:{cookies:[],origins:[]},extraHTTPHeaders:{}});
  test('anonymous APIs cannot retrieve research; login persists across contexts and logout removes access',async({page,browser})=>{
    for(const path of ['/api/research/market','/api/research/structure','/api/research/structures/compare','/api/market','/api/strategies']) {
      const r=await page.request.post(path,{data:{symbol:'SPY'}});expect(r.status()).toBe(401);
      expect(await r.text()).not.toContain('archive_sha256');
    }
    await page.goto('/market');await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByLabel('Password')).toHaveAttribute('type','password');
    await page.getByLabel('Password').fill('incorrect');await page.getByRole('button',{name:'Sign In'}).click();
    await expect(page.getByRole('alert')).toHaveText('Incorrect password.');
    await page.getByLabel('Password').fill(password);await page.getByRole('button',{name:'Sign In'}).click();
    await expect(page).toHaveURL(/\/market$/);
    const state=await page.context().storageState();const session=state.cookies.find(c=>c.name==='__Host-alphaos_session')!;
    expect(session.secure).toBe(true);expect(session.httpOnly).toBe(true);expect(session.sameSite).toBe('Strict');
    expect(session.expires).toBeGreaterThan(Date.now()/1000+29*86400);
    expect(await page.evaluate(()=>document.cookie)).not.toContain('__Host-alphaos_session');
    const restarted=await browser.newContext({storageState:state,baseURL:'http://127.0.0.1:3000'});
    const tab=await restarted.newPage();await tab.goto('/structures');await expect(tab).toHaveURL(/\/structures$/);
    await tab.getByRole('button',{name:'Sign Out'}).click();await expect(tab).toHaveURL(/\/login$/);
    expect((await restarted.request.get('/api/health')).status()).toBe(401);await restarted.close();
  });
  test('mobile login fits viewport and forged cookies do not authorize pages',async({page})=>{
    await page.setViewportSize({width:375,height:812});
    await page.context().addCookies([{name:'__Host-alphaos_session',value:'forged',domain:'127.0.0.1',path:'/',secure:true,httpOnly:true,sameSite:'Strict'}]);
    await page.goto('/structures');await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByLabel('Password')).toBeVisible();await expect(page.getByRole('button',{name:'Sign In'})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    const robots=await page.request.get('/robots.txt');expect(await robots.text()).toContain('Disallow: /');
    expect(robots.headers()['x-robots-tag']).toBe('noindex, nofollow');
  });
});
