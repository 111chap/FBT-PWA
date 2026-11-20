(function (root) {
  'use strict';
  const DB = 'fbt-private-offline-v1';
  const MAX_AGE = 7 * 24 * 60 * 60 * 1000;
  function validateSnapshot(value, userId = null, now = Date.now()) {
    if (!value || value.offline_safe===false || value.emergency || value.version !== 1 || !value.user || !Number.isInteger(value.user.id) || !Array.isArray(value.bills)) return false;
    if (userId !== null && value.user.id !== userId) return false;
    const synced = Date.parse(value.synced_at);
    return Number.isFinite(synced) && synced <= now + 60000 && now - synced <= MAX_AGE;
  }
  function connect() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB, 1);
      request.onupgradeneeded = () => request.result.createObjectStore('records');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(new Error('This browser could not open offline storage.'));
      request.onblocked = () => reject(new Error('Close other Family Bill Tracker tabs and try again.'));
    });
  }
  async function operation(mode, action) {
    const db = await connect();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction('records', mode);
        const request = action(tx.objectStore('records'));
        let result;
        request.onsuccess = () => { result = request.result; };
        tx.oncomplete = () => resolve(result);
        tx.onerror = tx.onabort = () => reject(new Error('The saved copy could not be updated. Storage may be full or unavailable.'));
      });
    } finally { db.close(); }
  }
  const store = {
    validateSnapshot,
    async read(userId = null) {
      const value = await operation('readonly', s => s.get('snapshot'));
      if (!validateSnapshot(value, userId)) { await store.clear(); return null; }
      return value;
    },
    async write(value) {
      if (!validateSnapshot(value)) throw new Error('The server returned an invalid snapshot.');
      await operation('readwrite', s => s.put(value, 'snapshot'));
    },
    async clear() { await operation('readwrite', s => s.clear()); }
  };
  root.FBTOffline = store;
  if (typeof module !== 'undefined') module.exports = {validateSnapshot, MAX_AGE};
})(typeof window !== 'undefined' ? window : globalThis);
