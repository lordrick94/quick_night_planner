"""
Print a target's visibility track (airmass, alt, az, HA) over a time range,
with the Keck pointing/vignetting limits evaluated at each step.

Answers "is this thing actually up, and for how long" for a specific
target without re-running the whole scheduler. Useful when deciding
whether to fill a gap with a truncated exposure the scheduler refused to
place at full allocation.

    python scripts/target_visibility.py TGT0461 --from 03:00 --to 05:02

The target is looked up in the plan directory's target_analysis.csv;
RA/Dec can be given directly instead with --ra/--dec (degrees).

Created by JXP and Claude
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
from night_planner.paths import plans_dir

_PLANS = plans_dir()
from keck_2026oct06_calculations import (
    HST, calculate_airmass, check_keck_limits,
)
from night_plan_io import load_night_meta, resolve_local_dt

DEFAULT_PLAN_DIR = f'{_PLANS}/Keck-2026B-02'


def lookup_target(plan_dir, name):
    """
    Find a target's RA/Dec/mag in a plan's target_analysis.csv.

    Returns
    -------
    dict with 'ra_deg', 'dec_deg', 'mag', 'window'
    """
    df = pd.read_csv(f'{plan_dir}/target_analysis.csv').set_index('TNS')
    if name not in df.index:
        raise SystemExit(f'{name} not in {plan_dir}/target_analysis.csv')
    row = df.loc[name]
    return {'ra_deg': float(row['RA_deg']), 'dec_deg': float(row['Dec_deg']),
            'mag': float(row['mag_r'])}


def track(ra_deg, dec_deg, start_local, end_local, step_min=5):
    """
    Sample the visibility track between two local times.

    Returns
    -------
    list of dict: time, airmass, alt, az, ha, ok, reason
    """
    rows = []
    t = start_local
    while t <= end_local:
        airmass, alt, az, ha = calculate_airmass(
            ra_deg, dec_deg, t.astimezone(tz=None).astimezone(
                __import__('datetime').timezone.utc))
        ok, reason = check_keck_limits(ra_deg, dec_deg, ha, alt, az)
        rows.append({'time': t, 'airmass': airmass, 'alt': alt, 'az': az,
                     'ha': ha, 'ok': ok, 'reason': reason})
        t += timedelta(minutes=step_min)
    return rows


def main():
    """Print the track and summarize the usable window."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('target')
    p.add_argument('--plan-dir', default=DEFAULT_PLAN_DIR)
    p.add_argument('--from', dest='start', required=True, help='HH:MM local')
    p.add_argument('--to', dest='end', required=True, help='HH:MM local')
    p.add_argument('--step', type=int, default=5)
    p.add_argument('--am-limit', type=float, default=2.0)
    p.add_argument('--ra', type=float)
    p.add_argument('--dec', type=float)
    args = p.parse_args()

    meta = load_night_meta(args.plan_dir)
    date = meta['date']

    if args.ra is not None and args.dec is not None:
        info = {'ra_deg': args.ra, 'dec_deg': args.dec, 'mag': float('nan')}
    else:
        info = lookup_target(args.plan_dir, args.target)

    start = resolve_local_dt(date, args.start, HST)
    end = resolve_local_dt(date, args.end, HST)

    rows = track(info['ra_deg'], info['dec_deg'], start, end, args.step)

    print(f"{args.target}  RA {info['ra_deg']:.3f} deg  Dec {info['dec_deg']:+.3f} deg "
          f" mag {info['mag']:.2f}")
    print(f"{date}  {start:%H:%M} -> {end:%H:%M} {start.tzname()}\n")
    print(f"{'time':>6}{'AM':>7}{'alt':>7}{'az':>7}{'HA':>7}   limits")
    for r in rows:
        flag = '' if r['ok'] else f"  <-- {r['reason']}"
        print(f"{r['time']:%H:%M}{r['airmass']:>7.2f}{r['alt']:>7.1f}"
              f"{r['az']:>7.1f}{r['ha']:>+7.2f}{flag}")

    usable = [r for r in rows if r['ok'] and r['airmass'] < args.am_limit]
    print()
    if usable:
        print(f"  usable (AM < {args.am_limit}, limits clear): "
              f"{usable[0]['time']:%H:%M} -> {usable[-1]['time']:%H:%M} "
              f"({(usable[-1]['time'] - usable[0]['time']).total_seconds() / 60:.0f} min), "
              f"airmass {min(r['airmass'] for r in usable):.2f}"
              f"-{max(r['airmass'] for r in usable):.2f}")
    else:
        print(f'  never usable at AM < {args.am_limit} in this range')


if __name__ == '__main__':
    main()
