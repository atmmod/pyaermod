// app.js: the pyaermod browser GUI.
//
// The page holds the project as the document a pyaermod project file holds
// (pyaermod.gui_v2.project_io), edits it in place, and asks pyaermod.browser
// (in a Web Worker, rpc.js) to check, write, run and read it. Uploaded files
// are kept here as well as in the worker, so a cancelled run (which ends the
// worker) or a reload loses nothing.

import { el, fieldGroup, fieldsInvalid } from './forms.js';
import { HttpBackend, WorkerBackend } from './rpc.js';
import * as store from './store.js';

const RECEPTOR_LISTS = {
  CartesianGrid: 'cartesian_grids',
  PolarGrid: 'polar_grids',
  DiscreteReceptor: 'discrete_receptors',
};

const state = {
  config: null,
  backend: null,
  schema: null,
  doc: null,
  step: 'project',
  review: null,
  run: null,
  running: null,          // {started, timer} while AERMOD runs
  dirty: false,
  fileName: null,
  uploads: new Map(),     // name -> base64, replayed into a new worker
  editing: null,          // {kind, list, index, item} while an editor is open
  notice: null,           // {kind, lines} shown at the top of the step
  files: [],
};

const main = () => document.getElementById('main');

// ----------------------------------------------------------------------
// Talking to pyaermod.browser
// ----------------------------------------------------------------------

async function api(op, args = {}, { quiet = false } = {}) {
  const reply = await state.backend.call(op, args);
  if (!reply.ok && !quiet && reply.error.kind !== 'cancelled') {
    showError(reply.error);
  }
  return reply;
}

function showError(error) {
  const box = document.getElementById('error');
  box.replaceChildren(
    el('strong', { text: error.step ? `${stepLabel(error.step)}: ` : 'Error: ' }),
    error.message,
    el('button', { class: 'link', type: 'button', text: 'Dismiss', onclick: () => box.replaceChildren() }),
  );
  box.hidden = false;
  if (error.traceback) console.error(error.traceback);
}

function clearError() {
  const box = document.getElementById('error');
  box.replaceChildren();
}

function setStatus(text) {
  document.getElementById('status').textContent = text;
}

// ----------------------------------------------------------------------
// Files
// ----------------------------------------------------------------------

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

function download(name, blob) {
  const url = URL.createObjectURL(blob);
  const a = el('a', { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function upload(name, buffer) {
  const data = toBase64(buffer);
  const reply = await api('put_file', { name, data_b64: data });
  if (reply.ok) {
    state.uploads.set(reply.name, data);
    await store.putFile(reply.name, data);
    await refreshFiles();
  } else if (reply.error.kind === 'cancelled') {
    showError({ message: `${name} was not uploaded: a run was cancelled while it was `
      + 'being sent. Upload it again.' });
  }
  return reply;
}

async function replayUploads() {
  for (const [name, data] of state.uploads) {
    await api('put_file', { name, data_b64: data }, { quiet: true });
  }
}

async function refreshFiles() {
  const reply = await api('list_files', {}, { quiet: true });
  state.files = reply.ok ? reply.files : [];
}

function pickFiles({ accept, multiple = false }) {
  return new Promise((resolve) => {
    const input = el('input', { type: 'file', accept, multiple });
    input.addEventListener('change', () => resolve([...input.files]));
    input.click();
  });
}

// ----------------------------------------------------------------------
// The project
// ----------------------------------------------------------------------

function project() {
  return state.doc.project;
}

function changed() {
  state.dirty = true;
  // Kept in this browser only once pyaermod has accepted it (runCheck), so
  // a value it refuses never replaces the last good copy.
  renderHeader();
  scheduleCheck();
}

async function replaceDocument(doc, fileName) {
  state.doc = doc;
  state.fileName = fileName || null;
  state.dirty = false;
  state.editing = null;
  state.run = null;
  store.saveDocument(doc);
  await runCheck();
  render();
}

function discardOk() {
  return !state.dirty || window.confirm('The project has changes that were not saved. Discard them?');
}

async function newProject() {
  if (!discardOk()) return;
  const reply = await api('new_project');
  if (reply.ok) await replaceDocument(reply.document, null);
}

async function openProject() {
  if (!discardOk()) return;
  const [file] = await pickFiles({ accept: '.json,application/json' });
  if (!file) return;
  const reply = await api('load', { text: await file.text() });
  if (reply.ok) {
    clearError();
    await replaceDocument(reply.document, file.name);
  }
}

function saveProject() {
  const title = (project().control.title_one || 'project').trim().replace(/[^\w.-]+/g, '_');
  const name = state.fileName || `${title || 'project'}.json`;
  download(name, new Blob([JSON.stringify(state.doc, null, 2)], { type: 'application/json' }));
  state.fileName = name;
  state.dirty = false;
  renderHeader();
}

async function importDeck() {
  if (!discardOk()) return;
  const files = await pickFiles({ accept: '.inp,.txt,.dat,.sfc,.pfl,.SFC,.PFL,*', multiple: true });
  if (!files.length) return;
  const deckFile = files.find((f) => /\.inp$/i.test(f.name)) || files[0];
  for (const f of files) {
    if (f !== deckFile) await upload(f.name, await f.arrayBuffer());
  }
  const reply = await api('import_deck', { name: deckFile.name, text: await deckFile.text() });
  if (!reply.ok) return;
  clearError();
  await replaceDocument(reply.document, null);
  const lines = [];
  for (const r of reply.renamed) lines.push(`${r.keyword}: ${r.from} is looked for as ${r.to}.`);
  if (reply.missing_files.length) {
    lines.push(`Still to upload on the Meteorology step: ${reply.missing_files.join(', ')}.`);
  }
  if (reply.kept_verbatim.length) {
    lines.push(`Kept as written (not editable here): ${reply.kept_verbatim.join(', ')}.`);
  }
  state.notice = { kind: 'info', lines: [`Imported ${deckFile.name}.`, ...lines] };
  render();
}

// ----------------------------------------------------------------------
// The checklist, kept current
// ----------------------------------------------------------------------

let checkTimer = null;

function scheduleCheck() {
  clearTimeout(checkTimer);
  checkTimer = setTimeout(async () => {
    await runCheck();
    renderNav();
    if (state.step === 'run' && !state.running) render();
  }, 400);
}

async function runCheck() {
  const reply = await api('check', { document: state.doc }, { quiet: true });
  if (reply.ok) store.saveDocument(state.doc);
  state.review = reply.ok ? reply : {
    ready: false, warnings: [], deck: null, met_summary: null,
    blocking: [{ step: reply.error.step || 'project', title: stepLabel(reply.error.step || 'project'),
      links: [reply.error.step || 'project'], problems: [reply.error.message] }],
  };
}

function problemsFor(step) {
  if (!state.review) return 0;
  return state.review.blocking.filter((i) => i.step === step)
    .reduce((n, i) => n + i.problems.length, 0);
}

function stepLabel(id) {
  const step = state.schema && state.schema.steps.find((s) => s.id === id);
  return step ? step.label : id;
}

// ----------------------------------------------------------------------
// Layout
// ----------------------------------------------------------------------

function goto(step) {
  state.step = step;
  state.editing = null;
  state.notice = null;
  render();
  main().focus();
}

function renderHeader() {
  const title = project().control.title_one || 'Untitled run';
  document.getElementById('project-title').textContent =
    `${state.fileName || title}${state.dirty ? ' (modified)' : ''}`;
}

function renderNav() {
  const nav = document.getElementById('steps');
  nav.replaceChildren(...state.schema.steps.map((s, i) => {
    const n = s.id === 'results' ? 0 : problemsFor(s.id);
    return el('li', {},
      el('button', {
        type: 'button', class: s.id === state.step ? 'step current' : 'step',
        'aria-current': s.id === state.step ? 'step' : null,
        onclick: () => goto(s.id),
      }, el('span', { class: 'num', text: String(i + 1) }), s.label,
      n ? el('span', { class: 'badge', 'aria-label': `${n} to fix`, text: String(n) }) : null));
  }));
}

function section(title, intro, ...children) {
  return el('section', { class: 'card' }, el('h2', { text: title }),
    intro ? el('p', { class: 'intro', text: intro }) : null, ...children);
}

function render() {
  renderHeader();
  renderNav();
  const page = { project: projectStep, sources: sourcesStep, receptors: receptorsStep,
    meteorology: meteorologyStep, output: outputStep, run: runStep, results: resultsStep }[state.step];
  const notice = state.notice ? el('div', { class: `notice ${state.notice.kind}`, role: 'status' },
    ...state.notice.lines.map((l) => el('p', { text: l })),
    state.notice.action ? el('button', { type: 'button', text: state.notice.action.label,
      onclick: state.notice.action.run }) : null) : null;
  main().replaceChildren(...[el('h1', { text: stepLabel(state.step) }), notice, ...page()].filter(Boolean));
}

function groupsFor(step, obj, className) {
  const cls = state.schema.classes[className];
  const groups = state.schema.groups[step];
  const named = groups.flatMap((g) => g.fields);
  const hidden = (state.schema.groups.hidden || {})[className] || [];
  const cards = groups.map((g) => section(g.title, g.intro,
    fieldGroup(cls, obj, g.fields, { onChange: changed })));
  const rest = cls.fields.filter((f) => !named.includes(f.name) && !hidden.includes(f.name));
  if (rest.length) {
    cards.push(el('details', { class: 'card' }, el('summary', { text: 'Advanced' }),
      fieldGroup(cls, obj, rest.map((f) => f.name), { onChange: changed })));
  }
  return cards;
}

// ----------------------------------------------------------------------
// Steps
// ----------------------------------------------------------------------

function projectStep() {
  const bar = el('div', { class: 'toolbar' },
    el('button', { type: 'button', onclick: newProject, text: 'New' }),
    el('button', { type: 'button', onclick: openProject, text: 'Open...' }),
    el('button', { type: 'button', onclick: saveProject, text: 'Save' }),
    el('button', { type: 'button', onclick: importDeck, text: 'Import deck...' }));
  const hint = el('p', { class: 'intro', text: 'Projects are the same .json files pyaermod-app '
    + 'opens and saves. Import deck reads an AERMOD .inp file; pick the met and other files it '
    + 'names together with it.' });
  return [section('Project file', null, bar, hint),
    ...groupsFor('project', project().control, 'ControlPathway')];
}

function describeItem(item) {
  const id = item.source_id || item.grid_name || '';
  const x = item.x_coord ?? item.x_start ?? item.x_init ?? item.x_center ??
    (item.vertices && item.vertices[0] ? item.vertices[0][0] : '');
  const y = item.y_coord ?? item.y_start ?? item.y_init ?? item.y_center ??
    (item.vertices && item.vertices[0] ? item.vertices[0][1] : '');
  return { id, type: item._type, at: x === '' ? '' : `(${x}, ${y})` };
}

function itemTable(entries, onEdit, onDelete, emptyText) {
  if (!entries.length) return el('p', { class: 'empty', text: emptyText });
  return el('table', {},
    el('thead', {}, el('tr', {}, ...['Name', 'Type', 'At (x, y)', ''].map((h) => el('th', { text: h })))),
    el('tbody', {}, ...entries.map(({ item, list, index }) => {
      const d = describeItem(item);
      return el('tr', {}, el('td', { text: d.id || '(no name)' }), el('td', { text: d.type }),
        el('td', { text: d.at }),
        el('td', { class: 'actions' },
          el('button', { type: 'button', class: 'link', text: 'Edit', 'aria-label': `Edit ${d.id}`,
            onclick: () => onEdit(list, index) }),
          el('button', { type: 'button', class: 'link danger', text: 'Delete',
            'aria-label': `Delete ${d.id}`, onclick: () => onDelete(list, index) })));
    })));
}

function editor(kind) {
  const e = state.editing;
  if (!e || e.kind !== kind) return null;
  const cls = state.schema.classes[e.item._type];
  let card = null;
  const save = async () => {
    // A field whose text does not parse still holds its old value; saving
    // would keep that value while the form shows something else.
    const bad = fieldsInvalid(card);
    if (bad.length) {
      showError({ step: kind === 'source' ? 'sources' : 'receptors',
        message: `Not saved: correct ${bad.join(', ')}, or Cancel.` });
      card.querySelector('[aria-invalid="true"]').focus();
      return;
    }
    const target = kind === 'source' ? project().sources.sources : project().receptors[e.list];
    const before = target.slice();
    if (e.index === null) target.push(e.item); else target[e.index] = e.item;
    const reply = await api('load', { text: JSON.stringify(state.doc) });
    if (!reply.ok) { target.splice(0, target.length, ...before); return; }
    clearError();
    state.doc = reply.document;
    state.editing = null;
    changed();
    render();
    refreshPlan();
  };
  card = section(`${e.index === null ? 'New' : 'Edit'} ${e.item._type}`, cls.doc,
    fieldGroup(cls, e.item, null),
    el('div', { class: 'toolbar' },
      el('button', { type: 'button', class: 'primary', text: 'Save', onclick: save }),
      el('button', { type: 'button', text: 'Cancel', onclick: () => { state.editing = null; render(); } })));
  return card;
}

async function refreshPlan() {
  const box = document.getElementById('plan');
  if (!box) return;
  const reply = await api('plan_view', { document: state.doc }, { quiet: true });
  // The SVG is pyaermod's own (plan_view_svg escapes every name); it is the
  // worker's reply, never text a user typed into the page.
  if (reply.ok) box.innerHTML = reply.svg;
}

function planCard() {
  const card = section('Plan view', null, el('div', { id: 'plan', class: 'plan' }));
  setTimeout(refreshPlan, 0);
  return card;
}

function sourcesStep() {
  const type = el('select', { 'aria-label': 'Source type' },
    ...state.schema.sources.map((t) => el('option', { value: t, text: t })));
  const add = async () => {
    const reply = await api('new_item', { type_name: type.value });
    if (reply.ok) { state.editing = { kind: 'source', list: 'sources', index: null, item: reply.item }; render(); }
  };
  const entries = project().sources.sources.map((item, index) => ({ item, list: 'sources', index }));
  const table = itemTable(entries,
    (list, index) => {
      state.editing = { kind: 'source', list, index, item: structuredClone(project().sources.sources[index]) };
      render();
    },
    (list, index) => {
      project().sources.sources.splice(index, 1);
      state.editing = null;       // its index may now name another source
      changed(); render(); refreshPlan();
    },
    'No sources yet.');
  return [section('Sources', 'Every source AERMOD models.', table,
    el('div', { class: 'toolbar' }, type, el('button', { type: 'button', text: 'Add source', onclick: add }))),
  editor('source'), planCard()].filter(Boolean);
}

function receptorsStep() {
  const type = el('select', { 'aria-label': 'Receptor type' },
    ...state.schema.receptors.map((t) => el('option', { value: t, text: t })));
  const add = async () => {
    const reply = await api('new_item', { type_name: type.value });
    if (reply.ok) {
      state.editing = { kind: 'receptor', list: RECEPTOR_LISTS[type.value], index: null, item: reply.item };
      render();
    }
  };
  const rp = project().receptors;
  const entries = Object.values(RECEPTOR_LISTS).flatMap((list) =>
    (rp[list] || []).map((item, index) => ({ item, list, index })));
  const table = itemTable(entries,
    (list, index) => {
      state.editing = { kind: 'receptor', list, index, item: structuredClone(rp[list][index]) };
      render();
    },
    (list, index) => {
      rp[list].splice(index, 1);
      state.editing = null;       // its index may now name another network
      changed(); render(); refreshPlan();
    },
    'No receptors yet.');
  const terrain = async () => {
    const [file] = await pickFiles({ accept: '.out,.rou,.csv,.txt,*' });
    if (!file) return;
    const put = await upload(file.name, await file.arrayBuffer());
    if (!put.ok) return;
    const reply = await api('apply_terrain', { document: state.doc, name: put.name });
    if (!reply.ok) return;
    clearError();
    state.doc = reply.document;
    changed();
    state.notice = { kind: reply.notes.length ? 'warn' : 'info',
      lines: [`Elevations read from ${put.name} (${reply.kind}, ${reply.rows} rows).`, ...reply.notes] };
    render();
  };
  return [section('Receptors', 'Where AERMOD computes concentrations.', table,
    el('div', { class: 'toolbar' }, type, el('button', { type: 'button', text: 'Add receptors', onclick: add }))),
  editor('receptor'),
  section('Terrain', 'With elevated terrain, AERMOD needs each receptor\'s elevation and hill height. '
    + 'Upload AERMAP\'s receptor or source output, or a CSV of x, y, elevation, hill height. '
    + 'AERMAP itself does not run in the browser.',
  el('div', { class: 'toolbar' }, el('button', { type: 'button', text: 'Upload elevations...', onclick: terrain }))),
  planCard()].filter(Boolean);
}

function filesCard() {
  const remove = async (name) => {
    await api('remove_file', { name });
    state.uploads.delete(name);
    await store.removeFile(name);
    await refreshFiles();
    scheduleCheck();
    render();
  };
  const list = state.files.length ? el('table', {},
    el('thead', {}, el('tr', {}, el('th', { text: 'File' }), el('th', { text: 'Size' }), el('th', { text: '' }))),
    el('tbody', {}, ...state.files.map((f) => el('tr', {}, el('td', { text: f.name }),
      el('td', { text: `${(f.size / 1024).toFixed(1)} kB` }),
      el('td', { class: 'actions' }, el('button', { type: 'button', class: 'link danger', text: 'Remove',
        'aria-label': `Remove ${f.name}`, onclick: () => remove(f.name) })))))) :
    el('p', { class: 'empty', text: 'No files yet.' });
  const add = async () => {
    for (const f of await pickFiles({ accept: '.sfc,.pfl,.SFC,.PFL,*', multiple: true })) {
      await upload(f.name, await f.arrayBuffer());
    }
    await refreshFiles();
    scheduleCheck();
    render();
  };
  return section('Files in the browser', 'AERMOD reads files from here by name. They stay in this '
    + 'browser; nothing is sent to a server.', list,
  el('div', { class: 'toolbar' }, el('button', { type: 'button', text: 'Upload files...', onclick: add })));
}

function samplesCard() {
  const samples = state.config.samples || [];
  if (!samples.length) return null;
  const use = async (sample) => {
    setStatus(`Loading ${sample.label}...`);
    for (const f of sample.files) {
      const response = await fetch(new URL(f.url, document.baseURI));
      if (!response.ok) { showError({ message: `Could not fetch ${f.name}` }); setStatus(''); return; }
      await upload(f.name, await response.arrayBuffer());
    }
    Object.assign(project().meteorology, sample.meteorology);
    changed();
    await refreshFiles();
    setStatus('');
    state.notice = { kind: 'info', lines: [`Using ${sample.label}.`] };
    render();
  };
  return section('Sample meteorology', 'AERMET output that EPA ships with its AERMOD test cases.',
    el('ul', { class: 'samples' }, ...samples.map((s) => el('li', {},
      el('button', { type: 'button', text: `Use ${s.label}`, onclick: () => use(s) }),
      el('span', { class: 'help', text: ` ${s.description}` })))));
}

function meteorologyStep() {
  // state.files is kept current by every upload and removal, so this step
  // never re-renders under the user's typing.
  return [samplesCard(), filesCard(),
    ...groupsFor('meteorology', project().meteorology, 'MeteorologyPathway')].filter(Boolean);
}

function outputStep() {
  return groupsFor('output', project().output, 'OutputPathway');
}

function checklist(items, kind) {
  return el('ul', { class: `checklist ${kind}` }, ...items.map((item) => el('li', {},
    el('strong', { text: `${item.title}: ` }),
    item.problems.join('; '),
    ...item.links.map((step) => el('button', { type: 'button', class: 'link', text: `Go to ${stepLabel(step)}`,
      onclick: () => goto(step) })))));
}

function runStep() {
  const r = state.review;
  if (state.running) {
    const elapsed = el('span', { id: 'elapsed', text: '0 s' });
    return [section('Running AERMOD', 'The page stays usable; AERMOD runs in the background.',
      el('p', { role: 'status' }, el('span', { class: 'spinner', 'aria-hidden': 'true' }), ' Running... ', elapsed),
      el('button', { type: 'button', class: 'danger', text: 'Cancel', onclick: cancelRun }))];
  }
  if (!r) return [el('p', { text: 'Checking the project...' })];
  const cards = [];
  cards.push(section(r.ready ? 'Ready to run' : 'Before you can run', null,
    r.blocking.length ? checklist(r.blocking, 'blocking') : el('p', { text: 'Nothing blocks the run.' }),
    el('div', { class: 'toolbar' },
      el('button', { type: 'button', class: 'primary', text: 'Run AERMOD', disabled: !r.ready, onclick: startRun }))));
  if (r.warnings.length) cards.push(section('Warnings', 'These do not stop the run.', checklist(r.warnings, 'warnings')));
  if (r.met_summary) cards.push(section('Met data', null, el('p', { text: r.met_summary })));
  if (r.deck) {
    cards.push(section('Deck', 'The AERMOD input file the run will use.',
      el('div', { class: 'toolbar' }, el('button', { type: 'button', text: 'Download deck',
        onclick: () => download('aermod.inp', new Blob([r.deck], { type: 'text/plain' })) })),
      el('pre', { class: 'deck', tabindex: '0', 'aria-label': 'Deck preview', text: r.deck })));
  }
  return cards;
}

async function startRun() {
  clearError();
  state.running = { started: Date.now() };
  render();
  state.running.timer = setInterval(() => {
    const node = document.getElementById('elapsed');
    if (node) node.textContent = `${Math.round((Date.now() - state.running.started) / 1000)} s`;
  }, 500);
  const reply = await api('run', { document: state.doc });
  const running = state.running;
  if (!running) return;                       // cancelled meanwhile
  clearInterval(running.timer);
  state.running = null;
  if (reply.ok) {
    state.run = reply;
    goto('results');
  } else {
    render();
  }
}

async function cancelRun() {
  if (!state.running) return;
  clearInterval(state.running.timer);
  state.running = null;
  setStatus('Cancelling: restarting Python...');
  render();
  await state.backend.restart();
  await replayUploads();
  await refreshFiles();
  setStatus('');
  // The new worker has the uploads back, but no run's output files.
  state.run = null;
  state.notice = { kind: 'warn', lines: ['The run was cancelled.'] };
  await runCheck();
  render();
}

function table(columns, rows, label) {
  return el('div', { class: 'scroll' }, el('table', { 'aria-label': label },
    el('thead', {}, el('tr', {}, ...columns.map(([, h]) => el('th', { text: h })))),
    el('tbody', {}, ...rows.map((row) => el('tr', {}, ...columns.map(([k]) => el('td', { text: row[k] ?? '' })))))));
}

async function fetchFile(name) {
  const reply = await api('get_file', { name });
  if (!reply.ok) return;
  const bytes = Uint8Array.from(atob(reply.data_b64), (c) => c.charCodeAt(0));
  download(name, new Blob([bytes]));
}

function resultsStep() {
  const run = state.run;
  if (!run) return [el('p', { class: 'empty', text: 'Run AERMOD on the Review & Run step to see results here.' })];
  const res = run.results;
  const cards = [section(res.headline, res.detail,
    res.succeeded ? null : el('p', { text: run.status_text }), run.counts_text ? el('p', { text: run.counts_text }) : null)];
  if (!res.succeeded) {
    cards.push(section('No results', res.ran ? 'AERMOD did not complete the run, so its output holds '
      + 'no valid concentrations.' : 'AERMOD did not run.',
    res.fatal.length ? el('ul', { class: 'checklist blocking' }, ...res.fatal.map((f) => el('li', { text: f }))) : null));
  }
  for (const note of res.notes) cards.push(el('p', { class: 'notice warn', text: note }));
  const maxCols = [['period', 'Period'], ['value', 'Max'], ['units', 'Units'], ['x', 'X (m)'], ['y', 'Y (m)'],
    ['group', 'Group'], ['date', 'Date (YYMMDDHH)'], ['flag', 'Note']];
  if (res.maxima.length) {
    cards.push(section('Maximum for each averaging period', 'As AERMOD printed them in its summary tables.',
      table(maxCols, res.maxima.map((m) => ({ ...m, period: m.qualifier ? `${m.period} (${m.qualifier})` : m.period })),
        'Maximum for each averaging period')));
  }
  if (res.deposition.length) {
    cards.push(section('Deposition maxima', null, table(maxCols, res.deposition, 'Deposition maxima')));
  }
  for (const map of res.maps) {
    cards.push(section(map.title, null, el('img', { src: map.src, alt: `Map: ${map.title}`, class: 'map' })));
  }
  if (res.naaqs.length) {
    cards.push(section('Comparison with the NAAQS', 'A screening comparison uses the highest value of the '
      + 'period, which no design value can exceed.',
    table([['standard', 'Standard'], ['level', 'NAAQS'], ['value', 'This run (µg/m³)'], ['basis', 'Compared'],
      ['verdict', 'Result'], ['how', 'Value from']], res.naaqs, 'Comparison with the NAAQS')));
  }
  if (run.messages.length) {
    cards.push(el('details', { class: 'card' }, el('summary', { text: `AERMOD's messages (${run.messages.length})` }),
      table([['code', 'Code'], ['pathway', 'Pathway'], ['module', 'Routine'], ['text', 'Message'], ['detail', 'Detail']],
        run.messages, "AERMOD's messages")));
  }
  for (const t of res.tables) {
    cards.push(el('details', { class: 'card' }, el('summary', { text: t.name }),
      t.total_rows > t.rows.length ? el('p', { class: 'help', text: `First ${t.rows.length} of ${t.total_rows} rows; download the .out file for all.` }) : null,
      table([['group', 'Group'], ['rank', 'Rank'], ['value', `Value (${t.units})`], ['flag', 'Note'], ['date', 'Date'],
        ['x', 'X (m)'], ['y', 'Y (m)'], ['network', 'Network']], t.rows, t.name)));
  }
  if (res.files.length) {
    cards.push(section('Downloads', null, el('ul', { class: 'downloads' }, ...res.files.map((f) => el('li', {},
      el('button', { type: 'button', class: 'link', text: f.label.includes(f.name) ? f.label : `${f.label}: ${f.name}`,
        onclick: () => fetchFile(f.name) }))))));
  }
  return cards;
}

// ----------------------------------------------------------------------
// Start
// ----------------------------------------------------------------------

async function boot() {
  const params = new URLSearchParams(window.location.search);
  state.config = await (await fetch('config.json', { cache: 'no-cache' })).json();
  const backend = params.get('backend') || state.config.backend || 'worker';
  setStatus('Loading Python and AERMOD; the first visit downloads about 30 MB...');
  state.backend = backend === 'http' ? new HttpBackend(state.config)
    : new WorkerBackend(state.config, (text) => setStatus(text));
  try {
    await state.backend.ready;
  } catch (err) {
    loadFailed(err);
    return;
  }
  const schema = await api('schema');
  if (!schema.ok) { loadFailed(new Error(schema.error.message)); return; }
  state.schema = schema;
  document.getElementById('banner').textContent = schema.banner;
  document.getElementById('version').textContent = `pyaermod ${schema.version}`;

  for (const [name, data] of await store.allFiles()) state.uploads.set(name, data);
  await replayUploads();
  await refreshFiles();

  const saved = store.loadDocument();
  let doc = null;
  if (saved) {
    const reply = await api('load', { text: JSON.stringify(saved) }, { quiet: true });
    if (reply.ok) {
      doc = reply.document;
    } else {
      // Not thrown away: offered as a file, and kept until a new project is accepted.
      state.notice = { kind: 'warn', lines: [
        `The project kept in this browser could not be opened: ${reply.error.message}`],
      action: { label: 'Download it', run: () => download('unopened-project.json',
        new Blob([JSON.stringify(saved, null, 2)], { type: 'application/json' })) } };
    }
  }
  if (!doc) doc = (await api('new_project')).document;
  state.doc = doc;
  await runCheck();
  setStatus('');
  document.getElementById('app').hidden = false;
  document.getElementById('loading').hidden = true;
  render();
}

function loadFailed(err) {
  const box = document.getElementById('loading');
  box.replaceChildren(
    el('h1', { text: 'The app could not start' }),
    el('p', { text: `Python or AERMOD did not load in this browser: ${err.message}` }),
    el('p', {}, 'Check the network connection and try again, or install the GUI with pip: ',
      el('a', { href: '../gui-guide/#install', text: 'GUI guide' }), '.'),
    el('button', { type: 'button', text: 'Try again', onclick: () => window.location.reload() }));
  setStatus('');
}

window.addEventListener('beforeunload', (event) => {
  if (state.running) { event.preventDefault(); event.returnValue = ''; }
});

boot();
