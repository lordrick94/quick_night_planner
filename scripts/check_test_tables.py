"""
Smoke-check the synthetic target tables in test_targs/.

Two jobs:

1. Every table loads, or refuses for the stated reason. The three `bad_`
   tables must refuse -- a release that reads them is guessing, and
   guessing an RA unit wrong moves the telescope by a factor of 15.

2. Report the best airmass each table reaches from each site. This is
   what makes a table a useful test rather than a pile of rows: a target
   can sit inside the Shane's hour-angle limits and still never rise far
   enough to be worth a spectrum, because those limits are mechanical and
   carry no airmass cut of their own.

Usage
-----
python scripts/check_test_tables.py [dir]

Created by JXP and Claude
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from night_planner.adapters import SITES  # noqa: E402
from night_planner.targets_io import TargetTableError, load_targets  # noqa: E402


def best_airmass(dec_deg, lat_deg):
    """
    Airmass at transit, the best a target can ever reach from a site.

    Parameters
    ----------
    dec_deg : array-like
    lat_deg : float

    Returns
    -------
    ndarray
        sec(z) at culmination; inf for anything that never rises.
    """
    alt = 90.0 - np.abs(np.asarray(dec_deg, dtype=float) - lat_deg)
    with np.errstate(divide='ignore', invalid='ignore'):
        airmass = 1.0 / np.sin(np.radians(alt))
    return np.where(alt > 0, airmass, np.inf)


def check(table_dir='test_targs'):
    """
    Load every table and summarise it.

    Returns
    -------
    DataFrame, one row per file.
    """
    rows = []
    for path in sorted(Path(table_dir).glob('*.csv')):
        expect_fail = path.name.startswith('bad_')
        try:
            df = load_targets(path)
        except TargetTableError as err:
            rows.append({'file': path.name, 'rows': None, 'status': 'refused',
                         'as_intended': expect_fail,
                         'detail': str(err).split(':', 1)[-1].strip()[:70]})
            continue

        detail = []
        for key, site in SITES.items():
            am = best_airmass(df['dec_deg'], site['location'].lat.deg)
            detail.append(f'{key}: {int((am < 2.0).sum())}/{len(df)} reach AM<2')
        rows.append({'file': path.name, 'rows': len(df), 'status': 'loaded',
                     'as_intended': not expect_fail,
                     'detail': '; '.join(detail)})
    return pd.DataFrame(rows)


def main():
    """Print the check and exit non-zero if any table misbehaved."""
    df = check(sys.argv[1] if len(sys.argv) > 1 else 'test_targs')
    print(df.to_string(index=False))

    wrong = df[~df['as_intended']]
    if len(wrong):
        print(f'\n{len(wrong)} table(s) did not behave as intended:')
        print(wrong.to_string(index=False))
        return 1
    print(f'\nAll {len(df)} tables behaved as intended.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
