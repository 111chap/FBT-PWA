const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const base=process.argv[2];
const selectors=['[data-nav=overview]','[data-nav=bills]','.mobile-add','[data-nav=loans]','[data-nav=history]','#logout'];
const box=el=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};};
function luminance(rgb){const c=rgb.match(/[\d.]+/g).slice(0,3).map(v=>{v=Number(v)/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});return c[0]*.2126+c[1]*.7152+c[2]*.0722;}
async function readable(locator){
  const colors=await locator.evaluate(el=>{let p=el,bg;do{bg=getComputedStyle(p).backgroundColor;p=p.parentElement;}while(bg==='rgba(0, 0, 0, 0)'&&p);return [getComputedStyle(el).color,bg];});
  const [a,b]=colors.map(luminance);assert.ok((Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5,JSON.stringify(colors));
}
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.FBT_BROWSER_EXECUTABLE?{executablePath:process.env.FBT_BROWSER_EXECUTABLE}:{})});
  const context=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'}),page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  fs.mkdirSync('tmp/browser-qa',{recursive:true});
  try{
    await page.goto(base+'/login/');
    await page.locator('[name=username]').fill('qa-admin');await page.locator('[name=password]').fill('Fictional-QA-passphrase-123!');await page.locator('form button').click();
    await page.locator('#overview').waitFor();
    await page.waitForFunction(()=>document.getElementById('connection-badge').textContent.includes('Home server connected'));
    for(const theme of ['light','dark']){
      if(await page.evaluate(()=>document.documentElement.dataset.theme)!==theme)await page.locator('#theme-toggle').click();
      for(const width of [320,390,430,768]){
        await page.setViewportSize({width,height:844});await page.evaluate(()=>document.fonts.ready);
        const baseline=await page.locator('.sidebar>nav a svg').evaluateAll(elements=>elements.map(el=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};}));
        for(const screen of ['overview','bills','loans','history']){
          await page.locator(`[data-nav=${screen}]`).click();await page.locator('#'+screen).waitFor();
          const icons=await page.locator('.sidebar>nav a svg').evaluateAll(elements=>elements.map(el=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};}));
          icons.forEach((r,index)=>Object.keys(r).forEach(key=>assert.ok(Math.abs(r[key]-baseline[index][key])<.5,`${theme}/${width}/${screen}: icon ${index} moved (${key})`)));
          const active=page.locator('.sidebar>nav a.active');
          const bounds=await active.evaluate(box);
          for(const child of ['svg','.mobile-label']){
            const r=await active.locator(child).evaluate(box);
            assert.ok(r.x>=bounds.x&&r.y>=bounds.y&&r.x+r.width<=bounds.x+bounds.width+.5&&r.y+r.height<=bounds.y+bounds.height+.5,`${child} escapes selected target`);
          }
          const icon=await active.locator('svg').evaluate(box);
          assert.ok(Math.abs(icon.x+icon.width/2-bounds.x-bounds.width/2)<1,'Selected icon stays centered');
          assert.notEqual(await active.evaluate(el=>getComputedStyle(el).backgroundColor),'rgba(0, 0, 0, 0)');
          await readable(active.locator('.mobile-label'));
          const controls=[];
          for(const selector of selectors){const r=await page.locator(selector).evaluate(box);assert.ok(r.width>=44&&r.height>=44,`${selector} touch target too small at ${width}`);controls.push(r);}
          for(let index=1;index<controls.length;index++)assert.ok(controls[index].x>=controls[index-1].x+controls[index-1].width-.5,'Navigation controls overlap');
          assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Page has horizontal overflow');
        }
        const sizes=await page.evaluate(()=>({family:parseFloat(getComputedStyle(document.getElementById('family-name')).fontSize),date:parseFloat(getComputedStyle(document.getElementById('today-label')).fontSize)}));
        assert.ok(sizes.family>=16&&sizes.date>=14,JSON.stringify(sizes));
        for(const selector of ['#family-name','#today-label','#logout','[data-nav=bills] .mobile-label','.mobile-add'])await readable(page.locator(selector));
        const title=await page.locator('.topbar>div:first-child').evaluate(box),controls=await page.locator('.topbar-right').evaluate(box);
        assert.ok(title.y+title.height<=controls.y+.5,'Header text overlaps controls');
        await page.locator('[data-nav=overview]').click();
        if([320,390].includes(width))await page.screenshot({path:`tmp/browser-qa/mobile-navigation-${theme}-${width}.png`});
      }
      await page.setViewportSize({width:320,height:844});
      await page.route('**/static/qa-large-text.css',route=>route.fulfill({contentType:'text/css',body:'#family-name{font-size:22px!important}#today-label{font-size:18px!important}.sidebar>nav a .mobile-label{font-size:13px!important}'}));
      const enlargement=await page.addStyleTag({url:base+'/static/qa-large-text.css'});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Larger text causes overflow');
      await page.keyboard.press('Tab');await page.locator('[data-nav=bills]').focus();assert.equal(await page.locator('[data-nav=bills]').evaluate(el=>getComputedStyle(el).outlineStyle),'solid');
      await page.locator('.mobile-add').click();await page.locator('#bill-type-dialog').waitFor();await page.locator('#bill-type-dialog .close-dialog').click();
      await page.locator('#logout').click();await page.locator('.signout-dialog').waitFor();await page.locator('.signout-dialog .secondary').click();
      await page.locator('#workspace-toggle').click();await page.locator('#workspace-menu').waitFor();await page.keyboard.press('Escape');
      // Remove the enlarged-text fixture before checking the next theme.
      await enlargement.evaluate(el=>el.remove());
      await page.unroute('**/static/qa-large-text.css');
    }
    assert.deepEqual(errors,[]);
    console.log('Mobile navigation stays fixed across selection, encloses its icon/label, and supports readable headers, both themes and enlarged text.');
  }finally{await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
