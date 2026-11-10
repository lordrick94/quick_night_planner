"""
Observing report for one night, built from the plan plus its observing log.

Created by JXP and Claude

Two outputs from the same data:
- render_markdown(plan, log): the human-readable night report
  (observing_report_<date>.md).
- build_ffffpz_rows(plan, log, survey, resource): rows for the FFFF-PZ
  observing-log CSV. scripts/make_observing_report.py also goes through
  this function, so the CLI and the Observing log page share one path.

Neither function adds a timestamp of its own, so the same plan and log
always give the same output.
"""

import csv
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .observing_log import (LOST_CAUSES, calibration_status, derived,
                            exposure_total_s)

FFFFPZ_COLUMNS = ['TNS', 'FRB_Survey', 'Resource', 'mode', 'date', 'texp',
                  'Conditions', 'success']

# The plan's internal mode strings -> the FFFF-PZ log's vocabulary.
MODE_MAP = {
    'longslit': 'longslit',
    'longslit (forced, no mask)': 'longslit',
    'MOS (mask required)': 'mask',
}

_SKY_LABEL = {'': '', 'clear': 'clear', 'thin_cirrus': 'thin cirrus',
              'patchy': 'patchy clouds', 'thick': 'thick clouds',
              'closed': 'closed'}
_REASON_LABEL = {'': '', 'weather': 'weather', 'ran_out_of_time': 'ran out of time',
                 'technical': 'technical', 'not_acquired': 'target not acquired',
                 'bumped': 'lower priority / bumped', 'other': 'other'}
_STATUS_LABEL = {'pending': 'pending', 'observed': 'observed',
                 'partial': 'partial', 'not_observed': 'not observed',
                 'skipped': 'skipped'}


# --------------------------------------------------------------------
# FFFF-PZ CSV
# --------------------------------------------------------------------

def planned_exposure_seconds(target_or_planned):
    """
    Planned on-target integration in seconds.

    Prefers the real exposure string ("3 x 1060" -> 3180 s), because the
    scheduled block can include overhead the detector never saw. A MOS
    allocation, for example, carries a mask-alignment buffer, so using the
    block length would overstate the integration.

    Parameters
    ----------
    target_or_planned : ScheduledTarget or dict
        Needs `exposure_red` and `on_target_min`.

    Returns
    -------
    (seconds, note) : (int, str). The note is non-empty when the seconds
    come from the allocated block rather than an exposure recipe.
    """
    get = (target_or_planned.get if isinstance(target_or_planned, dict)
           else lambda k: getattr(target_or_planned, k))
    match = re.match(r'\s*(\d+)\s*[xX]\s*(\d+)', str(get('exposure_red') or ''))
    if match:
        return int(match.group(1)) * int(match.group(2)), ''
    # No parseable exposure (MOS blocks are an allocation, not a recipe).
    return int(round((get('on_target_min') or 0) * 60)), 'from allocated block'


def log_from_flags(plan, conditions, drop=(), failed=(), extra=()):
    """
    The minimal observing log that make_observing_report.py's flags
    describe.

    Parameters
    ----------
    plan : PlanResult
    conditions : str
        FFFF-PZ conditions for the night, e.g. 'Fair'.
    drop : iterable of str
        Planned targets that weren't observed.
    failed : iterable of str
        Targets to mark success = no.
    extra : iterable of str
        Unplanned targets, as 'NAME' or 'NAME:texp_seconds'.

    Returns
    -------
    dict : a log with just the keys build_ffffpz_rows reads.
    """
    drop, failed = set(drop), set(failed)
    targets = {}
    for order, t in enumerate(plan.schedule):
        targets[t.name] = {
            'kind': 'science', 'order': order, 'not_in_plan': False,
            'planned': {'mode': t.mode, 'exposure_red': t.exposure_red,
                        'on_target_min': t.on_target_min},
            'status': 'not_observed' if t.name in drop else 'observed',
            'exposures_red': '',
            'success': 'no' if t.name in failed else '',
        }
    unplanned = []
    for spec in extra:
        name, _, texp = spec.partition(':')
        unplanned.append({'name': name, 'mode': 'longslit',
                          'status': 'observed',
                          'exposures_red': f'1 x {int(texp)}' if texp else '',
                          'success': 'no' if name in failed else ''})
    return {'night': {'ffffpz_conditions': conditions},
            'targets': targets, 'unplanned': unplanned}


def build_ffffpz_rows(plan, log, survey='CHIME/FRB', resource=None):
    """
    One FFFF-PZ observing-log row per observed target, in observing order.

    Parameters
    ----------
    plan : PlanResult
    log : dict
        An observing log (or log_from_flags output). Science rows with
        status 'observed' or 'partial' are reported, then unplanned targets.
        Standards are never reported.
    survey : str
        FRB_Survey column.
    resource : str, optional
        FFFF-PZ Resource name. Defaults to the plan directory's name.

    Returns
    -------
    (rows, notes) : list of dict (keys FFFFPZ_COLUMNS), list of str.
        - texp is the logged integration when one was typed. Otherwise it
          is the plan's recipe, with a note when that is only the allocated
          block.
        - success is False only for success = 'no'. 'yes', 'unknown' and
          blank all give True, matching the script's old default.
    """
    resource = resource or Path(plan.output_dir).name
    conditions = (log.get('night') or {}).get('ffffpz_conditions') or ''
    rows, notes = [], []

    science = sorted(((name, r) for name, r in log.get('targets', {}).items()
                      if r.get('kind') == 'science'),
                     key=lambda kv: kv[1].get('order', 0))
    for name, row in science:
        if row.get('status') not in ('observed', 'partial'):
            continue
        planned = row.get('planned') or {}
        logged = exposure_total_s(row.get('exposures_red'))
        if logged is not None:
            texp = int(round(logged))
        else:
            texp, note = planned_exposure_seconds(planned)
            if note:
                notes.append(f'{name}: texp {texp} s {note} '
                             f'({planned.get("mode")})')
        rows.append({
            'TNS': name, 'FRB_Survey': survey, 'Resource': resource,
            'mode': MODE_MAP.get(planned.get('mode'), planned.get('mode')),
            'date': plan.date, 'texp': texp, 'Conditions': conditions,
            'success': row.get('success') != 'no',
        })

    for row in log.get('unplanned', []):
        logged = exposure_total_s(row.get('exposures_red'))
        rows.append({
            'TNS': row['name'], 'FRB_Survey': survey, 'Resource': resource,
            'mode': MODE_MAP.get(row.get('mode'), row.get('mode') or 'longslit'),
            'date': plan.date,
            'texp': int(round(logged)) if logged is not None else '',
            'Conditions': conditions,
            'success': row.get('success') != 'no',
        })
        if logged is None:
            notes.append(f'{row["name"]}: observed but not in the plan -- texp '
                         f'left blank, fill it in from the night log')
    return rows, notes


def write_ffffpz_csv(rows, path):
    """
    Write FFFF-PZ rows to CSV.

    Parameters
    ----------
    rows : list of dict
    path : str

    Returns
    -------
    str : the path written.
    """
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FFFFPZ_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


# --------------------------------------------------------------------
# Markdown report
# --------------------------------------------------------------------

def _hhmm_ut(ut):
    """'YYYY-MM-DDTHH:MMZ' -> 'HH:MM'; '' stays ''."""
    return ut[11:16] if ut and len(ut) >= 16 else (ut or '')


def _planned_hhmm(iso):
    if not iso:
        return ''
    return datetime.fromisoformat(iso).astimezone(timezone.utc).strftime('%H:%M')


def _cell(value):
    """Markdown-table-safe cell text."""
    text = '' if value is None else str(value)
    return text.replace('|', '\\|').replace('\n', ' ').strip() or '—'


def _table(headers, rows):
    lines = ['| ' + ' | '.join(headers) + ' |',
             '|' + '|'.join('---' for _ in headers) + '|']
    for row in rows:
        lines.append('| ' + ' | '.join(_cell(v) for v in row) + ' |')
    return lines


def _sky_seeing(row, cond):
    sky = row.get('sky') or (cond or {}).get('sky') or ''
    seeing = row.get('seeing') or (cond or {}).get('seeing') or ''
    parts = [p for p in (_SKY_LABEL.get(sky, sky),
                         f'{seeing}″' if seeing else '') if p]
    return ', '.join(parts)


def report_warnings(plan, log):
    """
    Gaps worth a look before the report goes out. The report is still
    generated; these are listed at its top.

    Parameters
    ----------
    plan : PlanResult
    log : dict

    Returns
    -------
    list of str
    """
    warnings = []
    for name, row in sorted(log.get('targets', {}).items(),
                            key=lambda kv: kv[1].get('order', 0)):
        if row.get('not_in_plan'):
            continue
        status = row.get('status')
        if status == 'pending':
            warnings.append(f'{name}: still pending (no status set)')
        elif status in ('observed', 'partial') and row.get('kind') == 'science':
            if not row.get('exposures_red'):
                warnings.append(f'{name}: {status} but no exposures recorded '
                                f'(the planned recipe is used)')
            if not row.get('frames'):
                warnings.append(f'{name}: {status} but no frame numbers')
    for item in sorted(log.get('calibrations', {}).values(),
                       key=lambda c: c.get('order', 0)):
        if not item.get('done') and not item.get('not_in_plan'):
            warnings.append(f'calibration not taken: {item["label"]} '
                            f'({item["scope"]} {item["scope_name"]})')
    return warnings


def render_markdown(plan, log, location=None):
    """
    The night's observing report as Markdown.

    Parameters
    ----------
    plan : PlanResult
    log : dict
        The night's observing log (observing_log.open_log).
    location : astropy EarthLocation, optional
        For airmass at the actual start of each target.

    Returns
    -------
    str : the report. Deterministic: the only times in it are the plan's
    and the ones stored in the log.
    """
    night = log.get('night') or {}
    der = derived(log, plan, location)
    targets = sorted(log.get('targets', {}).items(),
                     key=lambda kv: kv[1].get('order', 0))
    science = [(n, r) for n, r in targets if r.get('kind') == 'science']
    standards = [(n, r) for n, r in targets if r.get('kind') == 'standard']
    counts = {s: sum(r.get('status') == s for _, r in science
                     if not r.get('not_in_plan'))
              for s in ('observed', 'partial', 'not_observed', 'skipped',
                        'pending')}
    configs = '; '.join(c.get('label', '') for c in log.get('configs', []))

    out = [f'# Observing report — {plan.telescope} / {plan.instrument.upper()} '
           f'— {plan.date}', '']

    warnings = report_warnings(plan, log)
    if warnings:
        out += ['> **Warnings**', '>']
        out += [f'> - {w}' for w in warnings]
        out.append('')

    # 1. Header
    out += ['## Night', '',
            f'- **Telescope / instrument:** {plan.telescope} / {plan.instrument}',
            f'- **Date (local night of):** {plan.date}',
            f'- **Observers:** {night.get("observers") or "—"}',
            f'- **Support / operator:** {night.get("support") or "—"}',
            f'- **Configuration:** {configs or "—"}',
            f'- **Dome open / close (UT):** {_hhmm_ut(night.get("dome_open_ut")) or "—"}'
            f' – {_hhmm_ut(night.get("dome_close_ut")) or "—"}',
            f'- **Plan directory:** `{plan.output_dir}`', '']

    # 2. Summary
    t = der['time']
    lost = ', '.join(f'{c} {t["lost_by_cause"][c]:.0f} min'
                     for c in LOST_CAUSES if t['lost_by_cause'][c])
    out += ['## Summary', '',
            f'- **Targets:** {counts["observed"]} observed, '
            f'{counts["partial"]} partial, {counts["not_observed"]} not observed, '
            f'{counts["skipped"]} skipped, {counts["pending"]} pending; '
            f'{len(log.get("unplanned", []))} unplanned',
            f'- **Integration:** {t["integrated_min"]:.0f} min of '
            f'{t["planned_on_target_min"]:.0f} min planned on target',
            f'- **Time lost:** {lost or "none recorded"}',
            f'- **Conditions:** {_SKY_LABEL.get(night.get("sky_summary"), night.get("sky_summary")) or "—"}'
            f'; seeing {night.get("seeing_range") or "—"}'
            + (f'; {night["weather_notes"]}' if night.get('weather_notes') else ''),
            '']
    time_lost = night.get('time_lost') or []
    if time_lost:
        out += _table(['Cause', 'Minutes', 'Reason'],
                      [[e['cause'], f'{e["minutes"]:.0f}', e.get('reason')]
                       for e in time_lost])
        out.append('')

    # 3. Conditions log
    out += ['## Conditions log', '']
    if log.get('conditions'):
        out += _table(['UT', 'Sky', 'Seeing (″)', 'Note'],
                      [[_hhmm_ut(c['ut']), _SKY_LABEL.get(c['sky'], c['sky']),
                        c['seeing'], c['note']] for c in log['conditions']])
    else:
        out.append('No entries.')
    out.append('')

    # 4. Observed targets
    observed = [(n, r) for n, r in science
                if r.get('status') in ('observed', 'partial')]
    out += ['## Observed targets', '']
    if observed:
        rows = []
        for name, r in observed:
            d = der['targets'][name]
            am = d['airmass_start']
            succ = r.get('success') or ''
            if r.get('z'):
                succ = f'{succ} (z = {r["z"]})' if succ else f'z = {r["z"]}'
            rows.append([
                name + (' (partial)' if r['status'] == 'partial' else ''),
                MODE_MAP.get(r['planned'].get('mode'), r['planned'].get('mode')),
                _hhmm_ut(r.get('actual_start_ut')) or
                f'{_planned_hhmm(r["planned"].get("science_start"))} (planned)',
                r.get('exposures_red') or f'{r["planned"].get("exposure_red")} (planned)',
                f'{d["integrated_s"]:.0f}' if d['integrated_s'] is not None else '',
                f'{am:.2f}' if am is not None else '',
                r.get('pa'), _sky_seeing(r, d['conditions']),
                r.get('quality'), r.get('frames'), succ, r.get('comments')])
        out += _table(['Target', 'Mode', 'UT start', 'Exposures (red)',
                       'Total (s)', 'Airmass', 'PA', 'Sky / seeing', 'Quality',
                       'Frames', 'Success / z', 'Comments'], rows)
    else:
        out.append('None.')
    out.append('')

    # 5. Not observed / partial
    missed = [(n, r) for n, r in science
              if r.get('status') in ('partial', 'not_observed', 'skipped', 'pending')]
    out += ['## Not observed or partial', '']
    if missed:
        out += _table(['Target', 'Status', 'Reason', 'Comment'],
                      [[n + (' (no longer in plan)' if r.get('not_in_plan') else ''),
                        _STATUS_LABEL.get(r['status'], r['status']),
                        ' — '.join(p for p in (_REASON_LABEL.get(r.get('reason'), r.get('reason')),
                                               r.get('reason_text')) if p),
                        r.get('comments')] for n, r in missed])
    else:
        out.append('None.')
    out.append('')

    # 6. Unplanned
    out += ['## Unplanned targets', '']
    if log.get('unplanned'):
        out += _table(['Target', 'Mode', 'UT start', 'Exposures (red)', 'Frames',
                       'Success / z', 'Comments'],
                      [[u['name'], u.get('mode'), _hhmm_ut(u.get('actual_start_ut')),
                        u.get('exposures_red'), u.get('frames'),
                        ' '.join(p for p in (u.get('success'),
                                             f'z = {u["z"]}' if u.get('z') else '') if p),
                        u.get('comments')] for u in log['unplanned']])
    else:
        out.append('None.')
    out.append('')

    # 7. Standards and calibrations
    out += ['## Standards and calibrations', '']
    if standards:
        out += _table(['Standard', 'Status', 'UT start', 'Frames', 'Comments'],
                      [[n, _STATUS_LABEL.get(r['status'], r['status']),
                        _hhmm_ut(r.get('actual_start_ut')), r.get('frames'),
                        r.get('comments')] for n, r in standards])
        out.append('')
    cals = sorted(log.get('calibrations', {}).values(),
                  key=lambda c: c.get('order', 0))
    taken, total = calibration_status(log)
    out.append(f'Calibrations taken: **{taken} / {total}**')
    out.append('')
    if cals:
        out += _table(['Calibration', 'For', 'Taken', 'UT', 'Frames', 'Note'],
                      [[c['label'],
                        f'{c["scope"]} {c["scope_name"]}'
                        + (' (no longer in plan)' if c.get('not_in_plan') else ''),
                        'yes' if c.get('done') else 'NO',
                        _hhmm_ut(c.get('ut')), c.get('frames'), c.get('note')]
                       for c in cals])
        out.append('')

    # 8. Night checklist and notes
    out += ['## Night checklist', '']
    for item in sorted(log.get('night_checklist', {}).values(),
                       key=lambda c: c.get('order', 0)):
        out.append(f'- [{"x" if item.get("done") else " "}] {item["label"]}')
    out += ['', '## Notes', '', night.get('notes') or 'None.', '']

    # 9. Footer
    out += ['---', '',
            f'Generated by night-planner from `plan_result.json` and '
            f'`observing_log.json` in `{plan.output_dir}`.', '']
    return '\n'.join(out)


def report_paths(plan, resource=None):
    """
    Where the report files go.

    Returns
    -------
    (markdown_path, csv_path) : tuple of str
    """
    resource = resource or Path(plan.output_dir).name
    return (os.path.join(plan.output_dir, f'observing_report_{plan.date}.md'),
            os.path.join(plan.output_dir, f'{resource}_report.csv'))


def write_report(plan, log, location=None, survey='CHIME/FRB', resource=None):
    """
    Write the Markdown report and the FFFF-PZ CSV into the plan directory.

    Parameters
    ----------
    plan : PlanResult
    log : dict
    location : astropy EarthLocation, optional
    survey, resource : str
        Passed to build_ffffpz_rows.

    Returns
    -------
    dict with 'markdown_path', 'csv_path', 'warnings' (report gaps) and
    'notes' (FFFF-PZ CSV notes).
    """
    md_path, csv_path = report_paths(plan, resource)
    with open(md_path, 'w') as f:
        f.write(render_markdown(plan, log, location))
    rows, notes = build_ffffpz_rows(plan, log, survey, resource)
    write_ffffpz_csv(rows, csv_path)
    return {'markdown_path': md_path, 'csv_path': csv_path,
            'warnings': report_warnings(plan, log), 'notes': notes}
