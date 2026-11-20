const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const base=process.argv[2],password='Fictional-QA-passphrase-123!';
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.FBT_BROWSER_EXECUTABLE?{executablePath:process.env.FBT_BROWSER_EXECUTABLE}:{})});
  const context=await browser.newContext({viewport:{width:390,height:844},extraHTTPHeaders:{'X-Forwarded-Proto':'https'}}),page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));fs.mkdirSync('tmp/browser-qa',{recursive:true});
  const review=async()=>{await page.locator('.review-dialog').waitFor();await page.locator('.review-dialog .primary').click();};
  const signin=async name=>{await page.goto(base+'/login/');await page.locator('[name=username]').fill(name);await page.locator('[name=password]').fill(password);await page.locator('form button').click();await page.locator('#overview').waitFor();};
  const signout=async()=>{await page.locator('#logout').click();await review();await page.waitForURL('**/login/');};
  try{
    await signin('qa-admin');
    await page.goto(base+'/app/#bills');await page.locator('#bill-rows').waitFor();
    assert(!await page.locator('#bill-rows').innerText().then(v=>v.includes('Private fictional school fee')));
    await page.locator('#bills .add-bill').click();await page.locator('[data-bill-type="one-time"]').click();
    assert.equal(await page.locator('#repeat-option').isVisible(),false);
    assert.equal(await page.locator('#bill-form [name=visibility]').inputValue(),'private');
    await page.locator('#bill-form [name=title]').fill('Fictional one-time repair');await page.locator('#bill-form [name=amount]').fill('125');await page.locator('#bill-form [name=visibility]').selectOption('family');
    await page.locator('#bill-form .primary').click();assert.match(await page.locator('.review-dialog').innerText(),/Family/);await review();await page.locator('#bill-dialog').waitFor({state:'hidden'});await page.locator('#toast').filter({hasText:'Saved for your family.'}).waitFor();
    await page.locator('#type-filter').selectOption('one-time');assert.match(await page.locator('#bill-rows').innerText(),/Fictional one-time repair/);
    await page.goto(base+'/app/#setup');await page.locator('#pin-settings-open').click();await page.locator('#pin-settings-form [name=password]').fill(password);await page.locator('#pin-settings-form [name=pin]').fill('839274');await page.locator('#pin-settings-form [name=pin_confirmation]').fill('839274');await page.locator('#pin-settings-form button.primary').click();await review();
    await page.locator('#toast').filter({hasText:'This device is enrolled'}).waitFor();
    const device=(await context.cookies()).find(c=>c.name==='fbt_pin_device');assert(device&&device.httpOnly&&device.secure&&device.sameSite==='Strict');
    await signout();await page.locator('a[href="/login/pin/"]').click();assert.equal(await page.locator('[name=pin]').getAttribute('inputmode'),'numeric');
    await page.locator('[name=pin]').fill('839274');await page.locator('form button').click();await page.locator('#overview').waitFor();
    await page.goto(base+'/app/#setup');await page.locator('#enable-offline').click();await page.locator('#toast').filter({hasText:'A read-only copy'}).waitFor();
    await page.locator('#emergency-open').click();await page.locator('#emergency-form [name=reason]').fill('Fictional emergency review');await page.locator('#emergency-form [name=password]').fill(password);await page.locator('#emergency-form button.primary').click();await review();await page.locator('#emergency-banner').waitFor();
    await page.locator('[data-nav=bills]').click();await page.locator('#type-filter').selectOption('all');assert.match(await page.locator('#bill-rows').innerText(),/Private fictional school fee/);
    assert.equal(await page.locator('#bills .add-bill').isDisabled(),true);
    const saved=await page.evaluate(async()=>await FBTOffline.read());assert(!saved.bills.some(b=>b.title==='Private fictional school fee'));
    await page.evaluate(()=>window.scrollTo(0,0));
    await page.screenshot({path:'tmp/browser-qa/privacy-emergency-mobile.png',fullPage:true});
    await page.locator('#emergency-exit').click();await page.locator('#emergency-banner').waitFor({state:'hidden'});assert(!await page.locator('#bill-rows').innerText().then(v=>v.includes('Private fictional school fee')));
    await signout();await signin('qa-member');await page.goto(base+'/app/#setup');await page.locator('#privacy-history-open').click();await page.locator('#privacy-history-dialog').waitFor();assert.match(await page.locator('#privacy-history-list').innerText(),/Fictional emergency review/);
    await page.screenshot({path:'tmp/browser-qa/privacy-owner-access-history.png',fullPage:true});
    assert.deepEqual(errors,[]);
  }catch(error){await page.screenshot({path:'tmp/browser-qa/privacy-pin-failure.png',fullPage:true});console.error(await page.locator('body').innerText());throw error;}finally{await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
