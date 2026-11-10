"""Tests for the slew + acquisition model (Milestone 2, T1.2 / T1.4).

Created by JXP and Claude.

Keck: 5 min base slew, 14 min for a S->N Dec +20 crossing, acquisition
5 min longslit / 10 min mask. Lick: 2 min slew + 3 min acquisition. The
totals must reconcile on both paths: on target + slew + acquisition +
readout + overheads + blocked + idle = night. Nothing here touches the network (the
Kast path uses the empirical exposure rule).
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

from keck_overheads import (keck_acquisition_minutes, keck_slew_minutes,  # noqa: E402
                            keck_slew_reason)
from night_planner.instrument_params import (LICK_ACQ_MIN, LICK_SLEW_MIN,  # noqa: E402
                                             lick_gap_minutes)
from night_planner.plan_result import PlanResult, ScheduledTarget, SunEvents  # noqa: E402

HST = ZoneInfo('Pacific/Honolulu')


def _reconcile(plan):
    """Sum every category of the night; return (accounted, night) minutes."""
    s = plan.summary()
    blocked = sum((b[1] - b[0]).total_seconds() / 60 for b in plan.blocks)
    accounted = (s['on_target_min'] + s['slew_min'] + s['acq_min']
                 + s['readout_min'] + s['overhead_min'] + blocked + s['idle_min'])
    return accounted, s['night_min']


def test_keck_slew_rule():
    """S->N across +20 deg costs 14 min; everything else the 5 min base.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    assert keck_slew_minutes(10, 30) == 14
    assert keck_slew_minutes(30, 10) == 5
    assert keck_slew_minutes(None, 30) == 5
    assert 'crossing' in keck_slew_reason(10, 30)
    assert keck_slew_reason(30, 10) == ''


def test_keck_acquisition_by_mode():
    """Masks take 10 min to acquire; longslit (forced or not) 5 min.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    assert keck_acquisition_minutes('MOS (mask required)') == 10
    assert keck_acquisition_minutes('longslit') == 5
    assert keck_acquisition_minutes('longslit (forced, no mask)') == 5


def test_mos_buffer_is_kept():
    """Q7 (Lordrick): the +5 min per-mask buffer stays, on top of the
    10 min mask acquisition.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    import keck_2026oct06_calculations as keck
    assert keck.MOS_MASK_BUFFER_MIN == 5


def test_lick_gap_is_two_plus_three():
    """Lick per-target overhead: 2 min slew + 3 min acquisition = 5 min.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    assert (LICK_SLEW_MIN, LICK_ACQ_MIN, lick_gap_minutes()) == (2, 3, 5)


def test_two_target_keck_plan_reconciles_to_the_minute():
    """A synthetic two-target LRIS plan: on target + slew + acq + overheads
    + idle = night, exactly.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    start = datetime(2026, 10, 6, 19, 0, tzinfo=HST)
    end = datetime(2026, 10, 7, 5, 0, tzinfo=HST)

    def target(name, t0, slew, acq, sci, mode='longslit'):
        sci_start = t0 + timedelta(minutes=slew + acq)
        return ScheduledTarget(name=name, ra_deg=0, dec_deg=0, mag=20, mode=mode,
                               start=t0, science_start=sci_start,
                               end=sci_start + timedelta(minutes=sci),
                               slew_min=slew, acq_min=acq, on_target_min=sci)

    a = target('A', start + timedelta(minutes=10), 5, 5, 40)
    b = target('B', a.end, 14, 10, 65, mode='MOS (mask required)')
    plan = PlanResult(
        instrument='lris', telescope='Keck I', date='2026-10-06',
        output_dir='/tmp', timezone=str(HST), sun=SunEvents(*[start] * 6),
        night_start=start, night_end=end, schedule=[a, b],
        overheads=[(start, start + timedelta(minutes=10), 'Evening standard')])
    accounted, night = _reconcile(plan)
    assert accounted == pytest.approx(night, abs=1e-9)
    assert plan.summary()['acq_min'] == 15


def test_old_plan_without_acq_still_loads():
    """A plan_result.json written before acq_min/slew_reason existed loads,
    with both defaulted.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    start = datetime(2026, 10, 6, 19, 0, tzinfo=HST)
    plan = PlanResult(
        instrument='lris', telescope='Keck I', date='2026-10-06',
        output_dir='/tmp', timezone=str(HST), sun=SunEvents(*[start] * 6),
        night_start=start, night_end=start + timedelta(hours=10),
        schedule=[ScheduledTarget(name='A', ra_deg=0, dec_deg=0, mag=20,
                                  mode='longslit', start=start,
                                  science_start=start, end=start + timedelta(hours=1))])
    data = plan.to_dict()
    for t in data['schedule']:
        del t['acq_min'], t['slew_reason']
    again = PlanResult.from_dict(data)
    assert again.schedule[0].acq_min == 0.0 and again.schedule[0].slew_reason == ''


@pytest.fixture(scope='module')
def kast_plan(tmp_path_factory):
    """A real Kast plan from the autumn synthetic table (no network)."""
    from night_planner.cli import generate_plan

    out = tmp_path_factory.mktemp('kast_plan')
    return generate_plan('kast', ['--targets-csv', str(REPO / 'test_targs' / 'autumn_ffffpz.csv'),
                                  '--output-dir', str(out), '--date', '2026-10-15'])


def test_kast_plan_splits_each_gap_into_slew_and_acquisition(kast_plan):
    """Every Kast target with room before it gets 2 min slew + 3 min acq,
    and the first one starts after focus + standard + one gap.

    Inputs: kast_plan (fixture).
    Outputs: none (asserts on success).
    """
    assert kast_plan.schedule, 'autumn table should schedule something on 2026-10-15'
    labels = [o[2] for o in kast_plan.overheads]
    assert labels == ['Focus', 'Evening standard']
    first = min(kast_plan.schedule, key=lambda t: t.start)
    assert first.start >= kast_plan.overheads[-1][1]
    for t in kast_plan.schedule:
        if t.slew_min:
            assert (t.slew_min, t.acq_min) == (2.0, 3.0)
            assert (t.science_start - t.start).total_seconds() / 60 == pytest.approx(5)


def test_kast_plan_reconciles(kast_plan):
    """Kast totals add up to the night, focus and standard included.

    Inputs: kast_plan (fixture).
    Outputs: none (asserts on success).
    """
    accounted, night = _reconcile(kast_plan)
    assert accounted == pytest.approx(night, abs=0.01)
