"""Make a plan's finder charts and starlist from the command line.

Created by JXP and Claude, 2026-11-10.

The same steps as the viewer's Finders and Starlist pages, without the
server: finder charts (image + offset star + slit, with PA and, at the
Shane, the Cass tub readout), the slit report, and a starlist in the
site's dialect.

Usage
-----
    python scripts/make_finders.py PLAN_DIR [--slit-mode candidates]
        [--overwrite] [--no-standards] [--starlist-name NAME]

Inputs
------
PLAN_DIR : a plan directory with plan_result.json
--slit-mode : 'parallactic' (default) or 'candidates' (slit through both
    PATH candidates for FFFF-PZ targets; every other target stays at
    parallactic and is listed as having fallen back)
--overwrite : redraw charts that already exist
--no-standards : leave the flux standards out of the starlist
--starlist-name : default <plan>_generated.starlist, as the viewer writes

Outputs
-------
<PLAN_DIR>/finders/<target>_finder.png and .json, finders/slit_report.txt,
and the starlist in PLAN_DIR. Prints one line per target (PA, TUB, image
source, offset star) and the starlist notes.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from night_planner.adapters import SITES  # noqa: E402
from night_planner.finder import (generate_for_plan, slit_report,  # noqa: E402
                                  write_slit_report)
from night_planner.plan_store import load_plan  # noqa: E402
from night_planner.starlist import build_starlist  # noqa: E402


def plan_targets_csv(plan):
    """
    The target table a plan was generated from (its --targets-csv).

    Inputs: plan (PlanResult).
    Outputs: str path, or None when the plan did not record one.
    """
    argv = (plan.request or {}).get('argv') or []
    for flag, value in zip(argv, argv[1:]):
        if flag == '--targets-csv':
            return value
    return None


def describe(entry):
    """
    One printed line for a finder result.

    Inputs: entry (dict from generate_for_plan).
    Outputs: str.
    """
    if entry.get('error'):
        return f"{entry['name']:<16} FAILED: {entry['error']}"
    tub = entry.get('cass_tub')
    tub_txt = (f"TUB {tub['tub']:7.2f} (or {tub['alt_tub']:.2f})" if tub else '')
    star = (f"offset star {entry.get('offset_star_band', 'G')}="
            f"{entry['offset_star_mag']:.1f} "
            f"{entry['offset_star_offset']:.0f}\" away ({entry.get('offset_star_catalog', '')})"
            if entry.get('offset_star_ra') is not None
            else f"NO offset star{': ' + entry['offset_star_error'][:60] if entry.get('offset_star_error') else ''}")
    mode = entry.get('slit_mode', '')
    if mode == 'candidates':
        mode += f" ({entry.get('pa_vs_parallactic', 0):.0f} deg off parallactic)"
    return (f"{entry['name']:<16} PA {entry['slit_pa']:6.1f}  {tub_txt}  {mode}; "
            f"{star}; image: {entry.get('image_source', entry.get('skipped', '?'))}")


def main(argv=None):
    """
    Parse arguments, make the charts, the slit report and the starlist.

    Inputs: argv (list of str, optional; default sys.argv).
    Outputs: exit code (0 when every chart was drawn).
    """
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('plan_dir')
    p.add_argument('--slit-mode', choices=('parallactic', 'candidates'),
                   default='parallactic')
    p.add_argument('--overwrite', action='store_true')
    p.add_argument('--no-standards', action='store_true')
    p.add_argument('--starlist-name')
    args = p.parse_args(argv)

    plan = load_plan(args.plan_dir)
    if plan is None:
        raise SystemExit(f'no plan_result.json in {args.plan_dir}')
    site = SITES[plan.instrument]
    base = Path(args.plan_dir)
    finder_dir = base / 'finders'
    targets_csv = plan_targets_csv(plan)
    if args.slit_mode == 'candidates' and not targets_csv:
        raise SystemExit('this plan does not record its target table, so the '
                         'second candidates cannot be read')

    def progress(done, total, name):
        if name is not None:
            print(f'  [{done + 1}/{total}] {name} ...', flush=True)

    results = generate_for_plan(
        plan, site['location'], finder_dir, overwrite=args.overwrite,
        slit_length_arcmin=site.get('slit_length_arcmin', 2.9),
        slit_width_arcsec=site.get('slit_width_arcsec', 1.0),
        targets_csv=targets_csv, slit_mode=args.slit_mode,
        rotator=site.get('rotator'), progress=progress)
    report = slit_report(results, args.slit_mode)
    write_slit_report(finder_dir, plan, report)
    print()
    for entry in results:
        print(describe(entry))
    if report['fell_back']:
        print('\nparallactic (no second candidate): ' + ', '.join(report['fell_back']))

    library = None
    if not args.no_standards:
        from night_planner.standards import load_library
        library = load_library()
    text, notes = build_starlist(
        plan, include_standards=not args.no_standards,
        location=site['location'], library=library, finder_dir=finder_dir,
        style=site.get('starlist_style', 'keck'))
    name = args.starlist_name or f'{base.name}_generated.starlist'
    (base / name).write_text(text)
    print(f'\nwrote {base / name}')
    for note in notes:
        print(f'  note: {note}')
    return 0 if not any(e.get('error') for e in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
