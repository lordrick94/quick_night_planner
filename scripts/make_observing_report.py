"""
Turn a night plan into an observing report row per target.

Columns match the FFFF-PZ observing log:
    TNS, FRB_Survey, Resource, mode, date, texp, Conditions, success

The plan records what was *scheduled*. Two fields it cannot know are the
conditions and whether each target actually yielded a redshift, so both
are passed in and default conservatively rather than being invented.

    python scripts/make_observing_report.py --plan-dir Night_plans/Keck-2026B-02 \
        --conditions Fair --extra TGT0607

Created by JXP and Claude
"""

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
from night_planner.plan_store import load_plan
from night_planner.observing_report import (FFFFPZ_COLUMNS as COLUMNS,
                                            MODE_MAP, build_ffffpz_rows,
                                            log_from_flags,
                                            planned_exposure_seconds,
                                            write_ffffpz_csv)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan-dir', required=True)
    p.add_argument('--conditions', required=True,
                   help='Observing conditions for the night, e.g. Fair.')
    p.add_argument('--resource', help='FFFF-PZ Resource name [plan directory].')
    p.add_argument('--survey', default='CHIME/FRB')
    p.add_argument('--out', help='Output CSV [<plan-dir>/<resource>_report.csv].')
    p.add_argument('--extra', action='append', default=[],
                   help='Target observed but not in the plan, as NAME or '
                        'NAME:texp_seconds. Repeatable.')
    p.add_argument('--drop', action='append', default=[],
                   help='Planned target that was not observed. Repeatable.')
    p.add_argument('--failed', action='append', default=[],
                   help='Target to mark success=False. Repeatable.')
    return p.parse_args(argv)


def exposure_seconds(target):
    """
    On-target integration time in seconds (kept for older callers).

    Parameters
    ----------
    target : ScheduledTarget

    Returns
    -------
    (seconds, note) -- see observing_report.planned_exposure_seconds.
    """
    return planned_exposure_seconds(target)


def build_rows(plan, args):
    """
    One report row per observed target, in observing order.

    The flags become a minimal observing log and go through
    observing_report.build_ffffpz_rows, the same function the Observing
    log page uses (2026-11-07).

    Parameters
    ----------
    plan : PlanResult
    args : argparse.Namespace from parse_args()

    Returns
    -------
    (rows, notes)
    """
    log = log_from_flags(plan, args.conditions, drop=args.drop,
                         failed=args.failed, extra=args.extra)
    return build_ffffpz_rows(plan, log, survey=args.survey,
                             resource=args.resource)


def main(argv=None):
    args = parse_args(argv)
    plan = load_plan(args.plan_dir)
    if plan is None:
        raise SystemExit(f'no plan_result.json in {args.plan_dir}')

    rows, notes = build_rows(plan, args)
    resource = args.resource or Path(plan.output_dir).name
    out = args.out or f'{args.plan_dir}/{resource}_report.csv'
    write_ffffpz_csv(rows, out)

    print(f'Wrote {out}  ({len(rows)} targets, {plan.date}, '
          f'{args.conditions})')
    for note in notes:
        print(f'  NOTE: {note}')
    print('  success defaults to True -- pass --failed NAME for any target '
          'that did not yield a usable spectrum.')
    return out


if __name__ == '__main__':
    main()
