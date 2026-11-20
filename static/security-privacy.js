/* Credentials exist only in these forms until submission; never in saved snapshots. */
(() => {
  const $=id=>document.getElementById(id);
  if('ResizeObserver' in window)new ResizeObserver(()=>document.documentElement.style.setProperty('--emergency-height',`${$('emergency-banner').getBoundingClientRect().height}px`)).observe($('emergency-banner'));
  let config, snapshot, online=false, expiryTimer, accessPage=1;
  const fail=(id,error)=>{$(id).textContent=error.message;};
  window.FBTSecurity={
    configure(value){config=value;},
    update(value,connected){
      snapshot=value;online=connected;
      $('emergency-open').hidden=!value.user.admin;
      $('emergency-banner').hidden=!value.emergency;
      clearTimeout(expiryTimer);
      if(value.emergency){
        $('emergency-banner-copy').textContent=`Reason: ${value.emergency_reason}. Expires ${new Date(value.emergency_expires_at).toLocaleTimeString()}.`;
        expiryTimer=setTimeout(()=>location.reload(),Math.max(0,Date.parse(value.emergency_expires_at)-Date.now()));
      }
    },
    sharingControl(kind,record){
      return !snapshot?.emergency && record.owner_id===snapshot?.user.id ? `<button type="button" class="button secondary sharing-control" data-kind="${kind}" data-record="${record.id}" data-online>Change sharing</button>` : '';
    }
  };
  $('pin-settings-open').addEventListener('click',()=>{if(!online||snapshot?.emergency)return;$('pin-settings-form').reset();$('pin-settings-error').textContent='';pinFields();$('pin-dialog').showModal();});
  function pinFields(){const enabled=$('pin-settings-form').elements.action.value==='enable';$('pin-new-fields').hidden=!enabled;for(const field of $('pin-new-fields').querySelectorAll('input')){field.required=enabled;field.disabled=!enabled;}}
  $('pin-settings-form').elements.action.addEventListener('change',pinFields);
  $('pin-settings-form').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget;if(form.dataset.busy)return;
    const action=form.elements.action.value;
    $('pin-dialog').close();
    if(!await FBTReview({title:'Confirm PIN settings',rows:[['Action',form.elements.action.selectedOptions[0].textContent]],action:'Confirm changes',note:'Your password remains unchanged. Credential values are never shown in history.'})){$('pin-dialog').showModal();return;}
    form.dataset.busy='yes';
    try{const result=await config.request('/api/security/pin/',{method:'POST',body:JSON.stringify({...Object.fromEntries(new FormData(form)),confirmed:true})});if(!result.ok)throw new Error(result.error);form.reset();config.notify(action==='enable'||action==='enroll'?'This device is enrolled for PIN sign-in for 30 days.':'PIN device access updated.');}
    catch(error){fail('pin-settings-error',error);$('pin-dialog').showModal();}
    finally{delete form.dataset.busy;form.elements.password.value='';form.elements.pin.value='';form.elements.pin_confirmation.value='';}
  });
  $('emergency-open').addEventListener('click',()=>{if(!online||snapshot?.emergency)return;$('emergency-form').reset();$('emergency-error').textContent='';$('emergency-dialog').showModal();});
  $('emergency-form').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget;if(form.dataset.busy)return;
    $('emergency-dialog').close();
    if(!await FBTReview({title:'Confirm emergency access',rows:[['Reason',form.elements.reason.value]],action:'Enable for 10 minutes',note:'Read-only access is logged for affected owners and cannot be saved offline.'})){$('emergency-dialog').showModal();return;}
    form.dataset.busy='yes';
    try{const result=await config.request('/api/privacy/emergency/',{method:'POST',body:JSON.stringify({...Object.fromEntries(new FormData(form)),confirmed:true})});if(!result.ok)throw new Error(result.error);form.reset();await config.emergency();}
    catch(error){fail('emergency-error',error);$('emergency-dialog').showModal();}
    finally{form.elements.password.value='';delete form.dataset.busy;}
  });
  $('emergency-exit').addEventListener('click',async()=>{try{await config.request('/api/privacy/emergency/',{method:'POST',body:JSON.stringify({action:'exit'})});await config.refresh();}catch(error){config.notify(error.message);}});
  async function showAccessHistory(page=1){
    try{const result=await config.request(`/api/privacy/access/?page=${page}`);const list=$('privacy-history-list');list.replaceChildren();for(const entry of result.events){const p=document.createElement('p');p.textContent=`${new Date(entry.at).toLocaleString()} · ${entry.administrator} · ${entry.action}${entry.record_type?` ${entry.record_type} #${entry.record_id}`:''} · Reason: ${entry.reason}`;list.append(p);}if(!result.events.length)list.textContent='No emergency access recorded.';accessPage=result.page;$('privacy-history-page').textContent=`Page ${result.page} of ${result.pages}`;$('privacy-history-previous').disabled=result.page<=1;$('privacy-history-next').disabled=result.page>=result.pages;if(!$('privacy-history-dialog').open)$('privacy-history-dialog').showModal();}catch(error){config.notify(error.message);}
  }
  $('privacy-history-open').addEventListener('click',()=>showAccessHistory());
  $('privacy-history-previous').addEventListener('click',()=>showAccessHistory(accessPage-1));
  $('privacy-history-next').addEventListener('click',()=>showAccessHistory(accessPage+1));
  document.addEventListener('click',async event=>{
    const button=event.target.closest('.sharing-control');if(!button||!online||snapshot?.emergency)return;
    const kind=button.dataset.kind,id=Number(button.dataset.record),record=(kind==='bill'?snapshot.bills:kind==='loan'?snapshot.loans:snapshot.recurrences).find(item=>item.id===id);
    if(!record)return;const target=record.visibility==='private'?'family':'private';
    // Review offers an explicit sharing confirmation; no ownership transfer.
    $('detail-dialog').close();
    const confirmed=await FBTReview({title:target==='family'?'Share this record with your family?':'Make this record private?',rows:[['Record',record.title],['Visibility',`${record.visibility} → ${target}`]],action:target==='family'?'Share with family':'Make private',note:target==='family'?'All members will see this record, its notes, and payment history.':'Earlier offline copies cannot be remotely erased. This also makes you the primary payer.'});
    if(!confirmed)return;
    try{await config.request('/api/privacy/visibility/',{method:'POST',body:JSON.stringify({kind,id,visibility:target,confirmed:true,reason:target==='family'?'Owner confirmed sharing with family':'Owner confirmed private visibility',expected_version:record.version})});await config.refresh();config.notify('Sharing updated. Other devices receive this change when refreshed.');}catch(error){config.notify(error.message);}
  });
})();
