"""Run the real LRIS pipeline in tests.

Created by JXP and Claude.

The network is already blocked and the UCO ETC faked for every test, by
tests/conftest.py. This module just drives the pipeline the way the
backend does.
"""

import contextlib
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO / 'scripts') not in sys.path:
    sys.path.insert(0, str(REPO / 'scripts'))


def generate_lris(monkeypatch, out_dir, table='autumn_ffffpz.csv',
                  date='2026-10-15', extra=()):
    """
    Generate a real LRIS plan from a test_targs/ table (faked ETC).

    Parameters
    ----------
    monkeypatch : pytest MonkeyPatch
        Unused; kept so existing callers needn't change.
    out_dir : path
    table : str
        A file in test_targs/.
    date : str
    extra : iterable of str
        More flags for the LRIS parser.

    Returns
    -------
    PlanResult
    """
    from night_planner.cli import generate_plan

    with contextlib.redirect_stdout(io.StringIO()):
        return generate_plan('lris', ['--targets-csv', str(REPO / 'test_targs' / table),
                                      '--output-dir', str(out_dir),
                                      '--date', date, *extra])
