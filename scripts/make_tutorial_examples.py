"""
Build the tutorial's example target lists and the worked example plan.

Created by JXP and Claude

The tutorial (the "night-planner tutorial" artifact, 2026-11-07) shows four
example tables and one real plan. This script makes both, so every number
in the tutorial comes from the planner rather than from memory.

Inputs
------
test_targs/autumn_ffffpz.csv : the synthetic October table (seed 20261014).
    None of its objects are real; every name starts with SIM.

Outputs
-------
examples/tutorial/minimal.csv       name, ra_deg, dec_deg, mag only
examples/tutorial/with_priority.csv adds mag_band, priority, t_target,
                                    required and a free-text Notes column
examples/tutorial/spreadsheet.csv   spreadsheet-style headers, sexagesimal
                                    coordinates, a Comments column
examples/tutorial/keck_faint.csv    faint hosts for LRIS (mag > 21 goes MOS)
examples/tutorial/ffffpz_with_priority.csv
    the FFFF-PZ pull as-is (every column kept) plus a priority column
examples/tutorial/kast_example_plan.json
    The Kast plan for 2026-10-20 made from with_priority.csv: summary,
    timeline segments, rejections and assumptions.
examples/tutorial/kast_ffffpz_example_plan.json
    The same night planned from ffffpz_with_priority.csv (FFFF-PZ mode).

    python scripts/make_tutorial_examples.py --plan-dir /tmp/tutorial_plan
"""

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import pandas as pd
from astropy import units as u
from astropy.coordinates import SkyCoord

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from night_planner.cli import generate_plan  # noqa: E402

SOURCE = REPO / 'test_targs' / 'autumn_ffffpz.csv'
OUT = REPO / 'examples' / 'tutorial'
DATE = '2026-10-20'

# Priority tiers, user times and required flags for the worked example.
# Chosen by hand to show each feature once: three tiers, one user time,
# one required target that fits and one required target that cannot.
PRIORITY = {'SIMFRB56192': 1, 'SIMFRB71564': 1, 'SIMFRB78184': 1,
            'SIMFRB40714': 1, 'SIMFRB64349': 2, 'SIMFRB65890': 2,
            'SIMFRB46681': 2, 'SIMFRB61257': 2, 'SIMFRB10432': 3,
            'SIMFRB95645': 3, 'SIMFRB61004': 3, 'SIMFRB54531': 3}
T_TARGET = {'SIMFRB46681': 45, 'SIMFRB61004': 300}
REQUIRED = {'SIMFRB78184', 'SIMFRB61004'}
NOTES = {'SIMFRB56192': 'bright host, repeat for z',
         'SIMFRB46681': 'user time: 45 min is enough for a redshift',
         'SIMFRB61004': 'required 300 min: cannot fit, so rejected',
         'SIMFRB10432': 'filler'}


def load_source(path=SOURCE):
    """
    The autumn table, reduced to host positions.

    Parameters
    ----------
    path : Path

    Returns
    -------
    DataFrame with name, ra_deg, dec_deg, mag, dm, tags (rounded).
    """
    d = pd.read_csv(path)
    return pd.DataFrame({'name': d['TNS'],
                         'ra_deg': d['Pri_RA'].round(5),
                         'dec_deg': d['Pri_Dec'].round(5),
                         'mag': d['Pri_mag'].round(2),
                         'dm': d['FRB_DM'].round(0)})


def make_tables(src):
    """
    The four example tables.

    Parameters
    ----------
    src : DataFrame from load_source

    Returns
    -------
    dict filename -> DataFrame
    """
    bright = src[src['mag'] < 21].reset_index(drop=True)
    minimal = bright.head(8)[['name', 'ra_deg', 'dec_deg', 'mag']]

    pri = src[src['name'].isin(PRIORITY)].copy()
    pri['mag_band'] = 'r'
    pri['priority'] = pri['name'].map(PRIORITY)
    pri['t_target'] = pri['name'].map(T_TARGET).astype('Int64')
    pri['required'] = pri['name'].isin(REQUIRED).map({True: 'yes', False: ''})
    pri['Notes'] = pri['name'].map(NOTES).fillna('')
    pri = pri.sort_values(['priority', 'name'])[
        ['name', 'ra_deg', 'dec_deg', 'mag', 'mag_band', 'priority',
         't_target', 'required', 'Notes']]

    sheet_rows = bright.head(5)
    c = SkyCoord(sheet_rows['ra_deg'].values * u.deg,
                 sheet_rows['dec_deg'].values * u.deg)
    spreadsheet = pd.DataFrame({
        'Object': sheet_rows['name'],
        'RA': c.ra.to_string(unit=u.hour, sep=':', precision=1, pad=True),
        'DEC': c.dec.to_string(unit=u.deg, sep=':', precision=0,
                               alwayssign=True, pad=True),
        'Rmag': sheet_rows['mag'],
        'priority': [1, 1, 2, 2, 3],
        'Comments': ['must get', 'bright host', '', 'second candidate nearby',
                     'filler'],
    })

    faint = src.sort_values('mag', ascending=False).head(8).copy()
    faint['priority'] = [1, 1, 1, 2, 2, 2, 3, 3]
    keck = faint[['name', 'ra_deg', 'dec_deg', 'mag', 'priority']]

    pull = pd.read_csv(SOURCE)
    pull['priority'] = pull['TNS'].map(PRIORITY).fillna(3).astype(int)

    return {'minimal.csv': minimal, 'with_priority.csv': pri,
            'spreadsheet.csv': spreadsheet, 'keck_faint.csv': keck,
            'ffffpz_with_priority.csv': pull}


def _hhmm(dt):
    return dt.strftime('%H:%M') if dt is not None else None


def plan_summary(plan):
    """
    The parts of a PlanResult the tutorial draws.

    Parameters
    ----------
    plan : PlanResult

    Returns
    -------
    dict with night, summary, segments (timeline, in minutes from night
    start), schedule rows, rejections and assumptions.
    """
    t0 = plan.night_start

    def m(dt):
        return round((dt - t0).total_seconds() / 60.0, 1)

    segs = []
    for s, e, label in plan.overheads:
        segs.append({'kind': 'overhead', 'label': label, 'start': m(s), 'end': m(e)})
    for s, e, reason in plan.blocks:
        segs.append({'kind': 'blocked', 'label': reason, 'start': m(s), 'end': m(e)})
    rows = []
    for t in plan.schedule:
        kind = ('partial' if t.notes.startswith('PARTIAL') else
                'forced' if t.notes.startswith('FORCED') else
                'mos' if t.mode.startswith('MOS') else 'science')
        slew_end = m(t.start) + t.slew_min
        if t.slew_min:
            segs.append({'kind': 'slew', 'label': t.name, 'start': m(t.start),
                         'end': round(slew_end, 1)})
        if t.acq_min:
            segs.append({'kind': 'acq', 'label': t.name, 'start': round(slew_end, 1),
                         'end': m(t.science_start)})
        segs.append({'kind': kind, 'label': t.name, 'start': m(t.science_start),
                     'end': m(t.end)})
        rows.append({'name': t.name, 'science': f'{_hhmm(t.science_start)}-{_hhmm(t.end)}',
                     'mode': t.mode, 'mag': t.mag, 'airmass': t.airmass,
                     'exposure': t.exposure_red, 'slew': t.slew_min,
                     'acq': t.acq_min, 'on_target': round(t.on_target_min, 1),
                     'readout': round(t.readout_min, 1), 'time_source': t.time_source,
                     'etc_min': t.etc_min, 'required': t.required,
                     'notes': t.notes, 'kind': kind})
    for gs, ge in plan.idle_gaps():
        segs.append({'kind': 'idle', 'label': 'idle', 'start': m(gs), 'end': m(ge)})
    segs.sort(key=lambda s: s['start'])
    prio = {d.name: d.priority for d in plan.decisions}
    for r in rows:
        r['priority'] = prio.get(r['name'])
    rej = [{'name': d.name, 'stage': d.stage, 'reason': d.reason,
            'priority': d.priority}
           for d in plan.decisions if d.status == 'rejected']
    return {'instrument': plan.instrument, 'telescope': plan.telescope,
            'date': plan.date, 'timezone': plan.timezone,
            'night_start': _hhmm(plan.night_start), 'night_end': _hhmm(plan.night_end),
            'night_min': m(plan.night_end), 'summary': plan.summary(),
            'segments': segs, 'schedule': rows, 'rejections': rej,
            'assumptions': plan.assumptions}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--plan-dir', required=True,
                   help='Where to write the worked example plan.')
    p.add_argument('--no-plan', action='store_true',
                   help='Only write the example tables.')
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, df in make_tables(load_source()).items():
        df.to_csv(OUT / name, index=False)
        print(f'Wrote {OUT / name} ({len(df)} rows)')
    if args.no_plan:
        return 0
    with contextlib.redirect_stdout(io.StringIO()):
        plan = generate_plan('kast', ['--targets-csv', str(OUT / 'with_priority.csv'),
                                      '--output-dir', args.plan_dir, '--date', DATE])
    _write_plan(plan, OUT / 'kast_example_plan.json')

    # FFFF-PZ mode: the pull itself, plus a priority column.
    with contextlib.redirect_stdout(io.StringIO()):
        plan = generate_plan('kast', ['--targets-csv', str(OUT / 'ffffpz_with_priority.csv'),
                                      '--output-dir', args.plan_dir + '_ffffpz',
                                      '--date', DATE])
    _write_plan(plan, OUT / 'kast_ffffpz_example_plan.json')
    return 0


def _write_plan(plan, path):
    """Write plan_summary(plan) as JSON and print a one-line summary."""
    out = plan_summary(plan)
    path.write_text(json.dumps(out, indent=1, default=str))
    s = out['summary']
    print(f"Wrote {path}: {s['n_scheduled']} scheduled, "
          f"{len(out['rejections'])} rejected, idle {s['idle_min']:.0f} min")


if __name__ == '__main__':
    sys.exit(main())
