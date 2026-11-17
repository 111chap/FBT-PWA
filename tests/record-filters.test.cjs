const {test}=require('node:test');
const assert=require('node:assert/strict');
const {filterRecords,loanSummaries,sortRecords,paidHistory,loanSchedule}=require('../static/record-filters.js');
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
test('headings sort titles, original amounts, unpaid amounts and explicit status ranks',()=>{
  const rows=[{id:4,title:'beta 10',amount:'100',balance:'2',due_date:'2028-01-01',status:'overdue'},
    {id:3,title:'Alpha',amount:'9',balance:'9',due_date:'2028-02-01',status:'upcoming'},
    {id:2,title:'alpha',amount:'100',balance:'10',due_date:'2028-02-01',status:'partial'},
    {id:1,title:'beta 2',amount:'200',balance:'0',due_date:'2028-03-01',status:'paid'}];
  const ids=sort=>sortRecords(rows,sort).map(b=>b.id);
  assert.deepEqual(ids('title-asc'),[2,3,1,4]); assert.deepEqual(ids('title-desc'),[4,1,2,3]);
  assert.deepEqual(ids('original-desc'),[1,2,4,3]); assert.deepEqual(ids('original-asc'),[3,2,4,1]);
  assert.deepEqual(ids('amount-desc'),[2,3,4,1]);
  assert.deepEqual(ids('status-asc'),[1,2,3,4]); assert.deepEqual(ids('status-desc'),[4,3,2,1]);
  assert.deepEqual(ids('date-asc'),[4,2,3,1]);
});
const historyBills=[{id:1,title:'Water',category:'Water',amount:'100',balance:'0',responsible:'Renamed payer',responsible_id:2,due_date:'2028-01-31',payments:[{amount:'40',paid_date:'2028-01-20',recorded_by_id:1,recorded_by:'Admin'},{amount:'60',paid_date:'2028-01-25',recorded_by_id:3,recorded_by:'Member'}]},
  {id:2,title:'Car · 1/3',category:'Loan',loan_id:1,amount:'50',balance:'0',responsible:'Member',responsible_id:3,due_date:'2028-02-29',payments:[{amount:'50',paid_date:'2028-02-01',recorded_by_id:1,recorded_by:'Admin'}]},
  {id:3,title:'Partial',category:'Water',amount:'100',balance:'10',responsible:'Member',responsible_id:3,due_date:'2028-01-31',payments:[{amount:'90',paid_date:'2028-01-25',recorded_by_id:1,recorded_by:'Admin'}]}];
test('paid history excludes partial records and uses latest payment date, not due date',()=>{
  const result=paidHistory(historyBills);
  assert.deepEqual(result.map(b=>b.id),[2,1]);
  assert.equal(result[1].completed_date,'2028-01-25'); assert.equal(result[1].due_date,'2028-01-31');
  assert.equal(result[1].total_paid,'100.00'); assert.equal(result[0].loan_id,1);
});
test('paid-history filters distinguish stable payer IDs from payment recorders',()=>{
  assert.deepEqual(paidHistory(historyBills,{payer:'2',recorder:'1',from:'2028-01-25',to:'2028-01-25'}).map(b=>b.id),[1]);
  assert.deepEqual(paidHistory(historyBills,{payer:'1'}),[]);
  assert.deepEqual(paidHistory(historyBills,{recorder:'3'}).map(b=>b.id),[1]);
  assert.deepEqual(paidHistory(historyBills,{sort:'amount-desc'}).map(b=>b.id),[1,2]);
  assert.deepEqual(paidHistory(historyBills,{search:'renamed'}).map(b=>b.id),[1]);
});
test('legacy offline snapshots can filter names before a refreshed identity snapshot',()=>{
  const legacy=historyBills.map(b=>({...b,responsible_id:undefined,payments:b.payments.map(p=>({...p,recorded_by_id:undefined}))}));
  assert.equal(paidHistory(legacy,{payer:'name:Renamed payer',recorder:'name:Admin'}).length,1);
});
test('history browsing leaves snapshot values and original order untouched',()=>{
  const before=JSON.stringify(historyBills); paidHistory(historyBills,{sort:'amount-asc'}); assert.equal(JSON.stringify(historyBills),before);
});
test('loan preview matches cent rounding and monthly anchors through leap years',()=>{
  const schedule=loanSchedule('1000',3,'2028-01-31');
  assert.deepEqual(schedule.map(p=>p.amount),['333.33','333.33','333.34']);
  assert.deepEqual(schedule.map(p=>p.due_date),['2028-01-31','2028-02-29','2028-03-31']);
  assert.equal(schedule.reduce((sum,p)=>sum+Math.round(Number(p.amount)*100),0),100000);
  assert.equal(loanSchedule('0.03',3,'2027-12-31')[1].due_date,'2028-01-31');
  assert.equal(loanSchedule('10',1,'2027-01-01')[0].amount,'10.00');
});
test('loan preview rejects impossible schedules before confirmation',()=>{
  for(const args of [['0.01',2,'2028-01-31'],['100',0,'2028-01-31'],['100',121,'2028-01-31'],['100',3,'2027-02-30'],['100',3,'1999-01-31'],['Infinity',3,'2028-01-31']]) assert.throws(()=>loanSchedule(...args));
});
