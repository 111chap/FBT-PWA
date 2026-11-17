/* Django still validates permissions, CSRF, protected relationships and form values. */
document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('#content-main form[method="post"]');
  if (!form || location.pathname.endsWith('/delete/')) return; // Django supplies deletion review.
  const initial = new Map();
  function values() {
    const fields = new Map();
    for (const field of form.elements) {
      if (!field.name || field.type === 'hidden' || ['submit','button'].includes(field.type) || field.disabled) continue;
      if (field.type === 'radio' && !field.checked) continue;
      const label = (form.querySelector(`label[for="${CSS.escape(field.id)}"]`)?.textContent || field.name).replace(/:$/, '');
      const value = field.type === 'password' ? (field.value ? 'Credential will change (hidden)' : 'No credential entered') : field.type === 'checkbox' ? (field.checked ? 'Yes' : 'No') : field.tagName === 'SELECT' ? Array.from(field.selectedOptions, o => o.textContent).join(', ') || 'None' : field.value;
      fields.set(field.name, {label, value});
    }
    return fields;
  }
  for(const [key, entry] of values()) initial.set(key, entry.value);
  let sending = false, reviewing = false;
  form.addEventListener('submit', async event => {
    if (sending) return;
    event.preventDefault();
    if(reviewing) return;
    reviewing = true;
    const submitter = event.submitter;
    const snapshot = Array.from(new FormData(form).entries());
    const rows = Array.from(values(), ([key, entry]) => [entry.label, initial.get(key) === entry.value ? entry.value : `${initial.get(key) ?? '—'} → ${entry.value}`]);
    const action = submitter?.value || 'Save changes';
    const accepted = await FBTReview({title:document.querySelector('#content h1')?.textContent || 'Review account changes', rows, action:`Confirm: ${action}`, note:'Review the account and access changes. Credentials are hidden. Referenced family accounts must be deactivated rather than deleted to preserve financial history.'});
    reviewing = false;
    if(accepted && JSON.stringify(snapshot) === JSON.stringify(Array.from(new FormData(form).entries()))) { sending = true; form.requestSubmit(submitter); }
  });
});
