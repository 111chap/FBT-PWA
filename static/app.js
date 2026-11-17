/* No third-party scripts. Personal snapshots live only in opt-in IndexedDB storage. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  FBTCorrections.configure({request:api,refresh:loadSnapshot,notify:toast});
  let data = null, connected = false, pendingRefresh = false, checking = false, signingOut = false;
  let auditEvents = [], auditPageNumber = 1, auditTransaction = '', selectedAudit = null, auditRequest = 0;
  let billSort='date-asc', loanSort='date-asc', historySort='date-desc', historyPage=1;
  const historyPageSize=25;
  let billPage=1,loanPage=1;
  const listPageSize=25;
  let offlineEnabled = localStorage.getItem('fbt-offline-enabled') === 'yes';
  const currencyFormatter=new Intl.NumberFormat('en-PH',{style:'currency',currency:'PHP'});
  const dayFormatter=new Intl.DateTimeFormat('en-PH',{month:'short',day:'numeric',year:'numeric'});
  const currency=value=>currencyFormatter.format(Number(value));
  const dateLabel = value => dayFormatter.format(new Date(value+'T12:00:00'));
  const stamp = value => new Date(value).toLocaleString('en-PH', {dateStyle:'medium', timeStyle:'short'});
  const auditStamp = value => new Date(value).toLocaleString('en-PH', {dateStyle:'medium', timeStyle:'medium', timeZone:'Asia/Manila'}) + ' PHT';
  const today = () => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Manila', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());
  const csrf = () => document.cookie.split('; ').find(v => v.startsWith('csrftoken='))?.split('=')[1] || '';
  const badge = state => `<span class="badge ${esc(state)}">${esc({paid:'Paid',overdue:'Overdue',partial:'Part paid',upcoming:'Upcoming',healthy:'Running',warning:'Needs attention',configured:'Configured',manual:'Check manually',error:'Not healthy'}[state] || state)}</span>`;
  function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => $('toast').hidden = true, 6000); }
  function error(message) { $('error').textContent = message; $('error').hidden = !message; }
  async function fetchTimed(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 6500);
    try { return await fetch(url, {...options, signal:controller.signal, credentials:'same-origin', cache:'no-store', redirect:'error'}); }
    finally { clearTimeout(timeout); }
  }
  async function purge() {
    offlineEnabled = false;
    localStorage.removeItem('fbt-offline-enabled');
    localStorage.removeItem('fbt-offline-owner');
    await FBTOffline.clear();
    localStorage.setItem('fbt-cleared', String(Date.now()));
  }
  async function expired() {
    try { await purge(); } catch (_) { /* Tell user below; do not render cached records. */ }
    data = null;
    location.replace('/login/');
  }
  async function api(url, options = {}) {
    if (options.method && options.method !== 'GET' && (!connected || pendingRefresh)) throw new Error('Reconnect and update your bills before making changes.');
    let response;
    try { response = await fetchTimed(url, {...options, headers:{'Content-Type':'application/json', 'X-CSRFToken':csrf(), ...options.headers}}); }
    catch (_) { setConnection(false); throw new Error('Your home server could not be reached. No offline changes are queued. If recording a payment, close this form, reconnect, then refresh and check its history to see whether it was saved.'); }
    if (response.status === 401) { await expired(); throw new Error('Please sign in again.'); }
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'The request could not be completed. Refresh and try again.');
    return result;
  }
  async function saveCurrent() {
    if (!offlineEnabled || !data) return;
    try { await FBTOffline.write(data); }
    catch (exception) { error(exception.message + ' Your online records are safe, but this device may have an older offline copy.'); }
  }
  async function loadSnapshot(initial = false) {
    if(signingOut) return;
    try {
      const response = await fetchTimed('/api/snapshot/');
      if (response.status === 401) { await expired(); return; }
      if (!response.ok) throw new Error('Server temporarily unavailable.');
      const value = await response.json();
      if(signingOut) return;
      if (!FBTOffline.validateSnapshot(value)) throw new Error('Invalid snapshot.');
      if ((data && value.user.id !== data.user.id) || (offlineEnabled && Number(localStorage.getItem('fbt-offline-owner')) !== value.user.id)) await purge();
      data = value; pendingRefresh = false; setConnection(true); error('');
      await saveCurrent(); render();
    } catch (exception) {
      if (initial && offlineEnabled && !localStorage.getItem('fbt-logout-pending')) {
        try { data = await FBTOffline.read(); } catch (storageError) { error(storageError.message); }
      }
      pendingRefresh = false; setConnection(false);
      if (data) render();
      else { $('loading').innerHTML = '<h2>Your home server is out of reach.</h2><p>Join your home network and reload. To review bills offline later, first enable a saved copy in Setup & devices while connected.</p><p>Saved copies expire after seven days.</p>'; }
    }
  }
  function setConnection(value) {
    connected = value;
    if(data){FBTProfile.update(data,connected);FBTCorrections.update(data,connected,pendingRefresh);}
    $('connection-badge').className = 'badge ' + (value ? 'healthy' : 'warning');
    $('connection-badge').textContent = value ? '● Home server connected' : '○ Offline · read-only';
    $('home-copy').textContent = value ? 'Your home server is reachable. Your family is connected.' : 'You are viewing a saved copy. Updates need a connection to your home server.';
    document.querySelectorAll('[data-online]').forEach(button => button.disabled = !value || pendingRefresh);
    $('server-form').querySelectorAll('input,button').forEach(input => input.disabled = !value || pendingRefresh || !data?.user.admin);
    $('export-link').hidden = !value;
    const showNotice = !value || pendingRefresh;
    $('notice').hidden = !showNotice;
    $('notice-title').textContent = pendingRefresh ? 'Welcome back. New information may be available.' : 'A copy for when you are away.';
    $('notice-copy').textContent = pendingRefresh ? 'Your home server is reachable again. Update this view before recording payments.' : data ? `Saved for ${data.user.name} on ${stamp(data.synced_at)}. Payments and amounts may have changed. Join your home network to update.` : 'Connect to your home server to load your family records.';
    $('refresh-snapshot').hidden = !pendingRefresh;
    if (!value) {
      auditRequest += 1;
      auditEvents = [];
      $('audit-rows').replaceChildren();
      $('audit-summary').textContent = 'Live audit history is unavailable while disconnected.';
      $('audit-previous').disabled = $('audit-next').disabled = true;
      $('audit-dialog').close();
      $('status-checked').textContent = 'Live status unavailable while the home server is out of reach.';
      $('health-cards').innerHTML = '<article class="card"><h2>Connection unavailable</h2><p class="muted">Component status cannot be checked offline. Reconnect, update your bills, then run a fresh status check.</p></article>';
    }
  }
  function row(bill) {
    return `<tr><td><button class="bill-detail" data-id="${bill.id}">${esc(bill.title)}</button><span class="small muted">${esc(bill.category)} · Primary payer: ${esc(bill.responsible)}${bill.recurring ? ' · Monthly' : ''}</span></td><td data-label="Due date">${dateLabel(bill.due_date)}</td><td data-label="Original amount">${currency(bill.amount)}</td><td data-label="Amount unpaid">${currency(bill.balance)}</td><td data-label="Payment status">${badge(bill.status)}</td><td>${Number(bill.balance) > 0 ? `<button class="button secondary pay-bill" data-id="${bill.id}" data-online ${!connected || pendingRefresh ? 'disabled' : ''}>Record payment</button>` : '✓ Complete'}</td></tr>`;
  }
  function renderBills(keepPage=false) {
    if(keepPage!==true)billPage=1;
    if (!data) return;
    const search = $('search').value.toLowerCase();
    const filter = $('status-filter').value;
    const bills = FBTFilters.filterRecords(data.bills.filter(b=>Number(b.balance)>0), {...viewFilters('bill'), search, status:filter, sort:billSort});
    billPage=pageControls('bill',billPage,bills.length);
    $('bill-rows').innerHTML=bills.slice((billPage-1)*listPageSize,billPage*listPageSize).map(row).join('');
    $('bills-empty').hidden = bills.length > 0;
    updateSortHeadings();
  }
  function pageControls(prefix,page,total){
    const pages=Math.max(1,Math.ceil(total/listPageSize));page=Math.min(page,pages);
    $(`${prefix}-page`).textContent=`Page ${page} of ${pages} · ${total} records`;
    $(`${prefix}-previous`).disabled=page<=1;$(`${prefix}-next`).disabled=page>=pages;
    return page;
  }
  for(const prefix of ['bill','loan']){
    for(const [direction,step] of [['previous',-1],['next',1]])$(`${prefix}-${direction}`).addEventListener('click',()=>{
      if(prefix==='bill'){billPage=Math.max(1,billPage+step);renderBills(true);}else{loanPage=Math.max(1,loanPage+step);renderLoans(true);}
    });
  }
  function viewFilters(prefix) {
    return Object.fromEntries(new FormData($(`${prefix}-view-filters`)));
  }
  const firstSort={title:'asc',date:'asc',due:'asc',original:'desc',amount:'desc',paid:'desc',status:'asc'};
  const sortViews={
    bill:{section:'bills',names:{title:'Bill name',date:'Due date',original:'Original amount',amount:'Amount unpaid',status:'Payment status'},get:()=>billSort,set:value=>{billSort=value;},render:renderBills},
    loan:{section:'loans',names:{title:'Loan name',date:'Next due date',original:'Agreed total',amount:'Amount unpaid',status:'Payment status'},get:()=>loanSort,set:value=>{loanSort=value;},render:renderLoans},
    history:{section:'history',names:{title:'Bill name',due:'Due date',original:'Original amount',paid:'Total paid',date:'Date fully paid'},get:()=>historySort,set:value=>{historySort=value;},render:()=>{historyPage=1;renderHistory();}}
  };
  const sortDirection=(view,key,direction)=>key==='title'?(direction==='asc'?'A–Z':'Z–A'):(key==='date'||key==='due')?(direction==='asc'?'earliest first':'latest first'):key==='status'?(direction==='asc'?`${view==='loan'?'Paid → ':''}Part paid → Upcoming → Overdue`:`Overdue → Upcoming → Part paid${view==='loan'?' → Paid':''}`):(direction==='asc'?'lowest first':'highest first');
  function updateSortHeadings(view='bill') {
    const config=sortViews[view], [key,direction]=config.get().split('-');
    $(config.section).querySelectorAll('[data-sort]').forEach(button=> {
      const active=button.dataset.sort===key;
      const next=active?(direction==='asc'?'desc':'asc'):firstSort[button.dataset.sort];
      button.querySelector('span').textContent=active?(direction==='asc'?' ↑':' ↓'):' ↕';
      button.setAttribute('aria-label',`${config.names[button.dataset.sort]}: sort ${sortDirection(view,button.dataset.sort,next)}`);
      button.closest('th')?.setAttribute('aria-sort',active?(direction==='asc'?'ascending':'descending'):'none');
      if(button.closest('.mobile-bill-sort')) button.setAttribute('aria-pressed',String(active));
    });
    $(`${view}-sort-description`).textContent=`Sorted by ${config.names[key].toLowerCase()}: ${sortDirection(view,key,direction)}. Select a heading again to reverse.`;
  }
  for(const [view,config] of Object.entries(sortViews)) {
    $(`mobile-${view}-sort`).innerHTML=Object.entries(config.names).map(([key,name])=>`<button type="button" class="button secondary" data-sort="${key}">${name}<span aria-hidden="true"></span></button>`).join('');
    $(config.section).querySelectorAll('[data-sort]').forEach(button=>button.addEventListener('click',()=> {
      const [current,direction]=config.get().split('-'), key=button.dataset.sort;
      config.set(`${key}-${key===current?(direction==='asc'?'desc':'asc'):firstSort[key]}`);
      config.render();
    }));
  }
  function renderHistoryMembers() {
    const payers=new Map(data.members.map(m=>[String(m.id),m.username])), recorders=new Map();
    for(const bill of data.bills) {
      payers.set(FBTFilters.identityKey(bill.responsible_id,bill.responsible),bill.responsible);
      for(const payment of bill.payments) recorders.set(FBTFilters.identityKey(payment.recorded_by_id,payment.recorded_by),payment.recorded_by);
    }
    for(const [name,entries,label] of [['payer',payers,'All family members'],['recorder',recorders,'Anyone']]) {
      const select=$('history-filters').elements[name], previous=select.value;
      select.innerHTML=`<option value="">${label}</option>`+[...entries].sort((a,b)=>a[1].localeCompare(b[1])).map(([id,name])=>`<option value="${esc(id)}">${esc(name)}</option>`).join('');
      if(entries.has(previous)) select.value=previous;
    }
  }
  function renderHistory() {
    if(!data) return;
    const filters={...Object.fromEntries(new FormData($('history-filters'))),sort:historySort};
    const invalid=(filters.from && filters.to && filters.from>filters.to) || (filters.min!=='' && filters.max!=='' && Number(filters.min)>Number(filters.max));
    const records=invalid?[]:FBTFilters.paidHistory(data.bills,filters);
    const pages=Math.max(1,Math.ceil(records.length/historyPageSize)); historyPage=Math.min(historyPage,pages);
    $('history-rows').innerHTML=records.slice((historyPage-1)*historyPageSize,historyPage*historyPageSize).map(bill=> {
      const loan=data.loans.find(loan=>loan.id===bill.loan_id);
      return `<tr><td><button class="bill-detail" data-id="${bill.id}">${esc(bill.title)}</button><span class="small muted">${esc(bill.category)} · Primary payer: ${esc(bill.responsible)}${loan?` · Loan: ${esc(loan.title)}`:''}</span></td><td data-label="Due date">${dateLabel(bill.due_date)}</td><td data-label="Original amount">${currency(bill.amount)}</td><td data-label="Total paid">${currency(bill.total_paid)}</td><td data-label="Date fully paid">${dateLabel(bill.completed_date)}</td><td><button class="button secondary bill-detail" data-id="${bill.id}">Review payments</button></td></tr>`;
    }).join('');
    $('history-empty').hidden=records.length>0;
    $('history-summary').textContent=invalid?'Check the date and amount ranges: minimum must not exceed maximum.':`${records.length} fully paid bill${records.length===1?'':'s'} · Shared family history · Saved ${stamp(data.synced_at)}`;
    $('history-page').textContent=`Page ${historyPage} of ${pages}`;
    $('history-previous').disabled=historyPage<=1; $('history-next').disabled=historyPage>=pages;
    updateSortHeadings('history');
  }
  const updateHistoryFilters=()=> {historyPage=1;renderHistory();};
  $('history-filters').addEventListener('input',updateHistoryFilters);
  $('history-filters').addEventListener('change',event=> {if(event.target.tagName==='SELECT') updateHistoryFilters();});
  $('history-filters').addEventListener('submit',event=>event.preventDefault());
  $('history-filters').addEventListener('reset',()=>setTimeout(()=> {historyPage=1;historySort='date-desc';renderHistory();},0));
  $('history-previous').addEventListener('click',()=> {historyPage=Math.max(1,historyPage-1);renderHistory();});
  $('history-next').addEventListener('click',()=> {historyPage+=1;renderHistory();});
  for(const prefix of ['bill','loan']) {
    const form = document.createElement('form'); form.id = `${prefix}-view-filters`; form.className = 'view-filters';
    form.innerHTML = `<label>${prefix === 'loan' ? 'Next unpaid due from' : 'Due from'}<input name="from" type="date"></label><label>Through date (inclusive)<input name="to" type="date"></label><label>Minimum unpaid (PHP)<input name="min" class="amount-input" inputmode="decimal" type="number" min="0" step="0.01"></label><label>Maximum unpaid (PHP)<input name="max" class="amount-input" inputmode="decimal" type="number" min="0" step="0.01"></label><button type="reset" class="button secondary">Clear filters</button><p class="filter-error form-error" hidden role="alert"></p>`;
    $(`${prefix}-filters`).append(form);
    const update = () => {
      const f = viewFilters(prefix), message = form.querySelector('.filter-error');
      const invalid = (f.from && f.to && f.from>f.to) || (f.min !== '' && f.max !== '' && Number(f.min)>Number(f.max));
      message.hidden = !invalid; message.textContent = 'Start date and minimum amount must not exceed their end / maximum.';
      if(prefix === 'bill') renderBills(); else renderLoans();
    };
    form.addEventListener('submit',event=>event.preventDefault()); form.addEventListener('input',update);
    // Text-field blur must not rebuild rows between pointer-down and click.
    form.addEventListener('change',event=> {if(event.target.tagName==='SELECT') update();});
    form.addEventListener('reset',()=> { if(prefix==='bill') { $('search').value=''; $('status-filter').value='all'; billSort='date-asc'; } else { $('loan-search').value=''; $('loan-status-filter').value='all'; loanSort='date-asc'; } setTimeout(update,0); });
  }
  function renderRecurrences() {
    $('recurrence-list').innerHTML = (data.recurrences || []).filter(r=>!r.removed).map(r=>`<div class="recurrence-item"><strong>${esc(r.title)}</strong><p class="hint">Day ${r.anchor_day} each month · ${r.active ? 'Active' : 'Cancelled'} · Primary payer: ${esc(data.members.find(m=>m.id===r.responsible_id)?.username || 'Inactive member')}</p>${data.user.admin && r.active ? `<button class="button secondary recurrence-action" data-id="${r.id}" data-action="cancel" data-online>Cancel schedule</button>` : ''}${data.user.admin && !data.bills.some(b=>b.recurrence_id===r.id && b.payments.length) ? `<button class="button secondary recurrence-action" data-id="${r.id}" data-action="remove" data-online>Remove schedule</button>` : ''}</div>`).join('') || '<p class="hint">No monthly schedules.</p>';
    setConnection(connected);
  }
  function showDetailActions(bill) {
    const recurrence = (data.recurrences || []).find(r=>r.id===bill.recurrence_id);
    $('detail-recurrence').textContent = recurrence ? `Monthly: day ${recurrence.anchor_day} (last valid day in shorter months). Schedule ${recurrence.active ? 'active' : 'cancelled'}.` : '';
    $('detail-actions').innerHTML = data.user.admin ? `<button class="button secondary reassign-payer" data-id="${bill.id}" data-online>Change primary payer</button>${FBTCorrections.controls('bill',bill.id)}` : '';
    setConnection(connected);
  }
  document.addEventListener('click',async event=> {
    const assign = event.target.closest('.reassign-payer');
    if(assign) {
      const bill = data.bills.find(b=>b.id===Number(assign.dataset.id)), form = $('payer-form');
      form.reset(); form.elements.bill_id.value = bill.id; form.elements.expected_version.value = bill.version;
      const recurrence = (data.recurrences || []).find(r=>r.id===bill.recurrence_id);
      form.elements.recurrence_version.value = recurrence?.version || '';
      form.elements.scope.options[1].disabled = !recurrence?.active;
      form.elements.responsible.value = bill.responsible_id;
      $('payer-current').textContent = `${bill.title} · Primary payer: ${bill.responsible}`;
      $('detail-dialog').close(); openDialog('payer-dialog');
    }
    const control = event.target.closest('.recurrence-action, .remove-bill');
    if(!control || control.disabled) return;
    control.disabled = true;
    try {
      if(!connected || pendingRefresh) throw new Error('Connect and refresh before reviewing changes.');
      const schedule = control.matches('.recurrence-action');
      const item = (schedule ? data.recurrences : data.bills).find(r=>r.id===Number(control.dataset.id));
      const action = schedule ? control.dataset.action : 'remove';
      const note = action === 'cancel' ? 'Stops new occurrences. Existing bills and payment history remain. Cancellation cannot be undone here.' : 'Removes unpaid records from active views. Retained records and audit history remain in the database. Records with payments cannot be removed. Removal cannot be undone here.';
      if(!await FBTReview({title:action === 'cancel' ? 'Cancel monthly schedule?' : 'Remove from active bills?', rows:[['Record',item.title],...(schedule ? [['Monthly due day',item.anchor_day],['State',item.active?'Active':'Cancelled']] : [['Due date',item.due_date],['Unpaid amount',currency(item.balance)]])], action:action === 'cancel' ? 'Cancel schedule' : 'Remove unpaid records',note})) return;
      await api(schedule ? `/api/recurrences/${item.id}/action/` : `/api/bills/${item.id}/remove/`,{method:'POST',body:JSON.stringify({action,expected_version:item.version})});
      $('detail-dialog').close(); await loadSnapshot(); toast('Saved. History has been retained.');
    } catch(exception) { error(exception.message); toast(exception.message); }
    finally { control.disabled = !connected || pendingRefresh; }
  });
  function renderLoans(keepPage=false) {
    if(keepPage!==true)loanPage=1;
    if(!data) return;
    const records=FBTFilters.filterRecords(FBTFilters.loanSummaries(data.loans,data.bills),{...viewFilters('loan'),search:$('loan-search').value,status:$('loan-status-filter').value,sort:loanSort});
    loanPage=pageControls('loan',loanPage,records.length);
    $('loan-rows').innerHTML=records.slice((loanPage-1)*listPageSize,loanPage*listPageSize).map(loan=> {
      const progress=Number(loan.total)>0?Math.max(0,Math.min(100,(Number(loan.total)-loan.balance)/Number(loan.total)*100)):0;
      return `<tr><td><button class="record-title loan-view" data-loan="${loan.id}">${esc(loan.title)}</button><span class="small muted">Primary payer: ${esc(loan.responsible)}</span><progress max="100" value="${progress.toFixed(2)}" aria-label="${esc(loan.title)} repayment progress"></progress><span class="small muted">${loan.paidCount} of ${loan.installments} installments paid</span></td><td data-label="Next due date">${loan.due_date?dateLabel(loan.due_date):'Fully repaid'}</td><td data-label="Agreed total">${currency(loan.total)}</td><td data-label="Amount unpaid">${currency(loan.balance)}</td><td data-label="Payment status">${badge(loan.status)}</td><td><button class="button secondary loan-view" data-loan="${loan.id}">Review installments</button></td></tr>`;
    }).join('');
    $('loans-empty').hidden=records.length>0;
    updateSortHeadings('loan');
  }
  function showLoanDetails(id) {
    const loan=data.loans.find(loan=>loan.id===id);
    if(!loan) return;
    const bills=data.bills.filter(bill=>bill.loan_id===id);
    $('detail-dialog').close();
    $('detail-title').textContent=loan.title;
    $('detail-summary').textContent=`${currency(loan.total)} agreed total · ${currency(bills.reduce((sum,b)=>sum+Math.round(Number(b.balance)*100),0)/100)} unpaid · ${loan.installments} installments`;
    $('detail-recurrence').textContent='Monthly repayment schedule';
    $('detail-actions').innerHTML=FBTCorrections.controls('loan',loan.id);
    $('detail-notes').textContent='Select an installment to review its bill and recorded payments.';
    $('detail-payments').innerHTML=bills.map(b=>`<div class="activity"><div><button class="bill-detail" data-id="${b.id}">${esc(b.title)}</button><p>${dateLabel(b.due_date)} · Primary payer: ${esc(b.responsible)}</p><p>${currency(b.amount)} original · ${currency(b.balance)} unpaid</p></div>${badge(b.status)}</div>`).join('');
    $('detail-dialog').showModal();
  }
  function render() {
    if (!data) return;
    $('loading').hidden = true;
    $('family-name').textContent = data.family_name.toUpperCase();
    $('today-label').textContent = new Date().toLocaleDateString('en-PH', {weekday:'long', month:'long', day:'numeric', year:'numeric'});
    $('user-avatar').textContent = data.user.name.slice(0,2).toUpperCase();
    $('user-avatar').title = data.user.name;
    FBTProfile.update(data,connected);
    $('home-name').textContent = data.nas_name;
    $('last-synced').textContent = `Last updated ${stamp(data.synced_at)}`;
    const unpaid = data.bills.filter(b => Number(b.balance) > 0);
    const overdue = unpaid.filter(b => b.status === 'overdue');
    const weekEnd = new Date(data.today + 'T12:00:00'); weekEnd.setDate(weekEnd.getDate()+7);
    const coming = unpaid.filter(b => b.due_date >= data.today && new Date(b.due_date + 'T12:00:00') <= weekEnd);
    const sum = bills => bills.reduce((total,b) => total + Math.round(Number(b.balance)*100),0)/100;
    $('stats').innerHTML = [
      ['Total unpaid',currency(sum(unpaid)),`${unpaid.length} bills to take care of`,''],
      ['Due in the next 7 days',currency(sum(coming)),`${coming.length} upcoming payments`,''],
      ['Overdue',currency(sum(overdue)),`${overdue.length} bills need a look`,'warm']
    ].map(([label,value,detail,cls]) => `<article class="stat ${cls}"><p class="stat-label">${label}</p><div class="stat-value">${value}</div><p>${detail}</p></article>`).join('');
    $('upcoming-list').innerHTML = unpaid.slice(0,5).map(b => `<div class="bill-item"><span class="category-icon" aria-hidden="true">${b.loan_id ? '↗' : '▤'}</span><div class="bill-info"><strong>${esc(b.title)}</strong><p>${dateLabel(b.due_date)} · Primary payer: ${esc(b.responsible)}</p></div><div class="bill-amount"><strong>${currency(b.balance)}</strong><div>${badge(b.status)}</div></div></div>`).join('') || '<div class="empty"><h3>Nothing on the list just yet.</h3><p>Add your first bill, or enjoy being all caught up.</p></div>';
    const activity = data.bills.flatMap(b => b.payments.map(p => ({...p, title:b.title}))).sort((a,b) => b.paid_date.localeCompare(a.paid_date)).slice(0,4);
    $('activity-list').innerHTML = activity.map(p => `<div class="activity"><div><strong>${esc(p.title)}</strong><p>Recorded by ${esc(p.recorded_by)} · ${dateLabel(p.paid_date)}</p></div><strong>${currency(p.amount)}</strong></div>`).join('') || '<p class="small muted">Payments recorded by your family will appear here.</p>';
    document.querySelectorAll('select.members').forEach(select => { const previous = select.value; select.innerHTML = data.members.map(member => `<option value="${member.id}">${esc(member.username)}</option>`).join(''); select.value = previous || data.user.id; });
    for (const name of ['family_name','nas_name','server_url']) $('server-form').elements[name].value = data[name] || '';
    $('server-form').querySelectorAll('input,button').forEach(input => input.disabled = !data.user.admin || !connected || pendingRefresh);
    $('server-form').hidden = !data.user.admin;
    $('shared-server').hidden = data.user.admin;
    $('server-heading').textContent = data.user.admin ? 'Name your home server' : 'Your family’s home server';
    $('server-copy').textContent = data.user.admin ? 'Use the HTTPS address configured on your NAS. Saving these details does not change DNS, connect to another NAS, or move data.' : 'One home server is shared by your family. Your administrator manages these details.';
    $('shared-server-values').innerHTML = [['Family name',data.family_name],['NAS display name',data.nas_name],['Home server address',data.server_url || 'Not set']].map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
    renderRecurrences();
    $('admin-note').textContent = data.user.admin ? 'Administrator settings. Saving does not change deployment configuration.' : 'Ask your family administrator to change these settings.';
    $('admin-link').hidden = !data.user.admin;
    $('audit-nav').hidden = !data.user.admin;
    $('offline-setting').textContent = offlineEnabled ? `Enabled on this device. Saved copies expire after seven days. Last fetched ${stamp(data.synced_at)}.` : 'Offline viewing is off. Enable it on a trusted device while connected.';
    renderHistoryMembers(); route();
  }
  function route() {
    const name = ['overview','bills','loans','history','system','setup','audit'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
    document.querySelectorAll('.page').forEach(section => section.hidden = !data || section.id !== name);
    document.querySelectorAll('[data-nav]').forEach(link => { link.classList.toggle('active',link.dataset.nav === name); if(link.dataset.nav === name) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current'); });
    if(name==='bills')renderBills();
    if(name==='loans')renderLoans();
    if(name==='history')renderHistory();
    if (name === 'system' && connected && !pendingRefresh) health();
    if (name === 'audit') loadAudit();
  }
  let auditFilterTimer;
  async function loadAudit() {
    clearTimeout(auditFilterTimer);
    const request = ++auditRequest;
    $('audit-message').hidden = true;
    if (!data?.user.admin || !connected || pendingRefresh) {
      auditEvents = [];
      $('audit-rows').replaceChildren();
      $('audit-summary').textContent = !data?.user.admin ? 'Only the family administrator can review the full audit history.' : 'Connect and update your bills before reviewing live audit history.';
      return;
    }
    const filters = new URLSearchParams(new FormData($('audit-filters')));
    filters.set('page',String(auditPageNumber));
    if (auditTransaction) filters.set('transaction',auditTransaction);
    $('audit-summary').textContent = 'Checking committed changes…';
    try {
      const result = await api('/api/audit/?'+filters.toString());
      if (request !== auditRequest || !connected) return;
      auditEvents = result.events;
      auditPageNumber = result.page;
      $('audit-rows').innerHTML = result.events.map(event => `<tr><td><strong>${esc(auditStamp(event.occurred_at))}</strong><span class="small muted">${esc(event.actor_name)} · ${esc(event.source)}</span></td><td>${auditAction(event.action)}</td><td><strong>${esc(event.label)}</strong><span class="small muted">${esc(event.entity_type)} #${esc(event.entity_id)}</span></td><td><button class="audit-transaction text-button" data-reference="${esc(event.transaction_id)}" title="Show all changes in this transaction">${esc(event.transaction_id.slice(0,12))}…</button></td><td><button class="audit-review button secondary" data-event="${event.id}">Review</button></td></tr>`).join('');
      $('audit-empty').hidden = result.events.length > 0;
      $('audit-summary').textContent = `${result.total} matching committed change${result.total === 1 ? '' : 's'}${auditTransaction ? ' · One transaction selected' : ''}`;
      $('audit-page').textContent = `Page ${result.page} of ${result.pages}`;
      $('audit-previous').disabled = !result.has_previous;
      $('audit-next').disabled = !result.has_next;
      $('audit-clear-transaction').hidden = !auditTransaction;
      $('audit-started').textContent = result.logging_started_at ? `Logging started ${auditStamp(result.logging_started_at)}. Earlier records are not retrospectively attributed.` : 'No logging-start marker is available.';
    } catch (exception) {
      if (request !== auditRequest) return;
      auditEvents = [];
      $('audit-rows').replaceChildren();
      $('audit-message').textContent = exception.message;
      $('audit-message').hidden = false;
      $('audit-summary').textContent = 'Audit history could not be checked.';
      $('audit-previous').disabled = $('audit-next').disabled = true;
    }
  }
  function auditAction(action) {
    const style = {insert:'healthy',update:'configured',delete:'error',started:'manual'}[action] || 'manual';
    const title = {insert:'Created',update:'Updated',delete:'Deleted',started:'Logging started'}[action] || action;
    return `<span class="badge ${style}">${esc(title)}</span>`;
  }
  function reviewAudit(event) {
    selectedAudit = event;
    $('audit-detail-title').textContent = event.label;
    $('audit-detail-reason').textContent=event.reason?`Reason: ${event.reason}`:'';
    $('audit-detail-meta').textContent = `${auditStamp(event.occurred_at)} · ${event.actor_name} · ${event.source} · ${event.action}`;
    $('audit-credentials-note').hidden = !event.credentials_changed;
    const before = event.before || {}, after = event.after || {};
    const fields = [...new Set([...Object.keys(before),...Object.keys(after)])];
    const value = item => item === null || item === undefined ? '—' : typeof item === 'object' ? JSON.stringify(item) : String(item);
    const titles = {amount:'Amount (PHP)',total:'Total (PHP)',bill_id:'Bill ID',paid_date:'Payment date',due_date:'Due date',recorded_by_id:'Recorded by (user ID)',responsible_id:'Primary payer (user ID)',created_by_id:'Created by (user ID)',is_active:'Account active',is_staff:'Staff access',is_superuser:'Administrator access'};
    $('audit-diff-rows').innerHTML = fields.map(field => `<tr class="${JSON.stringify(before[field]) !== JSON.stringify(after[field]) ? 'field-changed' : ''}"><th scope="row">${esc(titles[field] || field.replace(/_/g,' '))}</th><td>${esc(value(before[field]))}</td><td>${esc(value(after[field]))}</td></tr>`).join('');
    $('audit-detail-reference').textContent = `Transaction ${event.transaction_id} · ${event.entity_table} #${event.entity_id} · Event #${event.id}`;
    $('audit-dialog').showModal();
  }
  async function health() {
    if (!connected || pendingRefresh) return;
    try { const result = await api('/api/status/'); $('status-checked').textContent = `Last checked ${stamp(result.checked_at)}`; $('health-cards').innerHTML = result.checks.map(check => `<article class="card health-card"><div class="card-heading"><h2>${esc(check.name)}</h2>${badge(check.state)}</div><p>${esc(check.detail)}</p></article>`).join(''); }
    catch (exception) { error(exception.message); $('status-checked').textContent = 'The latest status check did not complete.'; $('health-cards').innerHTML = '<article class="card"><h2>Status unavailable</h2><p class="muted">Previous component results are no longer shown. Check your home connection and try again.</p></article>'; }
  }
  async function probe() {
    if (checking || signingOut || !data) return;
    checking = true;
    try {
      const response = await fetchTimed('/api/reachable/');
      if (response.status === 401) { await expired(); return; }
      if (!response.ok) throw new Error();
      const result = await response.json();
      if(signingOut) return;
      if (result.user_id !== data.user.id) { await purge(); location.reload(); return; }
      if (!connected || result.settings_version !== data.settings_version) { pendingRefresh = true; setConnection(true); $('notice-title').textContent = 'Updates are available from your family server.'; $('notice-copy').textContent = 'Update this view to receive the latest shared settings and bills before making changes.'; }
    } catch (_) { setConnection(false); }
    finally { checking = false; }
  }
  function openDialog(id) {
    if (!connected || pendingRefresh) { toast('Connect to home and update your bills first.'); return; }
    const dialog = $(id); dialog.querySelector('.dialog-error').hidden = true; dialog.showModal();
  }
  function formReview(form, value) {
    const rows = [];
    for (const field of form.elements) {
      if (!field.name || field.type === 'hidden' || ['button','submit'].includes(field.type)) continue;
      const name = field.closest('label')?.childNodes[0]?.textContent.trim() || field.labels?.[0]?.textContent.trim() || field.name.replaceAll('_',' ');
      const display = field.type === 'checkbox' ? (field.checked ? 'Yes' : 'No') : field.tagName === 'SELECT' ? field.selectedOptions[0]?.textContent : field.value || '—';
      rows.push([name, display]);
    }
    if(form.id === 'payment-form') {
      const bill = data.bills.find(b=>b.id===Number(value.bill_id));
      rows.unshift(['Bill',bill.title],['Current unpaid balance',currency(bill.balance)]);
      rows.push(['Remaining after payment',currency((Math.round(Number(bill.balance)*100)-Math.round(Number(value.amount)*100))/100)]);
    }
    if(form.id === 'loan-form') {
      const schedule=FBTFilters.loanSchedule(value.total,Number(value.installments),value.first_due);
      rows.push(['Monthly due day',`Day ${Number(value.first_due.slice(-2))}; last valid day in shorter months`],...schedule.map(part=>[`Installment ${part.number}`,`${dateLabel(part.due_date)} · ${currency(part.amount)}`]));
    }
    if(form.id === 'server-form') for(const key of ['family_name','nas_name','server_url']) rows.push([`Previously: ${key.replaceAll('_',' ')}`,data[key] || 'Not set']);
    if(form.id === 'payer-form') rows.unshift(['Current assignment',$('payer-current').textContent]);
    return {title:'Review before saving', rows, action:({'payment-form':'Confirm payment','bill-form':'Confirm new bill','loan-form':'Confirm loan schedule','server-form':'Confirm workspace changes','payer-form':'Confirm payer change'})[form.id]};
  }
  function submitForm(formId, endpoint, transform = value => value) {
    const form = $(formId);
    form.addEventListener('reset',()=> { delete form.dataset.requestKey; });
    form.addEventListener('input',()=> { delete form.dataset.requestKey; });
    form.addEventListener('submit', async event => {
      event.preventDefault(); if(form.dataset.busy) return;
      const button = form.querySelector('button[type="submit"], button.primary'), message = form.querySelector('.dialog-error');
      form.dataset.busy = 'yes'; button.disabled = true;
      try {
        if(!connected || pendingRefresh) throw new Error('Reconnect and refresh before reviewing changes.');
        const value = transform(Object.fromEntries(new FormData(form)));
        if(formId === 'payment-form') value.expected_version = data.bills.find(b=>b.id===Number(value.bill_id)).version;
        if(formId === 'server-form') value.expected_version = data.settings_version;
        if(['bill-form','loan-form'].includes(formId)) value.request_key = form.dataset.requestKey ||= crypto.randomUUID();
        const draft = JSON.stringify(Object.fromEntries(new FormData(form)));
        if(!await FBTReview(formReview(form,value))) return;
        if(draft !== JSON.stringify(Object.fromEntries(new FormData(form)))) throw new Error('The draft changed. Review again.');
        await api(typeof endpoint === 'function' ? endpoint(value) : endpoint, {method:'POST', body:JSON.stringify(value)});
        form.closest('dialog')?.close(); form.reset(); await loadSnapshot(); toast('Saved for your family.');
      } catch (exception) { if(message) { message.textContent = exception.message; message.hidden = false; } else error(exception.message); }
      finally { delete form.dataset.busy; button.disabled = !connected || pendingRefresh; }
    });
  }
  function startBillEntry(type=null) {
    if(!connected || pendingRefresh) { toast('Connect to home and update your bills first.'); return; }
    for(const id of ['bill-form','loan-form']) {
      const form=$(id); form.reset(); form.elements.responsible.value=data.user.id;
      form.elements[id==='bill-form'?'due_date':'first_due'].value=today();
    }
    updateLoanPreview();
    openDialog(type==='loan'?'loan-dialog':'bill-type-dialog');
  }
  document.querySelectorAll('.add-bill').forEach(button=>button.addEventListener('click',()=>startBillEntry()));
  $('add-loan').addEventListener('click',()=>startBillEntry('loan'));
  document.querySelectorAll('[data-bill-type]').forEach(button=>button.addEventListener('click',()=> {
    $('bill-type-dialog').close(); openDialog(button.dataset.billType==='loan'?'loan-dialog':'bill-dialog');
  }));
  document.querySelectorAll('.back-to-bill-type').forEach(button=>button.addEventListener('click',()=> {
    button.closest('dialog').close(); openDialog('bill-type-dialog');
  }));
  function updateLoanPreview() {
    try {
      const form=$('loan-form'), parts=FBTFilters.loanSchedule(form.elements.total.value,Number(form.elements.installments.value),form.elements.first_due.value);
      $('loan-preview-rows').innerHTML=parts.map(p=>`<tr><td>${p.number}</td><td>${dateLabel(p.due_date)}</td><td>${currency(p.amount)}</td></tr>`).join('');
      $('loan-preview-summary').textContent=`${parts.length} installments · ${currency(form.elements.total.value)} agreed total. The final installment includes any rounding difference.`;
      $('loan-preview').hidden=false;
    } catch(_) { $('loan-preview').hidden=true; $('loan-preview-rows').replaceChildren(); }
  }
  $('loan-form').addEventListener('input',updateLoanPreview);
  $('loan-form').addEventListener('change',updateLoanPreview);
  document.querySelectorAll('.close-dialog').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
  document.addEventListener('click', event => {
    const auditReview = event.target.closest('.audit-review');
    if (auditReview) {
      const entry = auditEvents.find(item => item.id === Number(auditReview.dataset.event));
      if (entry) reviewAudit(entry);
    }
    const auditGroup = event.target.closest('.audit-transaction');
    if (auditGroup) { auditTransaction = auditGroup.dataset.reference; auditPageNumber = 1; loadAudit(); }
    const detail = event.target.closest('.bill-detail');
    if (detail) {
      const bill = data.bills.find(b => b.id === Number(detail.dataset.id));
      $('detail-dialog').close();
      $('detail-title').textContent = bill.title;
      const parentLoan=data.loans.find(loan=>loan.id===bill.loan_id);
      $('detail-notes').textContent = (parentLoan ? `Loan: ${parentLoan.title}. ` : '') + (bill.notes || 'No notes added.');
      $('detail-summary').textContent = `${currency(bill.amount)} original · ${currency(bill.balance)} unpaid · Due ${dateLabel(bill.due_date)} · Primary payer: ${bill.responsible}`;
      $('detail-payments').innerHTML = bill.payments.map(p => `<div class="activity"><div><strong>${currency(p.amount)}</strong><p>${dateLabel(p.paid_date)} · Recorded by ${esc(p.recorded_by)}</p>${FBTCorrections.controls('payment',p.id)}</div></div>`).join('') || '<p class="small muted">No payments recorded yet.</p>';
      showDetailActions(bill);
      $('detail-dialog').showModal();
    }
    const payment = event.target.closest('.pay-bill');
    if (payment) {
      const bill = data.bills.find(b => b.id === Number(payment.dataset.id)), form = $('payment-form');
      form.reset(); form.elements.bill_id.value = bill.id; form.elements.amount.value = bill.balance; form.elements.amount.max = bill.balance; form.elements.paid_date.value = today(); form.elements.paid_date.max = today(); form.elements.request_key.value = crypto.randomUUID(); $('payment-title').textContent = `${bill.title} · ${currency(bill.balance)} unpaid`; openDialog('payment-dialog');
    }
    const loan = event.target.closest('.loan-view'); if (loan) showLoanDetails(Number(loan.dataset.loan));
  });
  submitForm('bill-form', '/api/bills/', value => ({...value,repeat_monthly: $('bill-form').elements.repeat_monthly.checked}));
  submitForm('loan-form', '/api/loans/');
  submitForm('payment-form', value => `/api/bills/${value.bill_id}/payments/`);
  submitForm('server-form', '/api/settings/');
  submitForm('payer-form', value => `/api/bills/${value.bill_id}/payer/`);
  $('search').addEventListener('input',renderBills); $('status-filter').addEventListener('change',renderBills);
  $('loan-search').addEventListener('input',renderLoans);
  $('loan-status-filter').addEventListener('change',renderLoans);
  $('refresh-loans').addEventListener('click',()=>loadSnapshot());
  $('refresh-history').addEventListener('click',()=>loadSnapshot());
  $('check-status').addEventListener('click',health);
  $('audit-refresh').addEventListener('click',loadAudit);
  function updateAuditFilters() {
    clearTimeout(auditFilterTimer);
    auditRequest += 1; // Ignore responses for the previous filter while typing.
    auditPageNumber = 1;
    $('audit-previous').disabled = $('audit-next').disabled = true;
    $('audit-summary').textContent = 'Updating results…';
    auditFilterTimer = setTimeout(loadAudit,250);
  }
  $('audit-filters').addEventListener('input',updateAuditFilters);
  $('audit-filters').addEventListener('change',updateAuditFilters);
  $('audit-filters').addEventListener('submit',event => { event.preventDefault(); auditPageNumber = 1; loadAudit(); });
  $('audit-reset').addEventListener('click',() => { $('audit-filters').reset(); auditTransaction = ''; auditPageNumber = 1; loadAudit(); });
  $('audit-previous').addEventListener('click',() => { auditPageNumber -= 1; loadAudit(); });
  $('audit-next').addEventListener('click',() => { auditPageNumber += 1; loadAudit(); });
  $('audit-clear-transaction').addEventListener('click',() => { auditTransaction = ''; auditPageNumber = 1; loadAudit(); });
  $('audit-related').addEventListener('click',() => { if(selectedAudit) { auditTransaction = selectedAudit.transaction_id; auditPageNumber = 1; $('audit-dialog').close(); loadAudit(); } });
  $('refresh-online').addEventListener('click',() => loadSnapshot());
  $('refresh-snapshot').addEventListener('click',async () => { $('refresh-snapshot').disabled = true; await loadSnapshot(); $('refresh-snapshot').disabled = false; });
  $('enable-offline').addEventListener('click',async () => {
    if (!connected || pendingRefresh || !data) { toast('Connect and update your bills before saving an offline copy.'); return; }
    if (!isSecureContext || !('serviceWorker' in navigator)) { error('Offline installation needs a trusted HTTPS address, or localhost for development.'); return; }
    try { await navigator.serviceWorker.ready; await FBTOffline.write(data); localStorage.setItem('fbt-offline-enabled','yes'); localStorage.setItem('fbt-offline-owner',String(data.user.id)); offlineEnabled = true; render(); toast('A read-only copy is saved on this device.'); }
    catch(exception) { error(exception.message); }
  });
  $('clear-offline').addEventListener('click',async () => { try { await purge(); if (!connected) { data = null; location.reload(); } else { render(); toast('The saved copy has been removed from this device.'); } } catch(exception) { error(exception.message); } });
  async function signOut() {
    if(signingOut) return;
    signingOut = true;
    data = null;
    document.querySelectorAll('.page').forEach(page => page.hidden = true);
    document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());
    localStorage.setItem('fbt-logout-pending','yes');
    try {
      await purge();
      document.querySelectorAll('.page').forEach(page => page.hidden = true);
      const response = await fetchTimed('/logout/', {method:'POST',headers:{'X-CSRFToken':csrf()}});
      if (!response.ok) throw new Error();
      localStorage.removeItem('fbt-logout-pending'); location.replace('/login/');
    } catch(_) { $('loading').hidden = false; $('loading').innerHTML = '<h2>Saved records removed.</h2><p>Reconnect to your home network and reload to finish signing out of the server. The existing server session may remain active until then.</p>'; }
  }
  let confirmingSignOut = false;
  $('logout').addEventListener('click',async () => {
    if(signingOut || confirmingSignOut) return;
    confirmingSignOut = true;
    try {
      const accepted = await FBTReview({title:'Confirm Sign out', action:'Sign out', cancelAction:'Cancel', variant:'signout'});
      if(accepted && !signingOut) await signOut();
    } finally { confirmingSignOut = false; }
  });
  function pushSupported() { if(!isSecureContext || !('PushManager' in window) || !('serviceWorker' in navigator)) throw new Error('Notifications need supported browser features and trusted HTTPS. On iPhone, first open the Home Screen app.'); }
  $('enable-push').addEventListener('click',async () => {
    try {
      pushSupported(); if(!data.vapid_public_key) throw new Error('Ask the administrator to add VAPID keys first.');
      const permission = await Notification.requestPermission(); if(permission !== 'granted') throw new Error('Notifications are not permitted. You can enable them in your browser settings.');
      const registration = await navigator.serviceWorker.ready;
      const raw = atob(data.vapid_public_key.replace(/-/g,'+').replace(/_/g,'/'));
      const subscription = await registration.pushManager.getSubscription() || await registration.pushManager.subscribe({userVisibleOnly:true, applicationServerKey:Uint8Array.from(raw,c => c.charCodeAt(0))});
      await api('/api/push/',{method:'POST',body:JSON.stringify(subscription.toJSON())}); toast('This device is registered. Send a test to check delivery.');
    } catch(exception) { error(exception.message); }
  });
  $('disable-push').addEventListener('click',async () => {
    try { pushSupported(); const registration = await navigator.serviceWorker.ready; const subscription = await registration.pushManager.getSubscription(); if(subscription) { await api('/api/push/',{method:'DELETE',body:JSON.stringify({endpoint:subscription.endpoint})}); await subscription.unsubscribe(); } toast('Notifications disabled on this device.'); }
    catch(exception) { error(exception.message); }
  });
  $('test-push').addEventListener('click',async () => { try { const result = await api('/api/push/test/',{method:'POST',body:'{}'}); toast(result.note); } catch(exception) { error(exception.message); } });
  window.addEventListener('hashchange',route);
  window.addEventListener('online',probe);
  window.addEventListener('offline',() => setConnection(false));
  window.addEventListener('storage',event => { if(event.key === 'fbt-cleared') { signingOut = true; data = null; document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close()); document.querySelectorAll('.page').forEach(page=>page.hidden=true); location.reload(); } });
  async function init() {
    if ('serviceWorker' in navigator && isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => error('Offline installation is unavailable. Online viewing still works.'));
    if(localStorage.getItem('fbt-logout-pending')) {
      try { const response = await fetchTimed('/logout/',{method:'POST',headers:{'X-CSRFToken':csrf()}}); if(!response.ok) throw new Error(); localStorage.removeItem('fbt-logout-pending'); location.replace('/login/'); }
      catch(_) { $('loading').innerHTML = '<h2>Sign-out is waiting for home.</h2><p>Reconnect and reload to end your server session. No saved bills are available on this device.</p>'; }
      return;
    }
    await loadSnapshot(true); setInterval(probe,30000);
  }
  init();
})();
