/* Current-account display only. No profile writes or additional account API. */
(() => {
  const $=id=>document.getElementById(id);
  const button=$('profile-toggle'),dialog=$('profile-dialog');
  const header=document.querySelector('.topbar');
  if('ResizeObserver' in window)new ResizeObserver(()=>document.documentElement.style.setProperty('--header-height',`${header.getBoundingClientRect().height}px`)).observe(header);
  window.FBTProfile={update(snapshot,connected){
    const {user,family_name,synced_at}=snapshot;
    $('account-name').textContent=user.name;
    button.setAttribute('aria-label',`Profile for ${user.name}`);
    $('profile-name').textContent=user.name;
    $('profile-family').textContent=family_name;
    $('profile-role').textContent=user.admin?'Family administrator':'Family member';
    $('profile-status').textContent=connected?'Current account · Profile details are read-only.':`Saved account details · Offline, read-only · Updated ${new Date(synced_at).toLocaleString()}`;
    $('profile-admin').hidden=!user.admin;
    $('profile-admin').setAttribute('aria-disabled',String(!connected));
    if(connected)$('profile-admin').setAttribute('href','/admin/');else $('profile-admin').removeAttribute('href');
    button.disabled=false;
  }};
  button.addEventListener('click',()=>dialog.showModal());
  $('profile-signout').addEventListener('click',()=>{dialog.close();$('logout').click();});
  dialog.addEventListener('click',event=>{if(event.target===dialog){const bounds=dialog.getBoundingClientRect();if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)dialog.close();}});
})();
