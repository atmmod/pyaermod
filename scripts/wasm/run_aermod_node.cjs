#!/usr/bin/env node
// Run the WebAssembly AERMOD build under Node, in the current directory.
//
// It loads aermod.js the way pyaermod's Pyodide runner does: the glue is
// evaluated with a Module object already defined and the wasm bytes handed
// over, so the runtime is ready synchronously, without awaiting a Promise.
// If it is not, the build is unusable from Python and this exits with 97.
//
// AERMOD sees the host filesystem under /host (NODEFS) and starts in
// /host<cwd>, so it reads ./aermod.inp and writes ./aermod.out like the
// native binary. A one-line shell wrapper named `aermod` that runs this
// script lets pyaermod's AERMODRunner and tests/test_real_aermod.py drive
// the WebAssembly build unchanged.
//
// Usage: node run_aermod_node.cjs        (AERMOD_WASM_DIR: where aermod.js/.wasm are;
//                                         default: this script's directory)
'use strict';
const fs = require('node:fs');
const path = require('node:path');

const dir = process.env.AERMOD_WASM_DIR || __dirname;
const glue = fs.readFileSync(path.join(dir, 'aermod.js'), 'utf8');
const wasmBinary = fs.readFileSync(path.join(dir, 'aermod.wasm'));

let ready = false;
let exitCode = null;
const Module = {
  noInitialRun: true,
  wasmBinary,
  print: (s) => process.stdout.write(s + '\n'),
  printErr: (s) => process.stderr.write(s + '\n'),
  onRuntimeInitialized: () => { ready = true; },
  onExit: (code) => { exitCode = code; },
  quit: (status, toThrow) => { exitCode = status; throw toThrow; },
};

const load = new Function('Module', 'require', '__dirname', '__filename',
  glue + '\nreturn Module;');
const M = load(Module, require, dir, path.join(dir, 'aermod.js'));
if (!ready) {
  process.stderr.write('aermod-wasm: runtime was not ready synchronously after loading aermod.js\n');
  process.exit(97);
}

M.FS.mkdir('/host');
M.FS.mount(M.NODEFS, { root: '/' }, '/host');
M.FS.chdir('/host' + process.cwd());

try {
  const ret = M.callMain([]);
  if (exitCode === null && typeof ret === 'number') exitCode = ret;
} catch (e) {
  if (e && e.name === 'ExitStatus') {
    exitCode = e.status;
  } else {
    process.stderr.write('aermod-wasm: ' + (e && e.stack ? e.stack : String(e)) + '\n');
    exitCode = 98;
  }
}
process.exit(exitCode === null ? 0 : exitCode);
