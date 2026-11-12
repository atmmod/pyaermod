// forms.js: inputs drawn from pyaermod.browser.schema(), editing a JSON object
// in place (a source, a receptor network, or a pathway of the project).
//
// Each field kind maps to one input. Values are written back in the form the
// project file uses ({"_enum": ...} for an enum, lists for points), so the
// object stays a valid part of the project document.

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

let uid = 0;

function sameEnum(a, b) {
  return a && b && typeof a === 'object' && typeof b === 'object' && a._enum === b._enum;
}

function parseNumber(text, integer) {
  const t = text.trim();
  if (t === '') return null;
  const v = Number(t);
  if (!Number.isFinite(v)) return undefined;
  if (integer && !Number.isInteger(v)) return undefined;
  return v;
}

// One input for one field. onChange(value) is called with the parsed value;
// a text that does not parse marks the input invalid and changes nothing.
export function fieldInput(field, value, onChange) {
  const id = `f${++uid}`;
  const label = el('label', { for: id, class: 'field-label' }, field.label,
    field.units ? el('span', { class: 'units', text: ` (${field.units})` }) : null);
  const help = field.help ? el('div', { class: 'help', id: `${id}-help`, text: field.help }) : null;
  const describedBy = help ? `${id}-help` : null;
  let input;

  // Shown under a value that does not parse, which changes nothing; an
  // item editor will not save while one shows (fieldsInvalid).
  const error = el('div', { class: 'field-error', id: `${id}-error`, hidden: true });
  const invalid = (node, bad, message) => {
    node.setAttribute('aria-invalid', bad ? 'true' : 'false');
    node.title = bad ? message : '';
    error.textContent = bad ? message : '';
    error.hidden = !bad;
    const ids = [describedBy, bad ? error.id : null].filter(Boolean).join(' ');
    if (ids) node.setAttribute('aria-describedby', ids); else node.removeAttribute('aria-describedby');
  };

  switch (field.kind) {
    case 'boolean': {
      input = el('input', { id, type: 'checkbox', 'aria-describedby': describedBy });
      input.checked = !!value;
      input.addEventListener('change', () => onChange(input.checked));
      const row = el('div', { class: 'field field-check' }, input, label, help);
      return row;
    }
    case 'number':
    case 'integer': {
      input = el('input', { id, type: 'text', inputmode: 'decimal', 'aria-describedby': describedBy });
      input.value = value === null || value === undefined ? '' : String(value);
      input.addEventListener('change', () => {
        const v = parseNumber(input.value, field.kind === 'integer');
        const bad = v === undefined || (v === null && !field.optional);
        invalid(input, bad, field.kind === 'integer' ? 'Enter a whole number.' : 'Enter a number.');
        if (!bad) onChange(v);
      });
      break;
    }
    case 'enum': {
      input = el('select', { id, 'aria-describedby': describedBy });
      if (field.optional) input.append(el('option', { value: '', text: '(none)' }));
      field.choices.forEach((c, i) => input.append(el('option', { value: String(i), text: c.label })));
      if (typeof value === 'string' && field.custom) {
        input.append(el('option', { value: 'custom', text: value }));
        input.value = 'custom';
      } else {
        const i = field.choices.findIndex((c) => sameEnum(c.value, value));
        input.value = i >= 0 ? String(i) : '';
      }
      input.addEventListener('change', () => {
        if (input.value === 'custom') return;
        onChange(input.value === '' ? null : field.choices[Number(input.value)].value);
      });
      break;
    }
    case 'multichoice': {
      const chosen = new Set(Array.isArray(value) ? value : []);
      const box = el('fieldset', { class: 'field choices', 'aria-describedby': describedBy },
        el('legend', { text: field.label }));
      for (const choice of field.choices) {
        const cid = `${id}-${choice}`;
        const cb = el('input', { id: cid, type: 'checkbox', value: choice });
        cb.checked = chosen.has(choice);
        cb.addEventListener('change', () => {
          if (cb.checked) chosen.add(choice); else chosen.delete(choice);
          onChange(field.choices.filter((c) => chosen.has(c)));
        });
        box.append(el('span', { class: 'choice' }, cb, el('label', { for: cid, text: choice })));
      }
      if (help) box.append(help);
      return box;
    }
    case 'list':
    case 'numbers': {
      input = el('input', { id, type: 'text', 'aria-describedby': describedBy,
        placeholder: field.kind === 'numbers' ? 'one value, or 36 separated by commas' : 'comma separated' });
      const shown = Array.isArray(value) ? value.join(', ') : (value ?? '');
      input.value = String(shown);
      input.addEventListener('change', () => {
        const parts = input.value.split(',').map((s) => s.trim()).filter((s) => s !== '');
        const numeric = field.kind === 'numbers' || field.item === 'number' || field.item === 'integer';
        if (!numeric) { onChange(parts); return; }
        const nums = parts.map((p) => parseNumber(p, field.item === 'integer'));
        const bad = nums.some((n) => n === undefined || n === null);
        invalid(input, bad, 'Enter numbers separated by commas.');
        if (bad) return;
        if (field.kind === 'numbers') onChange(nums.length === 0 ? null : nums.length === 1 ? nums[0] : nums);
        else onChange(nums);
      });
      break;
    }
    case 'points': {
      input = el('textarea', { id, rows: 5, 'aria-describedby': describedBy,
        placeholder: field.width === 3 ? 'x, y, z on each line' : 'x, y on each line' });
      input.value = (Array.isArray(value) ? value : []).map((p) => p.join(', ')).join('\n');
      input.addEventListener('change', () => {
        const rows = input.value.split('\n').map((l) => l.trim()).filter((l) => l);
        const points = rows.map((r) => r.split(/[ ,;\t]+/).map((s) => parseNumber(s, false)));
        const bad = points.some((p) => p.length !== field.width || p.some((n) => n === null || n === undefined));
        invalid(input, bad, `Enter ${field.width} numbers on each line.`);
        if (!bad) onChange(points);
      });
      break;
    }
    case 'json': {
      input = el('textarea', { id, rows: 3, class: 'mono', 'aria-describedby': describedBy });
      input.value = value === undefined ? '' : JSON.stringify(value);
      input.addEventListener('change', () => {
        try {
          const v = input.value.trim() === '' ? null : JSON.parse(input.value);
          invalid(input, false, '');
          onChange(v);
        } catch (err) {
          invalid(input, true, 'This is not valid JSON.');
        }
      });
      break;
    }
    default: {   // string
      input = el('input', { id, type: 'text', 'aria-describedby': describedBy });
      input.value = value ?? '';
      input.addEventListener('change', () => {
        onChange(input.value === '' && field.optional ? null : input.value);
      });
    }
  }
  return el('div', { class: `field field-${field.kind}` }, label, input, error, help);
}

// The names of the fields in `root` whose text does not parse.
export function fieldsInvalid(root) {
  return [...root.querySelectorAll('[aria-invalid="true"]')].map((input) => {
    const label = root.querySelector(`label[for="${input.id}"]`);
    return label ? label.firstChild.textContent.trim() : input.id;
  });
}

// The fields of `obj` that `names` lists, in that order, as one group; or,
// with names null, every field of the class not in `exclude`.
export function fieldGroup(classSchema, obj, names, { exclude = [], onChange } = {}) {
  const byName = new Map(classSchema.fields.map((f) => [f.name, f]));
  const fields = names ? names.map((n) => byName.get(n)).filter(Boolean)
    : classSchema.fields.filter((f) => !exclude.includes(f.name));
  const grid = el('div', { class: 'fields' });
  for (const field of fields) {
    grid.append(fieldInput(field, obj[field.name], (v) => {
      obj[field.name] = v;
      if (onChange) onChange(field.name, v);
    }));
  }
  return grid;
}
