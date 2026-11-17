/* A UI safeguard, not an authorization boundary. Never persist draft form values. */
(() => {
  'use strict';
  window.FBTReview = async function({title, rows, action = 'Confirm changes', cancelAction = 'Back / cancel', note = ''}) {
    const previous = document.activeElement;
    const dialog = document.createElement('dialog');
    dialog.className = 'review-dialog';
    dialog.setAttribute('aria-labelledby', 'review-title');
    const heading = document.createElement('h2'); heading.id = 'review-title'; heading.textContent = title;
    const copy = document.createElement('p'); copy.textContent = note || 'Review these details before saving. Nothing has been saved yet.';
    const list = document.createElement('dl');
    for (const [label, value] of rows) {
      const term = document.createElement('dt'), detail = document.createElement('dd');
      term.textContent = label; detail.textContent = String(value ?? '—'); list.append(term, detail);
    }
    const buttons = document.createElement('div'); buttons.className = 'button-row';
    const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'button secondary'; cancel.textContent = cancelAction; cancel.autofocus = true;
    const confirm = document.createElement('button'); confirm.type = 'button'; confirm.className = 'button primary'; confirm.textContent = action;
    buttons.append(cancel, confirm); dialog.append(heading, copy, list, buttons); document.body.append(dialog);
    return new Promise(resolve => {
      let accepted = false;
      cancel.addEventListener('click', () => dialog.close());
      confirm.addEventListener('click', () => { accepted = true; confirm.disabled = true; dialog.close(); });
      dialog.addEventListener('click', event => { if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if(event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close(); } });
      dialog.addEventListener('close', () => { dialog.remove(); previous?.focus(); resolve(accepted); }, {once:true});
      dialog.showModal(); cancel.focus();
    });
  };
})();
