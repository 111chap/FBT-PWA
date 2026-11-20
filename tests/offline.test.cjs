const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validateSnapshot,MAX_AGE}=require('../static/offline-store.js');
const now=Date.parse('2026-11-20T08:00:00Z');
const snapshot={version:1,user:{id:1},bills:[],synced_at:new Date(now).toISOString()};
test('accepts a fresh snapshot for the signed-in user',()=>assert.equal(validateSnapshot(snapshot,1,now),true));
test('rejects another account snapshot',()=>assert.equal(validateSnapshot(snapshot,2,now),false));
test('rejects emergency data from offline storage',()=>{
  assert.equal(validateSnapshot({...snapshot,offline_safe:false},1,now),false);
  assert.equal(validateSnapshot({...snapshot,emergency:true},1,now),false);
});
test('rejects expired offline financial records',()=>assert.equal(validateSnapshot(snapshot,1,now+MAX_AGE+1),false));
test('rejects snapshots with invalid or future dates',()=>{
  assert.equal(validateSnapshot({...snapshot,synced_at:'bad'},1,now),false);
  assert.equal(validateSnapshot({...snapshot,synced_at:new Date(now+120000).toISOString()},1,now),false);
});
test('rejects corrupt data and unsupported versions',()=>{
  for(const value of [null,{}, {...snapshot,version:2},{...snapshot,bills:null},{...snapshot,user:{id:'1'}}]) assert.equal(validateSnapshot(value,null,now),false);
});
