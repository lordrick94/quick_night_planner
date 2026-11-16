"""Finder chart and starlist rows for a target that is not in the schedule.

Created by JXP and Claude, 2026-11-11.

For a target added during the night that is not to be scheduled (a fresh
transient, a backup): draws its finder with the same code as the plan's
own charts (image + offset star + slit, PA and, at the Shane, the Cass
tub) and appends its target / _S / _C rows to the plan's starlist under a
"not scheduled" heading. Re-running for the same name replaces its rows.

The slit is at the mean parallactic angle over a window: by default the
--minutes centred on the target's highest point between now (or evening
twilight, if later) and morning twilight. The printed PA track lets the
observer reset the slit if they take it at another time.

Usage
-----
    python scripts/add_unscheduled_target.py [--minutes 30] [--start HH:MM]
        [--starlist NAME] [--overwrite] -- PLAN_DIR NAME RA DEC

    The '--' lets a negative Dec ('-11:58:59.8') through as a position.

Inputs
------
PLAN_DIR : a plan directory with plan_result.json and night_meta.json
NAME : target name (spaces become '_' in the starlist)
RA, DEC : sexagesimal (hours, degrees) or decimal degrees, ICRS
--minutes : exposure length used for the PA window and exptime (default 30)
--start : local start time of the window instead of the transit-centred one
--starlist : default <plan>_generated.starlist
--overwrite : redraw an existing chart

Outputs
-------
PLAN_DIR/finders/NAME_finder.png and .json; the starlist with NAME's rows
appended. Prints the chart summary, the PA track and the rows.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import astropy.units as u
import numpy as np
from astropy.coordinates import AltAz, SkyCoord
from astropy.time import Time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_finders import describe  # noqa: E402
from night_planner.adapters import SITES  # noqa: E402
from night_planner.finder import generate_for_plan  # noqa: E402
from night_planner.parallactic import parallactic_angle  # noqa: E402
from night_planner.plan_store import load_plan  # noqa: E402
from night_planner.starlist import _lick_block, _keck_block  # noqa: E402
from night_plan_io import resolve_local_dt  # noqa: E402

HEADING = '# --- not scheduled (added on request) ---'


def parse_coord(ra, dec):
    """
    Target position from sexagesimal or decimal strings.

    Inputs: ra, dec (str; 'HH:MM:SS.s' / 'DD:MM:SS.s' or degrees).
    Outputs: SkyCoord (ICRS).
    """
    ra, dec = ra.strip().rstrip(','), dec.strip().rstrip(',')
    if ':' in ra or ' ' in ra:
        return SkyCoord(ra, dec, unit=(u.hourangle, u.deg))
    return SkyCoord(float(ra), float(dec), unit='deg')


def best_window(coord, location, tz, twi_start, twi_end, minutes, now=None):
    """
    The exposure window centred on the target's highest point tonight.

    Inputs
    ------
    coord : SkyCoord
    location : EarthLocation
    tz : tzinfo of the site
    twi_start, twi_end : datetime, evening and morning twilight
    minutes : float, window length
    now : datetime, optional; the window does not start before it

    Outputs
    -------
    (start, end, peak_alt_deg) : datetimes (site tz) and float
    """
    lo = max(twi_start, now) if now else twi_start
    if lo >= twi_end:
        raise SystemExit('the night is over: no window left before twilight')
    grid = [lo + timedelta(minutes=m)
            for m in range(0, int((twi_end - lo).total_seconds() // 60) + 1, 5)]
    alt = coord.transform_to(AltAz(obstime=Time(grid),
                                   location=location)).alt.deg
    peak = grid[int(np.argmax(alt))]
    half = timedelta(minutes=minutes / 2)
    start = min(max(peak - half, lo), twi_end - 2 * half)
    start = max(start, lo)
    return start.astimezone(tz), (start + 2 * half).astimezone(tz), float(alt.max())


def strip_rows(text, name):
    """
    Remove NAME's rows (and an emptied heading) from a starlist.

    Inputs: text (str), name (str, starlist form).
    Outputs: str.
    """
    keep = [ln for ln in text.splitlines()
            if ln.split()[:1] not in ([name], [f'{name}_S'], [f'{name}_C'])]
    out = '\n'.join(keep).rstrip('\n') + '\n'
    if out.rstrip().endswith(HEADING):
        out = out.rstrip()[:-len(HEADING)].rstrip('\n') + '\n'
    return out


def main(argv=None):
    """
    Draw the chart and append the rows.

    Inputs: argv (list of str, optional; default sys.argv).
    Outputs: exit code (0 on success).
    """
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('plan_dir')
    p.add_argument('name')
    p.add_argument('ra')
    p.add_argument('dec')
    p.add_argument('--minutes', type=float, default=30.0)
    p.add_argument('--start')
    p.add_argument('--starlist')
    p.add_argument('--overwrite', action='store_true')
    args = p.parse_args(argv)

    base = Path(args.plan_dir)
    plan = load_plan(base)
    if plan is None:
        raise SystemExit(f'no plan_result.json in {base}')
    site = SITES[plan.instrument]
    tz, loc = site['tz'], site['location']
    meta = json.loads((base / 'night_meta.json').read_text())
    twi0 = datetime.fromisoformat(meta['evening_twilight_local'])
    twi1 = datetime.fromisoformat(meta['morning_twilight_local'])
    coord = parse_coord(args.ra, args.dec)

    if args.start:
        start = resolve_local_dt(meta['date'], args.start, tz)
        end = start + timedelta(minutes=args.minutes)
        peak = None
    else:
        start, end, peak = best_window(coord, loc, tz, twi0, twi1, args.minutes,
                                       now=datetime.now(tz))

    target = SimpleNamespace(name=args.name, ra_deg=float(coord.ra.deg),
                             dec_deg=float(coord.dec.deg), science_start=start,
                             end=end, mode='longslit',
                             on_target_min=args.minutes)
    one = SimpleNamespace(schedule=[target])
    results = generate_for_plan(
        one, loc, base / 'finders', overwrite=args.overwrite,
        slit_length_arcmin=site.get('slit_length_arcmin', 2.9),
        slit_width_arcsec=site.get('slit_width_arcsec', 1.0),
        rotator=site.get('rotator'))
    entry = results[0]
    print(describe(entry))
    print(f'window {start:%H:%M}-{end:%H:%M} local '
          f'{start:%Z}, {start.astimezone(timezone.utc):%H:%M}-'
          f'{end.astimezone(timezone.utc):%H:%M} UT; '
          + (f'peak altitude {peak:.1f} deg' if peak is not None else 'as given'))

    print('parallactic angle through the night (local, PA, alt):')
    t = max(twi0, datetime.now(tz)).replace(second=0, microsecond=0)
    t += timedelta(minutes=(30 - t.minute % 30) % 30)
    while t <= twi1:
        alt = coord.transform_to(AltAz(obstime=Time(t), location=loc)).alt.deg
        if alt > 15:
            pa = parallactic_angle(coord.ra.deg, coord.dec.deg, t, loc) % 180
            print(f'  {t:%H:%M}  {pa:6.1f}  {alt:5.1f}')
        t += timedelta(minutes=30)

    finder = json.loads((base / 'finders' / f'{args.name}_finder.json').read_text())
    has_star = finder.get('offset_star_ra') is not None
    if site.get('starlist_style', 'keck') == 'lick':
        rows = _lick_block(target, coord, finder, has_star)
    else:
        rows = _keck_block(target, coord, finder,
                           f'{start:%H:%M}-{end:%H:%M} (not scheduled)', has_star)

    path = base / (args.starlist or f'{base.name}_generated.starlist')
    text = strip_rows(path.read_text(), rows[0].split()[0]) if path.exists() else ''
    if HEADING not in text:
        text = text.rstrip('\n') + f'\n\n{HEADING}\n'
    path.write_text(text + '\n'.join(rows) + '\n')
    print(f'\nappended to {path}:')
    print('\n'.join(rows))
    return 0 if not entry.get('error') else 1


if __name__ == '__main__':
    raise SystemExit(main())
