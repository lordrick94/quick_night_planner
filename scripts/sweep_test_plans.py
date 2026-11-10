"""
Run every synthetic target table through the planner, on many dates.

A night plan has few natural unit tests: the output is a schedule, and
what makes it wrong is usually a relationship between rows rather than a
single bad value. So this builds a lot of plans and asserts the
invariants that must hold whatever the inputs -- blocks inside the night,
no overlaps, nothing scheduled outside its own window, every target
accounted for exactly once.

It exists to be run against the whole of `test_targs/` across the year,
which is where the seasonal and format variety pays off: a bug that only
appears in June, or only for a table with RA in hours, will not show up
in a single hand-run plan.

Usage
-----
python scripts/sweep_test_plans.py [--dates N] [--instrument kast|lris|both]

Created by JXP and Claude
"""

import argparse
import io
import contextlib
import sys
import tempfile
import traceback
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from night_planner.cli import generate_plan  # noqa: E402

# Spread across the year so seasonal failures surface: solstices and
# equinoxes, plus the months either side of the summer twilight problem.
# 2026-03-07 and 2026-11-01 are the nights the US clocks change, which
# is where wall-clock arithmetic goes wrong; they earn their place.
DATES = ['2026-01-15', '2026-03-07', '2026-03-20', '2026-04-15',
         '2026-05-15', '2026-06-01', '2026-06-21', '2026-07-15',
         '2026-08-15', '2026-09-22', '2026-10-12', '2026-11-01',
         '2026-11-07', '2026-12-21']

# Tables the planner should refuse; running them is not a sweep failure.
SKIP_PREFIX = 'bad_'


# Keck allows a block to run one sampling step past its airmass window,
# because that is how precisely find_observable_window() knows the edge.
# Lick's windows are analytic hour-angle limits with no such slack.
WINDOW_GRACE_MIN = {'lris': 10, 'kast': 0}


def check_plan(plan):
    """
    Invariants every schedule must satisfy, whatever the inputs.

    Parameters
    ----------
    plan : PlanResult

    Returns
    -------
    list of str, one per violation (empty when the plan is sane).
    """
    problems = []
    grace = timedelta(minutes=WINDOW_GRACE_MIN.get(plan.instrument, 0))
    blocks = sorted(plan.schedule, key=lambda t: t.start)

    seen = set()
    for t in blocks:
        if t.name in seen:
            problems.append(f'{t.name}: scheduled more than once')
        seen.add(t.name)

        if t.end <= t.start:
            problems.append(f'{t.name}: ends at or before it starts '
                            f'({t.start:%H:%M}-{t.end:%H:%M})')
        if t.on_target_min is not None and t.on_target_min <= 0:
            problems.append(f'{t.name}: non-positive exposure '
                            f'({t.on_target_min})')

        # A block may start on the night boundary but must not run past
        # morning twilight, which is when the sky stops being usable.
        if t.end > plan.night_end + timedelta(minutes=1):
            problems.append(f'{t.name}: ends {t.end:%H:%M}, after the night '
                            f'closes at {plan.night_end:%H:%M}')
        if t.start < plan.night_start - timedelta(minutes=1):
            problems.append(f'{t.name}: starts {t.start:%H:%M}, before the '
                            f'night opens at {plan.night_start:%H:%M}')

        # Its own pointability window, where the adapter recorded one.
        if t.window_start and t.science_start < t.window_start - timedelta(minutes=1):
            problems.append(f'{t.name}: on target {t.science_start:%H:%M}, '
                            f'before its window opens {t.window_start:%H:%M}')
        if t.window_end and t.end > t.window_end + grace + timedelta(minutes=1):
            problems.append(f'{t.name}: ends {t.end:%H:%M}, more than '
                            f'{grace} past its window close '
                            f'{t.window_end:%H:%M}')

    for a, b in zip(blocks, blocks[1:]):
        if b.start < a.end - timedelta(seconds=30):
            problems.append(f'{a.name} and {b.name} overlap '
                            f'({a.end:%H:%M} > {b.start:%H:%M})')

    # Every target in the table should be either scheduled or rejected
    # with a reason -- a target that simply vanishes is the failure mode
    # that is hardest to notice from the plan alone.
    for d in plan.decisions:
        if d.status == 'rejected' and not (d.reason or '').strip():
            problems.append(f'{d.name}: rejected with no reason given')

    decided = {d.name for d in plan.decisions}
    for t in plan.schedule:
        if t.name not in decided:
            problems.append(f'{t.name}: scheduled but absent from decisions')

    return problems


def run_one(instrument, table, date_str, out_root, overrides=False):
    """
    Build one plan and check it.

    Returns
    -------
    dict with 'table', 'date', 'instrument', 'status', 'detail',
    'n_scheduled', 'n_rejected'
    """
    suffix = '-ovr' if overrides else ''
    out_dir = Path(out_root) / f'{instrument}-{table.stem}-{date_str}{suffix}'
    argv = ['--targets-csv', str(table), '--output-dir', str(out_dir),
            '--date', date_str]
    if overrides:
        # A manual start and a mid-night block push blocks across times
        # the plain path never lands on -- including the DST gap.
        argv += ['--start', '22:00', '--block', '01:00-02:00@weather']

    row = {'instrument': instrument, 'table': table.name, 'date': date_str,
           'overrides': overrides, 'status': 'ok', 'detail': '',
           'n_scheduled': 0, 'n_rejected': 0}
    try:
        # The pipelines print a lot; the sweep only wants the outcome.
        with contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            plan = generate_plan(instrument, argv)
    except SystemExit as err:
        row.update(status='refused', detail=str(err))
        return row
    except Exception as err:                      # noqa: BLE001 - reporting
        row.update(status='CRASH',
                   detail=f'{type(err).__name__}: {err}'.replace('\n', ' ')[:160])
        return row

    row['n_scheduled'] = len(plan.schedule)
    row['n_rejected'] = sum(1 for d in plan.decisions if d.status == 'rejected')
    problems = check_plan(plan)
    if problems:
        row.update(status='INVALID', detail=' | '.join(problems[:3]))
    elif not plan.schedule:
        row.update(status='empty', detail='nothing scheduled')
    return row


def sweep(table_dir='test_targs', instruments=('kast',), dates=None,
           out_root=None):
    """
    Run every usable table on every date.

    Returns
    -------
    DataFrame, one row per (instrument, table, date).
    """
    dates = dates or DATES
    tables = [p for p in sorted(Path(table_dir).glob('*.csv'))
              if not p.name.startswith(SKIP_PREFIX)]

    holder = out_root or tempfile.mkdtemp(prefix='sweep-')
    rows = []
    for instrument in instruments:
        for table in tables:
            for date_str in dates:
                for overrides in (False, True):
                    rows.append(run_one(instrument, table, date_str, holder,
                                         overrides))
    return pd.DataFrame(rows)


def main():
    """Run the sweep and summarise."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--table-dir', default='test_targs')
    ap.add_argument('--instrument', default='kast',
                    choices=['kast', 'lris', 'both'])
    ap.add_argument('--dates', type=int, default=len(DATES),
                    help='how many of the built-in dates to use')
    ap.add_argument('--out-root', default=None)
    args = ap.parse_args()

    instruments = (('kast', 'lris') if args.instrument == 'both'
                   else (args.instrument,))
    df = sweep(args.table_dir, instruments, DATES[:args.dates], args.out_root)

    print(df['status'].value_counts().to_string())
    bad = df[df['status'].isin(['CRASH', 'INVALID'])]
    if len(bad):
        print(f'\n{len(bad)} problem runs:\n')
        print(bad[['instrument', 'table', 'date', 'overrides', 'status',
                   'detail']].to_string(index=False))
    else:
        print('\nNo crashes and no invalid schedules.')

    empty = df[df['status'] == 'empty']
    if len(empty):
        print(f'\n{len(empty)} runs scheduled nothing '
              f'(often correct -- wrong season for the table):')
        print(empty.groupby('table')['date'].count().to_string())
    return 1 if len(bad) else 0


if __name__ == '__main__':
    raise SystemExit(main())
