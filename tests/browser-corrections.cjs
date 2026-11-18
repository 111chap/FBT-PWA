const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const base=process.argv[2];
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.FBT_BROWSER_EXECUTABLE?{executablePath:process.env.FBT_BROWSER_EXECUTABLE}:{})});
  const context=await browser.newContext({viewport:{width:1280,height:900}}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const snapshot=()=>page.evaluate(async()=>{const r=await fetch('/api/snapshot/');return r.json();});
  const login=async(p,user)=>{await p.goto(base+'/login/');await p.locator('[name=username]').fill(user);await p.locator('[name=password]').fill('Fictional-QA-passphrase-123!');await p.locator('form button').click();await p.locator('#overview').waitFor();};
  const control=(kind,action)=>page.locator(`#detail-dialog .financial-correction[data-kind=${kind}][data-action=${action}]`).first();
  const reason=async(text='Browser correction for fictional QA')=>page.locator('#correction-form [name=reason]').fill(text);
  const review=async()=>{await page.locator('#correction-form [type=submit]').click();await page.locator('.review-dialog').waitFor();};
  const confirm=async()=>{const response=page.waitForResponse(r=>r.url().includes('/api/manage/')&&r.request().method()==='POST');await page.locator('.review-dialog .primary').click();const saved=await response;assert.equal(saved.status(),200,await saved.text());await page.waitForFunction(()=>!document.querySelector('#correction-form').dataset.busy);};
  try{
    await login(page,'qa-admin');await page.goto(base+'/app/#history');await page.getByRole('button',{name:'Paid water',exact:true}).click();
    await control('bill','edit').click();await page.locator('#correction-form [name=title]').fill('Corrected water');await reason();await review();
    assert.match(await page.locator('.review-dialog').innerText(),/Paid water → Corrected water/);
    await page.locator('.review-dialog .secondary').click();await page.locator('#correction-dialog').waitFor();assert.ok((await snapshot()).bills.some(b=>b.title==='Paid water'));
    await review();await confirm();await page.waitForFunction(()=>document.querySelector('#history-rows').innerText.includes('Corrected water'));
    await page.getByRole('button',{name:'Corrected water',exact:true}).click();await control('payment','edit').click();await page.locator('#correction-form [name=amount]').fill('80');await reason();await review();await confirm();
    await page.waitForFunction(()=>!document.querySelector('#history-rows').innerText.includes('Corrected water'));
    await page.goto(base+'/app/#bills');await page.locator('#search').fill('Corrected water');await page.locator('#bill-rows .bill-detail').click();await control('payment','delete').click();await reason();await review();
    assert.ok(await page.locator('.review-dialog').getAttribute('class').then(value=>value.includes('destructive')));await confirm();
    await page.waitForFunction(()=>document.querySelector('#bill-rows').innerText.includes('100.00'));
    await page.locator('#bill-rows .bill-detail').click();await control('bill','delete').click();await reason();await review();await confirm();await page.waitForFunction(()=>document.querySelectorAll('#bill-rows tr').length===0);
    await page.setViewportSize({width:390,height:844});await page.goto(base+'/app/#loans');await page.locator('#loan-rows .loan-view').first().click();await control('loan','edit').click();await page.locator('#correction-form [name=total]').fill('240');await reason();
    const correctionBox=await page.locator('#correction-dialog').boundingBox();assert.ok(correctionBox.x>=0&&correctionBox.x+correctionBox.width<=390);
    assert.match(await page.locator('#correction-impact').innerText(),/100.00 → PHP 140.00/);fs.mkdirSync('tmp/browser-qa',{recursive:true});await page.screenshot({path:'tmp/browser-qa/loan-correction-preview.png'});
    await review();await confirm();await page.waitForFunction(()=>document.querySelector('#loan-rows').innerText.includes('240.00'));
    await page.locator('#loan-rows .loan-view').first().click();await control('loan','delete').click();await reason();await review();assert.match(await page.locator('.review-dialog').innerText(),/2 active installment/);await confirm();await page.waitForFunction(()=>document.querySelectorAll('#loan-rows tr').length===0);
    await page.goto(base+'/app/#audit');await page.locator('#audit-filters [name=search]').fill('Browser correction');await page.waitForFunction(()=>document.querySelectorAll('#audit-rows tr').length>0&&document.querySelector('#audit-summary').textContent.includes('matching committed'));
    await page.locator('.audit-review').first().click();assert.match(await page.locator('#audit-detail-reason').innerText(),/Browser correction/);await page.screenshot({path:'tmp/browser-qa/correction-audit-reason.png'});await page.locator('#audit-dialog .close-dialog').click();
    await page.goto(base+'/app/#setup');await page.locator('#enable-offline').click();await page.waitForFunction(()=>localStorage.getItem('fbt-offline-enabled')==='yes');await context.setOffline(true);await page.goto(base+'/app/#bills');await page.reload();await page.locator('#bills').waitFor();await page.locator('#search').fill('Electricity');await page.locator('#bill-rows .bill-detail').click();assert.equal(await control('bill','edit').isDisabled(),true);assert.equal(await control('bill','delete').isDisabled(),true);
    await context.setOffline(false);
    const memberContext=await browser.newContext(),member=await memberContext.newPage();await login(member,'qa-member');await member.goto(base+'/app/#bills');await member.locator('#bill-rows .bill-detail').first().click();assert.equal(await member.locator('.financial-correction').count(),0);await memberContext.close();
    assert.deepEqual(errors,[]);console.log('Paid record corrections, canceled review, payment deletion, loan allocation/deletion, audit reasons and offline/member restrictions passed.');
  }finally{await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
