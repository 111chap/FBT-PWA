const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const {attachReceipt,image}=require('./browser-media-helper.cjs');
const base=process.argv[2];
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.FBT_BROWSER_EXECUTABLE?{executablePath:process.env.FBT_BROWSER_EXECUTABLE}:{})});
  const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));fs.mkdirSync('tmp/browser-qa',{recursive:true});
  const review=async()=>{await page.locator('.review-dialog').waitFor();await page.locator('.review-dialog .primary').click();};
  const snapshot=()=>page.evaluate(()=>fetch('/api/snapshot/').then(r=>r.json()));
  try{
    await page.goto(base+'/login/');await page.locator('[name=username]').fill('qa-admin');await page.locator('[name=password]').fill('Fictional-QA-passphrase-123!');await page.locator('form button').click();await page.locator('#overview').waitFor();
    await page.goto(base+'/app/#loans');await page.locator('#add-loan').click();
    for(const [name,value] of Object.entries({title:'Fictional installment plan',total:'50',installments:'2',first_due:'2027-01-31',notes:'Original shared note\nSecond line'}))await page.locator(`#loan-form [name=${name}]`).fill(value);
    await page.locator('#loan-form [name=visibility]').selectOption('family');await page.locator('#loan-form .primary').click();assert.match(await page.locator('.review-dialog').innerText(),/Original shared note/);await review();await page.locator('#loan-dialog').waitFor({state:'hidden'});await page.locator('#toast').filter({hasText:'Saved for your family.'}).waitFor();
    await page.goto(base+'/app/#bills');await page.locator('#search').fill('Fictional installment plan');assert.equal(await page.locator('#bill-rows tr').count(),1);
    await page.locator('#bill-rows .bill-detail').click();assert.match(await page.locator('#detail-notes').innerText(),/Original shared note/);await page.locator('#detail-actions .description-edit').click();await page.locator('#description-form [name=description]').fill('Current <script>text only</script>\nShared across months');await page.locator('#description-form [name=reason]').fill('Fictional description correction');await page.locator('#description-form .primary').click();await review();await page.locator('#toast').filter({hasText:'Description updated'}).waitFor();
    let current=(await snapshot()).bills.filter(b=>b.title.startsWith('Fictional installment plan'));assert.equal(current.length,2);assert(current.every(b=>b.shared_description.includes('<script>text only</script>')));
    for(const amount of ['10','15']){
      await page.locator('#bill-rows .pay-bill').click();await page.locator('#payment-form [name=amount]').fill(amount);await attachReceipt(page);await page.locator('#payment-preview').waitFor();await page.locator('#payment-form .primary').click();assert.match(await page.locator('.review-dialog').innerText(),/Validated image attached/);await review();await page.locator('#payment-dialog').waitFor({state:'hidden'});await page.waitForFunction(value=>value==='10'?document.querySelector('#bill-rows').textContent.includes('15.00'):document.querySelector('#bill-rows').textContent.includes('2/2'),amount);
    }
    assert.equal(await page.locator('#bill-rows tr').count(),1);assert.match(await page.locator('#bill-rows').innerText(),/2\/2/);
    current=(await snapshot()).bills.filter(b=>b.title.startsWith('Fictional installment plan'));assert.equal(current.reduce((n,b)=>n+b.payments.length,0),2);
    await page.goto(base+'/app/#history');await page.locator('#history-filters [name=search]').fill('Fictional installment plan');await page.locator('#history-rows .bill-detail').first().click();await page.locator('#detail-payments .view-evidence').first().click();await page.locator('#evidence-dialog').waitFor();await page.waitForFunction(()=>document.querySelector('#evidence-images img')?.naturalWidth===160);await page.locator('#evidence-dialog .close-dialog').click();await page.locator('#detail-dialog .close-dialog').click();
    await page.goto(base+'/app/#setup');await page.locator('#qr-settings-open').click();await page.locator('#qr-settings-form [name=recipient]').fill('Fictional demonstration recipient');await page.locator('#qr-settings-form [name=reason]').fill('Verified fictional QR for UI testing');await page.locator('#qr-settings-form input[type=file]').setInputFiles({name:'fictional-qr.png',mimeType:'image/png',buffer:image});await page.waitForFunction(()=>!!document.querySelector('#qr-settings-form [name=asset_id]').value);await page.locator('#qr-settings-form .primary').click();await review();await page.locator('#toast').filter({hasText:'Household QR updated'}).waitFor();
    const financialBefore=JSON.stringify((await snapshot()).bills.map(b=>[b.id,b.amount,b.balance,b.payments.length]));
    await page.locator('#setup .pay-qr').click();await page.waitForFunction(()=>document.querySelector('#qr-image').naturalWidth===160);assert.match(await page.locator('#qr-status').innerText(),/Fictional demonstration recipient/);
    const size=await page.locator('#qr-image').evaluate(img=>({w:img.naturalWidth,h:img.naturalHeight,filter:getComputedStyle(img).filter}));assert.deepEqual(size,{w:160,h:96,filter:'none'});await page.keyboard.press('Escape');
    assert.equal(JSON.stringify((await snapshot()).bills.map(b=>[b.id,b.amount,b.balance,b.payments.length])),financialBefore);
    await page.goto(base+'/app/#overview');
    for(const width of [320,390,768,1280]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);assert.match(await page.locator('#stats').innerText(),/Your total unpaid balance/);assert.match(await page.locator('#stats').innerText(),/Due this month/);}
    await page.setViewportSize({width:390,height:844});await page.locator('#theme-toggle').click();await page.goto(base+'/app/#setup');await page.locator('#setup .pay-qr').click();await page.waitForFunction(()=>document.querySelector('#qr-image').naturalWidth===160);await page.screenshot({path:'tmp/browser-qa/household-qr-dark-mobile.png',fullPage:true});await page.keyboard.press('Escape');
    await page.goto(base+'/app/#overview');await page.screenshot({path:'tmp/browser-qa/personal-totals-mobile.png',fullPage:true});assert.deepEqual(errors,[]);
  }catch(error){console.error(await page.locator('body').innerText());await page.screenshot({path:'tmp/browser-qa/remaining-features-failure.png',fullPage:true});throw error;}finally{await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
