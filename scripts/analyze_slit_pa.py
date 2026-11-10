"""
Why each target's slit sits where it does, and what it costs.

Two questions a night plan should be able to answer about a slit angle:

1. Is a *fixed* angle good enough for this exposure? The parallactic angle
   rotates through the night, fastest near transit, so a single setting
   can only match it on average. What matters is not the raw swing but the
   swing weighted by tan(zenith angle), since that is how atmospheric
   dispersion grows -- being 30 deg off at airmass 1.02 costs nothing.

2. Does the slit happen to catch the PATH secondary candidate anyway? The
   angle is chosen for the dispersion, not fitted through the two
   candidates (the author's instruction), but a close pair often falls in
   the slit regardless, and it is worth knowing which.

Reads the plan and its finder sidecars; writes a table to stdout and to
slit_pa_analysis.csv in the plan directory.

Usage
-----
python scripts/analyze_slit_pa.py Night_plans/Lick-2026B-03

Created by JXP and Claude
"""

import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from astropy import units as u
from astropy.coordinates import SkyCoord

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from night_planner.adapters import SITES
from night_planner.parallactic import average_parallactic
from night_planner.plan_store import load_plan


def slit_offset_arcsec(target, secondary, slit_pa_deg):
    """
    How far the secondary sits off the slit axis.

    Parameters
    ----------
    target, secondary : SkyCoord
    slit_pa_deg : float
        Slit position angle, east of north.

    Returns
    -------
    (separation_arcsec, angle_to_secondary_deg, perpendicular_arcsec)
        The perpendicular distance is what decides whether the secondary
        lands in the slit: sep * sin(angle between the pair and the slit).
    """
    sep = target.separation(secondary).arcsec
    pa_to_sec = target.position_angle(secondary).deg
    # A slit has no head or tail, so fold the angle onto [0, 90].
    delta = abs((pa_to_sec - slit_pa_deg + 90) % 180 - 90)
    return sep, pa_to_sec, sep * np.sin(np.radians(delta))


def analyze(plan_dir):
    """
    Build the per-target slit-angle table for one plan.

    Parameters
    ----------
    plan_dir : str or Path
        A plan directory holding plan_result.json and finders/.

    Returns
    -------
    DataFrame
    """
    plan_dir = Path(plan_dir)
    plan = load_plan(str(plan_dir))
    if plan is None:
        raise SystemExit(f'no plan_result.json in {plan_dir}')

    site = SITES[plan.instrument]
    location = site['location']
    slit_width = site.get('slit_width_arcsec', 1.0)

    rows = []
    for target in plan.schedule:
        pa = average_parallactic(target.ra_deg, target.dec_deg,
                                  target.science_start, target.end, location)
        sidecar = plan_dir / 'finders' / f'{target.name}_finder.json'
        finder = json.loads(sidecar.read_text()) if sidecar.exists() else {}

        row = {
            'TNS': target.name,
            'start': f'{target.science_start:%H:%M}',
            'end': f'{target.end:%H:%M}',
            'slit_pa': pa['mean_pa'],
            'pa_at_start': pa['start_pa'],
            'pa_at_end': pa['end_pa'],
            'swing': pa['max_offset'],
            'weighted_offset': pa['weighted_offset'],
            'min_alt': pa['min_alt'],
            'min_airmass': 1.0 / np.sin(np.radians(pa['min_alt'])),
        }

        if finder.get('secondary_ra') is not None:
            sec = SkyCoord(ra=finder['secondary_ra'] * u.deg,
                           dec=finder['secondary_dec'] * u.deg)
            coord = SkyCoord(ra=target.ra_deg * u.deg,
                             dec=target.dec_deg * u.deg)
            sep, pa_to_sec, perp = slit_offset_arcsec(coord, sec,
                                                       pa['mean_pa'])
            row.update({
                'sec_sep': sep,
                'sec_pa': pa_to_sec,
                'sec_perp': perp,
                'sec_in_slit': perp <= slit_width / 2,
            })
        rows.append(row)

    return pd.DataFrame(rows)


def pa_vs_exposure(ra_deg, dec_deg, start, location,
                    lengths_min=(20, 40, 60, 90, 120, 180)):
    """
    How the chosen slit angle moves as an exposure gets longer.

    The angle is an average over the block actually being taken, so it is
    a function of the exposure, not of the target alone. This shows both
    halves of that: the angle itself drifts, and -- the part that decides
    whether one setting is enough -- the dispersion-weighted misalignment
    grows.

    Parameters
    ----------
    ra_deg, dec_deg : float
    start : datetime (tz-aware)
        When the exposure begins.
    location : astropy EarthLocation
    lengths_min : iterable of float

    Returns
    -------
    DataFrame
    """
    rows = []
    for minutes in lengths_min:
        pa = average_parallactic(ra_deg, dec_deg, start,
                                  start + timedelta(minutes=minutes), location)
        rows.append({
            'exposure_min': minutes,
            'slit_pa': pa['mean_pa'],
            'pa_at_start': pa['start_pa'],
            'pa_at_end': pa['end_pa'],
            'swing': pa['max_offset'],
            'weighted_offset': pa['weighted_offset'],
        })
    return pd.DataFrame(rows)


def main():
    """Print the table and save it beside the plan."""
    plan_dir = Path(sys.argv[1] if len(sys.argv) > 1
                    else 'Night_plans/Lick-2026B-03')
    df = analyze(plan_dir)

    show = df.copy()
    for column in ('slit_pa', 'pa_at_start', 'pa_at_end', 'swing',
                    'weighted_offset', 'min_airmass', 'sec_sep', 'sec_pa',
                    'sec_perp'):
        if column in show:
            show[column] = show[column].round(2)
    print(show.drop(columns=['min_alt']).to_string(index=False))

    out = plan_dir / 'slit_pa_analysis.csv'
    df.to_csv(out, index=False)
    print(f'\nWrote {out}')

    # The exposure-length dependence, for whichever target swings most --
    # the one where a single fixed angle is hardest to justify.
    plan = load_plan(str(plan_dir))
    location = SITES[plan.instrument]['location']
    worst = df.loc[df['swing'].idxmax(), 'TNS']
    target = next(t for t in plan.schedule if t.name == worst)
    print(f'\nSlit angle vs exposure length for {worst}, '
          f'starting {target.science_start:%H:%M}:')
    print(pa_vs_exposure(target.ra_deg, target.dec_deg,
                          target.science_start, location).round(2)
          .to_string(index=False))


if __name__ == '__main__':
    main()
