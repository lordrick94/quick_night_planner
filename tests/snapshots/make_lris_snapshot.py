"""Record the single-tier LRIS schedule the M8 refactor must not change.

Created by JXP and Claude.

Runs the real LRIS pipeline on fixed test_targs/ tables and dates, with the
network blocked and the same fake ETC the test suite uses
(tests/conftest.fake_query), and writes the placements to
tests/snapshots/lris_single_tier.json. Rerun only on purpose, when a
schedule change is intended:

    python tests/snapshots/make_lris_snapshot.py
"""

import contextlib
import io
import json
import socket
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'scripts'))

CASES = [
    ('autumn_ffffpz.csv', '2026-10-15', []),
    ('allsky_mixed.csv', '2026-10-15', []),
    ('faint_mos_split.csv', '2026-10-15', ['--assume-masks']),
]
OUT = Path(__file__).with_name('lris_single_tier.json')


def placements(plan):
    """The parts of a schedule the snapshot pins down."""
    return [{'name': t.name, 'start': t.start.isoformat(),
             'science_start': t.science_start.isoformat(), 'end': t.end.isoformat(),
             'slew_min': t.slew_min, 'acq_min': t.acq_min,
             'on_target_min': round(t.on_target_min, 3)}
            for t in sorted(plan.schedule, key=lambda t: t.start)]


def run_case(table, date, extra, out_dir):
    """Generate one case offline; return its placements."""
    from night_planner.cli import generate_plan
    with contextlib.redirect_stdout(io.StringIO()):
        plan = generate_plan('lris', ['--targets-csv', str(REPO / 'test_targs' / table),
                                      '--output-dir', str(out_dir), '--date', date,
                                      *extra])
    return placements(plan)


def main(tmp_dir):
    from night_planner import etc
    from tests.conftest import fake_query

    def _no_network(*a, **k):
        raise RuntimeError('no network while snapshotting')
    socket.socket.connect = _no_network
    etc.query_uco_etc = fake_query
    snap = {f'{t}|{d}|{" ".join(x)}': run_case(t, d, x, Path(tmp_dir) / t)
            for t, d, x in CASES}
    OUT.write_text(json.dumps(snap, indent=1))
    print(f'wrote {OUT}: ' + ', '.join(f'{k} ({len(v)})' for k, v in snap.items()))


if __name__ == '__main__':
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        main(d)
