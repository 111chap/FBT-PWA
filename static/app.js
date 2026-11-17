/* No third-party scripts. Personal snapshots live only in opt-in IndexedDB storage. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  let data = null, connected = false, pendingRefresh = false, checking = false, signingOut = false;
  let offlineEnabled = localStorage.getItem('fbt-offline-enabled') === 'yes';
  const currency = value => new Intl.NumberFormat('en-PH', {style:'currency', currency:'PHP'}).format(Number(value));
  const dateLabel = value => new Date(value + 'T12:00:00').toLocaleDateString('en-PH', {month:'short', day:'numeric', year:'numeric'});
  const stamp = value => new Date(value).toLocaleString('en-PH', {dateStyle:'medium', timeStyle:'short'});
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
    try {
      const response = await fetchTimed('/api/snapshot/');
      if (response.status === 401) { await expired(); return; }
      if (!response.ok) throw new Error('Server temporarily unavailable.');
      const value = await response.json();
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
    $('connection-badge').className = 'badge ' + (value ? 'healthy' : 'warning');
    $('connection-badge').textContent = value ? '● Home server connected' : '○ Offline · read-only';
    $('rail-status').textContent = value ? 'Connected to home' : 'Home server unavailable';
    $('home-copy').textContent = value ? 'Your home server is reachable. Your family is connected.' : 'You are viewing a saved copy. Updates need a connection to your home server.';
    $('rail-dot').className = value ? 'connected-dot' : 'offline-dot';
    document.querySelectorAll('[data-online]').forEach(button => button.disabled = !value || pendingRefresh);
    $('server-form').querySelectorAll('input,button').forEach(input => input.disabled = !value || pendingRefresh || !data?.user.admin);
    $('export-link').hidden = !value;
    const showNotice = !value || pendingRefresh;
    $('notice').hidden = !showNotice;
    $('notice-title').textContent = pendingRefresh ? 'Welcome back. New information may be available.' : 'A copy for when you are away.';
    $('notice-copy').textContent = pendingRefresh ? 'Your home server is reachable again. Update this view before recording payments.' : data ? `Saved for ${data.user.name} on ${stamp(data.synced_at)}. Payments and amounts may have changed. Join your home network to update.` : 'Connect to your home server to load your family records.';
    $('refresh-snapshot').hidden = !pendingRefresh;
    if (!value) {
      $('status-checked').textContent = 'Live status unavailable while the home server is out of reach.';
      $('health-cards').innerHTML = '<article class="card"><h2>Connection unavailable</h2><p class="muted">Component status cannot be checked offline. Reconnect, update your bills, then run a fresh status check.</p></article>';
    }
  }
  function row(bill) {
    return `<tr><td><button class="bill-detail" data-id="${bill.id}">${esc(bill.title)}</button><span class="small muted">${esc(bill.category)} · ${esc(bill.responsible)}${bill.recurring ? ' · Monthly' : ''}</span></td><td>${dateLabel(bill.due_date)}</td><td>${currency(bill.balance)}</td><td>${badge(bill.status)}</td><td>${Number(bill.balance) > 0 ? `<button class="button secondary pay-bill" data-id="${bill.id}" data-online ${!connected || pendingRefresh ? 'disabled' : ''}>Record payment</button>` : '✓ Complete'}</td></tr>`;
  }
  function renderBills() {
    if (!data) return;
    const search = $('search').value.toLowerCase();
    const filter = $('status-filter').value;
    const bills = data.bills.filter(b => `${b.title} ${b.category} ${b.responsible}`.toLowerCase().includes(search) && (filter === 'all' || (filter === 'unpaid' ? b.status !== 'paid' : b.status === filter)));
    $('bill-rows').innerHTML = bills.map(row).join('');
    $('bills-empty').hidden = bills.length > 0;
  }
  function render() {
    if (!data) return;
    $('loading').hidden = true;
    $('family-name').textContent = data.family_name.toUpperCase();
    $('today-label').textContent = new Date().toLocaleDateString('en-PH', {weekday:'long', month:'long', day:'numeric', year:'numeric'});
    $('user-avatar').textContent = data.user.name.slice(0,2).toUpperCase();
    $('user-avatar').title = data.user.name;
    $('home-name').textContent = data.nas_name;
    $('last-synced').textContent = `Last updated ${stamp(data.synced_at)}`;
    const unpaid = data.bills.filter(b => Number(b.balance) > 0);
    const overdue = unpaid.filter(b => b.status === 'overdue');
    const weekEnd = new Date(data.today + 'T12:00:00'); weekEnd.setDate(weekEnd.getDate()+7);
    const coming = unpaid.filter(b => b.due_date >= data.today && new Date(b.due_date + 'T12:00:00') <= weekEnd);
    const paid = data.bills.filter(b => b.status === 'paid');
    const sum = bills => bills.reduce((total,b) => total + Math.round(Number(b.balance)*100),0)/100;
    $('stats').innerHTML = [
      ['Total unpaid',currency(sum(unpaid)),`${unpaid.length} bills to take care of`,''],
      ['Due in the next 7 days',currency(sum(coming)),`${coming.length} upcoming payments`,''],
      ['Overdue',currency(sum(overdue)),`${overdue.length} bills need a look`,'warm'],
      ['Paid bills',paid.length,'One less thing on your list','']
    ].map(([label,value,detail,cls]) => `<article class="stat ${cls}"><p class="stat-label">${label}</p><div class="stat-value">${value}</div><p>${detail}</p></article>`).join('');
    $('upcoming-list').innerHTML = unpaid.slice(0,5).map(b => `<div class="bill-item"><span class="category-icon" aria-hidden="true">${b.loan_id ? '↗' : '▤'}</span><div class="bill-info"><strong>${esc(b.title)}</strong><p>${dateLabel(b.due_date)} · ${esc(b.responsible)}</p></div><div class="bill-amount"><strong>${currency(b.balance)}</strong><div>${badge(b.status)}</div></div></div>`).join('') || '<div class="empty"><h3>Nothing on the list just yet.</h3><p>Add your first bill, or enjoy being all caught up.</p></div>';
    const activity = data.bills.flatMap(b => b.payments.map(p => ({...p, title:b.title}))).sort((a,b) => b.paid_date.localeCompare(a.paid_date)).slice(0,4);
    $('activity-list').innerHTML = activity.map(p => `<div class="activity"><div><strong>${esc(p.title)}</strong><p>Recorded by ${esc(p.recorded_by)} · ${dateLabel(p.paid_date)}</p></div><strong>${currency(p.amount)}</strong></div>`).join('') || '<p class="small muted">Payments recorded by your family will appear here.</p>';
    $('loan-cards').innerHTML = data.loans.map(loan => {
      const bills = data.bills.filter(b => b.loan_id === loan.id), remaining = sum(bills), paidCount = bills.filter(b => b.status === 'paid').length;
      return `<article class="card loan-card"><p class="eyebrow">MONTHLY REPAYMENTS</p><h2>${esc(loan.title)}</h2><div class="loan-total">${currency(remaining)}</div><p class="small muted">remaining of ${currency(loan.total)}</p><progress max="${loan.total}" value="${(Number(loan.total)-remaining).toFixed(2)}" aria-label="Loan repayment progress"></progress><p class="small muted">${paidCount} of ${loan.installments} installments paid</p><a class="button secondary loan-view" href="#bills" data-title="${esc(loan.title)}">Review installments →</a></article>`;
    }).join('') || '<article class="card empty"><h2>A plan for every repayment.</h2><p>Add a loan to create its monthly installment schedule.</p></article>';
    document.querySelectorAll('select.members').forEach(select => { const previous = select.value; select.innerHTML = data.members.map(member => `<option value="${member.id}">${esc(member.username)}</option>`).join(''); select.value = previous || data.user.id; });
    for (const name of ['family_name','nas_name','server_url']) $('server-form').elements[name].value = data[name] || '';
    $('server-form').querySelectorAll('input,button').forEach(input => input.disabled = !data.user.admin || !connected || pendingRefresh);
    $('admin-note').textContent = data.user.admin ? 'Administrator settings. Saving does not change deployment configuration.' : 'Ask your family administrator to change these settings.';
    $('admin-link').hidden = !data.user.admin;
    $('offline-setting').textContent = offlineEnabled ? `Enabled on this device. Saved copies expire after seven days. Last fetched ${stamp(data.synced_at)}.` : 'Offline viewing is off. Enable it on a trusted device while connected.';
    renderBills(); route();
  }
  function route() {
    const name = ['overview','bills','loans','system','setup'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
    document.querySelectorAll('.page').forEach(section => section.hidden = !data || section.id !== name);
    document.querySelectorAll('[data-nav]').forEach(link => { link.classList.toggle('active',link.dataset.nav === name); if(link.dataset.nav === name) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current'); });
    if (name === 'system' && connected && !pendingRefresh) health();
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
      if (result.user_id !== data.user.id) { await purge(); location.reload(); return; }
      if (!connected) { pendingRefresh = true; setConnection(true); }
    } catch (_) { setConnection(false); }
    finally { checking = false; }
  }
  function openDialog(id) {
    if (!connected || pendingRefresh) { toast('Connect to home and update your bills first.'); return; }
    const dialog = $(id); dialog.querySelector('.dialog-error').hidden = true; dialog.showModal();
  }
  function submitForm(formId, endpoint, transform = value => value) {
    $(formId).addEventListener('submit', async event => {
      event.preventDefault(); const form = event.currentTarget, button = form.querySelector('button[type="submit"], button.primary'), message = form.querySelector('.dialog-error');
      button.disabled = true;
      try {
        const value = transform(Object.fromEntries(new FormData(form)));
        await api(typeof endpoint === 'function' ? endpoint(value) : endpoint, {method:'POST', body:JSON.stringify(value)});
        form.closest('dialog')?.close(); form.reset(); await loadSnapshot(); toast('Saved for your family.');
      } catch (exception) { if(message) { message.textContent = exception.message; message.hidden = false; } else error(exception.message); }
      finally { button.disabled = !connected || pendingRefresh; }
    });
  }
  document.querySelectorAll('.add-bill').forEach(button => button.addEventListener('click', () => { $('bill-form').reset(); $('bill-form').elements.due_date.value = today(); openDialog('bill-dialog'); }));
  $('add-loan').addEventListener('click', () => { $('loan-form').reset(); $('loan-form').elements.first_due.value = today(); openDialog('loan-dialog'); });
  document.querySelectorAll('.close-dialog').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
  document.addEventListener('click', event => {
    const detail = event.target.closest('.bill-detail');
    if (detail) {
      const bill = data.bills.find(b => b.id === Number(detail.dataset.id));
      $('detail-title').textContent = bill.title;
      $('detail-notes').textContent = bill.notes || 'No notes added.';
      $('detail-summary').textContent = `${currency(bill.amount)} total · ${currency(bill.balance)} unpaid · Due ${dateLabel(bill.due_date)} · ${bill.responsible}`;
      $('detail-payments').innerHTML = bill.payments.map(p => `<div class="activity"><div><strong>${currency(p.amount)}</strong><p>${dateLabel(p.paid_date)} · Recorded by ${esc(p.recorded_by)}</p></div></div>`).join('') || '<p class="small muted">No payments recorded yet.</p>';
      $('detail-dialog').showModal();
    }
    const payment = event.target.closest('.pay-bill');
    if (payment) {
      const bill = data.bills.find(b => b.id === Number(payment.dataset.id)), form = $('payment-form');
      form.reset(); form.elements.bill_id.value = bill.id; form.elements.amount.value = bill.balance; form.elements.amount.max = bill.balance; form.elements.paid_date.value = today(); form.elements.paid_date.max = today(); form.elements.request_key.value = crypto.randomUUID(); $('payment-title').textContent = `${bill.title} · ${currency(bill.balance)} unpaid`; openDialog('payment-dialog');
    }
    const loan = event.target.closest('.loan-view'); if (loan) { $('search').value = loan.dataset.title; renderBills(); }
  });
  submitForm('bill-form', '/api/bills/', value => ({...value,repeat_monthly: $('bill-form').elements.repeat_monthly.checked}));
  submitForm('loan-form', '/api/loans/');
  submitForm('payment-form', value => `/api/bills/${value.bill_id}/payments/`);
  $('server-form').addEventListener('submit', async event => { event.preventDefault(); try { const result = await api('/api/settings/',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(event.target)))}); await loadSnapshot(); toast(result.note); } catch(exception) { error(exception.message); } });
  $('search').addEventListener('input',renderBills); $('status-filter').addEventListener('change',renderBills);
  $('check-status').addEventListener('click',health);
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
    signingOut = true;
    try {
      await purge(); localStorage.setItem('fbt-logout-pending','yes'); data = null;
      document.querySelectorAll('.page').forEach(page => page.hidden = true);
      const response = await fetchTimed('/logout/', {method:'POST',headers:{'X-CSRFToken':csrf()}});
      if (!response.ok) throw new Error();
      localStorage.removeItem('fbt-logout-pending'); location.replace('/login/');
    } catch(_) { $('loading').hidden = false; $('loading').innerHTML = '<h2>Saved records removed.</h2><p>Reconnect to your home network and reload to finish signing out of the server. The existing server session may remain active until then.</p>'; }
  }
  $('logout').addEventListener('click',signOut);
  $('logout-mobile').addEventListener('click',signOut);
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
  window.addEventListener('storage',event => { if(event.key === 'fbt-cleared') { data = null; location.reload(); } });
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
