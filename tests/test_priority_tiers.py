"""Tests for priority-tiered scheduling on the Lick/Kast path.

Created by JXP and Claude.

The guarantee that matters most here is the negative one: with every
target at the default priority the tier loop must reduce to the single
`schedule_greedy` call it replaced, so adding this feature cannot have
changed any night anyone has already planned.

The positive one is the reason the feature exists -- a target the greedy
earliest-window-close-first pass bumps (the TGT0456 case recorded in
context/claudes_brain.md v0.37/v0.38) must survive once it outranks the
targets that were crowding it out.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

import kast_calculations as kc                       # noqa: E402
from lick_2026b02_night2_calculations import schedule_greedy   # noqa: E402

TARGETS = str(REPO_ROOT / 'test_targs' / 'autumn_ffffpz.csv')
DATE = '2026-10-19'


@pytest.fixture(scope='module')
def night():
    """Observable targets and the night's bounds for one fixed date.

    Inputs: none.
    Outputs: (observable DataFrame, science_start, night_end).
    """
    results, twilight = kc.analyze_targets(TARGETS, DATE)
    observable = results[results['observable']].copy()
    science_start = kc.advance(twilight['evening_pst'], 20)
    return observable, science_start, twilight['morning_pst']


def _scheduled(frame):
    """Name/start/end of the scheduled rows, in a comparable form.

    Inputs: a schedule DataFrame.
    Outputs: a DataFrame indexed from zero.
    """
    got = frame[frame['scheduled'].fillna(False).astype(bool)]
    return (got[['TNS', 'start_pst', 'end_pst']]
            .sort_values('start_pst').reset_index(drop=True))


def test_one_tier_is_identical_to_the_plain_greedy_pass(night):
    """The regression guarantee: no priorities set changes nothing.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    observable, start, end = night
    assert observable['priority'].nunique() == 1

    # Same per-target gap and readout as the Kast path passes (2026-11-07).
    baseline, _ = schedule_greedy(observable, start, end, blocks=[],
                                  slew_min=kc.SLEW_MINUTES,
                                  readout=kc.kast_readout)
    tiered = kc.schedule_by_priority(observable, start, end, [])

    assert _scheduled(tiered).equals(_scheduled(baseline))


def test_a_promoted_target_is_no_longer_bumped(night):
    """A target the greedy pass drops survives once it outranks the rest.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    observable, start, end = night
    baseline = kc.schedule_by_priority(observable, start, end, [])
    bumped = sorted(set(observable['TNS']) - set(_scheduled(baseline)['TNS']))
    assert bumped, 'fixture must be oversubscribed for this test to mean anything'

    victim = bumped[0]
    promoted = observable.copy()
    promoted['priority'] = 2.0
    promoted.loc[promoted['TNS'] == victim, 'priority'] = 1.0

    tiered = kc.schedule_by_priority(promoted, start, end, [])
    assert victim in set(_scheduled(tiered)['TNS'])


def test_a_lower_tier_never_displaces_a_higher_one(night):
    """Whatever the top tier wins, it keeps -- lower tiers only fill gaps.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    observable, start, end = night
    names = sorted(observable['TNS'])
    top, rest = set(names[:3]), set(names[3:])

    tiers = observable.copy()
    tiers['priority'] = [1.0 if n in top else 2.0 for n in tiers['TNS']]

    # What the top tier achieves with the whole night to itself.
    alone = kc.schedule_by_priority(
        tiers[tiers['TNS'].isin(top)], start, end, [])
    together = kc.schedule_by_priority(tiers, start, end, [])

    kept = _scheduled(together)
    assert set(_scheduled(alone)['TNS']) <= set(kept['TNS'])
    # And the lower tier did get a look in, rather than the pool being ignored.
    assert set(kept['TNS']) & rest


def test_every_target_gets_exactly_one_row(night):
    """A target that misses several gaps is still one decision, not four.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    observable, start, end = night
    tiers = observable.copy()
    tiers['priority'] = [1.0 if i < 2 else 2.0 for i in range(len(tiers))]

    out = kc.schedule_by_priority(tiers, start, end, [])
    assert out['TNS'].value_counts().max() == 1
    assert set(out['TNS']) == set(observable['TNS'])


def test_free_gaps_covers_both_edges_and_buffers_for_slew():
    """Time before the first target and after the last is fillable too.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    from datetime import datetime, timedelta, timezone

    pst = timezone(timedelta(hours=-8))
    night_start = datetime(2026, 10, 19, 19, 0, tzinfo=pst)
    night_end = datetime(2026, 10, 20, 5, 0, tzinfo=pst)
    placements = [
        {'start_pst': datetime(2026, 10, 19, 21, 0, tzinfo=pst),
         'end_pst': datetime(2026, 10, 19, 22, 0, tzinfo=pst)},
        {'start_pst': datetime(2026, 10, 20, 1, 0, tzinfo=pst),
         'end_pst': datetime(2026, 10, 20, 2, 0, tzinfo=pst)},
    ]

    gaps = kc.free_gaps(placements, night_start, night_end)
    assert len(gaps) == 3
    # Leading edge, shortened by one slew before the first target.
    assert gaps[0][0] == night_start
    assert gaps[0][1] == datetime(2026, 10, 19, 20, 55, tzinfo=pst)
    # The hole in the middle, buffered on both sides.
    assert gaps[1] == (datetime(2026, 10, 19, 22, 5, tzinfo=pst),
                       datetime(2026, 10, 20, 0, 55, tzinfo=pst))
    # Trailing edge, out to the end of the night.
    assert gaps[2] == (datetime(2026, 10, 20, 2, 5, tzinfo=pst), night_end)


def test_free_gaps_does_not_invent_a_gap_between_overlapping_blocks():
    """A reservation sitting across another placement must not create one.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    from datetime import datetime, timedelta, timezone

    pst = timezone(timedelta(hours=-8))
    night_start = datetime(2026, 10, 19, 19, 0, tzinfo=pst)
    night_end = datetime(2026, 10, 19, 23, 0, tzinfo=pst)
    placements = [
        {'start_pst': datetime(2026, 10, 19, 20, 0, tzinfo=pst),
         'end_pst': datetime(2026, 10, 19, 22, 0, tzinfo=pst)},
        {'start_pst': datetime(2026, 10, 19, 20, 30, tzinfo=pst),
         'end_pst': datetime(2026, 10, 19, 21, 0, tzinfo=pst)},
    ]

    gaps = kc.free_gaps(placements, night_start, night_end)
    for start, end in gaps:
        assert end > start
    assert all(end <= datetime(2026, 10, 19, 19, 55, tzinfo=pst)
               or start >= datetime(2026, 10, 19, 22, 5, tzinfo=pst)
               for start, end in gaps)


def test_partials_backfill_idle_time_and_are_labelled(night):
    """A target dropped for want of time is put in anyway, and marked.

    The label is the whole contract here: a truncated spectrum is only
    acceptable because the observer can see it is truncated and drop it.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    observable, start, end = night
    tiered = kc.schedule_by_priority(observable, start, end, [])
    before = set(_scheduled(tiered)['TNS'])

    filled = kc.backfill_partials(tiered, start, end, [])
    after = _scheduled(filled)
    added = set(after['TNS']) - before
    assert added, 'the fixture must leave a fillable gap for this to mean anything'

    for name in added:
        row = filled[filled['TNS'] == name].iloc[0]
        assert str(row['skip_reason']).startswith('PARTIAL')
        assert row['duration_min'] >= kc.MIN_PARTIAL_MINUTES


def test_partials_never_displace_a_full_exposure(night):
    """Backfilling only uses leftover time; nothing already placed moves.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    observable, start, end = night
    tiered = kc.schedule_by_priority(observable, start, end, [])
    before = _scheduled(tiered).set_index('TNS')

    after = _scheduled(kc.backfill_partials(tiered, start, end, []))
    after = after.set_index('TNS')

    for name, row in before.iterrows():
        assert after.loc[name, 'start_pst'] == row['start_pst']
        assert after.loc[name, 'end_pst'] == row['end_pst']


def test_partials_stay_inside_their_own_ha_window(night):
    """Truncating does not excuse pointing the mount where it cannot go.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    observable, start, end = night
    filled = kc.backfill_partials(
        kc.schedule_by_priority(observable, start, end, []), start, end, [])

    for _, row in filled.iterrows():
        if not str(row.get('skip_reason', '')).startswith('PARTIAL'):
            continue
        assert row['start_pst'] >= row['entry_pst']
        assert row['end_pst'] <= row['exit_pst']


def test_min_partial_floor_is_respected(night):
    """A floor of a full night's length places nothing at all.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    observable, start, end = night
    tiered = kc.schedule_by_priority(observable, start, end, [])
    filled = kc.backfill_partials(tiered, start, end, [], min_minutes=10_000)
    assert set(_scheduled(filled)['TNS']) == set(_scheduled(tiered)['TNS'])


def test_partials_leave_unobservable_targets_alone(night):
    """No amount of truncation fixes a target that is never up.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    import pandas as pd

    observable, start, end = night
    tiered = kc.schedule_by_priority(observable, start, end, [])
    # A target with no window at all, as analyze_targets reports one.
    never = dict(tiered.iloc[0], TNS='NEVER_UP', scheduled=False,
                 observable=False, entry_pst=pd.NaT, exit_pst=pd.NaT,
                 skip_reason='Dec too high')
    frame = pd.concat([tiered, pd.DataFrame([never])], ignore_index=True)

    filled = kc.backfill_partials(frame, start, end, [])
    assert 'NEVER_UP' not in set(_scheduled(filled)['TNS'])
