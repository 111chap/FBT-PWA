/* Cache only the public shell. Authenticated responses and API data are never cached here. */
const SHELL_CACHE = 'fbt-shell-v7';
const ASSETS = ['/app/', '/static/app.css', '/static/fonts.css', '/static/app.js', '/static/review.js', '/static/review.css', '/static/record-filters.js', '/static/offline-store.js', '/static/icon.svg', '/static/icon-180.png', '/static/icon-192.png', '/static/icon-512.png', '/static/manifest.webmanifest'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL_CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('fbt-shell-') && key !== SHELL_CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || !ASSETS.includes(url.pathname)) return;
  event.respondWith(fetch(event.request).then(response => {
    if (response.ok && !response.redirected) {
      const copy = response.clone();
      event.waitUntil(caches.open(SHELL_CACHE).then(cache => cache.put(url.pathname, copy)));
    }
    return response;
  }).catch(() => caches.match(url.pathname).then(response => response || Response.error())));
});
self.addEventListener('push', event => {
  let message = {title: 'Family Bill Tracker', body: 'A family payment needs a look.'};
  try { if (event.data) message = {...message, ...event.data.json()}; } catch (_) { /* Show a generic notification. */ }
  event.waitUntil(self.registration.showNotification(String(message.title), {body: String(message.body), icon: '/static/icon-192.png', tag: 'fbt-reminder', data: {url: '/app/'}}));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.matchAll({type: 'window'}).then(windows => {
    const app = windows.find(win => new URL(win.url).pathname === '/app/');
    return app ? app.focus() : clients.openWindow('/app/');
  }));
});
