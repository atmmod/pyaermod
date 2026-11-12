// rpc.js: how the page reaches pyaermod.browser.
//
// WorkerBackend runs it in a Web Worker under Pyodide (the published site).
// HttpBackend posts to a local CPython server (scripts/wasm/app_dev_server.py),
// so the shell can be developed and tested without the WebAssembly build.
// Both give call(op, args) -> Promise of the reply object, and restart(),
// which is how a run is cancelled.

export class WorkerBackend {
  constructor(config, onProgress) {
    this.config = config;
    this.onProgress = onProgress || (() => {});
    this.pending = new Map();
    this.nextId = 1;
    this.ready = null;
    this.start();
  }

  start() {
    this.worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
    this.ready = new Promise((resolve, reject) => {
      this.worker.onmessage = (event) => {
        const m = event.data;
        if (m.progress) this.onProgress(m.progress);
        else if (m.ready) resolve();
        else if (m.failed) reject(new Error(m.failed));
        else if (m.id && this.pending.has(m.id)) {
          this.pending.get(m.id).resolve(m.reply);
          this.pending.delete(m.id);
        }
      };
      this.worker.onerror = (event) => {
        const err = new Error(event.message || 'the worker stopped');
        reject(err);
        for (const p of this.pending.values()) {
          p.resolve({ ok: false, error: { kind: 'internal', step: null, message: err.message } });
        }
        this.pending.clear();
      };
    });
    this.worker.postMessage({ init: this.config });
  }

  async call(op, args) {
    await this.ready;
    const id = this.nextId++;
    return new Promise((resolve) => {
      this.pending.set(id, { resolve });
      this.worker.postMessage({ id, op, args });
    });
  }

  // Ends the worker (and any run in it) and starts a new one. Calls in
  // flight get a "cancelled" reply.
  restart() {
    this.worker.terminate();
    for (const p of this.pending.values()) {
      p.resolve({ ok: false, error: { kind: 'cancelled', step: null, message: 'Cancelled' } });
    }
    this.pending.clear();
    this.start();
    return this.ready;
  }
}

export class HttpBackend {
  constructor(config) {
    this.url = new URL(config.api || 'api/call', document.baseURI).href;
    this.ready = Promise.resolve();
    this.controller = new AbortController();
  }

  async call(op, args) {
    try {
      const response = await fetch(this.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ op, args: args || {} }),
        signal: this.controller.signal,
      });
      return await response.json();
    } catch (err) {
      const cancelled = err && err.name === 'AbortError';
      return { ok: false, error: { kind: cancelled ? 'cancelled' : 'internal', step: null,
        message: cancelled ? 'Cancelled' : String(err) } };
    }
  }

  restart() {
    this.controller.abort();
    this.controller = new AbortController();
    return Promise.resolve();
  }
}
