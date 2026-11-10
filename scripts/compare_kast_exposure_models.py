"""
Kast exposures: the empirical magnitude rule vs the UCO/Lick ETC.

Created by JXP and Claude

Milestone 5c switches Kast plans from the empirical rule
(night_planner/estimate_kast_exposures.py) to the real ETC at the Kast target
S/N per sub-exposure, >= 3 sub-exposures. That target was 5 (Lordrick,
2026-11-07) and is now 10 (Lordrick, same day). This shows what that does to
exposure times before it becomes the default. Outputs so far:
docs/data/kast_exposure_model_comparison.csv (S/N 5) and
docs/data/kast_exposure_model_comparison_sn10.csv (S/N 10). They hold no
targets (magnitudes only), so they live in the public docs.

The ETC is called over a magnitude grid rather than per target, to keep the
load on etc.ucolick.org modest. Setup: G2 (600/4310) / 600/7500 / d55
(stand-in for d57) / 2.0" / 1x1, r band (AB), flat spectrum.

    python scripts/compare_kast_exposure_models.py \
        --out docs/data/kast_exposure_model_comparison.csv
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from night_planner import etc as etc_mod  # noqa: E402
from night_planner.estimate_kast_exposures import estimate_exposure  # noqa: E402
from night_planner.instrument_params import DEFAULT_CONFIG  # noqa: E402

MAGS = (16.0, 17.0, 18.0, 18.5, 19.0, 19.5, 20.0, 20.5, 21.0)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--airmass', type=float, default=1.2)
    p.add_argument('--seeing', type=float, default=1.5,
                   help='FWHM arcsec [1.5, the ETC Kast form default].')
    p.add_argument('--target-sn', type=float, default=etc_mod.TARGET_SN['kast'])
    p.add_argument('--out', help='Optional CSV to write.')
    return p.parse_args(argv)


def compare(mags, airmass, seeing, target_sn):
    """
    Empirical vs ETC exposures for each magnitude.

    Parameters
    ----------
    mags : iterable of float
    airmass, seeing, target_sn : float

    Returns
    -------
    list of dict with mag, empirical red/blue recipes and minutes, ETC
    recipe and minutes, the ETC's per-sub-exposure S/N (blue, red), and
    the ratio ETC / empirical.
    """
    rows = []
    for mag in mags:
        red, blue, dur_s = estimate_exposure(mag)
        e = etc_mod.exposure('kast', mag, 'r', airmass, seeing,
                             DEFAULT_CONFIG['kast'], target_sn,
                             etc_mod.N_SUB_MIN['kast'])
        rows.append({
            'mag_r': mag,
            'empirical_red': red, 'empirical_blue': blue,
            'empirical_min': round(dur_s / 60.0, 1),
            'etc_recipe': e['red_exp'], 'etc_min': round(e['science_min'], 1),
            'etc_sn_sub_blue': e['sn_sub']['blue'],
            'etc_sn_sub_red': e['sn_sub']['red'],
            'ratio_etc_over_empirical': round(e['science_min'] * 60.0 / dur_s, 2),
        })
    return rows


def main(argv=None):
    args = parse_args(argv)
    rows = compare(MAGS, args.airmass, args.seeing, args.target_sn)
    print(f'Kast, airmass {args.airmass}, seeing {args.seeing}", ETC target S/N '
          f'{args.target_sn:g} per sub-exposure (>= 3 subs)')
    print(f"{'mag':>5} {'empirical':>22} {'min':>6} | {'ETC':>10} {'min':>6} "
          f"{'S/N b/r':>11} {'ratio':>6}")
    for r in rows:
        print(f"{r['mag_r']:5.1f} {r['empirical_red'] + ' / ' + r['empirical_blue']:>22} "
              f"{r['empirical_min']:6.1f} | {r['etc_recipe']:>10} {r['etc_min']:6.1f} "
              f"{r['etc_sn_sub_blue']:5.1f}/{r['etc_sn_sub_red']:<5.1f} "
              f"{r['ratio_etc_over_empirical']:6.2f}")
    if args.out:
        with open(args.out, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f'Wrote {args.out}')
    return rows


if __name__ == '__main__':
    main()
