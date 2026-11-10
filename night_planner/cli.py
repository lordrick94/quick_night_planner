"""
`night-planner` console command: a single installed entry point that
dispatches to the right instrument's calculation/build scripts, instead of
running `python scripts/<whatever>.py` directly from inside the repo.

Dispatch is by `--instrument` alone (e.g. `lris`, `kast`) -- this project
never has two telescopes sharing one instrument name, so the instrument
name alone is enough to pick the telescope too; no separate `--telescope`
flag is needed.

Each instrument's actual scheduling logic still lives in scripts/ as its
own module (this is a thin dispatcher, not a rewrite of that logic) --
see scripts/night_plan_io.py and scripts/schedule_overrides.py for the
shared pieces (JSON config, manual start override, blocked windows) every
instrument module uses.

Created by JXP and Claude
"""

import argparse
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / 'scripts'

# instrument -> {command: module_name or None if not wired yet}.
#
# `supports` lists the generate options that instrument's pipeline actually
# accepts. The Keck script takes a target table, date and output directory;
# the Lick night-2 script is still hardcoded to its own run, so handing it
# those flags fails deep inside argparse with an unreadable error. Callers
# should check this first and say so plainly.
INSTRUMENTS = {
    'lris': {
        'calc': 'keck_2026oct06_calculations',
        'build': 'build_keck_night_plan',
        'supports': {'targets_csv', 'output_dir', 'date', 'start', 'blocks',
                     'forced', 'max_targets', 'assume_masks', 'config',
                     'seeing', 'mag_band', 'airmass_rule', 'etc', 'target_sn'},
    },
    'kast': {
        'calc': 'kast_calculations',
        'build': None,  # no Excel builder for the general Lick path yet
        'supports': {'targets_csv', 'output_dir', 'date', 'start', 'blocks',
                     'forced', 'max_targets', 'no_partials', 'config',
                     'seeing', 'mag_band', 'airmass_rule', 'etc', 'target_sn'},
    },
}


def _load_module(name):
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    return importlib.import_module(name)


def generate_plan(instrument, argv=None):
    """
    Run an instrument's calculation pipeline and return a normalized PlanResult.

    This is the entry point the GUI backend uses: one call per "Generate
    plan" click, giving back one instrument-independent object regardless
    of which scheduler actually ran. Side effects are unchanged -- the
    CSVs, starlist, and night_meta.json still land in the output
    directory exactly as the CLI writes them.

    Parameters
    ----------
    instrument : str
        Key into INSTRUMENTS, e.g. 'lris' or 'kast'.
    argv : list of str, optional
        Flags for that instrument's own parser (--config, --start,
        --block, ...), as the CLI would pass them.

    Returns
    -------
    night_planner.plan_result.PlanResult
    """
    mod = _load_module(INSTRUMENTS[instrument]['calc'])
    argv = list(argv or [])
    out = mod.run(mod.parse_args(argv))
    return _persist(instrument, out, argv)


def _persist(instrument, out, argv):
    """
    Normalize a pipeline run and save it beside the plan's other files.

    Returns
    -------
    PlanResult
    """
    from .adapters import ADAPTERS
    from .plan_store import save_plan

    plan = ADAPTERS[instrument](out)
    plan.request = {'instrument': instrument, 'argv': list(argv)}
    save_plan(plan)
    return plan


def _serve(args):
    """Launch the viewer with uvicorn, from the repo root."""
    import subprocess

    print(f'night-planner viewer -> http://{args.host}:{args.port}')
    cmd = [sys.executable, '-m', 'uvicorn', 'backend.app:app',
           '--host', args.host, '--port', str(args.port)]
    if args.reload:
        cmd.append('--reload')
    return subprocess.call(cmd, cwd=str(REPO_ROOT))


def _report(args):
    """
    Write the observing report from a saved plan and its observing log.

    Parameters
    ----------
    args : argparse.Namespace with plan_dir, survey, resource.

    Returns
    -------
    int : exit code (1 if the directory has no plan).
    """
    import os

    from .adapters import SITES
    from .observing_log import open_log
    from .observing_report import write_report
    from .plan_store import load_plan

    plan_dir = os.path.abspath(args.plan_dir)
    plan = load_plan(plan_dir)
    if plan is None:
        print(f'no plan_result.json in {plan_dir}', file=sys.stderr)
        return 1
    plan.output_dir = plan_dir
    log = open_log(plan, plan_dir)
    out = write_report(plan, log, SITES.get(plan.instrument, {}).get('location'),
                       survey=args.survey, resource=args.resource)
    print(f"Wrote {out['markdown_path']}")
    print(f"Wrote {out['csv_path']}")
    for line in out['warnings']:
        print(f'  WARNING: {line}')
    for line in out['notes']:
        print(f'  NOTE: {line}')
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv

    parser = argparse.ArgumentParser(
        prog='night-planner',
        description='Generate and rebuild observing night plans. Each '
                     'subcommand forwards its remaining flags (--config, '
                     '--start, --block, ...) straight to the chosen '
                     "instrument's own module -- run with --help after "
                     '--instrument is chosen to see that module\'s full flag '
                     'list, e.g. `night-planner calc --instrument lris --help`.')
    sub = parser.add_subparsers(dest='command', required=True)

    for cmd, help_text in [('calc', 'Run target analysis + scheduling.'),
                            ('build', 'Build the Excel night plan from an '
                                      'already-scheduled selected_targets.csv.')]:
        sp = sub.add_parser(cmd, help=help_text, add_help=False)
        sp.add_argument('--instrument', required=True, choices=sorted(INSTRUMENTS),
                         help='Instrument name selects the telescope too -- '
                              'lris = Keck I, kast = Shane 3m (Lick).')

    report = sub.add_parser('report', help='Write the observing report (.md) '
                                           'and FFFF-PZ CSV from a plan\'s '
                                           'observing log.')
    report.add_argument('--plan-dir', required=True)
    report.add_argument('--survey', default='CHIME/FRB')
    report.add_argument('--resource', help='FFFF-PZ Resource [plan directory name].')

    serve = sub.add_parser('serve', help='Run the night-plan viewer (web UI).')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8020)
    serve.add_argument('--reload', action='store_true')

    args, remaining = parser.parse_known_args(argv)

    if args.command == 'serve':
        return _serve(args)
    if args.command == 'report':
        return _report(args)

    module_name = INSTRUMENTS[args.instrument][args.command]
    if module_name is None:
        print(f"'{args.command}' isn't wired up for instrument "
              f"'{args.instrument}' yet -- run its script directly for now.",
              file=sys.stderr)
        return 1

    mod = _load_module(module_name)
    # Re-inject '--help' if the user asked for it after --instrument, so it
    # reaches the instrument module's own parser (not this dispatcher's).
    inner_args = mod.parse_args(remaining)
    out = mod.run(inner_args)

    # Persist the normalized plan here too, not only on the API path --
    # otherwise a CLI run leaves a stale plan_result.json next to freshly
    # written CSVs, and the viewer shows a different night than the files.
    if args.command == 'calc':
        _persist(args.instrument, out, remaining)
    return 0


if __name__ == '__main__':
    sys.exit(main())
