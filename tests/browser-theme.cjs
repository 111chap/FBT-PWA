const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
function luminance(rgb) {
  const c=rgb.match(/[\d.]+/g).slice(0,3).map(v=>{v=Number(v)/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});
  return c[0]*.2126+c[1]*.7152+c[2]*.0722;
}
function contrast(a,b){const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
async function main(){
  const browser=await chromium.launch({headless:true,...(process.env.FBT_BROWSER_EXECUTABLE?{executablePath:process.env.FBT_BROWSER_EXECUTABLE}:{})});
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[],remote=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(new URL(r.url()).origin!==new URL(process.argv[2]).origin)remote.push(r.url());});
  fs.mkdirSync('tmp/browser-qa',{recursive:true});
  await page.emulateMedia({reducedMotion:'reduce'});
  async function readable(selector){
    const colors=await page.locator(selector).first().evaluate(el=>{
      const s=getComputedStyle(el);let p=el,bg;
      do{bg=getComputedStyle(p).backgroundColor;p=p.parentElement;}while(bg==='rgba(0, 0, 0, 0)'&&p);
      return [s.color,bg];
    });
    assert.ok(contrast(...colors)>=4.5,`${selector}: ${colors} contrast ${contrast(...colors)}`);
  }
  try{
    await page.goto(process.argv[2]+'/login/');
    await page.evaluate(()=>document.fonts.ready);
    assert.ok(await page.evaluate(()=>document.fonts.check('15px "DM Sans"')));
    for(const scheme of ['light','dark']){
      await page.emulateMedia({colorScheme:scheme});await readable('.primary');await readable('.muted');
      await page.screenshot({path:`tmp/browser-qa/toffee-${scheme}-login.png`,fullPage:true});
    }
    await page.emulateMedia({colorScheme:'light'});
    await page.locator('[name=username]').fill('qa-admin');await page.locator('[name=password]').fill('Fictional-QA-passphrase-123!');await page.locator('form button').click();await page.locator('#overview').waitFor();
    for(const scheme of ['light','dark']){
      await page.goto(process.argv[2]+'/app/#overview');await page.locator('#overview').waitFor();
      await page.emulateMedia({colorScheme:scheme});
      if(await page.evaluate(()=>document.documentElement.dataset.theme)!==scheme)await page.locator('#theme-toggle').click();
      assert.equal(await page.locator('body').evaluate(el=>getComputedStyle(el).backgroundColor),scheme==='light'?'rgb(250, 247, 244)':'rgb(26, 18, 13)');
      for(const screen of ['overview','bills','loans','history','system','audit','setup']){
        await page.goto(process.argv[2]+'/app/#'+screen);await page.locator('#'+screen).waitFor();await page.evaluate(()=>document.fonts.ready);
        await readable('.sidebar nav a.active');await readable('#logout');await readable('#'+screen+' h1');
        if(screen==='bills'){
          await readable('#bills .primary');await readable('#bill-rows .badge');await readable('#bills .sort-heading');
          await page.keyboard.press('Tab');await page.locator('#bills .sort-heading').first().focus();
          const focus=await page.locator('#bills .sort-heading').first().evaluate(el=>getComputedStyle(el).outlineStyle);assert.equal(focus,'solid');
          await page.locator('#bills .sort-heading').first().hover();await readable('#bills .sort-heading');
          await page.locator('#logout').click();await page.locator('.signout-dialog').waitFor();await readable('.signout-dialog .primary');await readable('.signout-dialog .secondary');
          await page.screenshot({path:`tmp/browser-qa/toffee-${scheme}-signout.png`});await page.locator('.signout-dialog .secondary').click();
        }
        await page.screenshot({path:`tmp/browser-qa/toffee-${scheme}-${screen}.png`});
      }
      for(const width of [390,768]){
        await page.setViewportSize({width,height:844});
        for(const screen of ['overview','bills','loans','history']){
          await page.goto(process.argv[2]+'/app/#'+screen);await page.locator('#'+screen).waitFor();
          assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${screen} overflow at ${width}`);
          await page.screenshot({path:`tmp/browser-qa/toffee-${scheme}-${width}-${screen}.png`,fullPage:screen!=='overview'});
        }
        assert.ok(await page.locator('#logout').isVisible(),'Sign out stays visible in the mobile sidebar');
        await page.locator('.mobile-add').click();await page.locator('#bill-type-dialog').waitFor();await page.locator('#bill-type-dialog .close-dialog').click();
        await page.locator('#workspace-toggle').click();await page.locator('#workspace-menu').waitFor();
        assert.ok(await page.locator('[data-nav=setup]').isVisible());
        await page.keyboard.press('Escape');assert.equal(await page.locator('#workspace-toggle').getAttribute('aria-expanded'),'false');
      }
      await page.setViewportSize({width:1440,height:1000});
      await page.goto(process.argv[2]+'/admin/');await page.evaluate(()=>document.fonts.ready);
      assert.equal(await page.locator('link[href*="admin-theme"],link[href*="fonts.css"],script[src*="/static/theme.js"]').count(),0,'Administration keeps its original styling');
      assert.doesNotMatch(await page.locator('body').evaluate(el=>getComputedStyle(el).fontFamily),/DM Sans/);
      await page.goto(process.argv[2]+'/setup-guide/');await page.evaluate(()=>document.fonts.ready);
      await readable('h1');await readable('button');await readable('.callout p');
      await page.screenshot({path:`tmp/browser-qa/toffee-${scheme}-guide.png`,fullPage:true});
    }
    await page.goto(process.argv[2]+'/app/#setup');
    await page.evaluate(async()=>{await navigator.serviceWorker.ready;});
    await page.waitForFunction(async()=>{const c=await caches.open('fbt-shell-v13');return !!(await c.match('/static/fonts/dm-sans.ttf'));});
    await page.locator('#enable-offline').click();
    await page.waitForFunction(()=>localStorage.getItem('fbt-offline-enabled')==='yes');
    await page.goto(process.argv[2]+'/app/#overview');await page.locator('#overview').waitFor();
    await context.setOffline(true);await page.reload();await page.locator('#overview').waitFor();await page.evaluate(()=>document.fonts.ready);
    assert.ok(await page.evaluate(()=>document.fonts.check('15px "DM Sans"')));
    assert.deepEqual(remote,[]);assert.deepEqual(errors,[]);
    assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'dark','Device theme choice survives an offline reload');
    console.log('Light/dark themes, text contrast, focus, mobile navigation, original admin styling, and offline self-hosted font passed.');
  }finally{await context.close();await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
