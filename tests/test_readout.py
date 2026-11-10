"""Tests for detector readout (Milestone 3, T1.1).

Created by JXP and Claude.

LRIS 2x2: 80 s blue / 40 s red per frame (Lordrick, 2026-11-07), so 80 s
per frame. Kast slow mode: 20 s per frame. A missing value is NOT SET and
is never silently 0.
"""

import pytest

from night_planner import instrument_params as ip
from tests.lris_offline import generate_lris


def test_per_frame_readout_is_the_slower_arm():
    """LRIS 2x2 -> 80 s; Kast slow -> 20 s; an unknown binning -> None.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    assert ip.readout_seconds('lris') == 80
    assert ip.readout_seconds('kast') == 20
    assert ip.readout_seconds('lris', {'binning': '1x1'}) is None


def test_three_by_600_costs_thirty_plus_three_readouts(monkeypatch):
    """A 3 x 600 s target costs 30 + 3 x readout/60 min (patched READOUT_S).

    Inputs: monkeypatch (pytest).
    Outputs: none (asserts on success).
    """
    monkeypatch.setitem(ip.READOUT_S['lris'], '2x2', {'blue': 60, 'red': 30})
    readout = ip.readout_minutes('lris', '3 x 600', '3 x 600')
    assert 30 + readout == pytest.approx(30 + 3 * 60 / 60)


def test_dual_beam_readout_uses_the_slower_arm_wall_clock():
    """Kast red 6 x 600 + blue 3 x 1200: the red arm reads 6 frames, so it
    sets the wall clock (3600 + 120 s); readout cost is 2 min.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    assert ip.readout_minutes('kast', '6 x 600', '3 x 1200') == pytest.approx(2.0)
    # An allocation (no recipe) adds nothing; its length already includes it.
    assert ip.readout_minutes('lris', 'MOS mask required', '') == 0.0


def test_missing_readout_is_not_set_not_zero(monkeypatch):
    """With an arm missing, readout is None and the plan says NOT SET.

    Inputs: monkeypatch (pytest).
    Outputs: none (asserts on success).
    """
    from night_planner.adapters import plan_assumptions

    monkeypatch.setitem(ip.READOUT_S['lris'], '2x2', {'blue': None, 'red': 40})
    assert ip.readout_minutes('lris', '3 x 600', '3 x 600') is None
    assert plan_assumptions('lris')['readout [s per frame]'] == 'NOT SET'


def test_lris_plan_charges_readout_per_frame(monkeypatch, tmp_path):
    """In a generated LRIS plan, each longslit block is
    slew + acq + 3 x sub + 3 x 80 s; MOS blocks get no extra readout.

    Inputs: monkeypatch, tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    plan = generate_lris(monkeypatch, tmp_path)
    assert plan.schedule
    for t in plan.schedule:
        block = (t.end - t.start).total_seconds() / 60
        assert block == pytest.approx(t.slew_min + t.acq_min + t.on_target_min
                                      + t.readout_min, abs=0.01)
        if t.mode.startswith('MOS'):
            assert t.readout_min == 0
        else:
            assert t.readout_min == pytest.approx(3 * 80 / 60)
    assert plan.summary()['readout_min'] > 0
    assert plan.assumptions['readout [s per frame]'].startswith('80')
