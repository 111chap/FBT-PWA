/* Shared descriptions and private images. No financial writes while disconnected. */
(() => {
  const $=id=>document.getElementById(id),esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let config,data,online=false,qrTimer,qrVersion='',replacement=null;
  const csrf=()=>document.cookie.split('; ').find(c=>c.startsWith('csrftoken='))?.split('=')[1]||'';
  const canWrite=()=>online&&!data?.emergency;
  const message=(id,error)=>{$(id).textContent=error.message;};
  const resetImage=prefix=>{const form=prefix==='payment'?$('payment-form'):prefix==='replacement'?$('replacement-form'):$('qr-settings-form');form.querySelector('[name=receipt_id],[name=asset_id]').value='';$(prefix+'-preview').removeAttribute('src');$(prefix+'-preview').hidden=true;$(prefix+'-progress').hidden=true;$(prefix+'-upload-status').textContent='';};
  async function uploadImage(file,purpose,billId,prefix){
    if(!canWrite())throw new Error('Connect to home and exit emergency visibility before uploading.');
    const max=data.upload_limits?.bytes||8388608;
    if(!file||file.size>max)throw new Error(`Choose one JPEG, PNG or WebP image up to ${Math.round(max/1048576)} MB.`);
    const form=new FormData();form.append('image',file);form.append('purpose',purpose);if(billId)form.append('bill_id',billId);
    const progress=$(prefix+'-progress');progress.hidden=false;progress.value=0;$(prefix+'-upload-status').textContent='Uploading and validating image…';
    return new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest();xhr.open('POST','/api/media/upload/');xhr.withCredentials=true;xhr.timeout=60000;xhr.setRequestHeader('X-CSRFToken',csrf());
      xhr.upload.onprogress=event=>{if(event.lengthComputable)progress.value=Math.round(event.loaded/event.total*100);};
      xhr.onerror=xhr.ontimeout=()=>reject(new Error('Upload interrupted. No payment was recorded. Reconnect and select the image again.'));
      xhr.onload=()=>{let result;try{result=JSON.parse(xhr.responseText);}catch(_){reject(new Error('The upload could not be completed.'));return;}if(xhr.status<200||xhr.status>=300){reject(new Error(result.error||'Image upload failed.'));return;}progress.value=100;$(prefix+'-upload-status').textContent='Image validated. Ready for review.';resolve(result);};
      xhr.send(form);
    });
  }
  function wireUpload(formId,prefix,purpose,billId){
    const form=$(formId);let generation=0;
    form.addEventListener('reset',()=>{generation++;resetImage(prefix);});
    form.querySelector('input[type=file]').addEventListener('change',async event=>{
      const turn=++generation;resetImage(prefix);
      const button=form.querySelector('button.primary');button.disabled=true;
      try{const result=await uploadImage(event.target.files[0],purpose,billId(),prefix);if(turn!==generation)return;form.querySelector('[name=receipt_id],[name=asset_id]').value=result.id;$(prefix+'-preview').src=result.url;$(prefix+'-preview').hidden=false;}
      catch(error){if(turn===generation)$(prefix+'-upload-status').textContent=error.message;}
      finally{if(turn===generation)button.disabled=!canWrite();}
    });
  }
  window.FBTEnhancements={
    configure(value){config=value;},
    update(snapshot,connected,pending){
      data=snapshot;online=connected&&!pending;$('qr-settings-open').hidden=!data.user.admin;
      if(!online){for(const id of ['qr-dialog','evidence-dialog','replacement-dialog'])$(id).close();$('qr-image').removeAttribute('src');$('evidence-images').replaceChildren();}
    },
    notesText(bill,loan){return `${loan?`Loan: ${loan.title}\n\n`:''}${bill.loan_id?'Current loan description':bill.recurrence_id?'Current schedule description':'Description'}: ${bill.shared_description||(!bill.loan_id&&!bill.recurrence_id?bill.notes:'')||'None added.'}${bill.loan_id||bill.recurrence_id?`\n\n${bill.loan_id?'Installment':'Occurrence'} notes: ${bill.notes||'None added.'}`:''}`;},
    descriptionControl(kind,record){return record?.can_manage&&!data?.emergency?`<button type="button" class="button secondary description-edit" data-kind="${kind}" data-record="${record.id}" data-online>Edit description</button>`:'';},
    qrButton(){return '<button type="button" class="button secondary pay-qr" data-online>Pay using QR</button>';},
    evidenceControls(payment,bill){return `${payment.has_receipt?`<button type="button" class="button secondary view-evidence" data-payment="${payment.id}" data-online>View receipt</button>`:'<p class="hint">Legacy payment · receipt unavailable.</p>'}${bill.can_manage&&!data?.emergency?`<button type="button" class="button secondary replace-evidence" data-payment="${payment.id}" data-bill="${bill.id}" data-online>${payment.has_receipt?'Replace receipt':'Add receipt'}</button>`:''}`;}
  };
  wireUpload('payment-form','payment','receipt',()=>$('payment-form').elements.bill_id.value);
  wireUpload('replacement-form','replacement','receipt',()=>replacement?.billId);
  wireUpload('qr-settings-form','qr-settings','qr',()=>null);
  document.addEventListener('click',async event=>{
    const edit=event.target.closest('.description-edit');
    if(edit&&canWrite()){
      const kind=edit.dataset.kind,id=Number(edit.dataset.record),record=(kind==='loan'?data.loans:kind==='recurrence'?data.recurrences:data.bills).find(r=>r.id===id);
      if(!record?.can_manage)return;
      const form=$('description-form');form.reset();form.elements.kind.value=kind;form.elements.record_id.value=id;form.elements.expected_version.value=record.version;form.elements.description.value=kind==='bill'?record.notes:record.description||'';$('description-record').textContent=record.title;$('description-error').textContent='';$('detail-dialog').close();$('description-dialog').showModal();
    }
    if(event.target.closest('.pay-qr')&&online){$('qr-dialog').showModal();await showQR();}
    const evidence=event.target.closest('.view-evidence');if(evidence&&online)await showEvidence(Number(evidence.dataset.payment));
    const replace=event.target.closest('.replace-evidence');if(replace&&canWrite()){
      try{const result=await config.request(`/api/payments/${replace.dataset.payment}/evidence/`);replacement={paymentId:Number(replace.dataset.payment),billId:Number(replace.dataset.bill),version:result.version};$('replacement-form').reset();$('replacement-error').textContent='';$('detail-dialog').close();$('evidence-dialog').close();$('replacement-dialog').showModal();}catch(error){config.notify(error.message);}
    }
  });
  $('description-form').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget;if(!canWrite()||form.dataset.busy)return;
    const value=Object.fromEntries(new FormData(form));$('description-dialog').close();
    if(!await FBTReview({title:'Confirm description change',rows:[['Description',value.description||'Clear description'],['Reason',value.reason]],action:'Save description',note:'The current parent description appears across past and future entries. Amounts, schedules and installment notes stay unchanged.'})){$('description-dialog').showModal();return;}
    form.dataset.busy='yes';
    try{await config.request(`/api/descriptions/${value.kind}/${value.record_id}/`,{method:'POST',body:JSON.stringify({...value,confirmed:true,request_key:crypto.randomUUID()})});await config.refresh();config.notify('Description updated. The change is recorded in audit history.');}catch(error){message('description-error',error);$('description-dialog').showModal();}finally{delete form.dataset.busy;}
  });
  async function showQR(){
    clearTimeout(qrTimer);
    if(!online){$('qr-status').textContent='Connect to your home server to view the current QR.';$('qr-image').hidden=true;$('qr-download').hidden=true;return;}
    try{const result=await config.request('/api/payment-qr/');$('qr-status').textContent=result.configured?`Recipient configured by your administrator: ${result.recipient}. Verify the recipient in your payment app. This is not automatically the bill provider or primary payer.`:'No household QR is configured. Ask your administrator to upload and verify one.';$('qr-image').hidden=$('qr-download').hidden=!result.configured;if(result.configured&&$('qr-image').getAttribute('src')!==result.url){$('qr-image').src=result.url;}$('qr-download').href=result.url+'?download=1';}
    catch(error){$('qr-status').textContent='Current QR unavailable. Reconnect and reopen this window.';$('qr-image').hidden=$('qr-download').hidden=true;}
    if($('qr-dialog').open)qrTimer=setTimeout(showQR,15000);
  }
  $('qr-image').addEventListener('error',()=>{$('qr-image').hidden=$('qr-download').hidden=true;$('qr-status').textContent='The QR image is unavailable. Ask the administrator to check private image storage.';});
  $('qr-dialog').addEventListener('close',()=>{clearTimeout(qrTimer);$('qr-image').removeAttribute('src');});
  async function showEvidence(id){
    try{const result=await config.request(`/api/payments/${id}/evidence/`);const box=$('evidence-images');box.replaceChildren();if(!result.images.length)box.textContent='Legacy payment · no receipt is archived.';for(const image of result.images){const article=document.createElement('article'),p=document.createElement('p'),img=document.createElement('img'),a=document.createElement('a');p.textContent=`${image.id===result.current?'Current receipt':'Retained earlier receipt'} · ${new Date(image.uploaded_at).toLocaleString()} · ${image.reason}`;img.src=image.url;img.alt='Payment evidence supplied by a family member';img.className='private-image';img.loading='lazy';a.href=image.url+'?download=1';a.textContent='Download receipt';article.append(p,img,a);box.append(article);}$('evidence-dialog').showModal();}catch(error){config.notify(error.message);}
  }
  $('replacement-form').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget;if(!canWrite()||form.dataset.busy)return;
    const value=Object.fromEntries(new FormData(form));if(!value.receipt_id){message('replacement-error',new Error('Attach an image and wait for validation.'));return;}$('replacement-dialog').close();
    if(!await FBTReview({title:'Confirm receipt replacement',rows:[['Reason',value.reason]],action:'Save receipt',note:'The previous receipt is retained. This does not change the payment amount or verify the external transfer.'})){$('replacement-dialog').showModal();return;}
    form.dataset.busy='yes';try{await config.request(`/api/payments/${replacement.paymentId}/evidence/replace/`,{method:'POST',body:JSON.stringify({asset_id:value.receipt_id,reason:value.reason,confirmed:true,expected_version:replacement.version})});await config.refresh();config.notify('Receipt saved; earlier evidence is retained.');}catch(error){message('replacement-error',error);$('replacement-dialog').showModal();}finally{delete form.dataset.busy;}
  });
  $('qr-settings-open').addEventListener('click',async()=>{
    if(!canWrite()||!data.user.admin)return;
    try{const result=await config.request('/api/payment-qr/');qrVersion=result.version;$('qr-settings-form').reset();$('qr-settings-form').elements.recipient.value=result.recipient;$('qr-settings-current').textContent=result.configured?`Current configured recipient: ${result.recipient}`:'No household QR configured.';$('qr-settings-error').textContent='';qrFields();$('qr-settings-dialog').showModal();}catch(error){config.notify(error.message);}
  });
  function qrFields(){const replace=$('qr-settings-form').elements.action.value==='replace';$('qr-new-fields').hidden=!replace;$('qr-settings-form').elements.recipient.required=replace;$('qr-settings-form').querySelector('input[type=file]').required=replace;}
  $('qr-settings-form').elements.action.addEventListener('change',qrFields);
  $('qr-settings-form').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget;if(!canWrite()||form.dataset.busy)return;const value=Object.fromEntries(new FormData(form));if(value.action==='replace'&&!value.asset_id){message('qr-settings-error',new Error('Upload and validate the QR before reviewing.'));return;}$('qr-settings-dialog').close();
    if(!await FBTReview({title:'Confirm household QR change',rows:[['Action',value.action],['Recipient',value.action==='remove'?'Remove configuration':value.recipient],['Reason',value.reason]],action:value.action==='remove'?'Remove QR':'Save verified QR',note:'Confirm the recipient using your trusted payment app. Viewing or saving a QR never marks a bill paid.'})){$('qr-settings-dialog').showModal();return;}
    form.dataset.busy='yes';try{await config.request('/api/payment-qr/configure/',{method:'POST',body:JSON.stringify({...value,confirmed:true,expected_version:qrVersion})});config.notify('Household QR updated.');form.reset();}catch(error){message('qr-settings-error',error);$('qr-settings-dialog').showModal();}finally{delete form.dataset.busy;}
  });
})();
