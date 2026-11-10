"""
FastAPI backend for the night-plan viewer.

Serves one normalized plan (night_planner.plan_result.PlanResult) however
it was produced, so the frontend never has to know whether Keck's or
Lick's scheduler ran, or whether the targets came from FFFF-PZ or a
spreadsheet.

Generating a plan is slow (the Keck path makes live ETC calls per
target), so it's split in two: POST /api/generate does the work once and
writes plan_result.json, and every viewer endpoint reads that file back.

Run it with `night-planner serve`.

Created by JXP and Claude
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from night_planner.cli import INSTRUMENTS, generate_plan
from night_planner.paths import plans_dir
from night_planner.plan_store import load_plan
from night_planner.targets_io import (
    DEFAULT_PRIORITY, TargetTableError, detect_format, detect_mapping,
    field_coercions, load_targets, priority_coercions,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / 'frontend'
# night_planner.paths owns this: NIGHT_PLANNER_PLANS when set, else the
# git-ignored <repo>/pvt_Nighplans. Plans hold private targets.
PLANS_ROOT = plans_dir()
UPLOAD_DIR = Path(tempfile.gettempdir()) / 'night-planner-uploads'

# Rows returned by /api/targets/inspect. Generous enough that a normal
# target table is shown in full; anything beyond is reported as a count.
PREVIEW_LIMIT = 500

app = FastAPI(title='night-planner')


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------

def _write_prioritized_targets(targets_csv, priorities, output_dir):
    """
    Write a copy of the target table carrying the user's priorities.

    The scheduler reads priority as a column, not a flag, so the GUI's
    per-target choices have to land in a table. Writing that table into the
    plan directory -- rather than passing the numbers through the request
    and keeping them in memory -- is what makes a GUI plan reproducible from
    the command line: the directory ends up holding the exact input that
    produced it, and `night-planner calc --targets-csv` on that file
    rebuilds the same night.

    Inputs
    ------
    targets_csv : str
        Path to the table the user chose.
    priorities : dict
        {target name: priority}, lower = more important. Names absent from
        the table are ignored; targets absent from the dict keep whatever
        priority the table already carried.
    output_dir : Path
        Plan directory to write into; created if missing.

    Outputs
    -------
    str path of the written CSV.
    """
    import pandas as pd

    frame = pd.read_csv(targets_csv)
    mapping = detect_mapping(frame)
    if not mapping.ok:
        raise HTTPException(
            422, {'error': 'cannot apply priorities to a table whose columns '
                           'are still ambiguous: '
                           + '; '.join(mapping.issues),
                  'mapping': mapping.to_dict()})

    name_col = mapping.columns['name']
    # Write to the canonical column name, not whatever spelling the source
    # used, so the derived file reads back unambiguously.
    existing = mapping.columns.get('priority')
    frame['priority'] = (frame[existing] if existing else DEFAULT_PRIORITY)
    wanted = {str(k): v for k, v in priorities.items()}
    frame['priority'] = [
        wanted.get(str(name), current)
        for name, current in zip(frame[name_col], frame['priority'])]

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / 'targets_with_priority.csv'
    frame.to_csv(out_path, index=False)
    return str(out_path)


def _safe_dir(output_dir):
    """
    Resolve a caller-supplied plan directory, refusing anything outside
    the private plans directory (paths.plans_dir) or the upload scratch area.

    Every endpoint takes the plan directory from the query string, so this
    is the one place that stops a crafted path from reading the rest of
    the filesystem.
    """
    path = Path(output_dir).expanduser().resolve()
    allowed = (PLANS_ROOT.resolve(), UPLOAD_DIR.resolve(),
               Path(tempfile.gettempdir()).resolve())
    if not any(path == root or path.is_relative_to(root) for root in allowed):
        raise HTTPException(400, f'plan directory outside allowed roots: {path}')
    if not path.is_dir():
        raise HTTPException(404, f'no such plan directory: {path}')
    return path


def _plan_targets_csv(plan):
    """
    The target table a saved plan was generated from, if recoverable.

    The finder reads the PATH secondary candidates out of it, so this is
    best-effort: a plan whose inputs predate `request` simply gets charts
    without a secondary marked, which is what it had before.
    """
    argv = (plan.request or {}).get('argv') or []
    for flag, value in zip(argv, argv[1:]):
        if flag == '--targets-csv':
            return value
        if flag == '--config':
            try:
                with open(value) as f:
                    return json.load(f).get('targets_csv')
            except Exception:
                return None
    return None


def _require_plan(output_dir):
    """Load a saved plan or 404 with a useful message."""
    plan = load_plan(str(_safe_dir(output_dir)))
    if plan is None:
        raise HTTPException(
            404, 'no plan_result.json here yet -- generate the plan first')
    return plan


# --------------------------------------------------------------------
# Instruments and target tables
# --------------------------------------------------------------------

@app.get('/api/instruments')
def list_instruments():
    """Instruments the planner can run, for the home page."""
    from night_planner.adapters import SITES
    return [{'instrument': name,
             'telescope': SITES.get(name, {}).get('telescope', ''),
             'can_build_excel': bool(spec.get('build')),
             'supports_own_targets': 'targets_csv' in spec.get('supports', set()),
             'supports': sorted(spec.get('supports', set()))}
            for name, spec in sorted(INSTRUMENTS.items())]


@app.get('/api/instruments/{name}/options')
def instrument_options(name: str):
    """
    What the setup page's Configuration card may offer for an instrument:
    the ETC-supported values, the defaults, and the magnitude bands.
    """
    from night_planner.instrument_params import (DEFAULT_CONFIG, DEFAULT_MAG_BAND,
                                                 DEFAULT_SEEING, ETC_FILTERS,
                                                 ETC_OPTIONS, GRISM_NAMES)
    if name not in ETC_OPTIONS:
        raise HTTPException(404, f'unknown instrument: {name}')
    from night_planner.etc import DEFAULT_ETC, TARGET_SN
    return {
        'options': ETC_OPTIONS[name],
        'grism_names': GRISM_NAMES.get(name, {}),
        'defaults': {**DEFAULT_CONFIG[name], 'seeing': DEFAULT_SEEING[name],
                     'mag_band': DEFAULT_MAG_BAND, 'etc': DEFAULT_ETC[name],
                     'target_sn': TARGET_SN[name], 'airmass_rule': 'worst'},
        'bands': list(ETC_FILTERS),
        'etcs': [name] + (['empirical'] if name == 'kast' else []),
        'airmass_rules': ['worst', 'mid', 'best'],
    }


@app.get('/api/etc')
def etc_spectrum(output_dir: str, target: str):
    """
    A scheduled target's predicted S/N spectrum (T3.4a): what the ETC
    returned at the airmass the target was scheduled at, about 200 points.
    """
    base = _safe_dir(output_dir) / 'etc'
    path = (base / f'{target}.json').resolve()
    if not path.is_relative_to(base.resolve()):
        raise HTTPException(400, 'target name escapes the plan directory')
    if not path.exists():
        raise HTTPException(404, f'no ETC spectrum for {target} (MOS blocks, '
                                 'fixed recipes and the empirical Kast rule '
                                 'have none; older plans predate them)')
    with open(path) as f:
        return json.load(f)


@app.get('/api/plans')
def list_plans():
    """Existing plan directories under the private plans directory, newest first."""
    out = []
    for path in sorted(PLANS_ROOT.glob('*')):
        if not path.is_dir():
            continue
        saved = path / 'plan_result.json'
        out.append({'name': path.name, 'output_dir': str(path),
                    'has_plan': saved.exists(),
                    'modified': saved.stat().st_mtime if saved.exists() else None})
    return sorted(out, key=lambda p: (p['modified'] or 0), reverse=True)


@app.get('/api/targets/columns')
def target_columns():
    """
    The columns a target table needs and may have, with the spellings
    recognised for each (T2.4). Served from targets_io so the setup page's
    list can never drift from what the loader actually reads.
    """
    from night_planner.targets_io import ALIASES, OPTIONAL_FIELDS, REQUIRED_FIELDS
    return {'required': list(REQUIRED_FIELDS), 'optional': list(OPTIONAL_FIELDS),
            'aliases': {k: list(v) for k, v in ALIASES.items()}}


@app.post('/api/targets/inspect')
def inspect_targets(file: UploadFile = File(None), path: str = Query(None)):
    """
    Report how a target table's columns map to the canonical schema.

    Returns the detected mapping plus `candidates` so the frontend can ask
    the user only about what's genuinely ambiguous -- and a short preview
    so they can see they uploaded what they meant to.
    """
    if file is not None:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        saved = UPLOAD_DIR / file.filename
        with open(saved, 'wb') as f:
            shutil.copyfileobj(file.file, f)
        source = str(saved)
    elif path:
        source = str(Path(path).expanduser().resolve())
        if not os.path.exists(source):
            raise HTTPException(404, f'no such file: {source}')
    else:
        raise HTTPException(400, 'supply either an uploaded file or a path')

    import pandas as pd
    frame = pd.read_csv(source)
    mapping = detect_mapping(frame)
    # Decided once, here, rather than guessed per row later: whether a
    # two-candidate slit is even meaningful is a property of where the
    # table came from.
    source_format = detect_format(frame)

    # Show the whole table, not a head(). A truncated preview with no
    # indication it was truncated reads as "my rows are missing" -- which
    # is exactly how appended targets at the bottom get reported as lost.
    preview, truncated = [], 0
    if mapping.ok:
        try:
            canonical = load_targets(frame, mapping=mapping)
            columns = ['name', 'ra_deg', 'dec_deg', 'mag', 'priority',
                       't_target', 'required', 'tags', 'dm']
            head = canonical[columns].head(PREVIEW_LIMIT).astype(object)
            # NaN isn't JSON; an unset t_target travels as null.
            preview = head.where(head.notna(), None).to_dict('records')
            truncated = max(len(canonical) - PREVIEW_LIMIT, 0)
        except TargetTableError as err:
            mapping.issues.append(str(err))

    # A priority column we could not read as numbers is the one thing that
    # must not pass in silence: dropping it on the floor unannounced is the
    # behaviour this whole field was added to fix.
    coercions = priority_coercions(frame, mapping=mapping)

    return {'path': source, 'n_rows': len(frame),
            'columns': list(frame.columns),
            'source_format': source_format,
            'mapping': mapping.to_dict(), 'preview': preview,
            'preview_truncated': truncated,
            'default_priority': DEFAULT_PRIORITY,
            'priority_coercions': coercions,
            'field_coercions': field_coercions(frame, mapping=mapping)}


# --------------------------------------------------------------------
# Generating and reading plans
# --------------------------------------------------------------------

class GenerateRequest(BaseModel):
    """
    Everything the setup page can send.

    The optional fields are genuinely Optional rather than `str = None`:
    under Pydantic v2 the latter types the field as `str` and rejects an
    explicit null, which is exactly what a blank form field sends.
    """
    instrument: str
    targets_csv: Optional[str] = None
    output_dir: Optional[str] = None
    date: Optional[str] = None
    start: Optional[str] = None        # 'HH:MM' local, manual/ToO start
    blocks: list = []                  # [{'start','end','reason'}]
    forced: list = []                  # [{'target','minutes'}]
    max_targets: Optional[int] = None
    assume_masks: bool = False         # schedule mask-needing targets anyway
    priorities: dict = {}              # {target name: float}, lower = better
    no_partials: bool = False          # leave idle time idle
    # Instrument configuration and observing assumptions (M4). Unset = the
    # instrument's default (instrument_params.DEFAULT_CONFIG / DEFAULT_SEEING).
    grism: Optional[str] = None
    grating: Optional[str] = None
    dichroic: Optional[str] = None
    slit: Optional[float] = None
    binning: Optional[str] = None
    seeing: Optional[float] = None     # FWHM arcsec
    mag_band: Optional[str] = None     # band of the mag column
    # Milestone 5 (T1.3, T3.4).
    airmass_rule: Optional[str] = None  # worst | mid | best
    etc: Optional[str] = None           # registry name or 'pkg.mod:func'
    target_sn: Optional[float] = None   # per sub-exposure
    # Milestone 10 (T4.1): several plans for the night, one per scenario
    # [{name, seeing?, start?, blocks?}], each in <output_dir>/<slug>/.
    scenarios: list = []


@app.post('/api/generate')
def generate(req: GenerateRequest):
    """
    Run the instrument's pipeline and return the normalized plan.

    Defined with `def` rather than `async def` on purpose: the scheduler is
    blocking, CPU- and network-bound, so FastAPI runs it in a worker thread
    instead of stalling the event loop.
    """
    if req.instrument not in INSTRUMENTS:
        raise HTTPException(400, f'unknown instrument: {req.instrument}')

    # The instrument scripts carry hardcoded fallback paths from the run
    # they were written for. That's a convenience on the command line and a
    # hazard here: a blank form field would otherwise silently read another
    # run's targets and overwrite that run's plan directory. Require both.
    if not req.targets_csv:
        raise HTTPException(400, 'choose a target table -- the planner will '
                                 'not fall back to another run\'s targets')
    if not req.output_dir:
        raise HTTPException(400, 'choose an output directory -- the planner '
                                 'will not write into another run\'s plan')

    # A bare name means a plan directory, not a path relative to wherever
    # the server happens to have been started. Typing "Keck-2026B-04"
    # otherwise silently creates it beside the repo root, where the viewer
    # will never list it.
    output_dir = Path(req.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = PLANS_ROOT / output_dir
    output_dir = output_dir.resolve()
    if not output_dir.is_relative_to(PLANS_ROOT.resolve()):
        raise HTTPException(400, f'plans are written under {PLANS_ROOT}; '
                                 f'{output_dir} is outside it')

    # Catch an instrument/option mismatch here, where it can be explained.
    # Letting it through means argparse rejects the flags somewhere inside
    # the instrument module and the only thing that reaches the browser is
    # an exit code.
    supports = INSTRUMENTS[req.instrument].get('supports', set())
    asked = {name for name in ('targets_csv', 'output_dir', 'date',
                                'max_targets', 'assume_masks', 'no_partials')
             if getattr(req, name)}
    asked |= {'forced'} if req.forced else set()
    config_keys = ('grism', 'grating', 'dichroic', 'slit', 'binning')
    if any(getattr(req, k) is not None for k in config_keys):
        asked.add('config')
    asked |= {k for k in ('seeing', 'mag_band', 'airmass_rule', 'etc', 'target_sn')
              if getattr(req, k) is not None}
    unsupported = sorted(asked - supports)
    if unsupported:
        raise HTTPException(
            400, f"the {req.instrument} pipeline does not accept "
                 f"{', '.join(unsupported)} -- it is still tied to its own "
                 f"run's targets and output directory. Use lris for a plan "
                 f"built from your own target table.")

    # A configuration the ETC can't model is the user's to fix, so say what
    # is allowed here rather than failing deep inside the run.
    from night_planner.instrument_params import (ConfigError, DEFAULT_CONFIG,
                                                 etc_filter, validate_config)
    try:
        config = dict(DEFAULT_CONFIG[req.instrument])
        config.update({k: getattr(req, k) for k in config_keys
                       if getattr(req, k) is not None})
        validate_config(req.instrument, config)
        if req.mag_band is not None:
            etc_filter(req.mag_band)
    except ConfigError as err:
        raise HTTPException(400, str(err))
    if req.seeing is not None and not 0 < req.seeing < 10:
        raise HTTPException(400, f'seeing {req.seeing}" is not plausible')
    if req.airmass_rule is not None and req.airmass_rule not in ('worst', 'mid', 'best'):
        raise HTTPException(400, 'airmass rule must be worst, mid or best')
    if req.target_sn is not None and req.target_sn <= 0:
        raise HTTPException(400, 'target S/N must be positive')
    if req.etc is not None:
        from night_planner.etc import load_etc
        try:
            load_etc(req.etc)
        except (ValueError, ImportError) as err:
            raise HTTPException(400, str(err))

    # Priorities travel in the table, so the CLI and the GUI consume exactly
    # the same input and the plan directory records what it was built from.
    targets_csv = req.targets_csv
    if req.priorities:
        targets_csv = _write_prioritized_targets(
            targets_csv, req.priorities, output_dir)

    argv = []
    for flag, value in (('--targets-csv', targets_csv),
                         ('--output-dir', str(output_dir)),
                         ('--date', req.date),
                         ('--start', req.start)):
        if value:
            argv += [flag, str(value)]
    if req.max_targets:
        argv += ['--max-targets', str(req.max_targets)]
    for block in req.blocks:
        reason = block.get('reason') or 'blocked'
        argv += ['--block', f"{block['start']}-{block['end']}@{reason}"]
    for forced in req.forced:
        argv += ['--force', f"{forced['target']}@{forced['minutes']}"]
    if req.assume_masks:
        argv.append('--assume-masks')
    if req.no_partials:
        argv.append('--no-partials')
    for name in (*config_keys, 'seeing', 'mag_band', 'airmass_rule', 'etc',
                 'target_sn'):
        value = getattr(req, name)
        if value is not None and value != '':
            argv += [f"--{name.replace('_', '-')}", str(value)]

    if req.scenarios:
        names = [str(s.get('name') or '').strip() for s in req.scenarios]
        if not all(names):
            raise HTTPException(400, 'every scenario needs a name')
        from night_planner.scenarios import slugify
        if len({slugify(n) for n in names}) != len(names):
            raise HTTPException(400, 'scenario names must differ')

    try:
        # argparse writes its complaint to stderr and then raises SystemExit
        # carrying only an exit code, so capture the text or the browser gets
        # a bare number.
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            if req.scenarios:
                return _generate_scenarios(req, argv, output_dir)
            plan = generate_plan(req.instrument, argv)
    except TargetTableError as err:
        # The table needs a column mapping -- hand back what was detected
        # so the frontend can ask rather than just failing.
        raise HTTPException(
            422, {'error': str(err), 'mapping': err.mapping.to_dict()})
    except SystemExit as err:
        detail = stderr.getvalue().strip().splitlines()
        message = detail[-1] if detail else f'exit code {err}'
        raise HTTPException(400, f'the {req.instrument} planner rejected this '
                                 f'request: {message}')
    return _plan_payload(plan)


def _generate_scenarios(req, argv, base_dir):
    """
    Generate one plan per scenario into <base>/<slug>/ and index them in
    <base>/scenarios.json (T4.1).

    Returns
    -------
    dict : the first scenario's plan payload, plus 'scenarios' (the index).
    """
    from night_planner.adapters import SITES
    from night_planner.scenarios import scenario_argv, slugify, write_index
    from night_planner.sun_events import find_sun_events

    site = SITES[req.instrument]
    # 'Lost first half' blocks from the start of the night: astronomical
    # dusk, unless a manual start was given.
    night_hhmm = req.start
    if not night_hhmm and req.date:
        sun = find_sun_events(req.date, site['location'], site['tz'])
        night_hhmm = f'{sun.dusk_astronomical:%H:%M}'

    entries, first = [], None
    for scenario in req.scenarios:
        s_argv, s_dir = scenario_argv(argv, scenario, str(base_dir), night_hhmm)
        plan = generate_plan(req.instrument, s_argv)
        entries.append({'name': scenario['name'], 'slug': slugify(scenario['name']),
                        'dir': s_dir, 'seeing': scenario.get('seeing'),
                        'start': scenario.get('start'),
                        'blocks': scenario.get('blocks') or []})
        first = first or plan
    write_index(str(base_dir), entries)
    return {**_plan_payload(first), 'scenarios': entries}


@app.get('/api/scenarios')
def get_scenarios(output_dir: str):
    """
    The scenario tabs for a plan directory (a base or one of its scenarios),
    with a comparison row each: targets scheduled, on-target hours, idle
    minutes, and targets unique to that scenario.
    """
    from night_planner.scenarios import comparison, find_base, load_index

    base, slug = find_base(str(_safe_dir(output_dir)))
    if base is None:
        return {'base': None, 'active': None, 'scenarios': []}
    entries = load_index(base)
    plans = {}
    for e in entries:
        plan = load_plan(os.path.join(base, e['slug']))
        if plan is not None:
            plans[e['slug']] = plan
    rows = comparison(plans)
    return {'base': base, 'active': slug or (entries[0]['slug'] if entries else None),
            'scenarios': [{**e, 'dir': os.path.join(base, e['slug']),
                           **rows.get(e['slug'], {})} for e in entries]}


def _plan_payload(plan):
    """
    A plan as the API serves it: PlanResult.to_dict() plus the LST at the
    start and end of the night (T2.3), for the timeline's LST axis.
    PlanResult stays astropy-free, so LST is added here.
    """
    from night_planner.adapters import SITES
    from night_planner.sky import lst_hours

    data = plan.to_dict()
    site = SITES.get(plan.instrument)
    if site is not None:
        lst = lst_hours([plan.night_start, plan.night_end], site['location'])
        data['lst_start_h'], data['lst_end_h'] = float(lst[0]), float(lst[1])
    return data


@app.get('/api/plan')
def get_plan(output_dir: str):
    """The saved normalized plan for a directory."""
    return _plan_payload(_require_plan(output_dir))


class RegenerateRequest(BaseModel):
    output_dir: str
    forced: list = []    # [{'target','minutes'}] -- replaces any previous set


@app.post('/api/regenerate')
def regenerate(req: RegenerateRequest):
    """
    Re-run an existing plan with a different set of forced targets.

    Reuses the exact inputs the plan was generated from, so nothing else
    shifts underneath the comparison -- only the --force flags are
    replaced. Which is the point: the observer decides to rescue a
    rejected target *after* seeing why it was dropped.
    """
    plan = _require_plan(req.output_dir)
    request = plan.request or {}
    if not request.get('argv'):
        raise HTTPException(
            409, 'this plan predates recorded inputs, so it cannot be '
                 're-run automatically -- generate it again from Setup')

    # Drop any previous --force pairs; the incoming list is authoritative.
    argv, skip = [], False
    for token in request['argv']:
        if skip:
            skip = False
            continue
        if token == '--force':
            skip = True
            continue
        if token.startswith('--force='):
            continue
        argv.append(token)

    for forced in req.forced:
        argv += ['--force', f"{forced['target']}@{forced['minutes']}"]

    try:
        return _plan_payload(generate_plan(request.get('instrument', plan.instrument), argv))
    except SystemExit as err:
        raise HTTPException(400, f'planner exited: {err}')


@app.get('/api/airmass')
def airmass(output_dir: str, target: str, step_min: int = 5):
    """
    Airmass/alt/az track for one target across its night.

    Computed on demand rather than stored: it's a dense curve that would
    bloat every plan file, and it's cheap to recompute for one target.
    """
    from night_planner.adapters import SITES
    from night_planner.sky import night_grid, track

    plan = _require_plan(output_dir)
    match = [t for t in plan.schedule if t.name == target]
    decision = [d for d in plan.decisions if d.name == target]
    if match:
        ra_deg, dec_deg = match[0].ra_deg, match[0].dec_deg
    elif decision and decision[0].ra_deg is not None:
        ra_deg, dec_deg = decision[0].ra_deg, decision[0].dec_deg
    else:
        raise HTTPException(404, f'{target} is not in this plan')

    location = SITES[plan.instrument]['location']
    times = night_grid(plan.sun.sunset, plan.sun.sunrise, step_min)
    curve = track(ra_deg, dec_deg, times, location)

    points = [{'time': t.isoformat(), 'airmass': a, 'alt': alt, 'az': az,
               'ha': ha}
              for t, a, alt, az, ha in zip(times, curve['airmass'],
                                            curve['alt'], curve['az'],
                                            curve['ha'])]
    scheduled = ({'start': match[0].science_start.isoformat(),
                  'end': match[0].end.isoformat()} if match else None)
    return {'target': target, 'ra_deg': ra_deg, 'dec_deg': dec_deg,
            'points': points, 'scheduled': scheduled,
            'sun': plan.sun.to_dict()}


@app.get('/api/airmass/all')
def airmass_all(output_dir: str, step_min: int = 5, include_rejected: bool = False):
    """
    Every target's airmass across the night, plus the moon and LST.

    One call rather than one per target: the night chart draws all of
    them together, and the sample grid, sidereal times and moon are
    shared, so computing them once is both faster and guarantees every
    curve lands on the same x values.

    `observable` marks the samples a target is actually pointable for,
    which is what lets the chart draw the reachable part of a curve
    differently from the rest.
    """
    from night_planner.adapters import SITES
    from night_planner.sky import lst_hours, moon_track, night_grid, track

    plan = _require_plan(output_dir)
    site = SITES[plan.instrument]
    location = site['location']

    times = night_grid(plan.sun.sunset, plan.sun.sunrise, step_min)
    sidereal = lst_hours(times, location)

    scheduled = {t.name: t for t in plan.schedule}
    wanted = list(plan.schedule)
    if include_rejected:
        wanted += [d for d in plan.decisions
                   if d.status == 'rejected' and d.ra_deg is not None
                   and d.name not in scheduled]

    targets = []
    for item in wanted:
        curve = track(item.ra_deg, item.dec_deg, times, location, lst=sidereal)
        block = scheduled.get(item.name)
        targets.append({
            'name': item.name,
            'ra_deg': item.ra_deg, 'dec_deg': item.dec_deg,
            'mag': item.mag,
            'scheduled': ({'start': block.science_start.isoformat(),
                           'end': block.end.isoformat()} if block else None),
            'airmass': curve['airmass'],
            'ha': curve['ha'],
        })

    return {
        'output_dir': plan.output_dir,
        'telescope': plan.telescope,
        'date': plan.date,
        'times': [t.isoformat() for t in times],
        'lst': [round(float(h), 4) for h in sidereal],
        'sun': plan.sun.to_dict(),
        'moon': moon_track(times, location),
        'targets': targets,
    }


# --------------------------------------------------------------------
# Files: finders, starlist, export
# --------------------------------------------------------------------

@app.get('/api/image')
def image(output_dir: str, name: str, v: str = None):
    """
    Serve a finder chart from the plan's finders/ directory.

    `v` is ignored here and carries the file's modification time, set by
    the caller. Without it the URL of a regenerated chart is unchanged,
    so a browser holding the cached copy shows yesterday's slit next to
    today's report -- which is how a parallactic chart ends up sitting
    under a line claiming it was drawn through both candidates.
    """
    base = _safe_dir(output_dir) / 'finders'
    path = (base / name).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        raise HTTPException(404, f'no such finder: {name}')
    # Safe to cache hard, because the URL changes whenever the file does.
    return FileResponse(path, media_type='image/png',
                        headers={'Cache-Control':
                                 'public, max-age=86400, immutable'})


@app.get('/api/finders')
def finders(output_dir: str):
    """
    List the finder charts available for a plan.

    Each entry carries the file's modification time so the viewer can
    version the image URL and never show a stale chart.
    """
    base = _safe_dir(output_dir) / 'finders'
    if not base.is_dir():
        return []
    return [{'name': p.name, 'mtime': int(p.stat().st_mtime)}
            for p in sorted(base.glob('*.png'))]


@app.get('/api/starlist', response_class=PlainTextResponse)
def starlist(output_dir: str, name: str = None):
    """
    Raw starlist text.

    Defaults to the richest starlist present: the one with offset stars and
    PA, rather than the coordinates-only list the scheduler writes.
    """
    base = _safe_dir(output_dir)
    if name:
        path = (base / name).resolve()
        if not path.is_relative_to(base.resolve()) or not path.is_file():
            raise HTTPException(404, f'no such starlist: {name}')
    else:
        candidates = sorted(base.glob('*.starlist'),
                            key=lambda p: p.stat().st_size, reverse=True)
        if not candidates:
            raise HTTPException(404, 'no starlist in this plan directory')
        path = candidates[0]
    return path.read_text()


class FinderRequest(BaseModel):
    output_dir: str
    targets: list = []            # empty = every scheduled target
    slit_mode: str = 'parallactic'  # or 'candidates': both hosts on the slit
    overwrite: bool = False


@app.post('/api/finders/generate')
def generate_finders(req: FinderRequest):
    """
    Build finder charts for a plan's targets.

    Two slit angles to choose between. 'parallactic' is the default and
    needs nothing but the coordinates. 'candidates' lays the slit through
    the two PATH candidates, which only exists for targets that came from
    FFFF-PZ -- the second candidate is read from the plan's own target
    table, so nothing is fetched and no Resource has to be live.

    Any target without a second candidate falls back to parallactic and
    is named in the report. That is the one outcome worth being loud
    about: silently returning a parallactic slit to someone who asked for
    both candidates means they set an angle they did not choose.
    """
    from night_planner.adapters import SITES
    from night_planner.finder import generate_for_plan, slit_report

    base = _safe_dir(req.output_dir)
    plan = _require_plan(req.output_dir)
    site = SITES.get(plan.instrument)
    if site is None:
        raise HTTPException(400, f'no site known for {plan.instrument}')

    if req.slit_mode not in ('parallactic', 'candidates'):
        raise HTTPException(400, f'slit_mode must be parallactic or '
                                 f'candidates, not {req.slit_mode}')

    finder_dir = base / 'finders'
    targets_csv = _plan_targets_csv(plan)
    if req.slit_mode == 'candidates' and not targets_csv:
        raise HTTPException(
            400, 'this plan does not record the table it came from, so the '
                 'second candidate cannot be read -- regenerate the plan '
                 'from Setup, or use the parallactic slit')

    key = str(finder_dir)

    def note(done, total, name):
        _FINDER_PROGRESS[key] = {'done': done, 'total': total,
                                 'current': name,
                                 'running': name is not None}

    try:
        results = generate_for_plan(
            plan, site['location'], finder_dir,
            targets=req.targets or None, overwrite=req.overwrite,
            slit_length_arcmin=site.get('slit_length_arcmin', 2.9),
            slit_width_arcsec=site.get('slit_width_arcsec', 1.0),
            targets_csv=targets_csv, slit_mode=req.slit_mode,
            rotator=site.get('rotator'), progress=note)
    finally:
        # A crash must not leave the viewer polling a bar that never ends.
        _FINDER_PROGRESS.pop(key, None)

    report = slit_report(results, req.slit_mode)
    _write_slit_report(finder_dir, plan, report)
    return {'mode': req.slit_mode, 'finder_dir': str(finder_dir),
            'fell_back': report['fell_back'], 'report': report,
            'results': results}


# Live progress for a running finder generation, keyed by finders dir.
# A chart takes seconds (an image fetch plus a Gaia query), so a run of
# ten is long enough that a spinner alone tells the observer nothing.
# The endpoint is a plain `def`, so FastAPI runs it in a worker thread
# and the poll below is served while it works.
_FINDER_PROGRESS = {}


@app.get('/api/finders/progress')
def finders_progress(output_dir: str):
    """How far a running finder generation has got, if one is running."""
    key = str(_safe_dir(output_dir) / 'finders')
    return _FINDER_PROGRESS.get(key, {'running': False})


def _write_slit_report(finder_dir, plan, report):
    """
    Save the slit report beside the charts.

    Written to disk as well as returned because it is the record of what
    angle each chart was drawn at, and that question comes up again days
    later when a spectrum looks wrong.
    """
    path = Path(finder_dir) / 'slit_report.txt'
    header = [f'Slit angles for {plan.date} ({Path(plan.output_dir).name})',
              f'Requested: {report["requested"]}',
              'Created by JXP and Claude -- night-planner', '']
    if report['fell_back']:
        header += [f'Fell back to parallactic (not from FFFF-PZ): '
                   f'{", ".join(report["fell_back"])}', '']
    try:
        path.write_text('\n'.join(header + report['lines']) + '\n')
    except OSError:
        pass        # the report is a convenience; never fail a render for it


class StarlistRequest(BaseModel):
    output_dir: str
    include_standards: bool = True
    max_airmass: float = 2.0
    filename: Optional[str] = None
    allow_missing_finders: bool = False


@app.post('/api/starlist/generate')
def generate_starlist(req: StarlistRequest):
    """
    Write a starlist for a plan, optionally bracketed by flux standards.

    Standards are chosen from the PypeIt library at the times they'd
    actually be taken, so they match the science frames in airmass as well
    as in time.
    """
    from night_planner.adapters import SITES
    from night_planner.standards import load_library
    from night_planner.starlist import build_starlist

    base = _safe_dir(req.output_dir)
    plan = _require_plan(req.output_dir)

    site = SITES.get(plan.instrument)
    if site is None:
        raise HTTPException(400, f'no site known for {plan.instrument}')

    # A starlist without offset stars is close to useless at the telescope
    # for faint hosts, and the offsets come from the finder step. Refuse
    # rather than quietly emitting coordinate-only rows.
    finder_dir = base / 'finders'
    scheduled = {t.name for t in plan.schedule}
    have = {p.stem.replace('_finder', '')
            for p in finder_dir.glob('*_finder.json')} if finder_dir.is_dir() else set()
    missing = sorted(scheduled - have)
    if missing and not req.allow_missing_finders:
        raise HTTPException(
            409, {'error': 'generate finder charts first -- the starlist needs '
                           'their offset stars and slit angles',
                  'missing': missing,
                  'hint': 'use the Finders page, or re-send with '
                          'allow_missing_finders to get coordinate-only rows'})

    try:
        library = load_library() if req.include_standards else None
    except FileNotFoundError as err:
        raise HTTPException(503, str(err))

    text, notes = build_starlist(
        plan, include_standards=req.include_standards,
        location=site['location'], library=library,
        finder_dir=base / 'finders', max_airmass=req.max_airmass,
        style=site.get('starlist_style', 'keck'))

    name = req.filename or f'{base.name}_generated.starlist'
    path = (base / name).resolve()
    if not path.is_relative_to(base.resolve()):
        raise HTTPException(400, 'starlist name escapes the plan directory')
    path.write_text(text)

    return {'path': str(path), 'name': name, 'text': text, 'notes': notes}


# --------------------------------------------------------------------
# Observing log (with the calibrations checklist) and the night report
# --------------------------------------------------------------------

def _plan_here(output_dir):
    """
    The resolved plan directory and its plan, with plan.output_dir pinned
    to that directory. A copied or moved plan still records where it was
    generated, and the log and report must land beside the plan that was
    actually asked for.
    """
    base = _safe_dir(output_dir)
    plan = _require_plan(output_dir)
    plan.output_dir = str(base)
    return base, plan


def _log_context(output_dir):
    """
    Where the night's log lives and which plans feed it.

    A plain plan directory keeps its own log. A night with scenarios (T4.1)
    has one log at the scenario base: only one scenario is observed. Target
    rows follow the scenario marked in use (night.scenario, else the one
    being viewed), and calibrations are the union over every scenario.

    Returns
    -------
    (log_dir, plan, extra_plans) : (Path, PlanResult, list of PlanResult)
    """
    from night_planner.observing_log import load_log
    from night_planner.scenarios import find_base, load_index

    here, plan = _plan_here(output_dir)
    base, slug = find_base(str(here))
    if base is None:
        return here, plan, []
    entries = load_index(base)
    slugs = [e['slug'] for e in entries]
    log = load_log(base) or {}
    in_use = (log.get('night') or {}).get('scenario')
    if in_use not in slugs:
        in_use = slug or (slugs[0] if slugs else None)
    plans = {}
    for s in slugs:
        p = load_plan(os.path.join(base, s))
        if p is not None:
            p.output_dir = os.path.join(base, s)
            plans[s] = p
    plan = plans.get(in_use, plan)
    return Path(base), plan, [p for s, p in plans.items() if s != in_use]


def _log_payload(plan, log):
    """The log plus everything the page derives from it."""
    from night_planner import observing_log as olog
    from night_planner.adapters import SITES

    location = SITES.get(plan.instrument, {}).get('location')
    return {
        'log': log,
        'derived': olog.derived(log, plan, location),
        'options': {
            'statuses': olog.STATUSES, 'reasons': olog.REASONS,
            'qualities': olog.QUALITIES, 'success': olog.SUCCESS,
            'sky': olog.SKY, 'checks': olog.CHECKS,
            'lost_causes': olog.LOST_CAUSES,
        },
    }


@app.get('/api/log')
def get_log(output_dir: str):
    """
    The night's observing log, created on first visit and merged with the
    current plan on every visit, so a regenerated plan shows up without
    losing anything already typed.
    """
    from night_planner.observing_log import open_log

    log_dir, plan, extra = _log_context(output_dir)
    return _log_payload(plan, open_log(plan, str(log_dir), extra_plans=extra))


class LogPatch(BaseModel):
    output_dir: str
    # A list of keys, e.g. ["targets", "TGT0590", "status"]. A dotted
    # string is accepted too, for hand-typed calls, as long as no key has
    # a dot in it.
    path: list[str] | str
    value: object = None
    source: str = 'manual'


@app.patch('/api/log')
def patch_log(req: LogPatch):
    """Set one field of the log (small writes, safe to autosave on blur)."""
    from night_planner import observing_log as olog

    log_dir, plan, extra = _log_context(req.output_dir)
    log = olog.open_log(plan, str(log_dir), extra_plans=extra)
    path = req.path.split('.') if isinstance(req.path, str) else req.path
    try:
        value = olog.set_field(log, plan, path, req.value, source=req.source)
    except olog.LogEditError as err:
        raise HTTPException(400, str(err))
    olog.save_log(str(log_dir), log)
    return {'value': value, **_log_payload(plan, log)}


class ReportRequest(BaseModel):
    output_dir: str
    survey: str = 'CHIME/FRB'
    resource: Optional[str] = None


@app.post('/api/log/report')
def log_report(req: ReportRequest):
    """
    Write observing_report_<date>.md and the FFFF-PZ CSV from the log.
    Gaps (pending rows, missing frames, calibrations not taken) come back as
    warnings; the report is written anyway.
    """
    from night_planner.adapters import SITES
    from night_planner.observing_log import open_log
    from night_planner.observing_report import write_report

    log_dir, plan, extra = _log_context(req.output_dir)
    log = open_log(plan, str(log_dir), extra_plans=extra)
    # The report sits with the log: at the scenario base for a night with
    # scenarios.
    plan.output_dir = str(log_dir)
    location = SITES.get(plan.instrument, {}).get('location')
    out = write_report(plan, log, location, survey=req.survey,
                       resource=req.resource)
    with open(out['markdown_path']) as f:
        out['markdown'] = f.read()
    return out


@app.get('/api/export')
def export(output_dir: str, name: str = None):
    """Zip the whole plan directory for download."""
    base = _safe_dir(output_dir)
    stem = name or base.name
    archive = Path(tempfile.gettempdir()) / f'{stem}.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(base.rglob('*')):
            if path.is_file():
                zf.write(path, path.relative_to(base))
    return FileResponse(archive, media_type='application/zip',
                        filename=f'{stem}.zip')


# Mounted last so it never shadows the API routes above.
if FRONTEND_DIR.is_dir():
    app.mount('/', StaticFiles(directory=str(FRONTEND_DIR), html=True),
              name='frontend')
