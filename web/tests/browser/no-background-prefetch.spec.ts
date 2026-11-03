import {test,expect} from '@playwright/test';

for(const [name,viewport] of [['desktop',{width:1440,height:900}],['mobile',{width:390,height:844}]] as const) {
  test(`${name}: private research pages render only after navigation, not viewport or hover prefetch`,async({page})=>{
    await page.setViewportSize(viewport);
    const rsc:string[]=[];
    page.on('request',request=>{
      const url=new URL(request.url());
      if(url.searchParams.has('_rsc'))rsc.push(url.pathname);
    });
    await page.goto('/dashboard');
    await expect(page.getByRole('heading',{name:'Research Terminal Dashboard',exact:true})).toBeVisible();
    if(name==='mobile')await page.getByRole('button',{name:'Open navigation menu',exact:true}).click();
    const link=page.getByRole('link',{name:'Structure Lab',exact:true});
    await expect(link).toBeVisible();
    await link.hover();
    // Give viewport/idle/hover prefetch a bounded opportunity after hydration.
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    expect(rsc,'No protected destination should be rendered speculatively').toEqual([]);
    await link.click();
    await expect(page).toHaveURL(/\/structures$/);
    await expect(page.getByRole('heading',{name:'Structure Lab',exact:true})).toBeVisible();
  });
}
