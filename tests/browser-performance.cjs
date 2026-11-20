const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.argv[2];
const median=values=>values.sort((a,b)=>a-b)[Math.floor(values.length/2)];
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.FBT_BROWSER_EXECUTABLE?{executablePath:process.env.FBT_BROWSER_EXECUTABLE}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1366,height:768}});
    await page.goto(base+'/login/');await page.locator('[name=username]').fill('qa-admin');await page.locator('[name=password]').fill('Fictional-QA-passphrase-123!');
    await page.locator('form button').click();await page.locator('#overview').waitFor();
    const initial=await page.evaluate(()=>({readyMs:performance.now(),snapshotMs:performance.getEntriesByType('resource').find(r=>r.name.endsWith('/api/snapshot/'))?.duration,renderedRows:document.querySelectorAll('#bill-rows tr').length}));
    await page.goto(base+'/app/#bills');await page.locator('#bills').waitFor();
    const times=await page.evaluate(()=>{
      const input=document.getElementById('search'),times=[];
      for(const value of ['Power','Power 1','Power','Power 2','Power','Power 3','']){
        const start=performance.now();input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));times.push(performance.now()-start);
      }
      return times;
    });
    const historyStart=Date.now();await page.goto(base+'/app/#history');await page.locator('#history-rows tr').first().waitFor();
    const historyRows=await page.locator('#history-rows tr').count();assert.ok(historyRows<=25);
    const result={...initial,filterMedianMs:median(times),filterWorstMs:Math.max(...times),historyNavigationMs:Date.now()-historyStart,historyRows};
    fs.mkdirSync('tmp/browser-qa',{recursive:true});fs.writeFileSync(`tmp/browser-qa/performance-${process.env.FBT_BENCHMARK_LABEL||'current'}.json`,JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
    if(process.env.FBT_BENCHMARK_LABEL!=='baseline'){
      assert.ok(await page.locator('#bill-rows tr').count()<=25,'Bill DOM stays bounded for large households');
      await page.goto(base+'/app/#bills');const first=await page.locator('#bill-rows .bill-detail').first().getAttribute('data-id');
      await page.locator('#bill-next').click();assert.match(await page.locator('#bill-page').innerText(),/Page 2 of 36/);assert.equal(await page.locator('#bill-rows tr').count(),25);
      assert.notEqual(await page.locator('#bill-rows .bill-detail').first().getAttribute('data-id'),first);
      await page.locator('#bill-previous').click();assert.equal(await page.locator('#bill-rows .bill-detail').first().getAttribute('data-id'),first);
      await page.locator('#bill-next').click();await page.locator('#search').fill('Power 0000');assert.equal(await page.locator('#bill-rows tr').count(),1);assert.match(await page.locator('#bill-page').innerText(),/Page 1 of 1/);
      await page.goto(base+'/app/#history');await page.locator('#history-next').click();assert.match(await page.locator('#history-page').innerText(),/Page 2 of 40/);assert.equal(await page.locator('#history-rows tr').count(),25);
    }
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
