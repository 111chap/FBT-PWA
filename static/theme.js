/* The family app starts in cream. A device-local choice is optional and offline-safe. */
(() => {
  let theme='light';
  try {if(localStorage.getItem('fbt-theme')==='dark')theme='dark';}catch(_){/* Private browsing can disable storage. */}
  document.documentElement.dataset.theme=theme;
  const chrome=()=>document.querySelectorAll('meta[name="theme-color"]').forEach(meta=>{meta.content=theme==='light'?'#FAF7F4':'#1E1C1A';});
  chrome();
  document.addEventListener('DOMContentLoaded',()=>{
    const button=document.getElementById('theme-toggle');
    const update=()=>{chrome();if(button){button.setAttribute('aria-label',theme==='light'?'Switch to dark mode':'Switch to light mode');button.firstElementChild.textContent=theme==='light'?'☾':'☀';}};
    update();
    button?.addEventListener('click',()=>{theme=theme==='light'?'dark':'light';document.documentElement.dataset.theme=theme;try{localStorage.setItem('fbt-theme',theme);}catch(_){}update();});
    const sidebar=document.querySelector('.sidebar'),menu=document.getElementById('workspace-toggle');
    const close=()=>{sidebar?.classList.remove('menu-open');menu?.setAttribute('aria-expanded','false');menu?.setAttribute('aria-label','Open workspace menu');};
    menu?.addEventListener('click',()=>{const open=sidebar.classList.toggle('menu-open');menu.setAttribute('aria-expanded',String(open));menu.setAttribute('aria-label',open?'Close workspace menu':'Open workspace menu');});
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&sidebar?.classList.contains('menu-open')){close();menu.focus();}});
    document.addEventListener('click',event=>{if(!sidebar?.contains(event.target)&&!menu?.contains(event.target))close();});
    sidebar?.querySelectorAll('a').forEach(link=>link.addEventListener('click',close));
    sidebar?.querySelector('.mobile-add')?.addEventListener('click',close);
    window.addEventListener('hashchange',close);
  });
})();
