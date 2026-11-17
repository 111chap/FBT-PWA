const {test}=require('node:test');
const assert=require('node:assert/strict');
const {filterRecords,loanSummaries}=require('../static/record-filters.js');
const bills=[{id:3,title:'Water',balance:'100.00',amount:'200',due_date:'2028-02-29',status:'partial',loan_id:1,responsible:'Sam'},{id:1,title:'Power',balance:'9.00',due_date:'2028-01-31',status:'unpaid',loan_id:1,responsible:'Sam'},{id:2,title:'Paid',balance:'0.00',due_date:'2028-03-31',status:'paid',loan_id:2},{id:4,title:'Water',balance:'100',due_date:'2028-02-29',status:'unpaid'}];
test('numeric amounts and tied dates have deterministic order',()=>{
  assert.deepEqual(filterRecords(bills,{sort:'amount-asc'}).map(b=>b.id),[2,1,3,4]);
  assert.deepEqual(filterRecords(bills,{sort:'amount-desc'}).map(b=>b.id),[3,4,1,2]);
  assert.deepEqual(filterRecords(bills,{sort:'date-desc'}).map(b=>b.id),[2,3,4,1]);
});
test('inclusive date/amount boundaries combine with search and unpaid state',()=>{
  assert.deepEqual(filterRecords(bills,{search:'sam',status:'unpaid',from:'2028-02-29',to:'2028-02-29',min:'100',max:'100'}).map(b=>b.id),[3]);
  assert.deepEqual(filterRecords(bills,{from:'2029-01-01'}),[]);
  assert.equal(filterRecords(bills,{status:'paid',min:'0',max:'0'}).length,1);
});
test('loan dates use next unpaid installment and amounts use outstanding balance',()=>{
  const loans=loanSummaries([{id:1,title:'Car',total:'209',installments:2},{id:2,title:'Repaid',total:'20',installments:1}],bills);
  assert.equal(loans[0].balance,109); assert.equal(loans[0].due_date,'2028-01-31');
  assert.equal(loans[1].balance,0); assert.equal(loans[1].due_date,null);
  for(const sort of ['date-asc','date-desc']) assert.deepEqual(filterRecords(loans,{sort}).map(l=>l.id),[1,2]);
  assert.equal(filterRecords(loans,{from:'2028-01-01'}).length,1);
  assert.equal(filterRecords(loans,{status:'paid',min:'0',max:'0'})[0].id,2);
});
test('filtering never mutates the snapshot or source order',()=>{
  const before=JSON.stringify(bills); filterRecords(bills,{sort:'amount-desc'}); assert.equal(JSON.stringify(bills),before);
});
