const {test}=require('node:test'),assert=require('node:assert/strict');
const {nextUnpaid,personalTotals,filterRecords}=require('../static/record-filters.js');
const b=(id,date,balance,loan=null,extra={})=>({id,title:`Fictional ${id}`,due_date:date,balance:String(balance),amount:'100',loan_id:loan,responsible_id:1,visibility:'family',status:balance>0?'upcoming':'paid',...extra});
test('old and new loans expose only the actual earliest unpaid installment',()=>{
  const records=[b(9,'2027-03-01',90,4),b(2,'2027-01-01',0,4),b(3,'2027-02-01',20,4),b(4,'2027-02-01',100,4),b(1,'2027-01-05',100),b(8,'2027-01-01',100,5)];
  const before=JSON.stringify(records);assert.deepEqual(nextUnpaid(records).map(b=>b.id),[8,1,3]);assert.equal(JSON.stringify(records),before);
});
test('partial and overdue remain; full payment advances; reversing payment reopens earlier row',()=>{
  const records=[b(1,'2026-01-01',40,7,{status:'overdue'}),b(2,'2026-02-01',100,7)];
  assert.deepEqual(nextUnpaid(records).map(b=>b.id),[1]);records[0].balance='0';assert.deepEqual(nextUnpaid(records).map(b=>b.id),[2]);records[0].balance='1';assert.deepEqual(nextUnpaid(records).map(b=>b.id),[1]);
  records[0].removed=true;assert.deepEqual(nextUnpaid(records).map(b=>b.id),[2]);records[1].balance='0';assert.deepEqual(nextUnpaid(records),[]);
});
test('filters never promote a later installment',()=>{
  const records=[b(1,'2027-01-01',10,7),b(2,'2027-02-01',90,7)];
  assert.deepEqual(filterRecords(nextUnpaid(records),{from:'2027-02-01'}),[]);
  assert.deepEqual(filterRecords(nextUnpaid(records),{min:'50'}),[]);
  assert.deepEqual(filterRecords(nextUnpaid(records),{search:'Fictional 2'}),[]);
});
test('personal totals use primary payer and all installments, not just visible rows',()=>{
  const records=[b(1,'2027-01-01',10.1,7),b(2,'2027-01-15',20.2,7),b(3,'2027-02-01',70,7),b(4,'2027-01-02',50,null,{responsible_id:2,created_by_id:1}),b(5,'2026-12-31',5,null,{created_by_id:2}),b(6,'2027-01-01',0)];
  assert.deepEqual(personalTotals(records,1,'2027-01-31'),{personal:105.3,month:30.3,family:155.3,count:4});
  assert.equal(nextUnpaid(records).length,3);assert.equal(personalTotals(records,1,'2027-02-01').month,70);
});
test('private emergency rows never inflate personal or ordinary shared-family totals',()=>{
  const records=[b(1,'2027-01-01',50,null,{visibility:'private',owner_id:1}),b(2,'2027-01-01',80,null,{visibility:'private',owner_id:2,ordinary_visible:false}),b(3,'2027-01-01',10),b(4,'2027-01-01',500,null,{removed:true})];
  assert.deepEqual(personalTotals(records,1,'2027-01-01'),{personal:60,month:60,family:10,count:2});
  assert.deepEqual(personalTotals([],1,'2027-01-01'),{personal:0,month:0,family:0,count:0});
});
