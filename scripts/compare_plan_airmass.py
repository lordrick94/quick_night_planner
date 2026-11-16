"""
Created by JXP and Claude

Compare two saved Lick/Kast plans target by target: when each target is
observed, for how long, and at what airmass.

Written to check the 2026-11-15 placement change (night_planner.retime) on
a real plan: the old plan_result.json files carry no airmass for empirical
exposures, so the block airmass is recomputed here for both plans with the
same function (night_planner.sky.block_airmass) over each science span.

Inputs
------
old, new : plan directories (or plan_result.json paths)
--rule : airmass rule over a block, 'worst' (default), 'mid' or 'best'
--out : optional path for a Markdown table

Outputs
-------
Prints a per-target table and a summary (targets, full vs partial, science
minutes, time-weighted mean airmass, idle minutes); writes the same as
Markdown with --out.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from astropy import units as u  # noqa: E402
from astropy.coordinates import EarthLocation  # noqa: E402

from night_planner.sky import block_airmass  # noqa: E402

LICK = EarthLocation(lat=37.3414 * u.deg, lon=-121.6429 * u.deg, height=1283 * u.m)


def load(path):
    """
    Read a plan_result.json.

    Inputs: plan directory or file path. Outputs: dict.
    """
    p = Path(path)
    if p.is_dir():
        p = p / 'plan_result.json'
    with open(p) as f:
        return json.load(f)


def rows_of(plan, rule):
    """
    Per-target science span and block airmass.

    Inputs: plan dict, airmass rule.
    Outputs: dict name -> {'start', 'end', 'minutes', 'airmass', 'partial'}.
    """
    out = {}
    for t in plan['schedule']:
        t0 = datetime.fromisoformat(t['science_start'])
        t1 = datetime.fromisoformat(t['end'])
        out[t['name']] = dict(
            start=t0, end=t1, minutes=(t1 - t0).total_seconds() / 60.0,
            airmass=block_airmass(t['ra_deg'], t['dec_deg'], t0, t1, rule, LICK),
            partial=str(t.get('notes') or '').startswith(('PARTIAL', 'FORCED')))
    return out


def summary(plan, rows):
    """
    Plan-level numbers.

    Inputs: plan dict, rows from rows_of.
    Outputs: dict.
    """
    mins = np.array([r['minutes'] for r in rows.values()])
    am = np.array([r['airmass'] if r['airmass'] is not None else np.nan
                   for r in rows.values()])
    ok = np.isfinite(am)
    return dict(targets=len(rows), full=sum(not r['partial'] for r in rows.values()),
                partial=sum(r['partial'] for r in rows.values()),
                science_min=float(mins.sum()),
                mean_airmass=float(np.average(am[ok], weights=mins[ok])) if ok.any() else np.nan,
                idle_min=float(plan['summary'].get('idle_min', np.nan)))


def main():
    """Compare the two plans and print/write the table."""
    p = argparse.ArgumentParser(description='Compare two Kast plans by airmass')
    p.add_argument('old')
    p.add_argument('new')
    p.add_argument('--rule', default='worst', choices=('worst', 'mid', 'best'))
    p.add_argument('--out')
    args = p.parse_args()
    np.random.seed(42)  # nothing here is random; fixed by convention

    old, new = load(args.old), load(args.new)
    ro, rn = rows_of(old, args.rule), rows_of(new, args.rule)
    names = sorted(set(ro) | set(rn),
                   key=lambda n: (rn.get(n) or ro.get(n))['start'])

    def cell(r):
        if r is None:
            return 'not scheduled'
        am = f"{r['airmass']:.2f}" if r['airmass'] is not None else 'n/a'
        kind = ' partial' if r['partial'] else ''
        return f"{r['start']:%H:%M}-{r['end']:%H:%M} ({r['minutes']:.0f} min{kind}), X={am}"

    lines = [f'| Target | Old plan | New plan |', '|---|---|---|']
    for n in names:
        lines.append(f'| {n} | {cell(ro.get(n))} | {cell(rn.get(n))} |')
    so, sn = summary(old, ro), summary(new, rn)
    lines += ['', f'Airmass rule over each science span: {args.rule}.', '',
              '| | Old | New |', '|---|---|---|']
    for key, label, fmt in (('targets', 'Targets observed', '{:d}'),
                            ('full', 'Full exposures', '{:d}'),
                            ('partial', 'Partial exposures', '{:d}'),
                            ('science_min', 'Science minutes', '{:.0f}'),
                            ('mean_airmass', 'Time-weighted mean airmass', '{:.3f}'),
                            ('idle_min', 'Idle minutes', '{:.0f}')):
        lines.append(f'| {label} | {fmt.format(so[key])} | {fmt.format(sn[key])} |')
    text = '\n'.join(lines)
    print(text)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, 'w') as f:
            f.write(text + '\n')


if __name__ == '__main__':
    main()
