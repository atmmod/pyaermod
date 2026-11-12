// worker.js: Pyodide, pyaermod and AERMOD's WebAssembly build, in a Web Worker.
//
// The page (app.js, through rpc.js) posts {id, op, args}; the worker answers
// {id, reply}, where reply is what pyaermod.browser.call returned. A run
// holds this worker until AERMOD ends; the page cancels it by terminating
// the worker and starting a new one.
//
// The first message is {init: config}: config.json's pyodide URL and wheel
// URLs. Wheels are installed by URL from this site only, never by name, so
// nothing can come from PyPI instead.

let call = null;

async function init(config) {
  const base = new URL(config.pyodide, self.location.href).href;
  const { loadPyodide } = await import(base + 'pyodide.mjs');
  post({ progress: 'Loading Python (Pyodide)...' });
  const pyodide = await loadPyodide({ indexURL: base });
  post({ progress: 'Loading numpy, pandas and matplotlib...' });
  await pyodide.loadPackage(['micropip', 'numpy', 'pandas', 'matplotlib']);
  post({ progress: 'Installing pyaermod and AERMOD...' });
  const micropip = pyodide.pyimport('micropip');
  const wheels = config.wheels.map((w) => new URL(w, self.location.href).href);
  // deps=False: their dependencies (numpy, pandas) are Pyodide's own,
  // loaded above; nothing is looked up on PyPI.
  await micropip.install.callKwargs(pyodide.toPy(wheels), { deps: false });
  pyodide.FS.mkdirTree('/home/pyodide/work');
  pyodide.runPython('import matplotlib; matplotlib.use("Agg")');
  call = pyodide.pyimport('pyaermod.browser').call;
}

function post(message) {
  self.postMessage(message);
}

self.onmessage = async (event) => {
  const message = event.data;
  if (message.init) {
    try {
      await init(message.init);
      post({ ready: true });
    } catch (err) {
      post({ failed: String(err && err.message ? err.message : err) });
    }
    return;
  }
  const { id, op, args } = message;
  let reply;
  try {
    reply = JSON.parse(call(op, JSON.stringify(args || {})));
  } catch (err) {
    reply = { ok: false, error: { kind: 'internal', step: null,
      message: 'The worker failed: ' + String(err && err.message ? err.message : err) } };
  }
  post({ id, reply });
};
