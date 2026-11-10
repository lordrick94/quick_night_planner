"""Priority tiers on the LRIS path (Milestone 8, T1.6).

Created by JXP and Claude.

The single-tier schedule is pinned by tests/snapshots/lris_single_tier.json
(recorded before the refactor with tests/snapshots/make_lris_snapshot.py),
so tiering can't silently change a night with no priorities set.
"""

import contextlib
import io
import json

import pandas as pd
import pytest

from tests.snapshots.make_lris_snapshot import CASES, OUT, run_case
from tests.lris_offline import REPO


@pytest.mark.parametrize('table,date,extra', CASES, ids=[c[0] for c in CASES])
def test_single_tier_matches_the_snapshot(table, date, extra, tmp_path):
    """With every target in one tier the LRIS schedule is exactly the one
    recorded before tiers existed.

    Inputs: table, date, extra (parametrized), tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    snap = json.loads(OUT.read_text())[f'{table}|{date}|{" ".join(extra)}']
    assert run_case(table, date, extra, tmp_path) == snap


def _with_priorities(tmp_path, table, prio):
    """Copy a test_targs table with a priority column (name -> value, else 2)."""
    df = pd.read_csv(REPO / 'test_targs' / table)
    name_col = next(c for c in df.columns if c.lower() in ('tns', 'name', 'object'))
    df['priority'] = [prio.get(n, 2.0) for n in df[name_col]]
    path = tmp_path / f'prio_{table}'
    df.to_csv(path, index=False)
    return path


def _lris(path, out, date='2026-10-15'):
    from night_planner.cli import generate_plan
    with contextlib.redirect_stdout(io.StringIO()):
        return generate_plan('lris', ['--targets-csv', str(path), '--output-dir',
                                      str(out), '--date', date])


TABLE = 'allsky_mixed.csv'


def test_a_promoted_lris_target_is_no_longer_bumped(tmp_path):
    """A target the single-tier pass drops is scheduled once it is the only
    priority-1 target.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    table = 'autumn_ffffpz.csv'   # oversubscribed on LRIS on this date
    base = _lris(REPO / 'test_targs' / table, tmp_path / 'base')
    import re
    bumped = [(int(m.group(1)), d.name) for d in base.decisions
              if d.status == 'rejected' and d.stage == '3. Scheduling'
              for m in [re.search(r'needs (\d+) min', d.reason)] if m]
    assert bumped, 'fixture must be oversubscribed for this to mean anything'
    # One that fits when it's alone, so it was squeezed out by the others,
    # not by its own length or window (a 360 min target, or one whose window
    # closes at dusk, never fits whatever its priority).
    df = pd.read_csv(REPO / 'test_targs' / table)
    name_col = next(c for c in df.columns if c.lower() in ('tns', 'name', 'object'))
    hero = None
    for _, name in sorted(bumped):
        solo = tmp_path / f'solo_{name}.csv'
        df[df[name_col] == name].to_csv(solo, index=False)
        if _lris(solo, tmp_path / f'solo_{name}').schedule:
            hero = name
            break
    assert hero, 'need a bumped target that is schedulable on its own'
    tiered = _lris(_with_priorities(tmp_path, table, {hero: 1.0}), tmp_path / 't')
    assert hero in {t.name for t in tiered.schedule}
    # P1 is the default tier and stays unlabelled; the others say P2.
    others = [d for d in tiered.decisions if d.name != hero and d.priority == 2.0]
    assert others and all(d.reason.startswith('P2 --') for d in others)


def test_tier_one_is_scheduled_as_if_alone(tmp_path):
    """Lower tiers never move a higher one: the P1 targets sit exactly where
    a plan of the P1 targets alone puts them.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    base = _lris(REPO / 'test_targs' / TABLE, tmp_path / 'base')
    top = {t.name: 1.0 for t in base.schedule[: len(base.schedule) // 2]}
    tiered = _lris(_with_priorities(tmp_path, TABLE, top), tmp_path / 't')

    alone_df = pd.read_csv(_with_priorities(tmp_path, TABLE, top))
    alone_df = alone_df[alone_df['priority'] == 1.0]
    alone_path = tmp_path / 'alone.csv'
    alone_df.to_csv(alone_path, index=False)
    alone = _lris(alone_path, tmp_path / 'alone')

    got = {t.name: t.science_start for t in tiered.schedule if t.name in top}
    want = {t.name: t.science_start for t in alone.schedule}
    assert got == want
    assert len(tiered.schedule) > len(alone.schedule), 'P2 should fill some gaps'


def test_inserted_targets_respect_the_exact_slew(tmp_path):
    """After tier insertion, each target's slew is the Keck rule from the
    target actually before it, acquisition fits, and nothing overlaps.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    from keck_overheads import keck_acquisition_minutes, keck_slew_minutes
    import keck_2026oct06_calculations as keck

    base = _lris(REPO / 'test_targs' / TABLE, tmp_path / 'base')
    top = {t.name: 1.0 for t in base.schedule[::2]}
    plan = _lris(_with_priorities(tmp_path, TABLE, top), tmp_path / 't')
    seq = sorted(plan.schedule, key=lambda t: t.start)
    prev_dec, prev_end = keck.EVENING_STANDARD_DEC, None
    for t in seq:
        assert t.slew_min == keck_slew_minutes(prev_dec, t.dec_deg), t.name
        assert t.acq_min == keck_acquisition_minutes(t.mode)
        pre = (t.science_start - t.start).total_seconds() / 60
        assert pre == pytest.approx(t.slew_min + t.acq_min)
        if prev_end is not None:
            assert t.start >= prev_end, f'{t.name} overlaps the target before it'
        prev_dec, prev_end = t.dec_deg, t.end
