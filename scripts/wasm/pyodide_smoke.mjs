// Run EPA's AERTEST through pyaermod inside Pyodide, under Node, with the
// WebAssembly AERMOD: the path the JupyterLite site takes, without a browser.
//
// It installs the pyaermod wheel into Pyodide, points
// PYAERMOD_AERMOD_WASM at the build, runs the deck with AERMODRunner().run()
// and compares the 1-hour plotfile with EPA's published one, receptor by
// receptor, at the tolerance tests/test_real_aermod.py uses.
//
// Usage: node pyodide_smoke.mjs <pyaermod wheel> <dir with aermod.js/.wasm> <repo root>
// Needs the `pyodide` npm package (npm install pyodide@<version>).
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { loadPyodide } from 'pyodide';

const [wheel, wasmDir, repo] = process.argv.slice(2);
if (!wheel || !wasmDir || !repo) {
  console.error('usage: node pyodide_smoke.mjs <wheel> <wasm dir> <repo root>');
  process.exit(2);
}

// The glue's Node code paths use require; the browser has none and never
// takes them.
globalThis.require = createRequire(import.meta.url);

const py = await loadPyodide();
await py.loadPackage(['micropip', 'numpy', 'pandas']);

const put = (src, dest) => py.FS.writeFile(dest, fs.readFileSync(src));
py.FS.mkdirTree('/tmp/wheels');
const wheelName = path.basename(wheel);
put(wheel, `/tmp/wheels/${wheelName}`);
py.FS.mkdirTree('/opt/aermod_wasm');
put(path.join(wasmDir, 'aermod.js'), '/opt/aermod_wasm/aermod.js');
put(path.join(wasmDir, 'aermod.wasm'), '/opt/aermod_wasm/aermod.wasm');
const fixtures = path.join(repo, 'tests', 'fixtures', 'epa_official');
py.FS.mkdirTree('/home/pyodide/aertest');
for (const name of ['aertest.inp', 'AERMET2.SFC', 'AERMET2.PFL', 'AERTEST_01H.PLT']) {
  put(path.join(fixtures, name), `/home/pyodide/aertest/${name === 'AERTEST_01H.PLT' ? 'reference.plt' : name}`);
}

await py.runPythonAsync(`
import micropip
await micropip.install("emfs:/tmp/wheels/${wheelName}", deps=False)
`);

const verdict = py.runPython(`
import os, re
from pathlib import Path
os.environ["PYAERMOD_AERMOD_WASM"] = "/opt/aermod_wasm"

from pyaermod import AERMODRunner, read_plotfile

work = Path("/home/pyodide/aertest")
deck = work / "aertest.inp"
text = deck.read_text()
# Flatten EPA's archive paths, as tests/test_real_aermod.py does.
text = re.sub(r"\\.\\./(meteorology|Outputs|plotfiles|postfiles)/", "", text, flags=re.I)
text = text.replace("aermet2.sfc", "AERMET2.SFC").replace("aermet2.pfl", "AERMET2.PFL")
deck.write_text(text)

result = AERMODRunner().run(deck)
assert result.success, (result.error_message, result.stderr)

def by_receptor(plot):
    col = plot.concentration_column
    return {(round(r["X"], 3), round(r["Y"], 3)): r[col] for r in plot.records
            if isinstance(r[col], (int, float))}

got = by_receptor(read_plotfile(work / "AERTEST_01H.PLT"))
ref = by_receptor(read_plotfile(work / "reference.plt"))
assert set(got) == set(ref) and len(ref) == 144, (len(got), len(ref))
worst = max(abs(got[k] - ref[k]) / max(abs(ref[k]), 1e-12) for k in ref)
bad = [k for k in ref if abs(got[k] - ref[k]) > 1e-3 + 1e-4 * abs(ref[k])]
f"receptors={len(ref)} worst_rel_diff={worst:.3e} outside_tolerance={len(bad)} runtime={result.runtime_seconds:.1f}s"
`);
console.log(`pyodide-smoke: ${verdict}`);
if (!verdict.includes('outside_tolerance=0')) process.exit(1);
