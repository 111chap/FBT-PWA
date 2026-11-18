const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const base=process.argv[2];
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.FBT_BROWSER_EXECUTABLE?{executablePath:process.env.FBT_BROWSER_EXECUTABLE}:{})});
  const context=await browser.newContext({viewport:{width:1366,height:900},colorScheme:'dark',reducedMotion:'reduce'}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const theme=()=>page.evaluate(()=>document.documentElement.dataset.theme);
  const equalButtons=async(selector)=>{
    const sizes=await page.locator(selector).evaluateAll(buttons=>buttons.map(b=>{const r=b.getBoundingClientRect(),s=getComputedStyle(b);return {height:r.height,width:r.width,font:s.fontSize,opacity:s.opacity};}));
    assert.ok(sizes.length>=2);assert.ok(sizes.every(s=>s.height>=44&&Math.abs(s.height-sizes[0].height)<1&&Math.abs(s.width-sizes[0].width)<1&&s.font===sizes[0].font),JSON.stringify(sizes));
  };
  try{
    await page.goto(base+'/login/');assert.equal(await theme(),'light','The login default matches the homepage even on a dark-mode device');
    assert.equal(await page.locator('body').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(250, 247, 244)');
    assert.equal(await page.locator('.auth-card .brand-mark').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(158, 98, 53)');
    await page.locator('#theme-toggle').click();assert.equal(await theme(),'dark');await page.goto(base+'/setup-guide/');assert.equal(await theme(),'dark');
    await page.locator('#theme-toggle').click();await page.goto(base+'/setup-guide/#settings');assert.equal(await theme(),'light');
    assert.equal(await page.locator('body').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(250, 247, 244)');assert.equal(await page.locator('#env-form').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(255, 255, 255)');await page.screenshot({path:'tmp/browser-qa/matching-setup-guide.png'});
    await page.goto(base+'/login/');assert.equal(await theme(),'light');
    fs.mkdirSync('tmp/browser-qa',{recursive:true});await page.screenshot({path:'tmp/browser-qa/matching-login.png'});
    await page.locator('[name=username]').fill('qa-admin');await page.locator('[name=password]').fill('Fictional-QA-passphrase-123!');await page.locator('form button').click();await page.locator('#overview').waitFor();assert.equal(await theme(),'light');
    await page.goto(base+'/app/#setup');
    const pushNote='Push service accepted the test for 1 registered device(s). Removed 1 expired registration(s).';
    await page.route('**/api/push/test/',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true,accepted:1,expired:1,failed:0,note:pushNote})}));
    await page.locator('#test-push').click();
    await page.waitForFunction(note=>document.getElementById('push-test-status').textContent===note,pushNote);
    assert.equal(await page.locator('#push-test-status').isVisible(),true);
    assert.equal(await page.locator('#test-push').isEnabled(),true);
    await page.unroute('**/api/push/test/');
    const pushError='A fictional push service rejected this test.';
    await page.route('**/api/push/test/',route=>route.fulfill({status:502,contentType:'application/json',body:JSON.stringify({error:pushError})}));
    await page.locator('#test-push').click();
    await page.waitForFunction(note=>document.getElementById('push-test-status').textContent===note,pushError);
    assert.equal(await page.locator('#push-test-status').isVisible(),true);
    assert.equal(await page.locator('#test-push').isEnabled(),true);
    await page.unroute('**/api/push/test/');
    for(const width of [1366,390,320]){
      await page.setViewportSize({width,height:900});await page.goto(base+'/app/#bills');await page.locator('#search').fill('Unpaid utility');await page.locator('#bill-rows .bill-detail').click();
      await equalButtons('#detail-actions button');assert.ok(await page.locator('.reassign-payer').isEnabled());assert.equal(await page.locator('#detail-action-status').isVisible(),false);
      await page.screenshot({path:'tmp/browser-qa/bill-actions-'+width+'.png'});
      await page.locator('.reassign-payer').click();await page.locator('#payer-dialog').waitFor();assert.equal(await page.locator('#payer-form [name=responsible]').inputValue(),String(await page.evaluate(async()=>{const s=await(await fetch('/api/snapshot/')).json();return s.user.id;})));
      await page.locator('#payer-dialog .close-dialog').click();assert.equal(await page.locator('#detail-dialog').isVisible(),false);
      await page.goto(base+'/app/#loans');await page.locator('#loan-rows .loan-view').first().click();await equalButtons('#detail-actions button');await page.locator('#detail-dialog .close-dialog').click();
      await page.goto(base+'/app/#history');await page.getByRole('button',{name:'Paid utility',exact:true}).click();await equalButtons('#detail-payments .financial-correction');await page.locator('#detail-dialog .close-dialog').click();
    }
    await page.goto(base+'/app/#setup');await page.locator('#enable-offline').click();await page.waitForFunction(()=>localStorage.getItem('fbt-offline-enabled')==='yes');
    await context.setOffline(true);await page.goto(base+'/app/#bills');await page.reload();await page.locator('#bills').waitFor();await page.locator('#search').fill('Unpaid utility');await page.locator('#bill-rows .bill-detail').click();
    await equalButtons('#detail-actions button');assert.equal(await page.locator('#detail-actions button:disabled').count(),3);assert.match(await page.locator('#detail-action-status').innerText(),/Connect to your home server/);
    assert.ok(await page.locator('#detail-actions button').evaluateAll(buttons=>buttons.every(b=>getComputedStyle(b).opacity==='1')));
    await page.screenshot({path:'tmp/browser-qa/bill-actions-offline.png'});assert.deepEqual(errors,[]);
    console.log('Login/guide/home theme persistence and matching bill, payer, loan, payment and offline action controls passed.');
  }finally{await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
