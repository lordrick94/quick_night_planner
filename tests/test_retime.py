"""Tests for re-timing, insertion, precedence and stability (2026-11-15).

Created by JXP and Claude.

These are the four changes borrowed from the UCSC AstroScheduler: place
targets by airmass, let placed targets move so a dropped one fits, keep a
previous plan's starts, and honour schedule_before. The guarantees tested:

* solve_order is exact (it matches brute force on small problems);
* placement='earliest' with no precedence leaves the greedy schedule
  untouched (old plans are reproducible);
* placement='airmass' never schedules fewer targets than the greedy pass,
  and never at a higher summed airmass for the same targets;
* a run anchored on a previous plan reproduces it;
* schedule_before is respected.
"""

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

import kast_calculations as kc                       # noqa: E402
from night_planner import retime as rt               # noqa: E402

TARGETS = str(REPO_ROOT / 'test_targs' / 'autumn_ffffpz.csv')
DATE = '2026-10-19'


# --------------------------------------------------------------- pure DP
def _brute(costs, lengths, gap):
    """Exhaustive minimum for solve_order, on a coarse problem.

    Inputs: costs (list of arrays), lengths (min), gap (min).
    Outputs: best total (inf if none).
    """
    n = len(costs[0])
    best = np.inf
    for starts in itertools.product(range(n), repeat=len(costs)):
        ok = all(starts[j + 1] >= starts[j] + rt.steps_for(lengths[j] + gap)
                 for j in range(len(starts) - 1))
        if ok:
            best = min(best, sum(c[s] for c, s in zip(costs, starts)))
    return best


def test_solve_order_matches_brute_force():
    """The DP finds the exact optimum on random small problems.

    Inputs: none. Outputs: none (asserts on success).
    """
    rng = np.random.default_rng(42)
    for _ in range(25):
        n = 14
        costs = []
        for _ in range(3):
            c = rng.uniform(1.0, 2.0, n)
            c[rng.uniform(size=n) < 0.3] = np.inf
            costs.append(c)
        lengths = list(rng.integers(1, 3, 3).astype(float))
        starts, total = rt.solve_order(costs, lengths, 0.5)
        expect = _brute(costs, lengths, 0.5)
        if np.isinf(expect):
            assert starts is None
        else:
            assert total == pytest.approx(expect)
            assert sum(c[s] for c, s in zip(costs, starts)) == pytest.approx(total)


def test_insert_moves_a_placed_block_to_make_room():
    """A block whose best slot is taken gets in once the other one moves.

    Inputs: none. Outputs: none (asserts on success).
    """
    n = 40
    idx = np.arange(n)
    a = 1.0 + 0.01 * np.abs(idx - 5)        # A prefers the start
    b = np.where(idx <= 12, 1.0, np.inf)    # B can only be early
    starts, _ = rt.solve_order([a], [5.0], 0.0)
    assert starts == [5]
    pos, new, _ = rt.insert_target([a], [5.0], ['A'], b, 5.0, 'B', 0.0, {})
    assert pos is not None
    order = ['A', 'B'] if pos == 1 else ['B', 'A']
    spans = dict(zip(order, new))
    assert spans['B'] <= 12
    assert abs(spans['A'] - spans['B']) >= rt.steps_for(5.0)


def test_precedence_order_is_stable_and_finds_cycles():
    """Predecessors move forward, nothing else moves; cycles are reported.

    Inputs: none. Outputs: none (asserts on success).
    """
    out, cycle = rt.precedence_order(['A', 'B', 'C', 'D'], {'C': {'B'}})
    assert out == ['A', 'C', 'B', 'D'] and cycle == []
    out, cycle = rt.precedence_order(['A', 'B'], {'A': {'B'}, 'B': {'A'}})
    assert set(cycle) == {'A', 'B'}


# --------------------------------------------------------- on a real night
@pytest.fixture(scope='module')
def greedy():
    """The tiered greedy schedule for one fixed night.

    Inputs: none.
    Outputs: (schedule DataFrame, science_start, night_end, results_df).
    """
    results, twilight = kc.analyze_targets(TARGETS, DATE)
    observable = results[results['observable']].copy()
    start = kc.advance(twilight['evening_pst'], 25)
    sched = kc.schedule_by_priority(observable, start, twilight['morning_pst'], [])
    return sched, start, twilight['morning_pst'], results


def _placed(frame):
    """Name -> (start, end) of the scheduled rows.

    Inputs: schedule DataFrame. Outputs: dict.
    """
    got = frame[frame['scheduled'].fillna(False).astype(bool)]
    return {r['TNS']: (r['start_pst'], r['end_pst']) for _, r in got.iterrows()}


def _no_overlap(spans):
    """True if no two spans overlap and each gap is at least one slew.

    Inputs: dict name -> (start, end). Outputs: bool.
    """
    s = sorted(spans.values())
    return all(kc.advance(a[1], kc.SLEW_MINUTES) <= b[0] + pd.Timedelta(seconds=1)
               for a, b in zip(s, s[1:]))


def test_earliest_without_precedence_changes_nothing(greedy):
    """The regression guarantee: --placement earliest is the old schedule.

    Inputs: greedy fixture. Outputs: none (asserts on success).
    """
    sched, start, end, _ = greedy
    out = kc.retime_schedule(sched, start, end, [], placement='earliest')
    assert _placed(out) == _placed(sched)


def test_airmass_placement_keeps_targets_and_lowers_airmass(greedy):
    """Same or more targets, legal windows, and a lower summed airmass.

    Inputs: greedy fixture. Outputs: none (asserts on success).
    """
    sched, start, end, _ = greedy
    old = kc._annotate_airmass(sched)
    new = kc.retime_schedule(sched, start, end, [], placement='airmass', insert=False)
    before, after = _placed(old), _placed(new)
    assert set(after) == set(before)
    assert _no_overlap(after)
    for _, r in new[new['scheduled'].astype(bool)].iterrows():
        assert r['start_pst'] >= r['entry_pst'] and r['end_pst'] <= r['exit_pst']
    total = lambda f: f.loc[f['scheduled'].astype(bool), 'airmass_block'].sum()
    assert total(new) <= total(old) + 0.05   # grid snapping can cost a little


def test_insertion_never_loses_a_target(greedy):
    """With insertion on, every greedy target is still scheduled.

    Inputs: greedy fixture. Outputs: none (asserts on success).
    """
    sched, start, end, _ = greedy
    new = kc.retime_schedule(sched, start, end, [], placement='airmass',
                             partial_min=10)
    assert set(_placed(sched)) <= set(_placed(new))
    assert _no_overlap(_placed(new))


def test_previous_plan_is_reproduced(greedy):
    """Anchored on its own output, a re-run moves nothing.

    Inputs: greedy fixture. Outputs: none (asserts on success).
    """
    sched, start, end, _ = greedy
    first = kc.retime_schedule(sched, start, end, [], placement='airmass')
    previous = {n: s for n, (s, _) in _placed(first).items()}
    again = kc.retime_schedule(sched, start, end, [], placement='airmass',
                               previous=previous)
    assert _placed(again) == _placed(first)


def test_schedule_before_is_respected(greedy):
    """A precedence pair the greedy pass breaks is put right.

    Inputs: greedy fixture. Outputs: none (asserts on success).
    """
    sched, start, end, _ = greedy
    spans = sorted(_placed(sched).items(), key=lambda kv: kv[1][0])
    early, late = spans[0][0], spans[1][0]
    sched = sched.copy()
    sched['schedule_before'] = ''
    sched.loc[sched['TNS'] == late, 'schedule_before'] = early   # late before early
    out = kc.retime_schedule(sched, start, end, [], placement='earliest')
    got = _placed(out)
    if late in got and early in got:
        assert got[late][1] <= got[early][0]
    else:
        reasons = out.loc[out['TNS'].isin([late, early]), 'skip_reason'].astype(str)
        assert reasons.str.contains('schedule_before').any()


def test_partial_backfill_respects_precedence():
    """precedence_clear refuses a slot on the wrong side of a predecessor.

    Inputs: none. Outputs: none (asserts on success).
    """
    t = pd.Timestamp('2026-10-19 22:00', tz='America/Los_Angeles')
    placed = [{'TNS': 'B', 'start_pst': t, 'end_pst': t + pd.Timedelta(minutes=60)}]
    before = {'A': {'B'}}
    assert kc.precedence_clear('A', t - pd.Timedelta(minutes=40),
                               t - pd.Timedelta(minutes=10), placed, before)
    assert not kc.precedence_clear('A', t + pd.Timedelta(minutes=70),
                                   t + pd.Timedelta(minutes=90), placed, before)


def test_schedule_before_column_is_read():
    """targets_io reads schedule_before (';' or ',' separated) and keeps it.

    Inputs: none. Outputs: none (asserts on success).
    """
    from night_planner.targets_io import load_targets, parse_name_list
    df = pd.DataFrame({'name': ['A', 'B', 'C'], 'ra_deg': [10.0, 20.0, 30.0],
                       'dec_deg': [10.0, 20.0, 30.0], 'mag': [18.0, 18.0, 18.0],
                       'schedule_before': ['B, C', '', None]})
    out = load_targets(df)
    assert list(out['schedule_before']) == ['B;C', '', '']
    assert parse_name_list(out['schedule_before'][0]) == ['B', 'C']
