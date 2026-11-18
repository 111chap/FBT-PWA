const {chromium}=require('playwright');
const assert=require('node:assert/strict');
async function main() {
  const browser=await chromium.launch({headless:true,...(process.env.FBT_BROWSER_EXECUTABLE ? {executablePath:process.env.FBT_BROWSER_EXECUTABLE} : {})});
  const page=await browser.newPage();
  try {
    const base=process.argv[2];await page.emulateMedia({colorScheme:'dark'});await page.goto(base+'/setup/');
    assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'light');
    assert.equal(await page.locator('body').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(250, 247, 244)');
    await page.locator('[name=token]').fill('fictional-first-run-code-123');await page.locator('[name=family_name]').fill('Fictional QA family');
    await page.locator('[name=username]').fill('qa-first-admin');await page.locator('[name=password]').fill('Fictional-first-admin-passphrase-123!');
    await page.locator('form button').click();await page.locator('.review-dialog').waitFor();
    const review=await page.locator('.review-dialog').innerText();
    assert(review.includes('Fictional QA family'));assert(!review.includes('fictional-first-run-code-123'));assert(!review.includes('Fictional-first-admin-passphrase-123!'));
    assert.equal((await page.request.get(base+'/setup/',{maxRedirects:0})).status(),200,'Review must not create the account');
    await page.keyboard.press('Escape');assert.equal(await page.locator('[name=username]').inputValue(),'qa-first-admin');
    await page.locator('form button').click();await page.locator('.review-dialog .primary').click();
    await page.locator('#setup').waitFor({state:'visible'});
    assert.equal((await page.request.get(base+'/setup/',{maxRedirects:0})).status(),302);
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
