"""
Check one target CSV before it is used to plan a night.

This is the command-line twin of the viewer's "Read targets & set
priorities" step: it answers the same three questions without starting a
server.

1. *Can this table be read at all?* -- which source column feeds each
   canonical field, and which units were inferred for RA. A table that
   cannot be read unambiguously is refused here, with the same message
   the planner would give, rather than at 4pm on the observing day.
2. *Did anything get quietly dropped?* -- chiefly a priority column whose
   values are not numbers. Those fall back to the default, which is
   correct behaviour but worth seeing.
3. *Is the list any good?* -- the best airmass each target can ever
   reach, the Dec limit, and the exposure its magnitude implies. A table
   can be perfectly readable and still be a bad night: everything above
   the pointing limit, or 40 hours of exposure for a 9-hour night.

Usage
-----
python scripts/check_target_csv.py my_targets.csv
python scripts/check_target_csv.py my_targets.csv --instrument lris

Exit status is 1 when the table cannot be read, so this is usable in a
pipeline; a merely *poor* list still exits 0, because whether a list is
worth the night is the observer's call, not this script's.

Created by JXP and Claude
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from night_planner.adapters import SITES  # noqa: E402
from night_planner.estimate_kast_exposures import estimate_exposure  # noqa: E402
from night_planner.targets_io import (  # noqa: E402
    DEFAULT_PRIORITY, TargetTableError, detect_format, detect_mapping,
    load_targets, priority_coercions,
)

# Shane 3m mechanical pointing limit in declination. Repeated here rather
# than imported because this script must stay runnable against a table for
# any instrument, and the per-run scheduler modules each carry their own
# copy. Keck has no equivalent hard Dec ceiling, so the check is skipped
# there rather than applied with a borrowed number.
DEC_LIMIT = {'kast': 82.0}

# A target that never rises above this airmass is technically pointable and
# practically a waste of the slew.
POOR_AIRMASS = 2.0


def best_airmass(dec_deg, lat_deg):
    """Airmass at transit: the best a target can ever reach from a site.

    Created by JXP and Claude

    Inputs
    ------
    dec_deg : float
        Target declination in degrees.
    lat_deg : float
        Site latitude in degrees.

    Outputs
    -------
    float airmass at transit, or numpy.inf if the target never rises.
    """
    altitude = 90.0 - abs(dec_deg - lat_deg)
    if altitude <= 0:
        return np.inf
    return 1.0 / np.sin(np.radians(altitude))


def describe_mapping(mapping):
    """Render a detected column mapping as lines of text.

    Created by JXP and Claude

    Inputs
    ------
    mapping : night_planner.targets_io.ColumnMapping

    Outputs
    -------
    list of str, one line per canonical field that was matched.
    """
    lines = []
    for fieldname, column in mapping.columns.items():
        note = ''
        if fieldname == 'ra':
            note = f'   (read as {mapping.ra_unit})'
        lines.append(f'  {fieldname:<9} <- {column}{note}')
    return lines


def summarize_quality(frame, instrument):
    """Report what the table implies for a night, target by target.

    Created by JXP and Claude

    Inputs
    ------
    frame : pandas.DataFrame
        A canonical table, as returned by targets_io.load_targets.
    instrument : str
        Key into night_planner.adapters.SITES ('kast' or 'lris').

    Outputs
    -------
    dict with 'rows' (list of per-target dicts), 'total_hours' (float,
    on-source science time only), 'n_over_dec_limit' (int) and
    'dec_limit' (float or None when the instrument has no hard ceiling).
    """
    latitude = SITES[instrument]['location'].lat.deg
    dec_limit = DEC_LIMIT.get(instrument)

    rows = []
    for _, target in frame.iterrows():
        airmass = best_airmass(target['dec_deg'], latitude)
        _, _, seconds = estimate_exposure(target['mag'])
        rows.append({
            'name': target['name'],
            'ra_hours': target['ra_deg'] / 15.0,
            'dec_deg': target['dec_deg'],
            'mag': target['mag'],
            'priority': target['priority'],
            'best_airmass': airmass,
            'exposure_min': seconds / 60.0,
            'over_dec_limit': (dec_limit is not None
                                and target['dec_deg'] > dec_limit),
        })

    return {
        'rows': rows,
        'total_hours': sum(r['exposure_min'] for r in rows) / 60.0,
        'n_over_dec_limit': sum(1 for r in rows if r['over_dec_limit']),
        'dec_limit': dec_limit,
    }


def parse_args(argv=None):
    """Command-line arguments.

    Created by JXP and Claude

    Inputs
    ------
    argv : list of str, optional

    Outputs
    -------
    argparse.Namespace with csv, instrument and quiet.
    """
    parser = argparse.ArgumentParser(
        description='Check a target CSV before planning a night with it.')
    parser.add_argument('csv', help='Path to the target table.')
    parser.add_argument('--instrument', default='kast', choices=sorted(SITES),
                        help='Instrument whose site and limits to judge '
                             'against (default kast = Shane 3m at Lick).')
    parser.add_argument('--quiet', action='store_true',
                        help='Report problems only; skip the per-target table.')
    return parser.parse_args(argv)


def run(args):
    """Check one table and print the report.

    Created by JXP and Claude

    Inputs
    ------
    args : argparse.Namespace from parse_args.

    Outputs
    -------
    int exit status: 1 if the table cannot be read, else 0.
    """
    path = Path(args.csv)
    if not path.exists():
        print(f'no such file: {path}', file=sys.stderr)
        return 1

    raw = pd.read_csv(path)
    print(f'{path}  --  {len(raw)} rows, {len(raw.columns)} columns')

    fmt = detect_format(raw)
    print(f"format: {fmt['format']}"
          + ('  (two host candidates present: slit-angle mode available)'
             if fmt['has_candidates'] else ''))

    mapping = detect_mapping(raw)
    print('\ncolumns detected:')
    for line in describe_mapping(mapping):
        print(line)

    if not mapping.ok:
        print('\nTHIS TABLE CANNOT BE READ:')
        for issue in mapping.issues:
            print(f'  - {issue}')
        print('\nSee docs/target_csv_guide.md for how to fix each of these.')
        return 1

    try:
        frame = load_targets(raw, mapping=mapping)
    except TargetTableError as err:
        print(f'\nTHIS TABLE CANNOT BE READ:\n  - {err}')
        print('\nSee docs/target_csv_guide.md for how to fix each of these.')
        return 1

    coercions = priority_coercions(raw, mapping=mapping)
    if coercions['column'] is None:
        print(f"\npriority: no column -- every target defaults to "
              f'{DEFAULT_PRIORITY:g} (one tier, scheduled by urgency alone)')
    elif coercions['n_coerced']:
        print(f"\npriority: {coercions['n_coerced']} of {coercions['n_total']} "
              f"values in '{coercions['column']}' are not numbers "
              f"(e.g. {', '.join(coercions['examples'])}) and fell back to "
              f'{DEFAULT_PRIORITY:g} -- use numbers, lower = more important')
    else:
        tiers = sorted(frame['priority'].unique())
        print(f"\npriority: read from '{coercions['column']}', "
              f"{len(tiers)} tier(s): {', '.join(f'{t:g}' for t in tiers)}")

    quality = summarize_quality(frame, args.instrument)

    if not args.quiet:
        print(f'\n{"target":<18}{"RA(h)":>7}{"Dec":>8}{"mag":>7}{"prio":>6}'
              f'{"airmass":>9}{"exp(min)":>10}')
        for row in sorted(quality['rows'], key=lambda r: r['ra_hours']):
            airmass = ('never' if np.isinf(row['best_airmass'])
                       else f"{row['best_airmass']:.2f}")
            flag = '  << above Dec limit' if row['over_dec_limit'] else (
                '  << poor airmass'
                if row['best_airmass'] > POOR_AIRMASS else '')
            print(f"{row['name']:<18}{row['ra_hours']:>7.2f}"
                  f"{row['dec_deg']:>8.2f}{row['mag']:>7.2f}"
                  f"{row['priority']:>6g}{airmass:>9}"
                  f"{row['exposure_min']:>10.0f}{flag}")

    print(f"\n{len(quality['rows'])} targets, "
          f"{quality['total_hours']:.1f} h of on-source exposure "
          f'(before slews, focus and standards)')
    if args.instrument != 'kast':
        print('  NB exposure times are the Kast dual-beam heuristic; they '
              'are indicative only for other instruments')
    if quality['n_over_dec_limit']:
        print(f"  {quality['n_over_dec_limit']} above Dec "
              f"+{quality['dec_limit']:.0f}: the telescope cannot point "
              f'there and they will be rejected')
    print('  readable: yes')
    return 0


if __name__ == '__main__':
    sys.exit(run(parse_args()))
