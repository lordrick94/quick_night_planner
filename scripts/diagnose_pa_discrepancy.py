"""
Work out why a requested slit PA and the angle set at the telescope differ.

Given a plan, a target and two angles, this recomputes the geometry from
the catalogue and reports which explanation fits: the requested angle was
wrong, the reported one is in instrument units rather than sky units, a
sign or perpendicular mix-up, and so on.

The decisive number is usually the slit tolerance. Both objects are in
the slit only while `sep * sin(delta) <= width / 2`, and for a pair tens
of arcsec apart that is a degree or two -- far tighter than people
expect. If both spectra came out, any larger disagreement cannot be a
sky angle, which separates a units problem from a pointing problem in
one line.

Usage
-----
python scripts/diagnose_pa_discrepancy.py PLAN_DIR TNS REQUESTED OBSERVED

Created by JXP and Claude
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from astropy import units as u
from astropy.coordinates import SkyCoord

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def candidate_geometry(row):
    """
    Angle and separation between the primary and secondary candidates.

    Parameters
    ----------
    row : Series
        A target-table row carrying Pri_RA/Pri_Dec and Sec_RA/Sec_Dec.

    Returns
    -------
    dict with 'sep_arcsec', 'pa_pri_to_sec', 'pa_sec_to_pri', 'axis'
        `axis` is the orientation folded onto [0, 180): a slit has no head
        or tail, so that is the only part a slit angle has to match.
    """
    pri = SkyCoord(ra=float(row['Pri_RA']) * u.deg,
                   dec=float(row['Pri_Dec']) * u.deg)
    sec = SkyCoord(ra=float(row['Sec_RA']) * u.deg,
                   dec=float(row['Sec_Dec']) * u.deg)
    pa = float(pri.position_angle(sec).deg)
    return {
        'sep_arcsec': float(pri.separation(sec).arcsec),
        'pa_pri_to_sec': pa,
        'pa_sec_to_pri': (pa + 180.0) % 360.0,
        'axis': pa % 180.0,
    }


def axis_difference(a, b):
    """Smallest angle between two slit orientations, in degrees [0, 90]."""
    return float(abs((a - b + 90.0) % 180.0 - 90.0))


def slit_tolerance(sep_arcsec, slit_widths=(0.7, 1.0, 1.5, 2.0)):
    """
    How far off the candidate axis a slit can be and still hold both.

    This is the number that settles an argument about a reported angle.
    Both objects are in the slit only while
    `sep * sin(delta) <= width / 2`, and for a pair tens of arcsec apart
    that tolerance is a degree or two -- far tighter than people expect,
    and tight enough that a 20-degree disagreement cannot be a sky angle
    if both spectra came out.

    Parameters
    ----------
    sep_arcsec : float
    slit_widths : iterable of float

    Returns
    -------
    DataFrame
    """
    import pandas as pd

    rows = []
    for width in slit_widths:
        ratio = min(1.0, (width / 2.0) / sep_arcsec)
        rows.append({'slit_width': width,
                     'max_offset_deg': float(np.degrees(np.arcsin(ratio)))})
    return pd.DataFrame(rows)


def explain(requested, observed, geometry):
    """
    Test each candidate explanation for the discrepancy.

    Returns
    -------
    DataFrame, best match first.
    """
    truth = geometry['axis']
    tests = [
        ('requested angle', requested,
         'what the plan asked the observer to set'),
        ('observed angle', observed,
         'what the observer set by eye, with both traces recovered'),
        ('candidate axis (catalogue)', truth,
         'angle between the two PATH candidates, recomputed here'),
        ('requested + 90', requested + 90.0,
         'a slit-vs-perpendicular mix-up'),
        ('requested, sign flipped', -requested,
         'a PA measured west of north instead of east'),
        ('requested as a Lick tub reading', (requested - 0.05) / 0.87,
         'the plan quoted a tub number and it was read as a sky PA'),
        ('observed as a Lick tub reading', (observed - 0.05) / 0.87,
         'the observer read the tub and reported it as a sky PA'),
    ]
    rows = [{'hypothesis': name, 'angle': float(value) % 180.0,
             'vs_candidate_axis': axis_difference(value, truth),
             'note': note}
            for name, value, note in tests]
    return pd.DataFrame(rows).sort_values('vs_candidate_axis')


def main():
    """Run the diagnosis and print the comparison."""
    if len(sys.argv) != 5:
        raise SystemExit('usage: diagnose_pa_discrepancy.py PLAN_DIR TNS '
                         'REQUESTED_PA OBSERVED_PA')
    plan_dir = Path(sys.argv[1])
    tns = sys.argv[2]
    requested, observed = float(sys.argv[3]), float(sys.argv[4])

    table = next(p for p in plan_dir.glob('*_targets.csv'))
    df = pd.read_csv(table)
    row = df[df['TNS'] == tns]
    if row.empty:
        raise SystemExit(f'{tns} is not in {table}')
    row = row.iloc[0]

    geom = candidate_geometry(row)
    print(f'{tns}  ({table.name})')
    print(f"  primary   {row['Pri_name']}  mag {row['Pri_mag']:.2f}  "
          f"P(O|x) {row['Pri_POx']:.3f}")
    print(f"  secondary {row['Sec_name']}  mag {row['Sec_mag']:.2f}  "
          f"P(O|x) {row['Sec_POx']:.3g}")
    print(f"  separation {geom['sep_arcsec']:.2f}\"")
    print(f"  PA primary -> secondary : {geom['pa_pri_to_sec']:.2f} deg")
    print(f"  slit axis needed        : {geom['axis']:.2f} deg "
          f"(or {geom['axis'] + 180:.2f})")
    print(f'\nRequested {requested}, observer set {observed}, '
          f'difference {axis_difference(requested, observed):.2f} deg\n')
    print(explain(requested, observed, geom).round(2).to_string(index=False))

    off = geom['sep_arcsec'] * np.sin(np.radians(
        axis_difference(requested, observed)))
    print(f'\nAt the observed angle the secondary would sit {off:.2f}" off '
          f'the slit centreline.')
    print(slit_tolerance(geom['sep_arcsec']).round(2).to_string(index=False))
    print('\nIf both traces were recorded, the reported angle cannot be a '
          '\nsky position angle -- the pair would have missed the slit.')



if __name__ == '__main__':
    main()
