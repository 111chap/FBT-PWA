/* Same deterministic view filters for live and saved snapshots. No writes. */
(function(root) {
  'use strict';
  function filterRecords(records, {search='', status='all', from='', to='', min='', max='', sort='date-asc'} = {}) {
    const [key, direction] = sort.split('-'), sign = direction === 'desc' ? -1 : 1;
    return records.filter(r => `${r.title} ${r.category || ''} ${r.responsible || ''}`.toLowerCase().includes(search.toLowerCase()) &&
      (status === 'all' || (status === 'unpaid' ? Number(r.balance) > 0 : r.status === status)) &&
      (!from || (r.due_date && r.due_date >= from)) && (!to || (r.due_date && r.due_date <= to)) &&
      (min === '' || Number(r.balance) >= Number(min)) && (max === '' || Number(r.balance) <= Number(max)))
      .sort((a,b) => {
        // Fully repaid loans have no next due date and always appear last.
        if(key === 'date' && (!a.due_date || !b.due_date)) return a.due_date ? -1 : b.due_date ? 1 : a.id-b.id;
        const compare = key === 'amount' ? Number(a.balance)-Number(b.balance) : a.due_date.localeCompare(b.due_date);
        return compare * sign || a.id-b.id;
      });
  }
  function loanSummaries(loans, bills) {
    return loans.map(loan => {
      const installments = bills.filter(b => b.loan_id === loan.id);
      const unpaid = installments.filter(b => Number(b.balance)>0).sort((a,b)=>a.due_date.localeCompare(b.due_date) || a.id-b.id);
      const balance = installments.reduce((total,b)=>total+Math.round(Number(b.balance)*100),0)/100;
      return {...loan, balance, due_date:unpaid[0]?.due_date || null, status:balance>0?'unpaid':'paid', paidCount:installments.filter(b=>Number(b.balance)<=0).length, responsible:[...new Set(installments.map(b=>b.responsible))].join(', ')};
    });
  }
  const api = {filterRecords, loanSummaries};
  if(typeof module !== 'undefined') module.exports = api;
  else root.FBTFilters = api;
})(typeof window !== 'undefined' ? window : globalThis);
