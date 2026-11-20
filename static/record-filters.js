/* Same deterministic view filters for live and saved snapshots. No writes. */
(function(root) {
  'use strict';
  const titleOrder = new Intl.Collator('en-PH', {sensitivity:'base',numeric:true});
  const STATUS_RANK = {paid:0,partial:1,upcoming:2,overdue:3};
  function sortRecords(records, sort='date-asc') {
    const [key,direction]=sort.split('-'), sign=direction==='desc'?-1:1;
    return [...records].sort((a,b)=> {
      const dateA=key==='due'?a.original_due_date:a.due_date, dateB=key==='due'?b.original_due_date:b.due_date;
      if((key==='date' || key==='due') && (!dateA || !dateB)) return dateA?-1:dateB?1:a.id-b.id;
      const compare=key==='title'?titleOrder.compare(a.title,b.title):key==='status'?(STATUS_RANK[a.status]??4)-(STATUS_RANK[b.status]??4):key==='original'?Number(a.amount)-Number(b.amount):key==='amount'?Number(a.balance)-Number(b.balance):key==='paid'?Number(a.total_paid)-Number(b.total_paid):dateA.localeCompare(dateB);
      return compare*sign || a.id-b.id;
    });
  }
  function filterRecords(records, {search='', status='all', from='', to='', min='', max='', sort='date-asc'} = {}) {
    return sortRecords(records.filter(r => `${r.title} ${r.category || ''} ${r.responsible || ''}`.toLowerCase().includes(search.toLowerCase()) &&
      (status === 'all' || (status === 'unpaid' ? Number(r.balance) > 0 : r.status === status)) &&
      (!from || (r.due_date && r.due_date >= from)) && (!to || (r.due_date && r.due_date <= to)) &&
      (min === '' || Number(r.balance) >= Number(min)) && (max === '' || Number(r.balance) <= Number(max))),sort);
  }
  function loanSummaries(loans, bills) {
    return loans.map(loan => {
      const installments = bills.filter(b => b.loan_id === loan.id);
      const unpaid = installments.filter(b => Number(b.balance)>0).sort((a,b)=>a.due_date.localeCompare(b.due_date) || a.id-b.id);
      const balance = installments.reduce((total,b)=>total+Math.round(Number(b.balance)*100),0)/100;
      const status=balance<=0?'paid':unpaid.some(b=>b.status==='overdue')?'overdue':balance<Number(loan.total)?'partial':'upcoming';
      return {...loan, amount:loan.total, balance, due_date:unpaid[0]?.due_date || null, status, paidCount:installments.filter(b=>Number(b.balance)<=0).length, responsible:[...new Set(installments.map(b=>b.responsible))].join(', ')};
    });
  }
  function identityKey(id,name) { return id == null ? `name:${name}` : String(id); }
  function paidHistory(bills,{search='',payer='',recorder='',from='',to='',min='',max='',sort='date-desc'}={}) {
    const records=bills.filter(b=>Number(b.balance)<=0 && b.payments.length).map(b=>({...b,
      completed_date:b.payments.map(p=>p.paid_date).sort().at(-1),
      total_paid:(b.payments.reduce((n,p)=>n+Math.round(Number(p.amount)*100),0)/100).toFixed(2)}))
      .filter(b=>`${b.title} ${b.category} ${b.responsible}`.toLowerCase().includes(search.toLowerCase()) &&
        (!payer || identityKey(b.responsible_id,b.responsible)===payer) &&
        (!recorder || b.payments.some(p=>identityKey(p.recorded_by_id,p.recorded_by)===recorder)) &&
        (!from || b.completed_date>=from) && (!to || b.completed_date<=to) &&
        (min==='' || Number(b.amount)>=Number(min)) && (max==='' || Number(b.amount)<=Number(max)));
    // Sort a projected copy so history date means completion and amount means original amount.
    return sortRecords(records.map(b=>({...b,original_due_date:b.due_date,due_date:b.completed_date,balance:b.amount})),sort)
      .map(({original_due_date,...b})=>({...b,due_date:original_due_date,balance:'0.00'}));
  }
  function loanSchedule(total,count,firstDue) {
    const cents=Math.round(Number(total)*100);
    const match=/^(\d{4})-(\d{2})-(\d{2})$/.exec(firstDue || '');
    if(!Number.isFinite(cents) || cents<=0 || cents>999999999999 || !Number.isInteger(count) || count<1 || count>120 || cents<count || !match) throw new Error('Enter a valid total, 1–120 installments, and a first due date. Each installment must be at least PHP 0.01.');
    const [year,month,day]=match.slice(1).map(Number);
    const first=new Date(Date.UTC(year,month-1,day));
    if(year<2000 || year>2100 || first.toISOString().slice(0,10)!==firstDue) throw new Error('Use a valid first due date between 2000 and 2100.');
    const each=Math.floor(cents/count);
    return Array.from({length:count},(_,index)=> {
      const next=new Date(Date.UTC(year,month-1+index,1));
      next.setUTCDate(Math.min(day,new Date(Date.UTC(next.getUTCFullYear(),next.getUTCMonth()+1,0)).getUTCDate()));
      return {number:index+1,due_date:next.toISOString().slice(0,10),amount:((index===count-1?cents-each*(count-1):each)/100).toFixed(2)};
    });
  }
  function nextUnpaid(bills){
    const first=new Map(),singles=[];
    for(const b of bills){
      if(b.removed||Number(b.balance)<=0)continue;
      if(!b.loan_id){singles.push(b);continue;}
      const old=first.get(b.loan_id);
      if(!old||b.due_date<old.due_date||(b.due_date===old.due_date&&b.id<old.id))first.set(b.loan_id,b);
    }
    return sortRecords([...singles,...first.values()]);
  }
  function personalTotals(bills,userId,day){
    const eligible=bills.filter(b=>!b.removed&&b.ordinary_visible!==false&&Number(b.balance)>0);
    const sum=items=>items.reduce((n,b)=>n+Math.round(Number(b.balance)*100),0)/100;
    const mine=eligible.filter(b=>b.responsible_id===userId);
    return {personal:sum(mine),month:sum(mine.filter(b=>b.due_date.slice(0,7)===day.slice(0,7))),family:sum(eligible.filter(b=>(b.visibility||'family')==='family')),count:mine.length};
  }
  const api = {nextUnpaid, personalTotals, filterRecords, loanSummaries, sortRecords, paidHistory, identityKey, loanSchedule, STATUS_RANK};
  if(typeof module !== 'undefined') module.exports = api;
  else root.FBTFilters = api;
})(typeof window !== 'undefined' ? window : globalThis);
