/* Cent-exact loan correction preview, matched by the server's validated plan. */
(function(root){
  function allocation(total,bills){
    const cents=Math.round(Number(total)*100),original=bills.reduce((sum,b)=>sum+Math.round(Number(b.amount)*100),0);
    if(!Number.isSafeInteger(cents)||cents<=0||cents>999999999999||!bills.length)throw new Error('Enter a valid agreement total.');
    if(cents===original)return bills.map(b=>Math.round(Number(b.amount)*100));
    const paid=bills.map(b=>Math.round((Number(b.amount)-Number(b.balance))*100));
    let eligible=bills.map((b,i)=>Number(b.balance)>0?i:-1).filter(i=>i>=0);if(!eligible.length)eligible=[bills.length-1];
    const result=paid.map(value=>Math.max(value,1)),minimum=result.reduce((a,b)=>a+b,0);
    if(cents<minimum)throw new Error(`The agreement must be at least PHP ${(minimum/100).toFixed(2)}. Correct or delete payments/installments first.`);
    const remaining=cents-minimum,each=Math.floor(remaining/eligible.length);
    eligible.forEach((index,position)=>{result[index]+=each+(position===eligible.length-1?remaining%eligible.length:0);});return result;
  }
  if(typeof module!=='undefined')module.exports=allocation;else root.FBTAllocation=allocation;
})(typeof window!=='undefined'?window:globalThis);
