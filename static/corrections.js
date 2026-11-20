/* Drafts exist only in memory. The server validates permissions, versions, and accounting. */
(() => {
  const $=id=>document.getElementById(id),dialog=$('correction-dialog'),form=$('correction-form');
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let data=null,online=false,config=null,selected=null,retry=null,busy=false,blockedReason='';
  const allowed=()=>online&&!data?.emergency;
  const syncButtons=()=>{
    document.querySelectorAll('.financial-correction,#detail-actions .reassign-payer').forEach(button=>button.disabled=!allowed()||busy);
    form.querySelector('[type=submit]').disabled=!allowed()||busy;
    const status=$('detail-action-status');if(status){status.textContent=busy?'Saving changes…':blockedReason;status.hidden=!data?.user.admin||(!busy&&!blockedReason);}
  };
  const money=value=>`PHP ${Number(value).toFixed(2)}`;
  const fields=$('correction-fields');
  const input=(name,title,value,type='text')=>`<label>${title}<input name="${name}" type="${type}" value="${esc(value)}" ${type==='number'?'min="0.01" max="9999999999.99" step="0.01" inputmode="decimal"':type==='text'?'maxlength="100"':''} required></label>`;
  window.FBTCorrections={
    configure(value){config=value;},
    update(value,connected,pending){data=value;online=connected&&!pending;blockedReason=!connected?'Viewing saved records. Connect to your home server, close this window, and refresh before making changes.':pending?'Close this window and refresh your family records before making changes.':'';syncButtons();},
    controls(kind,id){const record=kind==='loan'?data?.loans.find(r=>r.id===id):kind==='bill'?data?.bills.find(r=>r.id===id):data?.bills.find(r=>r.payments.some(p=>p.id===id));return record?.can_manage&&!data?.emergency?`<span class="correction-actions"><button type="button" class="button secondary financial-correction" data-kind="${kind}" data-record="${id}" data-action="edit" ${!allowed()?'disabled':''}>Edit ${kind}</button><button type="button" class="button secondary danger-outline financial-correction" data-kind="${kind}" data-record="${id}" data-action="delete" ${!allowed()?'disabled':''}>Delete ${kind}</button></span>`:'';}
  };
  function preview(){
    const box=$('correction-impact');box.replaceChildren();
    if(!selected)return;
    const {kind,action,record,bill,bills,loan}=selected;
    const line=text=>{const p=document.createElement('p');p.textContent=text;box.append(p);};
    if(action==='delete'){
      line(kind==='loan'?`Deletes this loan and its ${bills.length} active installment(s) from family views. Related payments and audit records remain retained.`:kind==='bill'?`Deletes this bill from family views, including paid history. Its ${bill.payments.length} recorded payment(s) remain retained.${loan?' The loan agreement and installment count will be updated.':''}${bill.recurring?' Future monthly bills continue unless you cancel the schedule separately.':''}`:`Deletes the ${money(record.amount)} payment from the current bill balance. The bill's unpaid amount becomes ${money(Number(bill.balance)+Number(record.amount))}. The original record and recorder remain retained.`);
    }else if(kind==='loan'){
      line('Paid installments stay unchanged where possible. The remaining agreement is split across open installments; a fully paid loan reopens its final installment when increased. Renaming the loan does not rename its bills.');
      try{
        const plan=FBTAllocation(form.elements.total.value,bills),list=document.createElement('ol');
        bills.forEach((b,i)=>{const item=document.createElement('li');item.textContent=`${b.title} · Due ${b.due_date} · ${money(b.amount)} → ${money(plan[i]/100)}`;list.append(item);});box.append(list);
      }catch(error){line(error.message);}
    }else if(kind==='bill')line(`Current recorded payments: ${money(Number(bill.amount)-Number(bill.balance))}. Editing this occurrence does not change a repeating schedule.${loan?' Its loan agreement will follow the sum of retained installments.':''}`);
    else line(`Bill: ${bill.title}. Original recorder: ${record.recorded_by}. Corrected unpaid amount: ${money(Number(bill.balance)+Number(record.amount)-Number(form.elements.amount.value))}. Recorder and bill assignment do not change.`);
    if(kind==='bill'&&loan){
      const remaining=loan.installments-(action==='delete'?1:0);
      line(remaining?`Loan ${loan.title}: ${money(loan.total)} → ${money(Number(loan.total)-Number(bill.amount)+(action==='delete'?0:Number(form.elements.amount.value)))}; ${loan.installments} → ${remaining} installment(s).`:'This is the final retained installment, so its loan is also removed from family views.');
    }
  }
  document.addEventListener('click',event=>{
    const button=event.target.closest('.financial-correction');if(!button||!allowed()||busy)return;
    const kind=button.dataset.kind,id=Number(button.dataset.record),action=button.dataset.action;
    let record,bill,bills,loan;
    if(kind==='loan'){loan=data.loans.find(l=>l.id===id);record=loan;bills=data.bills.filter(b=>b.loan_id===id).sort((a,b)=>a.id-b.id);}
    else if(kind==='bill'){bill=data.bills.find(b=>b.id===id);record=bill;}
    else{bill=data.bills.find(b=>b.payments.some(p=>p.id===id));record=bill?.payments.find(p=>p.id===id);}
    const permitted=kind==='loan'?record:bill;if(!record?.version||!permitted?.can_manage)return;
    loan=loan||data.loans.find(l=>l.id===bill?.loan_id);selected={kind,action,record,bill,bills,loan};retry=null;
    form.reset();$('correction-error').hidden=true;$('correction-title').textContent=`${action==='delete'?'Delete':'Edit'} ${kind}`;
    $('correction-record').textContent=kind==='payment'?`${bill.title} · ${money(record.amount)} · ${record.paid_date}`:record.title;
    if(action==='delete')fields.replaceChildren();
    else if(kind==='loan')fields.innerHTML=input('title','Loan name',record.title)+input('total','Agreed total (PHP)',record.total,'number');
    else if(kind==='payment')fields.innerHTML=input('amount','Payment amount (PHP)',record.amount,'number')+input('paid_date','Payment date',record.paid_date,'date');
    else{
      const members=[...data.members];if(!members.some(m=>m.id===bill.responsible_id))members.push({id:bill.responsible_id,username:bill.responsible+' (inactive)'});
      fields.innerHTML=input('title','Bill name',record.title)+input('amount','Original amount (PHP)',record.amount,'number')+input('due_date','Due date',record.due_date,'date')+input('category','Category',record.category)+`<label>Primary payer<select name="responsible">${members.map(m=>`<option value="${m.id}" ${m.id===bill.responsible_id?'selected':''}>${esc(m.username)}</option>`).join('')}</select></label><label>Notes<textarea name="notes" maxlength="500">${esc(record.notes)}</textarea></label>`;
      form.elements.category.maxLength=40;
      form.elements.amount.min=Math.max(.01,Number(bill.amount)-Number(bill.balance)).toFixed(2);
    }
    if(action==='edit'&&kind==='payment'){form.elements.amount.max=(Number(bill.balance)+Number(record.amount)).toFixed(2);form.elements.paid_date.max=data.today;}
    form.querySelector('[type=submit]').textContent=action==='delete'?'Review deletion':'Review changes';
    $('detail-dialog').close();preview();dialog.showModal();
  });
  form.addEventListener('input',preview);
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(busy||!allowed()||!form.reportValidity())return;
    const {kind,action,record,bill,bills,loan}=selected;
    const values=Object.fromEntries(new FormData(form));
    if(kind==='loan'&&action==='edit'){try{FBTAllocation(values.total,bills);}catch(error){$('correction-error').textContent=error.message;$('correction-error').hidden=false;return;}}
    const payload={...values,action,confirmed:true,expected_version:record.version,...(bill?{expected_bill_version:bill.version}:{}),...(loan&&kind!=='loan'?{expected_loan_version:loan.version}:{})};
    const fingerprint=JSON.stringify(payload);if(retry?.fingerprint!==fingerprint)retry={fingerprint,key:crypto.randomUUID()};payload.request_key=retry.key;
    const rows=[['Record',kind==='payment'?bill.title:record.title],['Reason',values.reason]];
    if(action==='edit')for(const [name,value] of Object.entries(values)){if(name!=='reason')rows.push([name.replaceAll('_',' '),`${record[name]??''} → ${name==='responsible'?form.elements.responsible.selectedOptions[0].textContent:value}`]);}
    rows.push(['Impact',$('correction-impact').innerText]);
    dialog.close();
    const confirmed=await FBTReview({title:action==='delete'?`Confirm ${kind} deletion`:`Confirm ${kind} correction`,rows,action:action==='delete'?'Delete record':'Save correction',variant:action==='delete'?'destructive':'review',note:'The reason and before/after changes are recorded together in audit history.'});
    if(!confirmed){dialog.showModal();return;}
    busy=true;form.dataset.busy='true';syncButtons();
    try{await config.request(`/api/manage/${kind}/${record.id}/`,{method:'POST',body:JSON.stringify(payload)});selected=null;retry=null;await config.refresh();config.notify('Correction saved. Review its reason and changes in Audit history.');}
    catch(error){$('correction-error').textContent=error.message;$('correction-error').hidden=false;dialog.showModal();}
    finally{busy=false;delete form.dataset.busy;syncButtons();}
  });
})();
