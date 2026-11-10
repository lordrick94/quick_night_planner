"""Check an Excel night plan against the plan it was built from.

Created by JXP and Claude

Recalculates the workbook with headless LibreOffice (openpyxl writes formulas
without cached values), then for every timed row of the night sheet compares:

- column C/E (local start/end, from the formula chain) with the plan's own
  timeline rows (night_planner.excel_plan.timeline_rows);
- column B (UT) with the true UT of that instant;
- column A (LST) with astropy's apparent LST at that instant.

Prints counts and the worst differences in minutes only (no target names), so
the output is safe to paste anywhere.

Usage
-----
    python scripts/verify_excel_plan.py PLAN_DIR WORKBOOK.xlsx [--sheet NAME]

Inputs
------
PLAN_DIR : directory with plan_result.json
WORKBOOK : the .xlsx built from it
--sheet : night sheet (default: the first sheet after 'Observing Checklist')

Outputs
-------
Exit code 0 when every row agrees to within 1 min, else 1.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from night_planner.adapters import SITES  # noqa: E402
from night_planner.excel_plan import FIRST_ROW, timeline_rows  # noqa: E402
from night_planner.plan_store import load_plan  # noqa: E402
from night_planner.sky import lst_hours  # noqa: E402


def recalculated_copy(xlsx, workdir):
    """
    Let LibreOffice open, recalculate and re-save the workbook.

    Inputs
    ------
    xlsx : Path
    workdir : Path, scratch directory

    Outputs
    -------
    Path of the recalculated copy.
    """
    src = Path(workdir) / 'in' / Path(xlsx).name
    src.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(xlsx, src)
    out_dir = Path(workdir) / 'out'
    subprocess.run(['soffice', '--headless', '--calc', '--convert-to', 'xlsx',
                    '--outdir', str(out_dir), str(src)],
                   check=True, capture_output=True, timeout=180)
    return out_dir / src.name


def to_hours(value):
    """Cell value (time, datetime, or day fraction) -> hours in [0, 24)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.time()
    if isinstance(value, time):
        return value.hour + value.minute / 60 + value.second / 3600
    if isinstance(value, timedelta):
        return (value.total_seconds() / 3600) % 24
    return (float(value) * 24) % 24


def wrap_minutes(a_hours, b_hours):
    """Smallest |a - b| on a 24 h clock, in minutes."""
    d = abs(a_hours - b_hours) % 24
    return min(d, 24 - d) * 60


def verify(plan_dir, workbook, sheet=None):
    """
    Compare a workbook's recalculated times with its plan.

    Inputs
    ------
    plan_dir : str/Path with plan_result.json
    workbook : str/Path, the .xlsx built from it
    sheet : str, optional night-sheet name

    Outputs
    -------
    (sheet name, number of timed rows, dict of worst differences in minutes
    for 'start', 'end', 'UT', 'LST')
    """
    plan = load_plan(str(plan_dir))
    rows = timeline_rows(plan)
    location = SITES[plan.instrument]['location']
    with tempfile.TemporaryDirectory() as tmp:
        wb = openpyxl.load_workbook(recalculated_copy(Path(workbook), tmp),
                                    data_only=True)
    names = wb.sheetnames
    sheet = sheet or names[names.index('Observing Checklist') + 1]
    ws = wb[sheet]

    lsts = lst_hours([r['start'] for r in rows], location)
    worst = {'start': 0.0, 'end': 0.0, 'UT': 0.0, 'LST': 0.0}
    for i, (row, lst) in enumerate(zip(rows, lsts)):
        r = FIRST_ROW + i
        start = row['start']
        end = start + timedelta(minutes=row['minutes'])
        local = start.hour + start.minute / 60
        ut_h = (local - start.utcoffset().total_seconds() / 3600) % 24
        checks = {
            'start': (to_hours(ws.cell(r, 3).value), local),
            'end': (to_hours(ws.cell(r, 5).value), end.hour + end.minute / 60),
            'UT': (to_hours(ws.cell(r, 2).value), ut_h),
            'LST': (to_hours(ws.cell(r, 1).value), float(lst)),
        }
        for key, (got, want) in checks.items():
            if got is None:
                worst[key] = float('inf')
                continue
            worst[key] = max(worst[key], wrap_minutes(got, want))
    return sheet, len(rows), worst


def agrees(worst):
    """True when every worst difference is within 1 minute."""
    return all(v <= 1 for v in worst.values())


def main():
    """
    Parse arguments, recalculate, compare, report.

    Inputs
    ------
    command-line arguments (see module docstring).

    Outputs
    -------
    exit code (0 = all rows agree).
    """
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('plan_dir')
    p.add_argument('workbook')
    p.add_argument('--sheet')
    args = p.parse_args()
    sheet, nrows, worst = verify(args.plan_dir, args.workbook, args.sheet)
    print(f'sheet {sheet!r}: {nrows} timed rows')
    for key, val in worst.items():
        print(f'  worst {key:5s} difference: {val:.2f} min')
    ok = agrees(worst)
    print('OK' if ok else 'MISMATCH')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
