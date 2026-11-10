/* night-planner viewer — hash-routed, no framework.
   Created by JXP and Claude */

/* `setup`, `inspection` and `priorities` carry the pre-plan steps across a
   route change. They have to live here because useTemplate() clones a fresh
   template on every navigation, so the setup form's DOM -- and the closure
   holding the inspected path -- are gone the moment we leave #/setup. Unlike
   a plan, there is no `dir=` to re-fetch from: nothing has been written to
   disk yet, so if this is lost the only honest move is to send the user back. */
const state = { plan: null, outputDir: null, instrument: null, date: null,
                setup: null, inspection: null, priorities: null };

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};
const hhmm = (iso) => (iso ? iso.slice(11, 16) : '—');
const mins = (a, b) => (new Date(b) - new Date(a)) / 60000;

/* Every plan time is ISO with the telescope's own UTC offset. Never format
   with Date's local-time methods -- the browser is usually in a different
   zone than the observatory, which silently shifts every label. Instead
   pull the offset out of the string and do the arithmetic in that frame. */
const offsetMs = (iso) => {
  const m = /([+-])(\d{2}):(\d{2})$/.exec(iso || '');
  if (!m) return 0;
  return (m[1] === '-' ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3])) * 60000;
};
const siteTime = (epochMs, offMs) =>
  new Date(epochMs + offMs).toISOString().slice(11, 16);

async function api(path, opts) {
  const resp = await fetch(path, opts);
  if (!resp.ok) {
    let detail;
    try { detail = (await resp.json()).detail; } catch { detail = await resp.text(); }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return resp.headers.get('content-type')?.includes('json')
    ? resp.json() : resp.text();
}

function useTemplate(id) {
  const view = $('#view');
  view.replaceChildren($(`#${id}`).content.cloneNode(true));
  return view;
}

/* ---------------------------------------------------------------- routing */

const routes = {
  '/': renderHome,
  '/setup': renderSetup,
  '/priorities': renderPriorities,
  '/plan': renderPlan,
  '/rejections': renderRejections,
  '/finders': renderFinders,
  '/starlist': renderStarlist,
  '/airmass': renderAirmass,
  '/nightchart': renderNightChart,
  '/log': renderLog,
};

function parseHash() {
  const [path, query] = (location.hash.slice(1) || '/').split('?');
  return { path: path || '/', params: new URLSearchParams(query || '') };
}

async function route() {
  const { path, params } = parseHash();
  if (params.get('dir')) state.outputDir = params.get('dir');
  if (params.get('instrument')) state.instrument = params.get('instrument');
  if (params.get('date')) state.date = params.get('date');

  renderNav(path);
  closeLightbox();
  lightboxSlots = [];
  const handler = routes[path] || renderHome;
  try {
    await handler(params);
  } catch (err) {
    $('#view').replaceChildren(notice(err.message, true));
  }
}

function renderNav(current) {
  const nav = $('#nav');
  nav.replaceChildren();
  if (!state.outputDir) return;
  const d = encodeURIComponent(state.outputDir);
  [['Plan', '/plan'], ['Rejections', '/rejections'], ['Finders', '/finders'],
   ['Starlist', '/starlist'], ['Airmass', '/airmass'],
   ['Night chart', '/nightchart'], ['Observing log', '/log']].forEach(([label, p]) => {
    const a = el('a', current === p ? 'active' : '', label);
    a.href = `#${p}?dir=${d}`;
    nav.append(a);
  });
  // Instrument, telescope and date on every plan page (T2.2), once the
  // plan for this directory is loaded; the directory name until then.
  const p = state.plan;
  $('#context').textContent = (p && p.output_dir === state.outputDir)
    ? `${p.instrument.toUpperCase()} · ${p.telescope} · ${p.date} · `
      + `${state.outputDir.split('/').pop()}`
    : state.outputDir.split('/').pop();
}

function notice(message, isError) {
  return el('div', 'notice' + (isError ? ' error' : ''), message);
}

/* ------------------------------------------------------------------ home */

async function renderHome() {
  useTemplate('tpl-home');
  $('#context').textContent = '';

  const instruments = await api('/api/instruments');
  const select = $('#instrument');
  // No pre-selected instrument: the list is alphabetical, so defaulting to
  // the first silently picks kast for someone who meant Keck.
  const placeholder = el('option', '', '— choose an instrument —');
  placeholder.value = '';
  select.append(placeholder);
  instruments.forEach((i) => {
    const suffix = i.supports_own_targets ? '' : ' (fixed to its own run)';
    const o = el('option', '', `${i.instrument} — ${i.telescope}${suffix}`);
    o.value = i.instrument;
    select.append(o);
  });
  select.required = true;

  $('#home-form').addEventListener('submit', (ev) => {
    ev.preventDefault();
    if (!select.value) return;
    const q = new URLSearchParams({ instrument: select.value, date: $('#date').value });
    location.hash = `#/setup?${q}`;
  });

  const list = $('#plan-list');
  const plans = await api('/api/plans');
  const ready = plans.filter((p) => p.has_plan);
  if (!ready.length) {
    list.append(el('div', 'none', 'No generated plans yet.'));
    return;
  }
  ready.forEach((p) => {
    const a = el('a', '', p.name);
    a.href = `#/plan?dir=${encodeURIComponent(p.output_dir)}`;
    list.append(a);
  });
}

/* ----------------------------------------------------------------- setup */

function addRow(container, fields) {
  const row = el('div', 'row');
  fields.forEach(({ placeholder, key, size }) => {
    const input = el('input');
    input.type = 'text';
    input.placeholder = placeholder;
    input.dataset.key = key;
    if (size) input.size = size;
    row.append(input);
  });
  const remove = el('button', 'ghost', '×');
  remove.type = 'button';
  remove.addEventListener('click', () => row.remove());
  row.append(remove);
  container.append(row);
}

function collectRows(container) {
  return [...container.querySelectorAll('.row')].map((row) => {
    const out = {};
    row.querySelectorAll('input').forEach((i) => { out[i.dataset.key] = i.value; });
    return out;
  });
}

async function renderSetup(params) {
  useTemplate('tpl-setup');
  const instrument = params.get('instrument') || state.instrument;
  const date = params.get('date') || state.date;
  $('#setup-lede').textContent = `${instrument} · ${date || 'no date set'}`;

  let targetsPath = null;

  /* T2.4: the columns the loader reads, from the server so the list can't
     drift from targets_io. */
  api('/api/targets/columns').then((cols) => {
    const fmt = (f) => `<b>${f}</b> (${(cols.aliases[f] || []).slice(0, 4).join(', ')})`;
    $('#column-list').innerHTML = `Required columns: ${cols.required.map(fmt).join('; ')}. `
      + `Optional: ${cols.optional.map((f) => f).join(', ')}. `
      + 'See docs/target_csv_guide.md.';
  }).catch(() => {});

  /* Configuration card: dropdowns limited to what the ETC can model. */
  const configFields = $('#config-fields');
  const configInputs = {};
  try {
    const opt = await api(`/api/instruments/${encodeURIComponent(instrument)}/options`);
    const prev = state.setup?.instrument === instrument ? (state.setup.config || {}) : {};
    const choice = (key, label, values, names = {}) => {
      const sel = el('select');
      values.forEach((v) => {
        const label = key === 'slit' ? Number(v).toFixed(1) : String(v);
        const o = el('option', '', names[v] && names[v] !== v ? `${names[v]} (${v})` : label);
        o.value = String(v);
        sel.append(o);
      });
      sel.value = String(prev[key] ?? opt.defaults[key]);
      configInputs[key] = sel;
      const l = el('label', '', label);
      l.append(sel);
      configFields.append(l);
    };
    choice('grism', 'Blue grism', opt.options.grism, opt.grism_names);
    choice('grating', 'Red grating', opt.options.grating);
    choice('dichroic', 'Dichroic', opt.options.dichroic);
    choice('slit', 'Slit width [arcsec]', opt.options.slit);
    choice('binning', 'Binning', opt.options.binning);
    const seeing = el('input');
    seeing.type = 'number';
    seeing.step = '0.1';
    seeing.min = '0.2';
    seeing.value = prev.seeing ?? opt.defaults.seeing;
    configInputs.seeing = seeing;
    const sl = el('label', '', 'Seeing [arcsec]');
    sl.append(seeing);
    configFields.append(sl);
    choice('mag_band', 'Magnitude band', opt.bands);
    choice('etc', 'Exposure model', opt.etcs,
           { lris: 'UCO/Lick ETC', kast: 'UCO/Lick ETC', empirical: 'empirical rule' });
    const sn = el('input');
    sn.type = 'number';
    sn.step = '0.5';
    sn.min = '1';
    sn.value = prev.target_sn ?? opt.defaults.target_sn;
    configInputs.target_sn = sn;
    const snl = el('label', '', 'Target S/N per sub-exposure');
    snl.append(sn);
    configFields.append(snl);
    choice('airmass_rule', 'ETC airmass over the block', opt.airmass_rules,
           { worst: 'worst in the block', mid: 'mid-block', best: 'best in the block' });
  } catch (err) {
    configFields.replaceChildren(notice(`Configuration options unavailable: ${err.message}`, true));
  }

  /* Scenarios (T4.1): presets plus free rows. */
  const scenarioFields = [
    { placeholder: 'name', key: 'name', size: 16 },
    { placeholder: 'seeing ″', key: 'seeing', size: 6 },
    { placeholder: 'start HH:MM', key: 'start', size: 8 },
    { placeholder: 'block from HH:MM', key: 'bstart', size: 10 },
    { placeholder: 'block to HH:MM', key: 'bend', size: 10 }];
  const addScenario = (values = {}) => {
    addRow($('#scenarios'), scenarioFields);
    const rows = $('#scenarios').children;
    const inputs = rows[rows.length - 1].querySelectorAll('input');
    scenarioFields.forEach((f, i) => { if (values[f.key] != null) inputs[i].value = values[f.key]; });
  };
  [['good 0.6″', { name: 'good seeing', seeing: 0.6 }],
   ['median 0.8″', { name: 'median seeing', seeing: 0.8 }],
   ['poor 1.2″', { name: 'poor seeing', seeing: 1.2 }],
   ['lost first half', { name: 'lost first half', bstart: 'night', bend: '00:00' }]]
    .forEach(([label, values]) => {
      const b = el('button', 'ghost', `+ ${label}`);
      b.type = 'button';
      b.addEventListener('click', () => addScenario(values));
      $('#scenario-presets').append(b);
    });
  $('#add-scenario').addEventListener('click', () => addScenario());
  (state.setup?.scenarios || []).forEach((sc) => addScenario({
    name: sc.name, seeing: sc.seeing, start: sc.start,
    bstart: sc.blocks?.[0]?.start, bend: sc.blocks?.[0]?.end }));

  $('#add-block').addEventListener('click', () => addRow($('#blocks'), [
    { placeholder: 'from HH:MM', key: 'start' },
    { placeholder: 'to HH:MM', key: 'end' },
    { placeholder: 'reason', key: 'reason', size: 22 }]));

  /* Reads the table and moves on. This is the page's one forward action, so
     a table we cannot read unambiguously must stop here rather than landing
     the user on a priorities page it could not populate. */
  $('#inspect-btn').addEventListener('click', async () => {
    const button = $('#inspect-btn');
    const box = $('#inspect-result');
    const foot = $('#inspect-result-foot');
    button.disabled = true;
    foot.replaceChildren(el('p', 'hint', 'Reading the target table…'));
    box.replaceChildren();
    try {
      const file = $('#targets-file').files[0];
      let data;
      if (file) {
        const body = new FormData();
        body.append('file', file);
        data = await api('/api/targets/inspect', { method: 'POST', body });
      } else {
        const path = $('#targets-path').value.trim();
        if (!path) throw new Error('choose a file or type a path');
        data = await api(`/api/targets/inspect?path=${encodeURIComponent(path)}`,
                         { method: 'POST' });
      }
      if (!data.mapping.ok) {
        // Priorities on a table whose columns are still ambiguous would be
        // priorities on rows we cannot identify. Report it in place.
        foot.replaceChildren();
        box.replaceChildren(renderInspection(data));
        return;
      }

      state.inspection = data;
      state.setup = {
        instrument,
        date,
        targetsPath: data.path,
        start: $('#start').value.trim(),
        maxTargets: $('#max-targets').value,
        outputDir: $('#output-dir').value.trim(),
        assumeMasks: $('#assume-masks').checked,
        noPartials: $('#no-partials').checked,
        blocks: collectRows($('#blocks')).filter((b) => b.start && b.end),
        config: Object.fromEntries(Object.entries(configInputs)
          .map(([k, input]) => [k, input.value])),
        scenarios: collectRows($('#scenarios')).filter((r) => r.name).map((r) => ({
          name: r.name,
          seeing: r.seeing ? Number(r.seeing) : null,
          start: r.start || null,
          blocks: r.bstart && r.bend
            ? [{ start: r.bstart, end: r.bend, reason: r.name }] : [],
        })),
      };
      // Seed every target at the default, so an untouched page generates
      // precisely the night the planner produced before priorities existed.
      state.priorities = Object.fromEntries(
        data.preview.map((r) => [r.name, r.priority ?? data.default_priority]));
      location.hash = '#/priorities';
    } catch (err) {
      foot.replaceChildren();
      box.replaceChildren(notice(err.message, true));
    } finally {
      button.disabled = false;
    }
  });
}

/* ------------------------------------------------------------ priorities */

async function renderPriorities() {
  // No server round-trip can rescue this page: nothing is on disk yet, so
  // there is no output_dir to re-read. A reload therefore lands here empty,
  // and saying so beats rendering a page with no targets in it.
  if (!state.inspection || !state.setup) {
    useTemplate('tpl-priorities');
    const back = el('a', '', 'Start again from the targets page');
    back.href = '#/setup';
    $('#prio-notes').replaceChildren(
      notice('This page is built from the target table you just read, and '
             + 'that is lost on a reload.', true), back);
    $('#prio-list').remove();
    return;
  }

  const data = state.inspection;
  const setup = state.setup;
  useTemplate('tpl-priorities');
  $('#prio-lede').textContent =
    `${setup.instrument} · ${setup.date || 'no date set'} · `
    + `${data.n_rows} targets → ${setup.outputDir || 'no output directory set'}`;

  // The mapping summary and the source-format caveat were shown on the setup
  // page before; they still have to be seen, so they lead this page instead.
  $('#prio-notes').replaceChildren(renderInspection(data, { preview: false }));

  const list = $('#prio-list');
  const rows = [...data.preview].sort(
    (a, b) => (state.priorities[a.name] ?? 1) - (state.priorities[b.name] ?? 1)
      || String(a.name).localeCompare(String(b.name)));

  const tierNote = () => {
    const values = [...new Set(Object.values(state.priorities))].sort((a, b) => a - b);
    $('#prio-tiers').textContent = values.length === 1
      ? 'One tier — scheduled exactly as before.'
      : `${values.length} tiers: ${values.map((v) => 'P' + v).join(', ')}`;
  };

  list.replaceChildren(...rows.map((r) => {
    const row = el('div', 'prio-row');
    row.dataset.target = r.name;
    const input = el('input', 'prio');
    input.type = 'number';
    input.step = '0.5';
    input.min = '0';
    input.value = state.priorities[r.name] ?? data.default_priority;
    input.addEventListener('change', () => {
      state.priorities[r.name] = Number(input.value) || data.default_priority;
      tierNote();
    });
    row.append(input);
    const label = el('div', 'prio-label');
    label.append(el('b', '', String(r.name)));
    label.append(el('span', 'hint',
      ` mag ${r.mag ?? '—'} · RA ${r.ra_deg.toFixed(3)}° · Dec ${r.dec_deg.toFixed(3)}°`));
    const extra = [r.tags ? `tags: ${r.tags}` : '',
                   r.dm != null ? `DM ${Math.round(r.dm)}` : ''].filter(Boolean).join(' · ');
    if (extra) label.append(el('span', 'hint prio-tags', ` · ${extra}`));
    row.append(label);
    return row;
  }));
  tierNote();
  const showTags = $('#prio-show-tags');
  const applyTags = () => list.querySelectorAll('.prio-tags')
    .forEach((n) => { n.style.display = showTags.checked ? '' : 'none'; });
  showTags.addEventListener('change', applyTags);
  applyTags();

  if (data.preview_truncated) {
    $('#prio-notes').append(el('p', 'hint',
      `${data.preview_truncated} further targets are not listed here; `
      + `they keep the priority their table already carried.`));
  }

  $('#prio-bulk-apply').onclick = () => {
    const value = Number($('#prio-bulk').value);
    if (!value && value !== 0) return;
    list.querySelectorAll('.prio-row').forEach((row) => {
      row.querySelector('input.prio').value = value;
      state.priorities[row.dataset.target] = value;
    });
    tierNote();
  };

  $('#prio-back').onclick = () => { location.hash = '#/setup'; };

  $('#generate-btn').onclick = async () => {
    const status = $('#generate-status');
    const button = $('#generate-btn');
    button.disabled = true;
    status.replaceChildren(notice('Generating… the exposure-time calculator is '
      + 'queried live per target, so this takes a minute or two.'));
    try {
      if (!setup.targetsPath) {
        throw new Error('no target table — start again from the targets page');
      }
      if (!setup.outputDir) {
        throw new Error('set an output directory, so the plan does not land '
          + 'in another run\'s folder');
      }

      const plan = await api('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instrument: setup.instrument,
          date: setup.date || null,
          targets_csv: setup.targetsPath,
          output_dir: setup.outputDir,
          start: setup.start || null,
          max_targets: Number(setup.maxTargets) || null,
          assume_masks: setup.assumeMasks,
          no_partials: setup.noPartials,
          blocks: setup.blocks,
          forced: [],
          priorities: state.priorities,
          grism: setup.config?.grism || null,
          grating: setup.config?.grating || null,
          dichroic: setup.config?.dichroic || null,
          slit: setup.config?.slit ? Number(setup.config.slit) : null,
          binning: setup.config?.binning || null,
          seeing: setup.config?.seeing ? Number(setup.config.seeing) : null,
          mag_band: setup.config?.mag_band || null,
          etc: setup.config?.etc || null,
          target_sn: setup.config?.target_sn ? Number(setup.config.target_sn) : null,
          airmass_rule: setup.config?.airmass_rule || null,
          scenarios: setup.scenarios || [],
        }),
      });
      state.plan = plan;
      state.outputDir = plan.output_dir;
      location.hash = `#/plan?dir=${encodeURIComponent(plan.output_dir)}`;
    } catch (err) {
      status.replaceChildren(notice(err.message, true));
    } finally {
      // No stopPolling() here: nothing on this page starts a poll, and
      // the call this replaced was a ReferenceError that left the button
      // stuck disabled after any failed generate.
      button.disabled = false;
    }
  };
}

function renderInspection(data, opts = {}) {
  const showPreview = opts.preview !== false;
  const wrap = el('div');
  const m = data.mapping;
  if (!m.ok) {
    wrap.append(notice(`Needs a hand: ${m.issues.join('; ')}`, true));
  } else {
    wrap.append(notice(`Read ${data.n_rows} targets. `
      + Object.entries(m.columns).map(([k, v]) => `${k} ← ${v}`).join(', ')
      + (m.ra_unit === 'hour' ? ' (RA in hours)' : '')));
  }
  // Where the table came from decides whether a two-candidate slit is
  // even meaningful, so say so here rather than letting it surprise
  // someone on the Finders page.
  const fmt = data.source_format;
  if (fmt) {
    wrap.append(el('p', 'hint', fmt.format === 'ffff-pz'
      ? (fmt.has_candidates
        ? 'FFFF-PZ table with PATH candidates — the two-candidate slit is '
          + 'available for these targets.'
        : 'FFFF-PZ table, but no Sec_* candidate columns — finders will use '
          + 'the parallactic angle.')
      : 'Generic target list, not an FFFF-PZ pull. These are not localised '
        + 'FRBs with ranked host candidates, so finders will use the '
        + 'parallactic angle.'));
  }
  // Priority values the table carried but we could not read as numbers. The
  // targets are still perfectly usable; they just have no ranking, and that
  // has to be said rather than silently defaulted.
  Object.entries(data.field_coercions || {}).forEach(([field, c]) => {
    if (!c.n_coerced) return;
    wrap.append(notice(
      `The '${c.column}' column has ${c.n_coerced} value(s) that can't be read as `
      + `${field === 'required' ? 'true/false' : 'positive minutes'} `
      + `(${c.examples.join(', ')}) — those rows are treated as `
      + `${field === 'required' ? 'not required' : 'having no user time (the ETC decides)'}.`));
  });
  const coerced = data.priority_coercions;
  if (coerced && coerced.n_coerced) {
    wrap.append(notice(
      `The '${coerced.column}' column has ${coerced.n_coerced} value(s) that `
      + `are not numbers (${coerced.examples.join(', ')}) — those targets `
      + `start at the default priority of ${data.default_priority}.`));
  }
  if (showPreview && data.preview.length) {
    const shown = data.preview.length;
    wrap.append(el('p', 'hint', data.preview_truncated
      ? `Showing the first ${shown} of ${data.n_rows} targets `
        + `(${data.preview_truncated} more not listed).`
      : `All ${shown} targets:`));
    const scroller = el('div', 'preview-scroll');
    const table = el('table', 'data');
    table.innerHTML = '<tr><th>name</th><th class="num">RA °</th>'
      + '<th class="num">Dec °</th><th class="num">mag</th></tr>'
      + data.preview.map((r) => `<tr><td>${r.name}</td>`
        + `<td class="num">${r.ra_deg.toFixed(4)}</td>`
        + `<td class="num">${r.dec_deg.toFixed(4)}</td>`
        + `<td class="num">${r.mag ?? '—'}</td></tr>`).join('');
    scroller.append(table);
    wrap.append(scroller);
  }
  return wrap;
}

/* ------------------------------------------------------------ plan viewer */

async function loadPlan() {
  if (!state.outputDir) throw new Error('no plan selected — start from the home page');
  if (!state.plan || state.plan.output_dir !== state.outputDir) {
    state.plan = await api(`/api/plan?output_dir=${encodeURIComponent(state.outputDir)}`);
  }
  return state.plan;
}

function targetClass(t) {
  const notes = t.notes || '';
  // PARTIAL is the planner's own doing -- a truncated exposure dropped into
  // idle time -- so it reads differently from FORCED, which the observer
  // asked for by name.
  if (notes.startsWith('PARTIAL')) return 'partial';
  if (notes.startsWith('FORCED')) return 'forced';
  return t.mode.startsWith('MOS') ? 'mos' : 'science';
}

/* A single tooltip node reused by every segment: cheaper than one per
   segment, and it can be positioned against the viewport so it never gets
   clipped by the timeline's own overflow. */
let tooltip = null;

function attachHover(node, heading, rows) {
  node.addEventListener('mouseenter', () => {
    if (!tooltip) {
      tooltip = el('div', 'tooltip');
      document.body.append(tooltip);
    }
    tooltip.replaceChildren(el('b', '', heading));
    rows.filter(([, v]) => v !== null && v !== undefined && v !== '')
      .forEach(([k, v]) => {
        const line = el('div', 'trow');
        if (k) line.append(el('span', 'tkey', k));
        line.append(el('span', 'tval', String(v)));
        tooltip.append(line);
      });
    tooltip.style.display = 'block';
  });
  node.addEventListener('mousemove', (ev) => {
    if (!tooltip) return;
    // Flip to the left of the cursor near the right edge so the card stays
    // on screen on a narrow window.
    const width = tooltip.offsetWidth;
    const flip = ev.clientX + width + 24 > window.innerWidth;
    tooltip.style.left = `${flip ? ev.clientX - width - 14 : ev.clientX + 14}px`;
    tooltip.style.top = `${Math.min(ev.clientY + 14,
      window.innerHeight - tooltip.offsetHeight - 10)}px`;
  });
  node.addEventListener('mouseleave', () => {
    if (tooltip) tooltip.style.display = 'none';
  });
}

function targetDetail(t) {
  const window = (t.window_start && t.window_end)
    ? `${hhmm(t.window_start)}–${hhmm(t.window_end)}` : null;
  const coords = (t.ra_deg !== null && t.dec_deg !== null)
    ? `${(t.ra_deg / 15).toFixed(3)}h  ${t.dec_deg >= 0 ? '+' : ''}${t.dec_deg.toFixed(2)}°`
    : null;
  return [
    ['mode', t.mode],
    ['mag', t.mag?.toFixed(2)],
    ['RA / Dec', coords],
    ['airmass', t.airmass != null ? `${t.airmass.toFixed(2)}`
      + (t.airmass_rule ? ` (${t.airmass_rule} over the block; best ${t.airmass_min?.toFixed(2)})` : '') : null],
    ['S/N red', t.sn_sub_red != null
      ? `${t.sn_sub_red.toFixed(1)} per sub, ${t.sn_comb_red?.toFixed(1)} combined` : null],
    ['red', t.exposure_red],
    ['blue', t.exposure_blue],
    ['on target', `${Math.round(t.on_target_min)} min`],
    ['slew', t.slew_min ? `${Math.round(t.slew_min)} min`
      + (t.slew_reason ? ` (${t.slew_reason})` : '') : null],
    ['acquisition', t.acq_min ? `${Math.round(t.acq_min)} min` : null],
    ['readout', t.readout_min ? `${t.readout_min.toFixed(1)} min` : null],
    ['AM<2 window', window],
    ['', t.notes],
  ];
}

function renderTimeline(plan, host) {
  // Span the drawn night from sunset to sunrise so the twilight marks have
  // somewhere to sit, even when observing starts well after dark.
  const t0 = new Date(plan.sun.sunset).getTime();
  const t1 = new Date(plan.sun.sunrise).getTime();
  const pct = (iso) => ((new Date(iso).getTime() - t0) / (t1 - t0)) * 100;

  const track = el('div', 'track');
  const off = offsetMs(plan.sun.sunset);

  const hour = 3600000;
  for (let t = Math.ceil((t0 + off) / hour) * hour - off; t <= t1; t += hour) {
    const tick = el('div', 'tick', siteTime(t, off));
    tick.style.left = `${((t - t0) / (t1 - t0)) * 100}%`;
    track.append(tick);
  }

  const place = (start, end, cls, label, detail) => {
    const seg = el('div', `seg ${cls}`, label || '');
    seg.style.left = `${pct(start)}%`;
    seg.style.width = `${Math.max(pct(end) - pct(start), 0.25)}%`;
    const heading = `${label || cls} · ${hhmm(start)}–${hhmm(end)} `
      + `(${Math.round(mins(start, end))} min)`;
    attachHover(seg, heading, detail || []);
    track.append(seg);
  };

  plan.overheads.forEach((o) => place(o.start, o.end, 'overhead', '', []));
  plan.blocks.forEach((b) => place(b.start, b.end, 'blocked', b.reason,
    [['reason', b.reason]]));
  plan.schedule.forEach((t) => {
    // Slew, then acquisition, then science. Older plans carry no acq_min,
    // so their whole pre-science stretch is drawn as slew, as before.
    const acq = t.acq_min || 0;
    const acqStart = new Date(new Date(t.science_start).getTime() - acq * 60000)
      .toISOString();
    if (t.slew_min > 0) {
      place(t.start, acq ? acqStart : t.science_start, 'slew', '',
        [['slew to', t.name], ['duration', `${Math.round(t.slew_min)} min`],
         ['why', t.slew_reason || null]]);
    }
    if (acq > 0) {
      place(acqStart, t.science_start, 'acq', '',
        [['acquire', t.name], ['duration', `${Math.round(acq)} min`]]);
    }
    place(t.science_start, t.end, targetClass(t), t.name, targetDetail(t));
  });

  plan.idle_gaps.forEach((g) => {
    const seg = el('div', 'seg idle-hover');
    seg.style.left = `${pct(g.start)}%`;
    seg.style.width = `${Math.max(pct(g.end) - pct(g.start), 0.25)}%`;
    attachHover(seg, `idle · ${hhmm(g.start)}–${hhmm(g.end)} `
      + `(${Math.round(mins(g.start, g.end))} min)`,
      [['', 'nothing scheduled and nothing blocking']]);
    track.append(seg);
  });

  // Dusk and dawn each bunch three marks into ~2 hours, so alternate the
  // label height and flip the dawn labels to the left of their line --
  // otherwise they overlap into an unreadable smear at both ends.
  Object.entries({
    sunset: 'sunset', dusk_nautical: '−12°', dusk_astronomical: '−18°',
    dawn_astronomical: '−18°', dawn_nautical: '−12°', sunrise: 'sunrise',
  }).forEach(([key, label], index) => {
    const iso = plan.sun[key];
    if (!iso) return;
    const mark = el('div', 'sunmark');
    mark.style.left = `${pct(iso)}%`;
    const text = el('span', '', `${label} ${hhmm(iso)}`);
    text.style.bottom = index % 2 ? '-2.5rem' : '-1.3rem';
    if (index >= 3) { text.style.left = 'auto'; text.style.right = '2px'; }
    mark.append(text);
    track.append(mark);
  });

  host.append(track);

  // LST under the local-time axis (T2.3). Sidereal time runs 1.0027379x
  // faster than solar, so it is extrapolated from the LST at night start.
  if (plan.lst_start_h != null) {
    const row = el('div', 'lst-row');
    const n0 = new Date(plan.night_start).getTime();
    for (let t = Math.ceil((t0 + off) / hour) * hour - off; t <= t1; t += hour) {
      const lst = ((plan.lst_start_h + ((t - n0) / hour) * 1.0027379) % 24 + 24) % 24;
      const h = Math.floor(lst);
      const m = Math.floor((lst - h) * 60);
      const tick = el('div', 'tick',
        `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`);
      tick.style.left = `${((t - t0) / (t1 - t0)) * 100}%`;
      row.append(tick);
    }
    host.append(row, el('div', 'lst-label', 'upper axis: local time · lower axis: LST'));
  }
}

async function renderPlan() {
  const plan = await loadPlan();
  useTemplate('tpl-plan');
  renderNav('/plan');

  /* Scenario tabs and comparison (T4.1), when this night has several. */
  try {
    const sc = await api(`/api/scenarios?output_dir=${encodeURIComponent(state.outputDir)}`);
    if (sc.scenarios.length) {
      const host = $('#scenario-tabs');
      const tabs = el('div', 'tabs');
      sc.scenarios.forEach((e) => {
        const a = el('a', e.slug === sc.active ? 'tab active' : 'tab', e.name);
        a.href = `#/plan?dir=${encodeURIComponent(e.dir)}`;
        tabs.append(a);
      });
      const table = el('table', 'data compare');
      table.innerHTML = '<tr><th>scenario</th><th class="num">seeing [″]</th>'
        + '<th class="num">targets</th><th class="num">on target [h]</th>'
        + '<th class="num">idle [min]</th><th>only in this scenario</th></tr>'
        + sc.scenarios.map((e) => `<tr${e.slug === sc.active ? ' class="active"' : ''}>`
          + `<td>${e.name}</td><td class="num">${e.seeing ?? 'plan'}</td>`
          + `<td class="num">${e.n_scheduled ?? '—'}</td>`
          + `<td class="num">${e.on_target_h ?? '—'}</td>`
          + `<td class="num">${e.idle_min != null ? Math.round(e.idle_min) : '—'}</td>`
          + `<td>${(e.unique || []).join(', ') || '—'}</td></tr>`).join('');
      host.append(tabs, table);
    }
  } catch { /* no scenarios: a single plan */ }

  const s = plan.summary;
  const head = $('#plan-head');
  head.append(el('p', 'lede',
    `${plan.instrument.toUpperCase()} · ${plan.telescope} · ${plan.date} · `
    + `${hhmm(plan.night_start)}–${hhmm(plan.night_end)} (${plan.timezone})`));

  // T2.8: what this plan assumed, saved with it in plan_result.json.
  const assumptions = Object.entries(plan.assumptions || {});
  const at = $('#assumptions-table');
  if (assumptions.length) {
    at.replaceChildren(...assumptions.map(([k, v]) => {
      const tr = el('tr');
      const val = el('td', String(v) === 'NOT SET' ? 'notset' : '', String(v));
      tr.append(el('th', '', k), val);
      return tr;
    }));
  } else {
    at.replaceChildren(el('tr', '', 'This plan predates the assumptions record; '
      + 'regenerate it to see them.'));
  }

  const stats = el('div', 'stats');
  [[`${s.n_scheduled}`, 'targets'],
   [`${(s.on_target_min / 60).toFixed(1)} h`, 'on target'],
   [`${Math.round(s.utilization * 100)}%`, 'utilization'],
   [`${Math.round(s.slew_min)} min`, 'slew'],
   [`${Math.round(s.acq_min || 0)} min`, 'acquisition'],
   [`${Math.round(s.readout_min || 0)} min`, 'readout'],
   [`${Math.round(s.overhead_min)} min`, 'overheads'],
   [`${Math.round(s.idle_min)} min`, 'idle']].forEach(([value, label]) => {
    const stat = el('div', 'stat');
    stat.append(el('b', '', value), el('span', '', label));
    stats.append(stat);
  });
  head.append(stats);

  const exportRow = el('div', 'row');
  const nameInput = el('input');
  nameInput.type = 'text';
  nameInput.placeholder = 'export name';
  nameInput.value = plan.output_dir.split('/').pop();
  const exportBtn = el('button', 'primary', 'Export .zip');
  exportBtn.addEventListener('click', () => {
    const q = new URLSearchParams({ output_dir: plan.output_dir, name: nameInput.value });
    window.location = `/api/export?${q}`;
  });
  exportRow.append(nameInput, exportBtn);
  head.append(exportRow);

  renderTimeline(plan, $('#timeline'));

  const legend = $('#legend');
  [['science', 'longslit'], ['mos', 'MOS'], ['forced', 'forced/truncated'],
   ['partial', 'partial (backfilled)'],
   ['slew', 'slew'], ['acq', 'acquisition'], ['overhead', 'standards, focus'],
   ['blocked', 'blocked'], ['idle', 'idle']].forEach(([cls, label]) => {
    const item = el('span');
    const swatch = el('i', cls);
    // Idle's swatch is a hatch defined in CSS; an inline background would
    // override it and show a flat block that doesn't match the timeline.
    if (cls !== 'idle') swatch.style.background = `var(--${cls})`;
    item.append(swatch, document.createTextNode(label));
    legend.append(item);
  });

  if (plan.overruns.length) {
    const last = plan.overruns[plan.overruns.length - 1];
    $('#overruns').append(notice(
      `The end-of-night sequence runs past the end of the night — “${last.label}” ends `
      + `${Math.round(last.minutes_past_end)} min after ${hhmm(plan.night_end)}. `
      + 'The morning standard should be taken before it gets much brighter. '
      + '(Calibrations are not scheduled; see the Observing log.)'));
  }

  if (plan.idle_gaps.length) {
    const total = plan.idle_gaps.reduce((a, g) => a + mins(g.start, g.end), 0);
    $('#overruns').append(notice(`Idle: ${Math.round(total)} min across `
      + `${plan.idle_gaps.length} gap(s) — `
      + plan.idle_gaps.map((g) => `${hhmm(g.start)}–${hhmm(g.end)}`).join(', ')));
  }

  $('#plan-table').innerHTML =
    '<tr><th>Science (local)</th><th>Target</th><th>Mode</th>'
    + '<th class="num">mag</th><th class="num">AM</th><th>Exposure [n × s]</th>'
    + '<th class="num">slew [min]</th><th class="num">acq [min]</th>'
    + '<th class="num">on target [min]</th><th class="num">readout [min]</th>'
    + '<th class="num" title="median continuum S/N per pixel, red arm: one '
    + 'sub-exposure / all combined">S/N red [sub / comb]</th>'
    + '<th class="tagcol">Tags</th><th class="num tagcol">DM</th>'
    + '<th>Notes</th></tr>'
    + plan.schedule.map((t) => {
      const pill = t.mode.startsWith('MOS') ? '<span class="pill mos">MOS</span>'
        : (t.notes || '').startsWith('PARTIAL') ? '<span class="pill partial">partial</span>'
        : (t.notes || '').startsWith('FORCED') ? '<span class="pill forced">forced</span>' : '';
      const req = t.required ? ' <span class="pill no" title="full time or nothing: never truncated">required</span>' : '';
      return `<tr><td>${hhmm(t.science_start)}–${hhmm(t.end)}</td>`
        + `<td><a href="#/airmass?dir=${encodeURIComponent(plan.output_dir)}&target=${t.name}">${t.name}</a></td>`
        + `<td>${pill} ${t.mode}${req}</td>`
        + `<td class="num">${t.mag?.toFixed(1) ?? '—'}</td>`
        + `<td class="num"${t.airmass_rule ? ` title="ETC airmass (${t.airmass_rule} over the block); best tonight ${t.airmass_min?.toFixed(2) ?? '—'}"` : ''}>`
        + `${t.airmass?.toFixed(2) ?? '—'}</td>`
        + `<td>${t.exposure_red || '—'}</td>`
        + `<td class="num"${t.slew_reason ? ` title="${t.slew_reason}"` : ''}>`
        + `${Math.round(t.slew_min)}${t.slew_reason ? '*' : ''}</td>`
        + `<td class="num">${Math.round(t.acq_min || 0)}</td>`
        + `<td class="num" title="${t.time_source ? `time from: ${t.time_source}` : ''}`
        + `${t.etc_min != null && t.time_source !== 'ETC' ? `; ETC estimate ${t.etc_min.toFixed(0)} min` : ''}">`
        + `${Math.round(t.on_target_min)}`
        + `${t.time_source ? `<br><span class="hint">${t.time_source}`
          + `${t.etc_min != null && t.time_source === 'user' ? ` (ETC ${t.etc_min.toFixed(0)})` : ''}</span>` : ''}</td>`
        + `<td class="num">${(t.readout_min || 0).toFixed(1)}</td>`
        + `<td class="num">${t.sn_sub_red != null
          ? `${t.sn_sub_red.toFixed(1)} / ${t.sn_comb_red?.toFixed(1) ?? '—'}` : '—'}</td>`
        + `<td class="tagcol">${t.tags || ''}</td>`
        + `<td class="num tagcol">${t.dm != null ? Math.round(t.dm) : ''}</td>`
        + `<td>${t.notes || ''}</td></tr>`;
    }).join('');
  const tagToggle = $('#plan-show-tags');
  tagToggle.addEventListener('change', () =>
    $('#plan-table').classList.toggle('show-tags', tagToggle.checked));
}

/* ------------------------------------------------------------ rejections */

async function renderRejections() {
  const plan = await loadPlan();
  useTemplate('tpl-rejections');
  renderNav('/rejections');

  const byStage = {};
  plan.decisions.forEach((d) => {
    byStage[d.stage] = (byStage[d.stage] || 0) + (d.status === 'rejected' ? 1 : 0);
  });
  $('#rej-summary').append(el('p', 'lede',
    `${plan.decisions.length} targets considered, ${plan.summary.n_scheduled} scheduled. `
    + 'Rejections by stage: '
    + Object.entries(byStage).filter(([, n]) => n)
      .map(([stage, n]) => `${stage} (${n})`).join(', ')));

  renderRescue(plan);

  const order = (d) => (d.status === 'scheduled' ? 0 : 1);
  $('#rej-table').innerHTML =
    '<tr><th>Target</th><th class="num">mag</th><th class="num">Dec</th>'
    + '<th>Status</th><th>Stage</th><th>Reason</th></tr>'
    + [...plan.decisions].sort((a, b) => order(a) - order(b)
        || a.name.localeCompare(b.name))
      .map((d) => `<tr class="${d.status}">`
        + `<td>${d.name}</td>`
        + `<td class="num">${d.mag?.toFixed(1) ?? '—'}</td>`
        + `<td class="num">${d.dec_deg?.toFixed(1) ?? '—'}</td>`
        + `<td><span class="pill ${d.status === 'scheduled' ? 'ok' : 'no'}">`
        + `${d.status}</span></td>`
        + `<td>${d.stage}</td><td>${d.reason}</td></tr>`).join('');
}

/* Every rejected target is offerable. Filtering to "only the ones that ran
   out of time" was too clever: a target dropped for 0.50 h at AM<2 when the
   rule wants >0.5 h is marginally observable, and whether a short exposure
   on it is worth taking is the observer's call, not the tool's. The planner
   re-checks pointability when it places a forced target and reports plainly
   if it can't, so an impossible choice fails loudly rather than silently. */
function rescuable(plan) {
  const forcedAlready = new Set(plan.schedule
    .filter((t) => (t.notes || '').startsWith('FORCED')).map((t) => t.name));
  return plan.decisions
    .filter((d) => d.status === 'rejected' && !forcedAlready.has(d.name))
    .map((d) => {
      // The scheduler says how much room the window actually had left;
      // use it as the default so the suggestion starts out feasible.
      const m = /only\s+(\d+)\s+min left/.exec(d.reason);
      return { ...d, available: m ? Number(m[1]) : null };
    })
    .sort((a, b) => a.stage.localeCompare(b.stage) || a.name.localeCompare(b.name));
}

function renderRescue(plan) {
  const pick = $('#rescue-pick');
  const minsInput = $('#rescue-mins');
  const chosen = $('#rescue-chosen');
  const candidates = rescuable(plan);
  const byName = Object.fromEntries(candidates.map((d) => [d.name, d]));

  // Forcing appends after the last scheduled target, so a target whose
  // window shuts before then can't be caught that way. Still offered --
  // just flagged, since the observer may know something the plan doesn't.
  const scheduleEnd = plan.schedule.length
    ? plan.schedule.map((t) => t.end).sort().slice(-1)[0] : plan.night_start;

  pick.replaceChildren();
  const placeholder = el('option', '', candidates.length
    ? '— choose a rejected target —' : '— nothing was rejected —');
  placeholder.value = '';
  pick.append(placeholder);

  const stages = [...new Set(candidates.map((d) => d.stage))].sort();
  stages.forEach((stage) => {
    const group = document.createElement('optgroup');
    group.label = stage;
    candidates.filter((d) => d.stage === stage).forEach((d) => {
      const o = el('option', '', `${d.name}  (mag ${d.mag?.toFixed(1) ?? '—'})`);
      o.value = d.name;
      group.append(o);
    });
    pick.append(group);
  });

  // Pre-fill the minutes box with whatever room the scheduler reported.
  pick.onchange = () => {
    const d = byName[pick.value];
    minsInput.value = d?.available ?? '';
  };

  const addRowFor = (name, minutes) => {
    if (chosen.querySelector(`[data-target="${name}"]`)) return;
    const d = byName[name];
    const row = el('div', 'rescue-row');
    row.dataset.target = name;

    const mins = el('input', 'mins');
    mins.type = 'number';
    mins.min = '1';
    mins.value = minutes ?? d?.available ?? '';

    const label = el('div', 'rescue-label');
    label.append(el('b', '', name));
    if (d) label.append(el('span', 'hint', ` ${d.stage} · ${d.reason}`));

    if (d?.window_end && d.window_end <= scheduleEnd) {
      label.append(el('div', 'warn',
        `window closed at ${hhmm(d.window_end)}, before the schedule ends at `
        + `${hhmm(scheduleEnd)} — forcing appends after the last target, so the `
        + 'planner will likely refuse to point there'));
    }

    const remove = el('button', 'ghost', '×');
    remove.type = 'button';
    remove.addEventListener('click', () => row.remove());

    row.append(mins, label, remove);
    chosen.append(row);
  };

  // Anything already forced starts in the list, so regenerating without
  // touching it keeps it, and removing it drops it.
  plan.schedule.filter((t) => (t.notes || '').startsWith('FORCED'))
    .forEach((t) => addRowFor(t.name, Math.round(t.on_target_min)));

  $('#rescue-add').onclick = () => {
    if (!pick.value) return;
    addRowFor(pick.value, Number(minsInput.value) || null);
    pick.value = '';
    minsInput.value = '';
  };

  $('#regen-btn').onclick = async () => {
    const forced = [...chosen.querySelectorAll('.rescue-row')]
      .map((row) => ({
        target: row.dataset.target,
        minutes: Number(row.querySelector('input.mins').value),
      }))
      .filter((f) => f.minutes > 0);

    const status = $('#regen-status');
    $('#regen-btn').disabled = true;
    status.textContent = 'Regenerating — a minute or two while the ETC is queried…';
    try {
      const updated = await api('/api/regenerate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_dir: plan.output_dir, forced }),
      });
      state.plan = updated;
      location.hash = `#/plan?dir=${encodeURIComponent(updated.output_dir)}`;
    } catch (err) {
      status.replaceChildren(notice(err.message, true));
    } finally {
      $('#regen-btn').disabled = false;
    }
  };
}

/* --------------------------------------------------------------- finders */

/* Survives the re-render that follows a generate, so the form still
   shows what was actually asked for. */
let lastSlitMode = 'parallactic';

async function renderFinders() {
  const plan = await loadPlan();
  useTemplate('tpl-finders');
  renderNav('/finders');
  const chosen = $(`input[name="fd-slit"][value="${lastSlitMode}"]`);
  if (chosen) chosen.checked = true;

  $('#fd-generate').addEventListener('click', async () => {
    const status = $('#fd-status');
    const button = $('#fd-generate');
    lastSlitMode = $('input[name="fd-slit"]:checked').value;
    button.disabled = true;
    status.textContent = 'Fetching images and offset stars…';
    $('#fd-notes').replaceChildren();
    const stopPolling = startFinderProgress(plan.output_dir);
    try {
      const result = await api('/api/finders/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          output_dir: plan.output_dir,
          slit_mode: lastSlitMode,
          overwrite: $('#fd-overwrite').checked,
        }),
      });
      const failed = result.results.filter((r) => r.error);
      status.textContent = `${result.results.length - failed.length} of `
        + `${result.results.length} done (${result.mode})`;
      failed.forEach((r) => $('#fd-notes')
        .append(notice(`${r.name}: ${r.error}`, true)));
      // Asking for both candidates and silently getting a parallactic slit
      // would be the worst outcome: you'd set an angle you didn't choose.
      if (result.fell_back && result.fell_back.length) {
        $('#fd-notes').append(notice(
          `${result.fell_back.length} target(s) are not from FFFF-PZ and have `
          + `no second candidate — ${result.fell_back.join(', ')} stayed at `
          + 'the parallactic angle.'));
      }
      const report = result.report;
      await renderFinders();   // reload the grid with what was just made
      if (report) renderSlitReport(report);
    } catch (err) {
      $('#fd-notes').replaceChildren(notice(err.message, true));
      status.textContent = '';
    } finally {
      stopPolling();
      button.disabled = false;
    }
  });

  const files = await api(`/api/finders?output_dir=${encodeURIComponent(plan.output_dir)}`);
  const grid = $('#finder-grid');

  /* T2.7: one chart at a time, so fixing one target doesn't mean
     re-fetching every image. */
  const generateOne = async (target, button) => {
    button.disabled = true;
    button.textContent = '…';
    $('#fd-notes').replaceChildren();
    try {
      const result = await api('/api/finders/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_dir: plan.output_dir, targets: [target],
                               slit_mode: lastSlitMode, overwrite: true }),
      });
      result.results.filter((r) => r.error)
        .forEach((r) => $('#fd-notes').append(notice(`${r.name}: ${r.error}`, true)));
      await renderFinders();
    } catch (err) {
      $('#fd-notes').replaceChildren(notice(err.message, true));
      button.disabled = false;
      button.textContent = 'retry';
    }
  };

  // Scheduled targets with no chart yet get a placeholder card.
  const have = new Set(files.map((f) => f.name.replace('_finder.png', '')));
  plan.schedule.filter((t) => !have.has(t.name)).forEach((t) => {
    const fig = el('figure', 'missing');
    const b = el('button', 'btn-now', 'Generate');
    b.type = 'button';
    b.addEventListener('click', () => generateOne(t.name, b));
    fig.append(el('figcaption', '', `${t.name} · no chart yet`), b);
    grid.append(fig);
  });
  if (!files.length) {
    grid.prepend(el('p', 'hint',
      'No finder charts yet — generate them all above, or one at a time below.'));
    return;
  }

  // Schedule order, not alphabetical: at the telescope you work down the
  // night, so the next chart you want is the next one along.
  const order = new Map(plan.schedule.map((t, i) => [t.name, i]));
  const named = files.map((f) => ({
    file: f.name, mtime: f.mtime, target: f.name.replace('_finder.png', ''),
  }));
  named.sort((a, b) => (order.has(a.target) ? order.get(a.target) : 1e6)
                        - (order.has(b.target) ? order.get(b.target) : 1e6)
                        || a.target.localeCompare(b.target));

  const slots = named.map(({ file, target, mtime }, i) => {
    const block = plan.schedule.find((t) => t.name === target);
    const caption = block
      ? `${target} · ${hhmm(block.start)}–${hhmm(block.end)}`
      : `${target} (not scheduled)`;
    // The mtime versions the URL, so regenerating a chart busts the
    // browser cache. Without it the old slit sits under the new report.
    const src = `/api/image?output_dir=${encodeURIComponent(plan.output_dir)}`
                + `&name=${file}&v=${mtime}`;

    const fig = el('figure');
    fig.tabIndex = 0;
    fig.setAttribute('role', 'button');
    fig.title = 'Click to view full size';
    const img = el('img');
    img.loading = 'lazy';
    img.alt = target;
    img.src = src;
    const cap = el('figcaption', '', caption);
    const redo = el('button', 'btn-now', 'Re-render');
    redo.type = 'button';
    redo.title = 'Regenerate just this chart, with the slit choice above';
    redo.addEventListener('click', (e) => { e.stopPropagation(); generateOne(target, redo); });
    cap.append(redo);
    fig.append(img, cap);
    fig.addEventListener('click', () => openLightbox(i));
    fig.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openLightbox(i); }
    });
    grid.append(fig);
    return { src, caption };
  });

  lightboxSlots = slots;
}

/* Where every slit ended up, as a table. The observer sets this angle by
   hand, so "what did I actually ask for" has to be answerable after the
   fact and not only in the moment the charts were made. */
function renderSlitReport(report) {
  const host = $('#fd-report');
  if (!host || !report.rows.length) return;
  host.replaceChildren();

  host.append(el('h3', '', `Slit angles (${report.requested} requested)`));

  const table = el('table', 'slit-report');
  const head = el('tr');
  ['target', 'slit', 'PA', 'off parallactic', 'secondary', 'note']
    .forEach((h) => head.append(el('th', '', h)));
  table.append(head);

  report.rows.forEach((r) => {
    const tr = el('tr', r.slit_mode === 'candidates' ? '' : 'fallback');
    const cells = [
      r.name,
      r.slit_mode,
      r.slit_pa === null || r.slit_pa === undefined ? '—' : r.slit_pa.toFixed(2),
      r.off_parallactic ? `${r.off_parallactic.toFixed(1)}°` : '—',
      r.secondary_sep_arcsec ? `${r.secondary_sep_arcsec.toFixed(1)}″` : '—',
      r.reason || r.skipped || '',
    ];
    cells.forEach((c) => tr.append(el('td', '', String(c))));
    table.append(tr);
  });
  host.append(table);
  host.append(el('p', 'hint',
    'Also saved as finders/slit_report.txt, so the angle each chart was '
    + 'drawn at can be checked later.'));
}

/* Poll the server while charts are being drawn. The generate request is
   one long POST, so the only way to show movement is to ask a second
   endpoint how far it has got. Returns a function that stops the poll
   and hides the bar. */
function startFinderProgress(outputDir) {
  const wrap = $('#fd-progress');
  const bar = $('#fd-bar');
  const text = $('#fd-progress-text');
  if (!wrap) return () => {};

  bar.value = 0;
  bar.removeAttribute('value');     // indeterminate until the first reply
  text.textContent = 'starting…';
  wrap.hidden = false;

  const timer = setInterval(async () => {
    try {
      const p = await api(
        `/api/finders/progress?output_dir=${encodeURIComponent(outputDir)}`);
      if (!p.running || !p.total) return;
      bar.max = p.total;
      bar.value = p.done;
      // p.done counts finished charts; the one named is the one in
      // flight, so it reads as "3 of 8" while the third is being drawn.
      text.textContent = p.current
        ? `${p.done + 1} of ${p.total} — ${p.current}`
        : `${p.done} of ${p.total}`;
    } catch (err) {
      /* A failed poll is not worth interrupting the run for. */
    }
  }, 700);

  return () => {
    clearInterval(timer);
    wrap.hidden = true;
  };
}

/* ------------------------------------------------------------- lightbox */

/* The charts currently on screen, in the order they are displayed, so the
   arrows walk the night rather than the filesystem. */
let lightboxSlots = [];
let lightboxAt = 0;

function showLightboxSlot(index) {
  if (!lightboxSlots.length) return;
  lightboxAt = (index + lightboxSlots.length) % lightboxSlots.length;
  const slot = lightboxSlots[lightboxAt];
  $('#lb-img').src = slot.src;
  $('#lb-img').alt = slot.caption;
  $('#lb-caption').textContent = lightboxSlots.length > 1
    ? `${slot.caption}  ·  ${lightboxAt + 1} of ${lightboxSlots.length}`
    : slot.caption;
}

function openLightbox(index) {
  showLightboxSlot(index);
  $('#lightbox').hidden = false;
  $('#lb-close').focus();
}

function closeLightbox() {
  $('#lightbox').hidden = true;
}

function initLightbox() {
  const box = $('#lightbox');
  $('#lb-close').addEventListener('click', closeLightbox);
  $('#lb-prev').addEventListener('click', () => showLightboxSlot(lightboxAt - 1));
  $('#lb-next').addEventListener('click', () => showLightboxSlot(lightboxAt + 1));
  // Clicking the backdrop closes; clicking the image itself must not.
  box.addEventListener('click', (e) => { if (e.target === box) closeLightbox(); });
  document.addEventListener('keydown', (e) => {
    if (box.hidden) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowLeft') showLightboxSlot(lightboxAt - 1);
    if (e.key === 'ArrowRight') showLightboxSlot(lightboxAt + 1);
  });
}

/* -------------------------------------------------------------- starlist */

async function renderStarlist() {
  const plan = await loadPlan();
  useTemplate('tpl-starlist');
  renderNav('/starlist');

  const q = encodeURIComponent(plan.output_dir);

  const show = (text) => {
    $('#starlist-text').textContent = text;
    $('#starlist-actions').replaceChildren();
    const copy = el('button', '', 'Copy');
    copy.addEventListener('click', async () => {
      await navigator.clipboard.writeText(text);
      copy.textContent = 'Copied';
      setTimeout(() => { copy.textContent = 'Copy'; }, 1500);
    });
    $('#starlist-actions').append(copy);
  };

  try {
    show(await api(`/api/starlist?output_dir=${q}`));
  } catch {
    $('#starlist-text').textContent =
      'No starlist in this plan directory yet — generate one above.';
  }

  $('#sl-generate').addEventListener('click', async () => {
    const status = $('#sl-status');
    const button = $('#sl-generate');
    button.disabled = true;
    status.textContent = 'Generating…';
    $('#sl-notes').replaceChildren();
    try {
      const result = await api('/api/starlist/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          output_dir: plan.output_dir,
          include_standards: $('#sl-standards').checked,
          max_airmass: Number($('#sl-maxam').value) || 2.0,
        }),
      });
      show(result.text);
      status.textContent = `Wrote ${result.name}`;
      result.notes.forEach((n) => $('#sl-notes').append(notice(n)));
    } catch (err) {
      $('#sl-notes').replaceChildren(notice(err.message, true));
      status.textContent = '';
    } finally {
      stopPolling();
      button.disabled = false;
    }
  });
}

/* --------------------------------------------------------------- airmass */

async function renderAirmass(params) {
  const plan = await loadPlan();
  useTemplate('tpl-airmass');
  renderNav('/airmass');

  const select = $('#airmass-target');
  const names = plan.schedule.map((t) => t.name);
  plan.decisions.filter((d) => d.status === 'rejected' && d.ra_deg !== null)
    .forEach((d) => names.includes(d.name) || names.push(d.name));
  names.forEach((name) => {
    const o = el('option', '', name);
    o.value = name;
    select.append(o);
  });
  const wanted = params.get('target');
  if (wanted && names.includes(wanted)) select.value = wanted;

  // Plotly converts offset-bearing ISO strings into the *browser's* zone.
  // Strip the offset so it plots the telescope's own clock verbatim.
  const naive = (iso) => (iso ? iso.slice(0, 19) : null);

  const draw = async () => {
    const q = new URLSearchParams({ output_dir: plan.output_dir, target: select.value });
    const data = await api(`/api/airmass?${q}`);

    const traces = [{
      x: data.points.map((p) => naive(p.time)),
      y: data.points.map((p) => p.airmass),
      mode: 'lines',
      name: 'airmass',
      line: { color: '#2563eb', width: 2 },
      connectgaps: false,
      hovertemplate: 'airmass %{y:.2f}<br>%{x|%H:%M}<extra></extra>',
    }];

    const shapes = [{
      type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 2, y1: 2,
      line: { color: '#dc2626', width: 1, dash: 'dot' },
    }];
    if (data.scheduled) {
      shapes.push({
        type: 'rect', xref: 'x', yref: 'paper',
        x0: naive(data.scheduled.start), x1: naive(data.scheduled.end), y0: 0, y1: 1,
        fillcolor: '#2563eb', opacity: 0.12, line: { width: 0 },
      });
    }
    ['dusk_astronomical', 'dawn_astronomical'].forEach((k) => {
      if (!data.sun[k]) return;
      shapes.push({
        type: 'line', xref: 'x', yref: 'paper',
        x0: naive(data.sun[k]), x1: naive(data.sun[k]), y0: 0, y1: 1,
        line: { color: '#1e293b', width: 1, dash: 'dash' },
      });
    });

    Plotly.newPlot('airmass-plot', traces, {
      margin: { t: 20, r: 20, b: 50, l: 60 },
      height: 420,
      xaxis: { title: 'local time at the telescope', tickformat: '%H:%M' },
      // Airmass runs away to hundreds within a few arcmin of the horizon,
      // which would crush the only part anyone reads. Clamp to the range
      // that's actually observable, low airmass at the top.
      yaxis: { title: 'airmass', range: [3, 1] },
      shapes,
      showlegend: false,
    }, { responsive: true, displayModeBar: false });

    // "Best" only means something inside the dark window -- a rising target
    // keeps improving past dawn, which is useless to an observer.
    const darkStart = data.sun.dusk_astronomical;
    const darkEnd = data.sun.dawn_astronomical;
    const inDark = data.points.filter((p) => p.airmass
      && p.time >= darkStart && p.time <= darkEnd);
    const best = inDark.reduce((a, p) => (a && a.airmass <= p.airmass ? a : p), null);
    $('#airmass-note').textContent = best
      ? `Best airmass while dark: ${best.airmass.toFixed(2)} at ${hhmm(best.time)}. `
        + 'Dotted line is airmass 2.0; shaded band is the scheduled exposure; '
        + 'dashed lines are 18° twilight. Gaps are below the horizon.'
      : 'This target is never above the horizon during astronomical night.';
  };

  /* Predicted S/N(lambda) at the airmass the target was scheduled at
     (T3.4a): the target S/N line and the two continuum windows the ETC
     sizes exposures on. */
  const drawSN = async () => {
    const q = new URLSearchParams({ output_dir: plan.output_dir, target: select.value });
    let spec;
    try {
      spec = await api(`/api/etc?${q}`);
    } catch (err) {
      Plotly.purge('sn-plot');
      $('#sn-plot').replaceChildren();
      $('#sn-note').textContent = err.message;
      return;
    }
    const shapes = Object.values(spec.windows || {}).map(([w0, w1]) => ({
      type: 'rect', xref: 'x', yref: 'paper', x0: w0, x1: w1, y0: 0, y1: 1,
      fillcolor: '#64748b', opacity: 0.12, line: { width: 0 },
    }));
    if (spec.target_sn) {
      shapes.push({ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y',
                    y0: spec.target_sn, y1: spec.target_sn,
                    line: { color: '#dc2626', width: 1, dash: 'dot' } });
    }
    Plotly.newPlot('sn-plot', [{
      x: spec.wave, y: spec.s2n, mode: 'lines', line: { color: '#0d9488', width: 2 },
      hovertemplate: '%{x:.0f} Å: S/N %{y:.1f}<extra></extra>',
    }], {
      margin: { t: 10, r: 20, b: 50, l: 60 }, height: 300,
      xaxis: { title: 'wavelength [Å]' },
      yaxis: { title: 'S/N per pixel, one sub-exposure', rangemode: 'tozero' },
      shapes, showlegend: false,
    }, { responsive: true, displayModeBar: false });
    $('#sn-note').textContent = `One ${spec.sub_len_s} s sub-exposure (${spec.n_sub} planned) at `
      + `airmass ${Number(spec.airmass).toFixed(2)}, band ${spec.band}. Dotted line: `
      + `target S/N ${spec.target_sn ?? '—'}; shaded: the continuum windows the `
      + 'exposure is sized on.';
  };

  select.addEventListener('change', () => { draw(); drawSN(); });
  await draw();
  await drawSN();
}

/* ----------------------------------------------------------- night chart */

/* One qualitative colour per target. Eight hues, because a Lick night
   rarely holds more than that and more than eight is unreadable anyway. */
const NIGHT_COLORS = ['#2563eb', '#dc2626', '#059669', '#7c3aed',
                      '#d97706', '#0891b2', '#db2777', '#4d7c0f'];

/* Plotly reads an offset-bearing ISO string into the *browser's* zone.
   Strip the offset so the chart plots the telescope's own clock. */
const naiveTime = (iso) => (iso ? iso.slice(0, 19) : null);

function lstLabel(hours) {
  const h = Math.floor(hours);
  const m = Math.round((hours - h) * 60);
  return m === 60 ? `${(h + 1) % 24}:00` : `${h}:${String(m).padStart(2, '0')}`;
}

/* Ticks on whole local hours, labelled with local and UT on two lines,
   and the same positions reused for the sidereal axis on top.

   Built from the clock rather than from the samples: the grid starts at
   sunset, so with a 5-minute step its minutes never land on :00 and
   selecting samples would yield no ticks at all. */
function nightTicks(times, lst) {
  const first = new Date(times[0]);
  const last = new Date(times[times.length - 1]);
  const span = last - first;

  // Sidereal time advances steadily across the night; interpolating it
  // between the end samples is accurate to well under a tick label.
  const lstAt = (when) => {
    const f = (when - first) / span;
    const turns = (lst[lst.length - 1] - lst[0] + 24) % 24;
    return (lst[0] + f * turns) % 24;
  };

  const vals = [], local = [], sidereal = [];
  const tick = new Date(first);
  tick.setMinutes(0, 0, 0);
  if (tick < first) tick.setHours(tick.getHours() + 1);
  for (; tick <= last; tick.setHours(tick.getHours() + 1)) {
    // times[] carries the telescope's own offset; reuse it so the tick
    // string sits in the same naive frame as the plotted points.
    const offset = times[0].slice(19);
    const localIso = new Date(tick - tick.getTimezoneOffset() * 60000)
      .toISOString().slice(0, 19);
    vals.push(localIso);
    local.push(`${localIso.slice(11, 16)}<br>`
               + `${new Date(localIso + offset).toISOString().slice(11, 16)} UT`);
    sidereal.push(lstLabel(lstAt(tick)));
  }
  return { vals, local, sidereal };
}

/* Twilight drawn as nested bands rather than one flat wash: sunset to
   12 deg is where you can still only take standards, 12 to 18 is usable
   for bright targets, and the difference is worth seeing at a glance. */
function twilightShapes(sun) {
  const band = (a, b, opacity) => ({
    type: 'rect', xref: 'x', yref: 'paper',
    x0: naiveTime(sun[a]), x1: naiveTime(sun[b]),
    y0: 0, y1: 1, fillcolor: '#1e293b', opacity, line: { width: 0 },
    layer: 'below',
  });
  const mark = (key, color) => ({
    type: 'line', xref: 'x', yref: 'paper',
    x0: naiveTime(sun[key]), x1: naiveTime(sun[key]), y0: 0, y1: 1,
    line: { color, width: 1, dash: 'dash' }, layer: 'below',
  });
  return [
    band('sunset', 'dusk_nautical', 0.14),
    band('dusk_nautical', 'dusk_astronomical', 0.07),
    band('dawn_astronomical', 'dawn_nautical', 0.07),
    band('dawn_nautical', 'sunrise', 0.14),
    mark('sunset', '#f59e0b'), mark('sunrise', '#f59e0b'),
    mark('dusk_nautical', '#60a5fa'), mark('dawn_nautical', '#60a5fa'),
    mark('dusk_astronomical', '#7c3aed'), mark('dawn_astronomical', '#7c3aed'),
  ];
}

function twilightLabels(sun) {
  return [['sunset', 'sunset'], ['dusk_nautical', '12°'],
          ['dusk_astronomical', '18°'], ['dawn_astronomical', '18°'],
          ['dawn_nautical', '12°'], ['sunrise', 'sunrise']]
    .filter(([k]) => sun[k])
    .map(([k, text]) => ({
      x: naiveTime(sun[k]), y: 0.995, xref: 'x', yref: 'paper',
      text, showarrow: false, yanchor: 'top',
      font: { size: 9, color: '#64748b' },
    }));
}

async function renderNightChart() {
  const plan = await loadPlan();
  useTemplate('tpl-nightchart');
  renderNav('/nightchart');

  const draw = async () => {
    const q = new URLSearchParams({
      output_dir: plan.output_dir,
      include_rejected: $('#nc-rejected').checked,
    });
    const data = await api(`/api/airmass/all?${q}`);
    const x = data.times.map(naiveTime);
    const ticks = nightTicks(data.times, data.lst);

    // Plotly only draws an overlaying axis that something sits on, so the
    // sidereal scale needs a carrier trace even though it shows nothing.
    const traces = [{
      x: [x[0], x[x.length - 1]], y: [1, 1], xaxis: 'x2',
      mode: 'markers', marker: { opacity: 0 },
      hoverinfo: 'skip', showlegend: false,
    }];

    if ($('#nc-moon').checked && data.moon.airmass.some((a) => a !== null)) {
      traces.push({
        x, y: data.moon.airmass, mode: 'lines', name: 'moon',
        line: { color: '#94a3b8', width: 2.5 }, connectgaps: false,
        hovertemplate: 'moon · airmass %{y:.2f}<extra></extra>',
      });
    }

    let colorIdx = 0;
    data.targets.forEach((t) => {
      // Rejected targets stay grey. They are context -- "this is what was
      // up and you didn't take it" -- and giving them a hue of their own
      // would make the chart look like twice as much got observed.
      const color = t.scheduled
        ? NIGHT_COLORS[colorIdx++ % NIGHT_COLORS.length] : '#94a3b8';

      // The whole night, faint: context for where the thick bit sits.
      traces.push({
        x, y: t.airmass, mode: 'lines', name: t.name,
        legendgroup: t.name, showlegend: false, connectgaps: false,
        line: { color, width: 1.2, dash: 'dot' },
        opacity: t.scheduled ? 0.45 : 0.6,
        // Named on hover only when nothing else identifies it.
        hoverinfo: t.scheduled ? 'skip' : undefined,
        hovertemplate: t.scheduled ? undefined
          : `${t.name} (not scheduled)<br>airmass %{y:.2f} at %{x|%H:%M}`
            + '<extra></extra>',
      });

      if (!t.scheduled) return;
      // The exposure itself, heavy: nulled outside the block so one
      // trace carries both the timing and the airmass actually got.
      const start = naiveTime(t.scheduled.start);
      const end = naiveTime(t.scheduled.end);
      traces.push({
        x,
        y: t.airmass.map((a, j) => (x[j] >= start && x[j] <= end ? a : null)),
        mode: 'lines', name: t.name, legendgroup: t.name,
        line: { color, width: 7 }, connectgaps: false,
        hovertemplate: `${t.name}<br>airmass %{y:.2f} at %{x|%H:%M}`
                       + '<extra></extra>',
      });
    });

    // Low airmass at the top, and only as deep as the night actually
    // goes -- a fixed axis to 3 would squash everything readable.
    const used = data.targets.flatMap((t) => (t.scheduled
      ? t.airmass.filter((a, j) => a !== null
          && x[j] >= naiveTime(t.scheduled.start)
          && x[j] <= naiveTime(t.scheduled.end))
      : []));
    const worst = Math.max(2.0, ...used) + 0.1;

    Plotly.newPlot('nightchart-plot', traces, {
      margin: { t: 48, r: 20, b: 64, l: 60 },
      height: 520,
      hovermode: 'closest',
      xaxis: {
        title: 'local time at the telescope · UT',
        tickmode: 'array', tickvals: ticks.vals, ticktext: ticks.local,
        range: [x[0], x[x.length - 1]],
      },
      xaxis2: {
        overlaying: 'x', side: 'top', showgrid: false, zeroline: false,
        range: [x[0], x[x.length - 1]],
        title: { text: 'LST', font: { size: 11, color: '#7c3aed' } },
        tickmode: 'array', tickvals: ticks.vals, ticktext: ticks.sidereal,
        tickfont: { size: 10, color: '#7c3aed' },
      },
      yaxis: { title: 'airmass', range: [worst, 1.0] },
      shapes: twilightShapes(data.sun),
      annotations: twilightLabels(data.sun),
      legend: { orientation: 'h', y: -0.22 },
    }, { responsive: true, displayModeBar: false });

    const rejected = data.targets.filter((t) => !t.scheduled).length;
    const lit = Math.round(data.moon.illumination * 100);
    const up = data.moon.airmass.filter((a) => a !== null).length;
    $('#nightchart-note').textContent =
      `${data.targets.filter((t) => t.scheduled).length} scheduled targets, `
      + `${data.date} at ${data.telescope}. Moon ${lit}% lit and `
      + (up ? `above the horizon for part of the night.`
            : `below the horizon all night.`)
      + ' Shaded bands are twilight; dashed lines mark sunset, 12° and 18°.'
      + (rejected ? ` ${rejected} rejected targets are drawn grey.` : '');
  };

  $('#nc-rejected').addEventListener('change', draw);
  $('#nc-moon').addEventListener('change', draw);
  await draw();
}

/* ------------------------------------------------------- observing log */

/* One page for the night as it actually happened: header, calibrations
   checklist, night checklist, conditions log, the target table and the
   report. Every field autosaves on change with a single PATCH, and the
   server returns the derived numbers (calibration count, airmass at the
   actual start, time accounting), so this page never recomputes them. */

const LOG_LABELS = {
  pending: 'pending', observed: 'observed', partial: 'partial',
  not_observed: 'not observed', skipped: 'skipped',
  weather: 'weather', ran_out_of_time: 'ran out of time', technical: 'technical',
  not_acquired: 'target not acquired', bumped: 'lower priority / bumped',
  other: 'other', good: 'good', usable: 'usable', poor: 'poor',
  yes: 'yes', no: 'no', unknown: 'unknown', clear: 'clear',
  thin_cirrus: 'thin cirrus', patchy: 'patchy', thick: 'thick', closed: 'closed',
  acquired: 'acquired', on_slit: 'on slit / mask aligned',
  exposures_complete: 'exposures complete', quicklook: 'quick-look OK',
};
const logLabel = (v) => (v === '' ? '—' : (LOG_LABELS[v] || v));
const utHHMM = (ut) => (ut ? ut.slice(11, 16) : '');
const isoUT = (iso) => (iso ? new Date(iso).toISOString().slice(11, 16) : '');

async function renderLog() {
  const plan = await loadPlan();
  useTemplate('tpl-log');
  renderNav('/log');
  // The directory this page was opened with, not plan.output_dir: a copied
  // or moved plan still records where it was generated, and the log must be
  // written beside the plan actually being viewed.
  const dir = state.outputDir || plan.output_dir;
  let data = await api(`/api/log?output_dir=${encodeURIComponent(dir)}`);
  const opts = data.options;

  $('#log-lede').textContent =
    `${plan.telescope} · ${plan.instrument.toUpperCase()} · ${plan.date} · `
    + `${(data.log.configs || []).map((c) => c.label).join('; ')} · times in UT`;

  const saved = $('#log-saved');
  async function save(path, value) {
    $('#log-errors').replaceChildren();
    try {
      const resp = await api('/api/log', {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_dir: dir, path, value }),
      });
      data = resp;
      saved.textContent = `Saved ${new Date().toISOString().slice(11, 19)} UT`;
      refreshDerived();
      return resp.value;
    } catch (err) {
      $('#log-errors').replaceChildren(notice(`Not saved: ${err.message}`, true));
      throw err;
    }
  }

  /* Small input builders. Each saves itself on change. */
  const textIn = (value, path, cls, placeholder) => {
    const input = el('input', cls || '');
    input.type = 'text';
    input.value = value ?? '';
    if (placeholder) input.placeholder = placeholder;
    if (path) input.addEventListener('change', () => save(path, input.value));
    return input;
  };
  const selectIn = (value, choices, path, onSaved) => {
    const sel = el('select');
    choices.forEach((c) => {
      const o = el('option', '', logLabel(c));
      o.value = c;
      sel.append(o);
    });
    sel.value = value ?? '';
    if (path) {
      sel.addEventListener('change', async () => {
        await save(path, sel.value);
        if (onSaved) onSaved(sel.value);
      });
    }
    return sel;
  };
  const checkIn = (value, path, onSaved) => {
    const box = el('input');
    box.type = 'checkbox';
    box.checked = !!value;
    box.addEventListener('change', async () => {
      try { await save(path, box.checked); if (onSaved) onSaved(box.checked); }
      catch { box.checked = !box.checked; }
    });
    return box;
  };
  /* A UT HH:MM field plus a "now" button. The server turns HH:MM into a
     full UT timestamp on the right night. */
  const utIn = (value, path, onSaved) => {
    const wrap = el('span', 'ut-cell');
    const input = textIn(utHHMM(value), null, 'ut', 'HH:MM');
    const store = async (v) => {
      const clean = await save(path, v);
      input.value = utHHMM(clean);
      if (onSaved) onSaved(clean);
    };
    input.addEventListener('change', () => store(input.value));
    const now = el('button', 'btn-now', 'now');
    now.type = 'button';
    now.addEventListener('click', () => store(new Date().toISOString()));
    wrap.append(input, now);
    return wrap;
  };
  const labelled = (text, control, cls) => {
    const l = el('label', cls || '', text);
    l.append(control);
    return l;
  };

  /* ---- 1. Night header */
  const night = data.log.night;
  const nf = $('#log-night-fields');
  nf.append(
    labelled('Observers', textIn(night.observers, ['night', 'observers'])),
    labelled('Support astronomer / operator', textIn(night.support, ['night', 'support'])),
    labelled('Dome open (UT)', utIn(night.dome_open_ut, ['night', 'dome_open_ut'])),
    labelled('Dome close (UT)', utIn(night.dome_close_ut, ['night', 'dome_close_ut'])),
    labelled('Sky (night summary)', selectIn(night.sky_summary, opts.sky, ['night', 'sky_summary'])),
    labelled('Seeing range (″)', textIn(night.seeing_range, ['night', 'seeing_range'], '', 'e.g. 0.7–1.1')),
    labelled('FFFF-PZ conditions', textIn(night.ffffpz_conditions, ['night', 'ffffpz_conditions'], '', 'Good / Fair / Poor')),
    labelled('Humidity / wind', textIn(night.weather_notes, ['night', 'weather_notes'])),
  );
  const notes = el('textarea');
  notes.value = night.notes || '';
  notes.addEventListener('change', () => save(['night', 'notes'], notes.value));
  nf.append(labelled('General notes', notes, 'wide'));

  /* Scenario in use (T4.1): one log per night; its target rows follow the
     scenario actually being observed. Changing it re-merges the log. */
  try {
    const sc = await api(`/api/scenarios?output_dir=${encodeURIComponent(dir)}`);
    if (sc.scenarios.length) {
      const slugs = sc.scenarios.map((e) => e.slug);
      const current = slugs.includes(night.scenario) ? night.scenario : sc.active;
      const sel = el('select');
      sc.scenarios.forEach((e) => {
        const o = el('option', '', e.name);
        o.value = e.slug;
        sel.append(o);
      });
      sel.value = current;
      sel.addEventListener('change', async () => {
        await save(['night', 'scenario'], sel.value);
        renderLog();
      });
      $('#log-scenario').append(labelled('Scenario in use (one log per night; '
        + 'calibrations cover every scenario)', sel));
    }
  } catch { /* single plan */ }

  /* Time lost: a small list saved whole. */
  function renderLost() {
    const host = $('#log-lost');
    host.replaceChildren();
    const rows = data.log.night.time_lost || [];
    if (!rows.length) host.append(el('div', 'hint', 'None recorded.'));
    rows.forEach((row, i) => {
      const line = el('div', 'log-line');
      const mins_ = el('input', 'ut');
      mins_.type = 'number'; mins_.min = '0'; mins_.value = row.minutes;
      const cause = selectIn(row.cause, opts.lost_causes);
      const reason = textIn(row.reason, null, 'grow', 'reason');
      const commit = () => {
        const list = rows.map((r, j) => (j === i
          ? { minutes: Number(mins_.value) || 0, cause: cause.value, reason: reason.value } : r));
        save(['night', 'time_lost'], list).then(renderLost);
      };
      [mins_, cause, reason].forEach((c) => c.addEventListener('change', commit));
      const del = el('button', 'ghost', 'Remove');
      del.type = 'button';
      del.addEventListener('click', () =>
        save(['night', 'time_lost'], rows.filter((_, j) => j !== i)).then(renderLost));
      line.append(mins_, el('span', 'hint', 'min'), cause, reason, del);
      host.append(line);
    });
  }
  $('#log-lost-add').addEventListener('click', () =>
    save(['night', 'time_lost'],
         [...(data.log.night.time_lost || []), { minutes: 0, cause: 'weather', reason: '' }])
      .then(renderLost));
  renderLost();

  /* ---- 2. Calibrations, grouped by configuration then mask */
  function renderCals() {
    const host = $('#log-cals');
    host.replaceChildren();
    const items = Object.entries(data.log.calibrations)
      .sort((a, b) => a[1].order - b[1].order);
    if (!items.length) host.append(el('div', 'hint', 'No calibrations needed.'));
    let group = null;
    items.forEach(([id, c]) => {
      const g = `${c.scope === 'mask' ? 'Mask' : 'Configuration'}: ${c.scope_name}`
        + (c.not_in_plan ? ' (no longer in plan)' : '');
      if (g !== group) { host.append(el('div', 'cal-group', g)); group = g; }
      const line = el('div', 'log-line' + (c.done ? ' done' : '') + (c.not_in_plan ? ' gone' : ''));
      const box = checkIn(c.done, ['calibrations', id, 'done'],
                          (v) => line.classList.toggle('done', v));
      const name = el('label', 'check');
      name.style.margin = '0';
      name.append(box, el('span', '', c.label));
      line.append(name,
        el('span', 'hint', 'UT'), utIn(c.ut, ['calibrations', id, 'ut']),
        textIn(c.frames, ['calibrations', id, 'frames'], 'mid', 'frames'),
        textIn(c.note, ['calibrations', id, 'note'], 'grow', 'note'));
      host.append(line);
    });
  }
  renderCals();

  /* ---- 3. Night checklist */
  const cl = $('#log-checklist');
  Object.entries(data.log.night_checklist)
    .sort((a, b) => a[1].order - b[1].order)
    .forEach(([key, item]) => {
      const l = el('label', 'check');
      l.append(checkIn(item.done, ['night_checklist', key, 'done']),
               el('span', '', item.label));
      cl.append(l);
    });

  /* ---- 4. Conditions log, saved whole */
  function renderConditions() {
    const host = $('#log-conditions');
    host.replaceChildren();
    const rows = data.log.conditions || [];
    if (!rows.length) host.append(el('div', 'hint', 'No entries yet.'));
    rows.forEach((row, i) => {
      const line = el('div', 'log-line');
      const ut = textIn(utHHMM(row.ut), null, 'ut', 'HH:MM');
      const sky = selectIn(row.sky, opts.sky);
      const seeing = textIn(row.seeing, null, 'ut', 'seeing ″');
      const note = textIn(row.note, null, 'grow', 'note');
      const commit = () => {
        const list = rows.map((r, j) => (j === i
          ? { ut: ut.value, sky: sky.value, seeing: seeing.value, note: note.value } : r));
        save(['conditions'], list).then(() => { renderConditions(); renderTargets(); });
      };
      [ut, sky, seeing, note].forEach((c) => c.addEventListener('change', commit));
      const del = el('button', 'ghost', 'Remove');
      del.type = 'button';
      del.addEventListener('click', () =>
        save(['conditions'], rows.filter((_, j) => j !== i))
          .then(() => { renderConditions(); renderTargets(); }));
      line.append(el('span', 'hint', 'UT'), ut, sky, seeing, note, del);
      host.append(line);
    });
  }
  $('#log-cond-add').addEventListener('click', () =>
    save(['conditions'], [...(data.log.conditions || []),
      { ut: new Date().toISOString(), sky: '', seeing: '', note: '' }])
      .then(renderConditions));
  renderConditions();

  /* ---- 5. Target table */
  const rowClass = (r) => {
    let cls = `st-${r.status}`;
    // During the night only, highlight pending rows whose planned end has
    // already passed. Reviewing an old night shouldn't paint every row.
    const now = new Date();
    const live = now >= new Date(plan.night_start)
      && now <= new Date(new Date(plan.night_end).getTime() + 2 * 3600e3);
    if (live && r.status === 'pending' && r.planned.end && new Date(r.planned.end) < now) {
      cls = 'st-late';
    }
    return cls + (r.not_in_plan ? ' gone' : '');
  };

  function renderTargets() {
    const table = $('#log-targets');
    table.replaceChildren();
    const head = el('tr');
    ['Target', 'Status', 'Reason', 'Start [UT]', 'Exposures [n × s]',
     'Frames', 'Airmass', 'PA [deg]', 'Sky / seeing [″]', 'Checks',
     'Quality', 'Success / z', 'Comments'].forEach((h) => head.append(el('th', '', h)));
    table.append(head);

    Object.entries(data.log.targets)
      .sort((a, b) => a[1].order - b[1].order)
      .forEach(([name, r]) => {
        const tr = el('tr', rowClass(r));
        const p = r.planned;
        const der = data.derived.targets[name] || {};
        const base = ['targets', name];

        const who = el('td', 'w-l');
        who.append(el('b', '', name + (r.not_in_plan ? ' (no longer in plan)' : '')));
        const tub = p.cass_tub ? ` · tub ${p.cass_tub.tub.toFixed(2)} / ${p.cass_tub.alt_tub.toFixed(2)}` : '';
        who.append(el('div', 'planned',
          `${p.mode} · planned ${isoUT(p.science_start)}–${isoUT(p.end)} UT `
          + `(${hhmm(p.science_start)}–${hhmm(p.end)} local)`
          + (p.exposure_red ? ` · ${p.exposure_red}` : '') + tub));

        const td = (cls, ...nodes) => { const c = el('td', cls); c.append(...nodes); return c; };
        const status = selectIn(r.status, opts.statuses, [...base, 'status'],
                                (v) => { r.status = v; tr.className = rowClass(r); });
        const reason = selectIn(r.reason, opts.reasons, [...base, 'reason']);
        const reasonText = textIn(r.reason_text, [...base, 'reason_text'], '', 'details');

        const cond = der.conditions || {};
        const sky = selectIn(r.sky, opts.sky, [...base, 'sky']);
        if (!r.sky && cond.sky) sky.title = `log: ${logLabel(cond.sky)}`;
        const seeing = textIn(r.seeing, [...base, 'seeing'], '',
                              cond.seeing ? `log: ${cond.seeing}` : 'seeing');

        const checks = el('div', 'checks');
        opts.checks.forEach((k) => {
          const l = el('label');
          l.append(checkIn(r.checks[k], [...base, 'checks', k]), el('span', '', logLabel(k)));
          checks.append(l);
        });

        const am = der.airmass_start;
        tr.append(
          who,
          td('w-m', status),
          td('w-m', reason, reasonText),
          td('w-s', utIn(r.actual_start_ut, [...base, 'actual_start_ut'], () => refreshDerived())),
          td('w-m', textIn(r.exposures_red, [...base, 'exposures_red'], '',
                           p.exposure_red && /\d+\s*x/i.test(p.exposure_red) ? p.exposure_red : 'n x s')),
          td('w-m', textIn(r.frames, [...base, 'frames'], '', 'e.g. r0045–0047')),
          el('td', 'num am-cell', am == null ? '—' : am.toFixed(2)),
          td('w-s', textIn(r.pa, [...base, 'pa'])),
          td('w-m', sky, seeing),
          td('', checks),
          td('w-s', selectIn(r.quality, opts.qualities, [...base, 'quality'])),
          td('w-s', selectIn(r.success, opts.success, [...base, 'success']),
                    textIn(r.z, [...base, 'z'], '', 'z')),
          td('w-l', textIn(r.comments, [...base, 'comments'])),
        );
        tr.dataset.name = name;
        table.append(tr);
      });
  }
  renderTargets();

  /* Unplanned targets: a list saved whole. */
  function renderUnplanned() {
    const table = $('#log-unplanned');
    table.replaceChildren();
    const rows = data.log.unplanned || [];
    if (!rows.length) {
      const tr = el('tr');
      tr.append(el('td', 'hint', 'None.'));
      table.append(tr);
      return;
    }
    const head = el('tr');
    ['Target', 'Status', 'Start [UT]', 'Exposures [n × s]', 'Frames',
     'Success / z', 'Comments', ''].forEach((h) => head.append(el('th', '', h)));
    table.append(head);
    rows.forEach((row, i) => {
      const tr = el('tr', `st-${row.status}`);
      const status = selectIn(row.status, opts.statuses);
      const start = textIn(utHHMM(row.actual_start_ut), null, 'ut', 'HH:MM');
      const exp = textIn(row.exposures_red, null, '', 'n x s');
      const frames = textIn(row.frames, null, '', 'frames');
      const succ = selectIn(row.success, opts.success);
      const z = textIn(row.z, null, '', 'z');
      const comments = textIn(row.comments, null, '', '');
      const commit = () => {
        const list = rows.map((r, j) => (j === i ? {
          ...r, status: status.value, actual_start_ut: start.value,
          exposures_red: exp.value, frames: frames.value, success: succ.value,
          z: z.value, comments: comments.value,
        } : r));
        save(['unplanned'], list).then(renderUnplanned);
      };
      [status, start, exp, frames, succ, z, comments]
        .forEach((c) => c.addEventListener('change', commit));
      const del = el('button', 'ghost', 'Remove');
      del.type = 'button';
      del.addEventListener('click', () =>
        save(['unplanned'], rows.filter((_, j) => j !== i)).then(renderUnplanned));
      const cell = (...n) => { const c = el('td'); c.append(...n); return c; };
      tr.append(cell(el('b', '', row.name)), cell(status), cell(start), cell(exp),
                cell(frames), cell(succ, z), cell(comments), cell(del));
      table.append(tr);
    });
  }
  const pick = $('#log-unplanned-pick');
  const firstOpt = el('option', '', 'pick a rejected target…');
  firstOpt.value = '';
  pick.append(firstOpt);
  plan.decisions.filter((d) => d.status === 'rejected').forEach((d) => {
    const o = el('option', '', `${d.name}${d.mag != null ? ` (mag ${d.mag})` : ''}`);
    o.value = d.name;
    pick.append(o);
  });
  $('#log-unplanned-add').addEventListener('click', () => {
    const name = pick.value || $('#log-unplanned-name').value.trim();
    if (!name) return;
    const d = plan.decisions.find((x) => x.name === name) || {};
    save(['unplanned'], [...(data.log.unplanned || []), {
      name, mode: 'longslit', status: 'observed', ra_deg: d.ra_deg ?? null,
      dec_deg: d.dec_deg ?? null, mag: d.mag ?? null,
    }]).then(() => {
      pick.value = '';
      $('#log-unplanned-name').value = '';
      renderUnplanned();
    });
  });
  renderUnplanned();

  /* Numbers the server derives: refreshed after every save, without
     re-rendering inputs (that would steal focus mid-typing). */
  function refreshDerived() {
    const c = data.derived.calibrations;
    const label = `${c.taken} / ${c.total} taken`;
    $('#log-cal-count').textContent = label;
    $('#log-cal-count2').textContent = `· calibrations ${label}`;
    const t = data.derived.time;
    const stats = $('#log-time');
    stats.replaceChildren();
    [[`${Math.round(t.planned_on_target_min)} min`, 'planned on target'],
     [`${Math.round(t.integrated_min)} min`, 'integrated'],
     [`${Math.round(t.lost_min)} min`, 'lost (weather / technical / other)']]
      .forEach(([value, l]) => {
        const s = el('div', 'stat');
        s.append(el('b', '', value), el('span', '', l));
        stats.append(s);
      });
    document.querySelectorAll('#log-targets tr[data-name]').forEach((tr) => {
      const am = (data.derived.targets[tr.dataset.name] || {}).airmass_start;
      const cell = tr.querySelector('.am-cell');
      if (cell) cell.textContent = am == null ? '—' : am.toFixed(2);
    });
  }
  refreshDerived();

  /* ---- 6. Report */
  $('#log-report').addEventListener('click', async () => {
    const button = $('#log-report');
    const status = $('#log-report-status');
    button.disabled = true;
    status.textContent = 'Writing…';
    $('#log-report-warnings').replaceChildren();
    try {
      const out = await api('/api/log/report', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_dir: dir }),
      });
      status.textContent = `Wrote ${out.markdown_path.split('/').pop()} and `
        + `${out.csv_path.split('/').pop()}`;
      if (out.warnings.length) {
        const box = notice(`${out.warnings.length} warning(s): `);
        const ul = el('ul');
        out.warnings.forEach((w) => ul.append(el('li', '', w)));
        box.append(ul);
        $('#log-report-warnings').append(box);
      }
      const pre = $('#log-report-md');
      pre.textContent = out.markdown;
      pre.hidden = false;
    } catch (err) {
      $('#log-report-warnings').replaceChildren(notice(err.message, true));
      status.textContent = '';
    } finally {
      button.disabled = false;
    }
  });
}

window.addEventListener('hashchange', route);
window.addEventListener('DOMContentLoaded', () => { initLightbox(); route(); });
