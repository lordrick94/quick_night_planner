"""
Lick Shane: parallactic angle and Cassegrain tub readout, after Burrous.

`helpful_scripts/pa.c` (Jim Burrous, Lick Observatory, 1990, following
Filippenko 1982 PASP) is the tool Lick observers actually use. It answers
a different question from ours in two ways, and both are worth having in
Python:

1. **It evaluates the parallactic angle at the midpoint of the exposure**,
   not as an average over it. That is the observatory's convention, so it
   is what a Lick observer expects a plan to quote.

2. **It converts that angle into a Cassegrain tub position** -- the Nixie
   readout, which is the number actually dialled at the telescope and is
   *not* the sky PA. `calcint.c` interpolates a 37-row table; the table is
   linear to a hundredth of a count, readout = 0.87 x PA + 0.05, which is
   worth knowing but is reproduced here by interpolation so it stays
   faithful to the file.

Both are ported literally, quadrant patches and all, so they can be used
as a check on night_planner.parallactic rather than as a rewrite of it.

Created by JXP and Claude
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from night_planner.lick_tub import cass_tub_readout  # noqa: E402

LICK_LAT = 37.343
PALOMAR_LAT = 33.3567
KECK_LAT = 19.825

def burrous_pa(ha_hours, dec_deg, exposure_sec=0.0, lat_deg=LICK_LAT):
    """
    Parallactic angle at the midpoint of an exposure, after pa.c.

    A literal port, including the quadrant patch: pa.c works with |HA|
    and asin(), which cannot tell the two solutions apart on its own, so
    for a target north of the latitude it tests HA against
    acos(tan(lat)/tan(dec)) and reflects the angle when inside.

    Parameters
    ----------
    ha_hours : float
        Hour angle at the *start* of the exposure, hours.
    dec_deg : float
    exposure_sec : float
        Exposure length. The angle is evaluated at ha + exposure/2.
    lat_deg : float

    Returns
    -------
    dict with 'pa', 'alt_pa' (the 180-degree complement pa.c also prints),
    'airmass', 'ha_mid_hours'
    """
    lat = np.radians(lat_deg)
    ha_mid = ha_hours + 0.5 * exposure_sec / 3600.0
    dha = np.radians(ha_mid * 15.0)
    dec = np.radians(dec_deg)
    ha = abs(dha)                       # pa.c: "must use positive ha"

    num = np.sin(ha) * np.cos(lat)
    tmp = np.sin(lat) * np.sin(dec) + np.cos(lat) * np.cos(dec) * np.cos(ha)
    denom = np.sqrt(1.0 - tmp ** 2)
    eta = np.degrees(np.arcsin(num / denom))

    if dec >= lat:
        ha_test = np.arccos(np.tan(lat) / np.tan(dec))
        if ha <= ha_test:
            eta = 180.0 - eta

    eta = 360.0 - eta if dha < 0 else eta
    eta = eta - 180.0 if eta >= 180.0 else eta + 180.0

    alt_pa = eta - 180.0 if eta >= 180.0 else eta + 180.0
    return {'pa': float(eta), 'alt_pa': float(alt_pa),
            'airmass': float(1.0 / tmp), 'ha_mid_hours': float(ha_mid)}


def compare_with_night_planner(lat_deg=LICK_LAT):
    """
    Check night_planner.parallactic against pa.c across the sky.

    Both are folded onto [0, 180): a slit has no head or tail, and pa.c
    adds 180 to report a tub angle rather than the bare parallactic
    angle, so only the axis is comparable.

    Returns
    -------
    DataFrame with the worst disagreements first.
    """
    import pandas as pd

    from night_planner.parallactic import parallactic_angle_from_ha

    rows = []
    for dec in range(-20, 85, 5):
        for ha in np.arange(-5.0, 5.01, 0.5):
            if abs(dec - lat_deg) < 0.2 and abs(ha) < 0.05:
                continue            # straight overhead: PA is undefined
            theirs = burrous_pa(ha, dec, 0.0, lat_deg)['pa'] % 180.0
            ours = parallactic_angle_from_ha(ha, dec, lat_deg) % 180.0
            diff = abs((theirs - ours + 90) % 180 - 90)
            rows.append({'dec': dec, 'ha': ha, 'burrous': theirs,
                         'night_planner': ours, 'diff': diff})
    return pd.DataFrame(rows).sort_values('diff', ascending=False)


def plan_tub_table(plan_dir='Night_plans/Lick-2026B-03'):
    """
    Per-target tub readout for a plan, and midpoint vs weighted angle.

    Two columns worth reading together: `pa_mid` is what pa.c would say
    (the angle at the midpoint of the exposure) and `pa_weighted` is what
    night_planner chooses (tan(z)-weighted over the block). They differ
    only when the target is low, which is exactly when it matters.

    Returns
    -------
    DataFrame
    """
    import pandas as pd

    from night_planner.adapters import SITES
    from night_planner.parallactic import (average_parallactic, hour_angle,
                                            parallactic_angle_from_ha)
    from night_planner.plan_store import load_plan

    plan = load_plan(str(plan_dir))
    location = SITES[plan.instrument]['location']
    lat = location.lat.deg

    rows = []
    for target in plan.schedule:
        mid = target.science_start + (target.end - target.science_start) / 2
        ha_mid = hour_angle(target.ra_deg, mid, location)
        pa_mid = parallactic_angle_from_ha(ha_mid, target.dec_deg, lat)
        pa_w = average_parallactic(target.ra_deg, target.dec_deg,
                                    target.science_start, target.end,
                                    location)['mean_pa']
        rows.append({
            'TNS': target.name,
            'ha_mid': ha_mid,
            'pa_mid': pa_mid,
            'pa_weighted': pa_w,
            'delta': abs((pa_mid - pa_w + 90) % 180 - 90),
            'tub': cass_tub_readout(pa_w),
            'tub_alt': cass_tub_readout(pa_w + 180.0),
        })
    return pd.DataFrame(rows)


def main():
    """Convert one PA if given, else run the cross-check."""
    if len(sys.argv) > 1:
        # At the telescope: "what do I dial for this angle?"
        from night_planner.lick_tub import tub_settings
        both = tub_settings(float(sys.argv[1]))
        print(f"Sky PA {both['pa']:.2f} deg  ->  Cass tub {both['tub']:.2f}")
        print(f"Sky PA {both['alt_pa']:.2f} deg  ->  Cass tub "
              f"{both['alt_tub']:.2f}   (same slit on the sky)")
        return

    df = compare_with_night_planner()
    print(f'Compared {len(df)} HA/Dec points against pa.c (Lick, '
          f'lat {LICK_LAT}):')
    print(f'  worst disagreement : {df["diff"].max():.6f} deg')
    print(f'  mean disagreement  : {df["diff"].mean():.6f} deg')
    print('\nWorst five:')
    print(df.head(5).round(4).to_string(index=False))

    print('\nCassegrain tub readout (calcint.c):')
    for pa in (0, 20, 45, 90, 108.9, 135, 180, 270, 359):
        print(f'  PA {pa:6.1f} deg -> Nixie {cass_tub_readout(pa):7.2f}')

    print('\nTonight:')
    print(plan_tub_table().round(2).to_string(index=False))


if __name__ == '__main__':
    main()
