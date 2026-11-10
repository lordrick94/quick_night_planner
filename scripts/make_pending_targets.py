"""
Write a *_pending.csv holding just the targets from one night's plan.

Use it to carry a set of targets forward: observed-but-no-redshift hosts
that want another night, or a subset you want to re-plan against a
different date. The output keeps the source table's own schema and column
order, so it feeds straight back into the planner like any other pull.

    python scripts/make_pending_targets.py --plan-dir Night_plans/Keck-2026B-02

Targets come from the plan's scheduled list by default; --include adds
names that were observed but never made it into the plan (a target picked
up opportunistically, say), and --exclude drops any you don't want carried
forward.

Created by JXP and Claude
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
from night_planner.plan_store import load_plan
from night_planner.targets_io import detect_mapping


def parse_args(argv=None):
    """
    Parameters
    ----------
    argv : list of str, optional

    Returns
    -------
    argparse.Namespace
    """
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan-dir', required=True,
                   help='Plan directory holding plan_result.json.')
    p.add_argument('--source',
                   help='Target table to take rows from. Defaults to the '
                        '*_targets.csv in the plan directory.')
    p.add_argument('--out', help='Output path. Defaults to '
                                 '<plan-dir>/<resource>_pending.csv.')
    p.add_argument('--include', action='append', default=[],
                   help='Extra target name to carry forward. Repeatable.')
    p.add_argument('--exclude', action='append', default=[],
                   help='Target name to leave out. Repeatable.')
    return p.parse_args(argv)


def pending_frame(source_csv, names):
    """
    Rows of `source_csv` whose target name is in `names`.

    Keeps the source schema untouched -- the name column is located via
    the same detection the planner uses, so this works on an FFFF-PZ pull
    or on someone's own spreadsheet.

    Parameters
    ----------
    source_csv : str
    names : list of str

    Returns
    -------
    (DataFrame, list of str)
        The filtered rows, and any requested names the source didn't have.
    """
    df = pd.read_csv(source_csv)
    name_col = detect_mapping(df).columns.get('name')
    if name_col is None:
        raise SystemExit(f'cannot find a target-name column in {source_csv}')

    wanted = list(dict.fromkeys(names))
    present = df[df[name_col].isin(wanted)].copy()
    missing = [n for n in wanted if n not in set(df[name_col])]

    # Emit in the order asked for, so the file reads like the night did.
    order = {name: i for i, name in enumerate(wanted)}
    present = present.sort_values(by=name_col, key=lambda s: s.map(order))
    return present, missing


def main(argv=None):
    """Write the pending table and report what went into it."""
    args = parse_args(argv)

    plan = load_plan(args.plan_dir)
    if plan is None:
        raise SystemExit(f'no plan_result.json in {args.plan_dir}')

    source = args.source
    if source is None:
        candidates = sorted(__import__('pathlib').Path(args.plan_dir)
                            .glob('*_targets.csv'))
        if not candidates:
            raise SystemExit(f'no *_targets.csv in {args.plan_dir}; pass --source')
        source = str(candidates[0])

    names = [t.name for t in plan.schedule] + list(args.include)
    names = [n for n in names if n not in set(args.exclude)]

    frame, missing = pending_frame(source, names)

    out = args.out
    if out is None:
        stem = __import__('pathlib').Path(source).name.replace('_targets.csv', '')
        out = f'{args.plan_dir}/{stem}_pending.csv'
    frame.to_csv(out, index=False)

    print(f'Wrote {out}')
    print(f'  {len(frame)} of {len(names)} requested targets, '
          f'from {source}')
    for name in frame[detect_mapping(frame).columns['name']]:
        print(f'    {name}')
    if missing:
        print(f'  NOT FOUND in the source table: {", ".join(missing)}')
    return out


if __name__ == '__main__':
    main()
