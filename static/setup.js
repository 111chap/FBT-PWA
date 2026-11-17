document.getElementById('env-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button'), result = document.getElementById('env-result');
  button.disabled = true;
  try {
    if(!globalThis.crypto?.subtle) throw new Error('Web Crypto is unavailable. Open this guide on trusted HTTPS or localhost.');
    const url = new URL(document.getElementById('origin').value.trim());
    if(url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/' || !/^[a-z0-9.-]+$/i.test(url.hostname)) throw new Error('Enter an HTTPS origin with a hostname, no path, password, or query.');
    const contact = document.getElementById('contact').value.trim();
    if(!/^[^\s@=]+@[^\s@=]+\.[^\s@=]+$/.test(contact)) throw new Error('Enter a valid contact email.');
    const secret = () => Array.from(crypto.getRandomValues(new Uint8Array(40)), b => b.toString(16).padStart(2,'0')).join('');
    const pair = await crypto.subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},true,['sign','verify']);
    const jwk = await crypto.subtle.exportKey('jwk',pair.privateKey);
    const raw = new Uint8Array(await crypto.subtle.exportKey('raw',pair.publicKey));
    const publicKey = btoa(String.fromCharCode(...raw)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
    const env = [
      '# Private configuration. Never commit or share this file.',
      'DJANGO_SECRET_KEY='+secret(), 'POSTGRES_PASSWORD='+secret(),
      'FBT_SETUP_TOKEN='+secret(), 'FBT_ALLOWED_HOSTS='+url.hostname+',localhost,127.0.0.1',
      'FBT_TRUSTED_ORIGINS='+url.origin, 'FBT_TRUST_PROXY=1', 'FBT_DEBUG=0',
      'VAPID_PRIVATE_KEY='+jwk.d, 'VAPID_PUBLIC_KEY='+publicKey,
      'VAPID_SUBJECT=mailto:'+contact, ''
    ].join('\n');
    const link = document.createElement('a'), objectUrl = URL.createObjectURL(new Blob([env],{type:'text/plain'}));
    link.href = objectUrl; link.download = '.env'; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl),1000);
    result.textContent = 'Your settings download is ready. Some browsers name it env.txt: rename it exactly .env (remove .txt), then upload it beside compose.yaml. Keep it private. Open the file locally to find your one-time setup code. Generating again creates different keys; do not replace an existing deployment’s file casually.';
  } catch(error) { result.textContent = error.message; }
  finally { button.disabled = false; }
});
