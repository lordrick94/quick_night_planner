"""
Observing log for one night: what actually happened, next to what was
planned. The calibrations checklist is part of it.

Created by JXP and Claude

One file, `observing_log.json`, lives in the plan directory beside
`plan_result.json`. It holds:

- night : header fields (observers, dome open/close, time lost, notes)
- calibrations : {item_id: {...}}, one per calibration x configuration and
  per calibration x slitmask, from instrument_params.CALIBRATION_RULES
- night_checklist : {item_id: {...}}, from instrument_params.NIGHT_CHECKLIST
- conditions : [{ut, sky, seeing, note}], a timestamped log
- targets : {name: {...}}, one row per scheduled target and standard
- unplanned : [{...}], targets observed that weren't in the plan
- edits : {path_key: {updated_ut, source}}, who/what set each value

Regenerating a plan mid-night must never lose what the observer typed.
merge_log() is the one rule for that. Rows and calibration items with any
user input are kept; if they left the plan they're marked
`not_in_plan: True`.

Methods, not classes, per the repo convention.
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone

from .instrument_params import (CALIBRATION_LABELS, CALIBRATION_RULES,
                                DEFAULT_CONFIG, NIGHT_CHECKLIST, config_label,
                                is_mask_mode)

FILENAME = 'observing_log.json'
LOG_VERSION = 1

STATUSES = ('pending', 'observed', 'partial', 'not_observed', 'skipped')
REASONS = ('', 'weather', 'ran_out_of_time', 'technical', 'not_acquired',
           'bumped', 'other')
QUALITIES = ('', 'good', 'usable', 'poor')
SUCCESS = ('', 'yes', 'no', 'unknown')
SKY = ('', 'clear', 'thin_cirrus', 'patchy', 'thick', 'closed')
CHECKS = ('acquired', 'on_slit', 'exposures_complete', 'quicklook')
LOST_CAUSES = ('weather', 'technical', 'other')

# Free-text fields observers can set on a target (or unplanned) row.
_TARGET_TEXT = ('reason_text', 'actual_start_ut', 'exposures_red',
                'exposures_blue', 'frames', 'pa', 'seeing', 'z', 'comments')
_NIGHT_TEXT = ('observers', 'support', 'dome_open_ut', 'dome_close_ut',
               'sky_summary', 'seeing_range', 'weather_notes', 'notes',
               'ffffpz_conditions', 'scenario')
MAX_TEXT = 2000


# --------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------

def _now_ut():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def default_configs(plan):
    """
    The configurations a plan was run with.

    Parameters
    ----------
    plan : PlanResult

    Returns
    -------
    list of dict: the plan's own configuration (PlanResult.config, M4),
    or the instrument's DEFAULT_CONFIG for a plan saved before that existed.
    It's a list so a multi-config night needs no change later.
    """
    keys = ('grism', 'grating', 'dichroic', 'slit', 'binning')
    config = {k: v for k, v in (getattr(plan, 'config', None) or {}).items()
              if k in keys}
    return [config or {k: v for k, v in DEFAULT_CONFIG.get(plan.instrument, {}).items()
                       if k in keys}]


def calibration_items(plan, configs, extra_plans=()):
    """
    The calibrations a night needs, from CALIBRATION_RULES and the plan.

    Parameters
    ----------
    plan : PlanResult
        Masks are scheduled targets whose mode starts with 'MOS'. The
        mask is named after its target.
    configs : list of dict
        Instrument configurations used on the night.
    extra_plans : iterable of PlanResult
        The night's other scenarios (T4.1). Their configurations and masks
        are added, because a mask needs its arcs and flats if any scenario
        might use it.

    Returns
    -------
    list of dict, each with 'id' ('{kind}:{scope}:{scope_name}'), 'kind',
    'scope' ('config' | 'mask'), 'scope_name' and 'label'. Grouped by
    configuration first, then by mask.
    """
    rules = CALIBRATION_RULES.get(plan.instrument,
                                  {'per_config': [], 'per_mask': []})
    items, seen = [], set()
    configs = list(configs)
    for other in extra_plans:
        for config in default_configs(other):
            if config not in configs:
                configs.append(config)
    for config in configs:
        name = config_label(plan.instrument, config)
        if name in seen:
            continue
        seen.add(name)
        for kind in rules['per_config']:
            items.append({'id': f'{kind}:config:{name}', 'kind': kind,
                          'scope': 'config', 'scope_name': name,
                          'label': CALIBRATION_LABELS.get(kind, kind)})
    masks = []
    for p in (plan, *extra_plans):
        masks += [t.name for t in p.schedule
                  if is_mask_mode(t.mode) and t.name not in masks]
    for mask in masks:
        for kind in rules['per_mask']:
            items.append({'id': f'{kind}:mask:{mask}', 'kind': kind,
                          'scope': 'mask', 'scope_name': mask,
                          'label': CALIBRATION_LABELS.get(kind, kind)})
    return items


def _finder_pa(plan, name):
    """Planned slit PA (and Shane tub settings) from the finder sidecar."""
    path = os.path.join(plan.output_dir or '', 'finders', f'{name}_finder.json')
    if not os.path.exists(path):
        return '', None
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return '', None
    pa = data.get('slit_pa')
    return ('' if pa is None else f'{float(pa):.1f}'), data.get('cass_tub')


def _iso(dt):
    return dt.isoformat() if dt is not None else None


def planned_rows(plan):
    """
    The rows the target table starts from: scheduled targets plus the
    standards the plan emits as overheads, in time order.

    Parameters
    ----------
    plan : PlanResult

    Returns
    -------
    list of (name, planned_dict, kind) with kind 'science' or 'standard'.
    """
    rows = []
    for t in plan.schedule:
        pa, tub = _finder_pa(plan, t.name)
        rows.append((t.start, t.name, {
            'mode': t.mode, 'start': _iso(t.start),
            'science_start': _iso(t.science_start), 'end': _iso(t.end),
            'exposure_red': t.exposure_red, 'exposure_blue': t.exposure_blue,
            'on_target_min': t.on_target_min, 'ra_deg': t.ra_deg,
            'dec_deg': t.dec_deg, 'mag': t.mag, 'pa': pa, 'cass_tub': tub,
        }, 'science'))
    for start, end, label in plan.overheads:
        if 'standard' not in label.lower():
            continue
        rows.append((start, label, {
            'mode': 'standard', 'start': _iso(start), 'science_start': _iso(start),
            'end': _iso(end), 'exposure_red': '', 'exposure_blue': '',
            'on_target_min': (end - start).total_seconds() / 60,
            'ra_deg': None, 'dec_deg': None, 'mag': None, 'pa': '',
            'cass_tub': None,
        }, 'standard'))
    rows.sort(key=lambda r: r[0])
    return [(name, planned, kind) for _, name, planned, kind in rows]


def _blank_target(planned, kind, order):
    return {
        'kind': kind, 'order': order, 'planned': planned,
        'not_in_plan': False, 'status': 'pending', 'reason': '',
        'reason_text': '', 'actual_start_ut': '', 'exposures_red': '',
        'exposures_blue': '', 'frames': '', 'pa': planned.get('pa', ''),
        'sky': '', 'seeing': '', 'checks': {k: False for k in CHECKS},
        'quality': '', 'success': '', 'z': '', 'comments': '',
    }


def _blank_calibration(item, order):
    return {**{k: item[k] for k in ('kind', 'scope', 'scope_name', 'label')},
            'order': order, 'not_in_plan': False, 'done': False,
            'ut': '', 'frames': '', 'note': ''}


def new_log(plan, configs=None, extra_plans=()):
    """
    A fresh, empty log for a plan.

    Parameters
    ----------
    plan : PlanResult
    configs : list of dict, optional
        Defaults to default_configs(plan).

    Returns
    -------
    dict : the log (see the module docstring for its keys).
    """
    configs = configs if configs is not None else default_configs(plan)
    log = {
        'version': LOG_VERSION,
        'instrument': plan.instrument,
        'telescope': plan.telescope,
        'date': plan.date,
        'configs': [{'label': config_label(plan.instrument, c), **c}
                    for c in configs],
        'night': {**{k: '' for k in _NIGHT_TEXT},
                  'dome_open_ut': _utc_hhmm(plan.night_start),
                  'dome_close_ut': _utc_hhmm(plan.night_end),
                  'time_lost': []},
        'calibrations': {},
        'night_checklist': {key: {'label': label, 'done': False, 'order': i}
                            for i, (key, label) in enumerate(
                                NIGHT_CHECKLIST.get(plan.instrument, []))},
        'conditions': [],
        'targets': {},
        'unplanned': [],
        'edits': {},
    }
    return merge_log(log, plan, configs, extra_plans)


def _utc_hhmm(dt):
    if dt is None:
        return ''
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')


def _path_key(path):
    return json.dumps(list(path))


def _touched(log, prefix):
    """True if any edit was recorded at or under `prefix` (a path list)."""
    head = _path_key(prefix)[:-1]   # drop the closing bracket
    return any(k == head + ']' or k.startswith(head + ',')
               for k in log.get('edits', {}))


def merge_log(log, plan, configs=None, extra_plans=()):
    """
    Bring a log up to date with a (possibly regenerated) plan.

    Parameters
    ----------
    log : dict
        An existing log. It is modified in place and also returned.
    plan : PlanResult
    configs : list of dict, optional
        Defaults to default_configs(plan).
    extra_plans : iterable of PlanResult
        Other scenarios of the same night; their calibrations are kept too.

    Returns
    -------
    dict : the merged log.
        - Targets and calibration items still in the plan get fresh planned
          values, and keep everything the observer typed.
        - New targets and items get blank, pending/unticked entries.
        - Ones that left the plan are kept and marked `not_in_plan: True`
          if they hold any user input; untouched ones are dropped.
    """
    configs = configs if configs is not None else default_configs(plan)
    log['configs'] = [{'label': config_label(plan.instrument, c), **c}
                      for c in configs]

    # Targets
    rows = planned_rows(plan)
    current = {name for name, _, _ in rows}
    for order, (name, planned, kind) in enumerate(rows):
        row = log['targets'].get(name)
        if row is None:
            log['targets'][name] = _blank_target(planned, kind, order)
        else:
            row.update(planned=planned, kind=kind, order=order,
                       not_in_plan=False)
            if not row.get('pa') and not _touched(log, ['targets', name, 'pa']):
                row['pa'] = planned.get('pa', '')
    for name in list(log['targets']):
        if name in current:
            continue
        if _touched(log, ['targets', name]):
            log['targets'][name]['not_in_plan'] = True
        else:
            del log['targets'][name]

    # Calibrations
    items = calibration_items(plan, configs, extra_plans)
    current = {item['id'] for item in items}
    for order, item in enumerate(items):
        entry = log['calibrations'].get(item['id'])
        if entry is None:
            log['calibrations'][item['id']] = _blank_calibration(item, order)
        else:
            entry.update(order=order, not_in_plan=False)
    for item_id in list(log['calibrations']):
        if item_id in current:
            continue
        if _touched(log, ['calibrations', item_id]):
            log['calibrations'][item_id]['not_in_plan'] = True
        else:
            del log['calibrations'][item_id]
    return log


# --------------------------------------------------------------------
# Disk
# --------------------------------------------------------------------

def load_log(output_dir):
    """
    Read observing_log.json from a plan directory.

    Parameters
    ----------
    output_dir : str

    Returns
    -------
    dict, or None if the directory has no log yet.
    """
    path = os.path.join(output_dir, FILENAME)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def save_log(output_dir, log):
    """
    Write observing_log.json atomically (temp file + rename), so an
    autosave interrupted mid-write never leaves a truncated log.

    Parameters
    ----------
    output_dir : str
    log : dict

    Returns
    -------
    str : the path written.
    """
    path = os.path.join(output_dir, FILENAME)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(log, f, indent=2)
    os.replace(tmp, path)
    return path


def open_log(plan, output_dir=None, configs=None, extra_plans=()):
    """
    Load the plan's log (creating it if needed), merge it with the plan,
    save it and return it.

    Parameters
    ----------
    plan : PlanResult
    output_dir : str, optional
        Defaults to plan.output_dir.
    configs : list of dict, optional
    extra_plans : iterable of PlanResult
        The night's other scenarios (T4.1): calibrations are their union.

    Returns
    -------
    dict : the log.
    """
    output_dir = output_dir or plan.output_dir
    log = load_log(output_dir)
    log = (new_log(plan, configs, extra_plans) if log is None
           else merge_log(log, plan, configs, extra_plans))
    save_log(output_dir, log)
    return log


# --------------------------------------------------------------------
# Editing
# --------------------------------------------------------------------

class LogEditError(ValueError):
    """A PATCH that names an unknown field or carries a bad value."""


def _text(value):
    if value is None:
        return ''
    if not isinstance(value, (str, int, float)):
        raise LogEditError('expected text')
    value = str(value)
    if len(value) > MAX_TEXT:
        raise LogEditError(f'text longer than {MAX_TEXT} characters')
    return value


def _choice(value, allowed):
    value = '' if value is None else str(value)
    if value not in allowed:
        raise LogEditError(f'{value!r} is not one of {", ".join(a for a in allowed if a)}')
    return value


def _bool(value):
    if not isinstance(value, bool):
        raise LogEditError('expected true or false')
    return value


def resolve_ut(plan, value):
    """
    Turn an observer's UT time into a full UTC timestamp.

    Parameters
    ----------
    plan : PlanResult
        Its night (night_start..night_end) picks the UT date for a bare
        time, so 'HH:MM' never lands on the wrong day across UT midnight.
    value : str
        '', 'HH:MM', or a full ISO timestamp (from a "now" button).

    Returns
    -------
    str : '' or 'YYYY-MM-DDTHH:MMZ'.
    """
    value = (value or '').strip()
    if not value:
        return ''
    m = re.fullmatch(r'(\d{1,2}):(\d{2})', value)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if hour > 23 or minute > 59:
            raise LogEditError(f'bad UT time {value!r}')
        start = plan.night_start.astimezone(timezone.utc)
        mid = start + (plan.night_end - plan.night_start) / 2
        # The candidate on the UT date nearest the middle of the night.
        best = None
        for day in (-1, 0, 1):
            d = (mid + timedelta(days=day)).date()
            cand = datetime(d.year, d.month, d.day, hour, minute,
                            tzinfo=timezone.utc)
            if best is None or abs(cand - mid) < abs(best - mid):
                best = cand
        return best.strftime('%Y-%m-%dT%H:%MZ')
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise LogEditError(f'bad UT time {value!r} (use HH:MM)')
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')


def _clean_target_field(plan, field, value):
    if field == 'status':
        return _choice(value, STATUSES)
    if field == 'reason':
        return _choice(value, REASONS)
    if field == 'quality':
        return _choice(value, QUALITIES)
    if field == 'success':
        return _choice(value, SUCCESS)
    if field == 'sky':
        return _choice(value, SKY)
    if field == 'actual_start_ut':
        return resolve_ut(plan, _text(value))
    if field in _TARGET_TEXT:
        return _text(value)
    raise LogEditError(f'unknown target field {field!r}')


def _clean_unplanned(plan, value):
    if not isinstance(value, list):
        raise LogEditError('unplanned must be a list')
    out = []
    for row in value:
        if not isinstance(row, dict) or not _text(row.get('name')).strip():
            raise LogEditError('each unplanned target needs a name')
        clean = {'name': _text(row['name']).strip(),
                 'mode': _text(row.get('mode') or 'longslit'),
                 'ra_deg': row.get('ra_deg'), 'dec_deg': row.get('dec_deg'),
                 'mag': row.get('mag'),
                 'checks': {k: bool((row.get('checks') or {}).get(k))
                            for k in CHECKS}}
        for field in ('status', 'reason', 'quality', 'success', 'sky',
                      *_TARGET_TEXT):
            clean[field] = _clean_target_field(
                plan, field, row.get(field, 'observed' if field == 'status' else ''))
        out.append(clean)
    return out


def _clean_conditions(plan, value):
    if not isinstance(value, list):
        raise LogEditError('conditions must be a list')
    out = []
    for row in value:
        if not isinstance(row, dict):
            raise LogEditError('each condition entry must be an object')
        out.append({'ut': resolve_ut(plan, _text(row.get('ut'))),
                    'sky': _choice(row.get('sky'), SKY),
                    'seeing': _text(row.get('seeing')),
                    'note': _text(row.get('note'))})
    out.sort(key=lambda r: r['ut'] or '~')
    return out


def _clean_time_lost(value):
    if not isinstance(value, list):
        raise LogEditError('time_lost must be a list')
    out = []
    for row in value:
        if not isinstance(row, dict):
            raise LogEditError('each time-lost entry must be an object')
        try:
            minutes = float(row.get('minutes') or 0)
        except (TypeError, ValueError):
            raise LogEditError('time lost minutes must be a number')
        if minutes < 0:
            raise LogEditError('time lost minutes cannot be negative')
        out.append({'minutes': minutes,
                    'cause': _choice(row.get('cause') or 'other', LOST_CAUSES),
                    'reason': _text(row.get('reason'))})
    return out


def set_field(log, plan, path, value, source='manual', now=None):
    """
    Set one value in the log, validating the path and the value.

    Parameters
    ----------
    log : dict
        Modified in place.
    plan : PlanResult
        Needed to resolve bare UT times.
    path : list of str
        Allowed paths:
        - ['night', field] (or ['night', 'time_lost'] for the whole list)
        - ['calibrations', item_id, 'done'|'ut'|'frames'|'note']
        - ['night_checklist', key, 'done']
        - ['conditions'] (the whole list)
        - ['targets', name, field] or ['targets', name, 'checks', check]
        - ['unplanned'] (the whole list)
    value : any JSON value
    source : str
        'manual' (typed on the page) or 'auto' (written by a tool).
    now : str, optional
        UT timestamp to record; defaults to the current time.

    Returns
    -------
    The cleaned value that was stored.

    Raises
    ------
    LogEditError for an unknown path or a bad value.
    """
    path = [str(p) for p in path]
    if source not in ('manual', 'auto'):
        raise LogEditError("source must be 'manual' or 'auto'")
    if not path:
        raise LogEditError('empty path')
    root = path[0]

    if root == 'night' and len(path) == 2:
        if path[1] == 'time_lost':
            clean = _clean_time_lost(value)
        elif path[1] in ('dome_open_ut', 'dome_close_ut'):
            clean = resolve_ut(plan, _text(value))
        elif path[1] in _NIGHT_TEXT:
            clean = _text(value)
        else:
            raise LogEditError(f'unknown night field {path[1]!r}')
        log['night'][path[1]] = clean

    elif root == 'calibrations' and len(path) == 3:
        entry = log['calibrations'].get(path[1])
        if entry is None:
            raise LogEditError(f'no calibration item {path[1]!r}')
        field = path[2]
        if field == 'done':
            clean = _bool(value)
        elif field == 'ut':
            clean = resolve_ut(plan, _text(value))
        elif field in ('frames', 'note'):
            clean = _text(value)
        else:
            raise LogEditError(f'unknown calibration field {field!r}')
        entry[field] = clean

    elif root == 'night_checklist' and len(path) == 3 and path[2] == 'done':
        entry = log['night_checklist'].get(path[1])
        if entry is None:
            raise LogEditError(f'no checklist item {path[1]!r}')
        clean = entry['done'] = _bool(value)

    elif root == 'conditions' and len(path) == 1:
        clean = log['conditions'] = _clean_conditions(plan, value)

    elif root == 'unplanned' and len(path) == 1:
        clean = log['unplanned'] = _clean_unplanned(plan, value)

    elif root == 'targets' and len(path) in (3, 4):
        row = log['targets'].get(path[1])
        if row is None:
            raise LogEditError(f'no target {path[1]!r} in the log')
        if len(path) == 4:
            if path[2] != 'checks' or path[3] not in CHECKS:
                raise LogEditError(f'unknown target field {".".join(path[2:])!r}')
            clean = row['checks'][path[3]] = _bool(value)
        else:
            clean = row[path[2]] = _clean_target_field(plan, path[2], value)

    else:
        raise LogEditError(f'cannot set {"/".join(path)!r}')

    log.setdefault('edits', {})[_path_key(path)] = {
        'updated_ut': now or _now_ut(), 'source': source}
    return clean


# --------------------------------------------------------------------
# Derived values (computed, never typed)
# --------------------------------------------------------------------

_EXPOSURE = re.compile(r'(\d+)\s*[xX×]\s*(\d+(?:\.\d+)?)')


def exposure_total_s(text):
    """
    Total integration in a recipe string.

    Parameters
    ----------
    text : str
        e.g. '3 x 600', or '3x600, 1x300' (each 'n x s' term is summed).

    Returns
    -------
    float or None (None if the string holds no 'n x s' term).
    """
    terms = _EXPOSURE.findall(str(text or ''))
    if not terms:
        return None
    return sum(int(n) * float(s) for n, s in terms)


def conditions_at(log, ut):
    """
    The conditions-log entry in force at a UT time.

    Parameters
    ----------
    log : dict
    ut : str
        'YYYY-MM-DDTHH:MMZ' (or '' for none).

    Returns
    -------
    dict or None : the latest entry at or before `ut`.
    """
    if not ut:
        return None
    best = None
    for entry in log.get('conditions', []):
        if entry.get('ut') and entry['ut'] <= ut:
            best = entry
    return best


def calibration_status(log):
    """
    Calibrations taken vs needed, counting only items still in the plan.

    Returns
    -------
    (taken, total) : tuple of int
    """
    live = [c for c in log.get('calibrations', {}).values()
            if not c.get('not_in_plan')]
    return sum(bool(c.get('done')) for c in live), len(live)


def airmass_at(location, ra_deg, dec_deg, ut):
    """
    Airmass of a target at a UT time.

    Parameters
    ----------
    location : astropy EarthLocation
    ra_deg, dec_deg : float or None
    ut : str
        'YYYY-MM-DDTHH:MMZ'.

    Returns
    -------
    float or None (None without coordinates or time, or below the horizon).
    """
    if not ut or ra_deg is None or dec_deg is None:
        return None
    from .sky import track
    when = datetime.fromisoformat(ut.replace('Z', '+00:00'))
    return track(ra_deg, dec_deg, [when], location)['airmass'][0]


def _start_ut(row):
    if row.get('actual_start_ut'):
        return row['actual_start_ut']
    start = (row.get('planned') or {}).get('science_start')
    if not start:
        return ''
    return datetime.fromisoformat(start).astimezone(timezone.utc).strftime(
        '%Y-%m-%dT%H:%MZ')


def derived(log, plan, location=None):
    """
    Values the page and report show but nobody types.

    Parameters
    ----------
    log : dict
    plan : PlanResult
    location : astropy EarthLocation, optional
        Needed for airmass at the actual start. Without it, airmass is None.

    Returns
    -------
    dict with:
        - targets : {name: {airmass_start, conditions, integrated_s,
          planned_s}}
        - calibrations : {'taken', 'total'}
        - time : {planned_on_target_min, integrated_min, lost_min,
          lost_by_cause}
    """
    out = {'targets': {}}
    planned_total = integrated_total = 0.0
    for name, row in log.get('targets', {}).items():
        planned = row.get('planned') or {}
        integ = exposure_total_s(row.get('exposures_red'))
        if integ is None and row.get('status') in ('observed', 'partial'):
            integ = exposure_total_s(planned.get('exposure_red'))
        planned_s = exposure_total_s(planned.get('exposure_red'))
        if planned_s is None and row.get('kind') == 'science':
            planned_s = (planned.get('on_target_min') or 0) * 60
        start = row.get('actual_start_ut') or ''
        cond = conditions_at(log, _start_ut(row))
        out['targets'][name] = {
            'airmass_start': (airmass_at(location, planned.get('ra_deg'),
                                         planned.get('dec_deg'), start)
                              if location is not None else None),
            'conditions': cond,
            'integrated_s': integ,
            'planned_s': planned_s,
        }
        if row.get('kind') == 'science' and not row.get('not_in_plan'):
            planned_total += planned_s or 0
            if row.get('status') in ('observed', 'partial'):
                integrated_total += integ or 0
    for row in log.get('unplanned', []):
        integrated_total += exposure_total_s(row.get('exposures_red')) or 0

    lost = {cause: 0.0 for cause in LOST_CAUSES}
    for entry in log.get('night', {}).get('time_lost', []):
        lost[entry['cause']] += entry['minutes']

    taken, total = calibration_status(log)
    out['calibrations'] = {'taken': taken, 'total': total}
    out['time'] = {'planned_on_target_min': planned_total / 60,
                   'integrated_min': integrated_total / 60,
                   'lost_min': sum(lost.values()),
                   'lost_by_cause': lost}
    return out
