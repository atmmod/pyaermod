// store.js: what the page keeps across a reload, in this browser only.
//
// The project document goes to localStorage and uploaded files to IndexedDB.
// Both are conveniences: a private window, blocked site data or a full disk
// make every call here a no-op, and the page still works.

const DOC_KEY = 'pyaermod-app/document';
const DB_NAME = 'pyaermod-app';
const STORE = 'files';

export function saveDocument(doc) {
  try { localStorage.setItem(DOC_KEY, JSON.stringify(doc)); } catch (err) { /* not kept */ }
}

export function loadDocument() {
  try {
    const text = localStorage.getItem(DOC_KEY);
    return text ? JSON.parse(text) : null;
  } catch (err) {
    return null;
  }
}

function open() {
  return new Promise((resolve) => {
    try {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => resolve(null);
    } catch (err) {
      resolve(null);
    }
  });
}

async function withStore(mode, fn) {
  const db = await open();
  if (!db) return null;
  return new Promise((resolve) => {
    try {
      const tx = db.transaction(STORE, mode);
      const result = fn(tx.objectStore(STORE));
      tx.oncomplete = () => resolve(result && 'result' in result ? result.result : null);
      tx.onerror = () => resolve(null);
    } catch (err) {
      resolve(null);
    }
  });
}

export function putFile(name, data) {
  return withStore('readwrite', (s) => s.put(data, name));
}

export function removeFile(name) {
  return withStore('readwrite', (s) => s.delete(name));
}

// [[name, base64], ...] of every file kept.
export async function allFiles() {
  const db = await open();
  if (!db) return [];
  return new Promise((resolve) => {
    try {
      const out = [];
      const tx = db.transaction(STORE, 'readonly');
      const cursor = tx.objectStore(STORE).openCursor();
      cursor.onsuccess = () => {
        const c = cursor.result;
        if (c) { out.push([c.key, c.value]); c.continue(); }
      };
      tx.oncomplete = () => resolve(out);
      tx.onerror = () => resolve([]);
    } catch (err) {
      resolve([]);
    }
  });
}
