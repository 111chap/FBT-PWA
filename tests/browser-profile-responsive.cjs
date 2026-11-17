const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.argv[2];
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.FBT_BROWSER_EXECUTABLE?{executablePath:process.env.FBT_BROWSER_EXECUTABLE}:{})});
  try{
    for(const [user,role] of [['qa-admin','Family administrator'],['qa-member-with-a-long-display-name-for-layout-checks','Family member']]){
      const context=await browser.newContext(),page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.goto(base+'/login/');await page.locator('[name=username]').fill(user);await page.locator('[name=password]').fill('Fictional-QA-passphrase-123!');await page.locator('form button').click();await page.locator('#overview').waitFor();
      for(const viewport of [{width:320,height:568},{width:390,height:844},{width:768,height:1024},{width:1024,height:480},{width:1366,height:768}]){
        await page.setViewportSize(viewport);
        for(const screen of ['overview','bills','loans','history','system',...(user==='qa-admin'?['audit']:[]),'setup']){
          await page.goto(base+'/app/#'+screen);await page.locator('#'+screen).waitFor();
          await page.evaluate(async()=>{await document.fonts.ready;await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
          const overflow=await page.evaluate(()=>({page:document.documentElement.scrollWidth,width:innerWidth,elements:[...document.querySelectorAll('body *')].filter(el=>!el.closest('.table-scroll')).map(el=>({tag:el.tagName,id:el.id,classes:el.className,right:el.getBoundingClientRect().right,width:el.getBoundingClientRect().width})).filter(el=>el.right>innerWidth).slice(0,12)}));
          const horizontalPan=await page.evaluate(()=>{const x=scrollX;scrollTo({left:1000});const moved=scrollX;scrollTo({left:x});return moved;});
          assert.equal(horizontalPan,0,`${user} ${screen} allows page-wide horizontal panning at ${viewport.width}: ${JSON.stringify(overflow)}`);
          const clippedControls=await page.evaluate(()=>[...document.querySelectorAll('input,select,textarea,button')].filter(el=>!el.closest('.table-scroll,.audit-table,.mobile-bill-sort')).filter(el=>{const r=el.getBoundingClientRect();return r.width>0&&(r.left<0||r.right>innerWidth+1);}).map(el=>el.id||el.name||el.className));
          assert.deepEqual(clippedControls,[],`${screen} has clipped controls at ${viewport.width}`);
          for(const selector of ['#profile-toggle','#logout']){
            const r=await page.locator(selector).boundingBox();assert.ok(r&&r.x>=0&&r.y>=0&&r.x+r.width<=viewport.width+1&&r.y+r.height<=viewport.height+1,`${selector} clipped at ${viewport.width}x${viewport.height}: ${JSON.stringify(r)}`);
          }
        }
        await page.locator('#profile-toggle').focus();await page.keyboard.press('Enter');await page.locator('#profile-dialog').waitFor();
        assert.equal(await page.locator('#profile-name').innerText(),user);assert.equal(await page.locator('#profile-role').innerText(),role);
        assert.equal(await page.locator('#profile-admin').isVisible(),user==='qa-admin');assert.equal(await page.locator('#profile-dialog input').count(),0,'Profile is explicitly read-only');
        assert.ok(await page.locator('#profile-toggle').getAttribute('aria-label').then(label=>label.includes(user)));
        const dialog=await page.locator('#profile-dialog').boundingBox();assert.ok(dialog.x>=0&&dialog.x+dialog.width<=viewport.width&&dialog.height<=viewport.height);
        if([390,1366].includes(viewport.width)){fs.mkdirSync('tmp/browser-qa',{recursive:true});await page.screenshot({path:`tmp/browser-qa/profile-${user==='qa-admin'?'admin':'member'}-${viewport.width}.png`});}
        await page.keyboard.press('Escape');assert.equal(await page.locator('#profile-dialog').isVisible(),false);assert.equal(await page.evaluate(()=>document.activeElement.id),'profile-toggle');
      }
      await page.goto(base+'/app/#loans');assert.equal(await page.locator('#loan-rows tr').count(),25);await page.locator('#loan-next').click();assert.equal(await page.locator('#loan-rows tr').count(),10);assert.match(await page.locator('#loan-page').innerText(),/Page 2 of 2/);
      await page.locator('#loan-search').fill('Fictional loan 00');assert.equal(await page.locator('#loan-rows tr').count(),1);assert.match(await page.locator('#loan-page').innerText(),/Page 1 of 1/);
      await page.locator('#profile-toggle').click();await page.locator('#profile-signout').click();await page.locator('.signout-dialog').waitFor();assert.equal(await page.locator('#profile-dialog').isVisible(),false);await page.locator('.signout-dialog .secondary').click();
      await page.goto(base+'/app/#setup');await page.locator('#enable-offline').click();await page.waitForFunction(()=>localStorage.getItem('fbt-offline-enabled')==='yes');
      await context.setOffline(true);await page.reload();await page.locator('#setup').waitFor();await page.locator('#profile-toggle').click();assert.match(await page.locator('#profile-status').innerText(),/Offline, read-only/);assert.equal(await page.locator('#profile-name').innerText(),user);
      if(user==='qa-admin')assert.equal(await page.locator('#profile-admin').getAttribute('href'),null);
      await page.keyboard.press('Escape');await context.setOffline(false);await page.reload();await page.locator('#profile-toggle').click();assert.match(await page.locator('#profile-status').innerText(),/Current account/);
      assert.deepEqual(errors,[]);await context.close();
    }
    console.log('Profile roles, isolation, read-only scope, confirmation sign-out, offline recovery and responsive matrix passed.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
