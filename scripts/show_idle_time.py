"""
Report where a generated night plan is idle.

Reads the saved plan_result.json, so the numbers are the same ones the
viewer shows -- the sequence overheads (standards, focus, calibrations)
are carried in the plan itself rather than re-derived here, which is what
kept this script and the API disagreeing before.

    python scripts/show_idle_time.py Night_plans/Keck-2026B-02

Created by JXP and Claude
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
from night_planner.paths import plans_dir

_PLANS = plans_dir()
from night_planner.plan_store import load_plan

DEFAULT_DIR = f'{_PLANS}/Keck-2026B-02'


def main():
    """Print the idle breakdown for a plan directory."""
    plan_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    plan = load_plan(plan_dir)
    if plan is None:
        raise SystemExit(f'no plan_result.json in {plan_dir} -- generate it first')

    s = plan.summary()
    print(f'{plan.date}  {plan.night_start:%H:%M} -> {plan.night_end:%H:%M} '
          f'({s["night_min"]:.0f} min)')

    for b_start, b_end, reason in plan.blocks:
        print(f'  blocked {b_start:%H:%M}-{b_end:%H:%M}  ({reason})')

    gaps = plan.idle_gaps()
    if gaps:
        print('\nidle gaps:')
        for start, end in gaps:
            print(f'  {start:%H:%M}-{end:%H:%M}  '
                  f'{(end - start).total_seconds() / 60:.0f} min')
    else:
        print('\nno idle gaps -- back to back all night')

    print(f'\n  on target  {s["on_target_min"]:>5.0f} min  '
          f'({s["utilization"]:.0%} of the night)')
    print(f'  slew       {s["slew_min"]:>5.0f} min')
    print(f'  overheads  {s["overhead_min"]:>5.0f} min  (standards, focus, calibrations)')
    print(f'  IDLE       {s["idle_min"]:>5.0f} min  '
          f'-- time that could have held another target')

    for over in plan.overruns():
        print(f'\n  NOTE: "{over["label"]}" ends {over["minutes_past_end"]:.0f} min '
              f'past {plan.night_end:%H:%M}.')


if __name__ == '__main__':
    main()
