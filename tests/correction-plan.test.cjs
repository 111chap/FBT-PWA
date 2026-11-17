const test=require('node:test'),assert=require('node:assert/strict'),plan=require('../static/correction-plan.js');
test('loan correction retains paid installments and puts rounding cents in the last open one',()=>{
  assert.deepEqual(plan('250.01',[{amount:'100',balance:'0'},{amount:'100',balance:'100'},{amount:'100',balance:'100'}]),[10000,7500,7501]);
});
test('raising a paid loan reopens only its final installment',()=>{
  assert.deepEqual(plan('220',[{amount:'100',balance:'0'},{amount:'100',balance:'0'}]),[10000,12000]);
});
test('a title-only correction does not redistribute an uneven schedule',()=>{
  assert.deepEqual(plan('220',[{amount:'120',balance:'20'},{amount:'100',balance:'100'}]),[12000,10000]);
});
test('allocation rejects an agreement below retained payments and positive installment minima',()=>{
  assert.throws(()=>plan('100',[{amount:'100',balance:'0'},{amount:'100',balance:'100'}]),/at least/);
});
