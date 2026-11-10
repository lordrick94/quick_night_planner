"""Tests for the pluggable ETC, exposures at the scheduled airmass and the
S/N diagnostics (Milestone 5: T1.3, T3.4).

Created by JXP and Claude.

The UCO ETC is faked by tests/conftest.py (S/N ~ sqrt(t), worse at higher
airmass), except in the one test marked `network`.
"""

import json
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from night_planner import etc
from night_planner.sky import block_airmass
from tests.lris_offline import REPO, generate_lris


def test_block_airmass_rules_are_ordered():
    """Over a span where a target is setting: best <= mid <= worst.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    from night_planner.adapters import SITES

    hst = ZoneInfo('Pacific/Honolulu')
    t0 = datetime(2026, 10, 15, 21, 0, tzinfo=hst)
    t1 = t0 + timedelta(hours=1.5)
    args = (300.0, 20.0, t0, t1)
    loc = SITES['lris']['location']
    best = block_airmass(*args, 'best', loc)
    mid = block_airmass(*args, 'mid', loc)
    worst = block_airmass(*args, 'worst', loc)
    assert best <= mid <= worst
    with pytest.raises(ValueError):
        block_airmass(*args, 'median', loc)


def test_combined_sn_is_root_n_times_per_sub():
    """sn_combined = sqrt(n_sub) x sn_sub, per arm.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    e = etc.exposure('lris', 20.0, 'r', 1.2, 0.8, {}, 10.0, 3)
    for arm in ('blue', 'red'):
        assert e['sn_combined'][arm] == pytest.approx(math.sqrt(3) * e['sn_sub'][arm],
                                                      abs=0.02)
    assert e['sn_sub']['red'] >= 10.0 * 0.95
    assert e['red_exp'] == f"3 x {e['sub_len_s']}"


def test_higher_airmass_needs_longer_exposures():
    """The (faked) ETC asks for more time at higher airmass.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    low = etc.exposure('lris', 20.5, 'r', 1.05, 0.8, {}, 10.0, 3)
    high = etc.exposure('lris', 20.5, 'r', 1.8, 0.8, {}, 10.0, 3)
    assert high['science_min'] > low['science_min']


def test_load_etc_accepts_registry_names_and_user_functions():
    """Registry names and 'package.module:function' both load.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    from tests import fake_etc

    assert etc.load_etc('kast') is etc.kast_etc
    assert etc.load_etc('tests.fake_etc:etc') is fake_etc.etc
    with pytest.raises(ValueError):
        etc.load_etc('nope')


def test_worst_airmass_rule_never_gives_shorter_exposures(monkeypatch, tmp_path):
    """Same targets, --airmass-rule worst vs best: worst is never shorter,
    and is longer for at least one target; the plan records the airmass
    actually used, which is never below the night's best.

    Inputs: monkeypatch, tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    worst = generate_lris(monkeypatch, tmp_path / 'w', extra=['--airmass-rule', 'worst'])
    best = generate_lris(monkeypatch, tmp_path / 'b', extra=['--airmass-rule', 'best'])
    w = {t.name: t for t in worst.schedule if t.airmass_rule}
    b = {t.name: t for t in best.schedule if t.airmass_rule}
    common = set(w) & set(b)
    assert common
    assert all(w[n].on_target_min >= b[n].on_target_min - 1e-9 for n in common)
    assert any(w[n].on_target_min > b[n].on_target_min for n in common)
    for t in w.values():
        assert t.airmass >= t.airmass_min - 0.01
        assert t.airmass_rule == 'worst'
    assert worst.assumptions['airmass rule'].startswith('worst')


def test_user_etc_is_used_when_passed(monkeypatch, tmp_path):
    """--etc tests.fake_etc:etc gives every longslit target 3 x 300 s.

    Inputs: monkeypatch, tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    plan = generate_lris(monkeypatch, tmp_path, extra=['--etc', 'tests.fake_etc:etc'])
    longslit = [t for t in plan.schedule if not t.mode.startswith('MOS')]
    assert longslit
    assert all(t.exposure_red == '3 x 300' and t.on_target_min == pytest.approx(15)
               for t in longslit)
    assert 'tests.fake_etc:etc' in plan.assumptions['exposure model']


def test_lris_plan_writes_and_serves_sn_spectra(monkeypatch, tmp_path):
    """Each ETC-sized target gets <plan>/etc/<target>.json (<= ~200 points),
    S/N columns on the plan, and GET /api/etc serves it.

    Inputs: monkeypatch, tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    plan = generate_lris(monkeypatch, tmp_path)
    sized = [t for t in plan.schedule if t.airmass_rule]
    assert sized
    t = sized[0]
    assert t.sn_sub_red is not None and t.sn_comb_red > t.sn_sub_red
    path = tmp_path / 'etc' / f'{t.name}.json'
    data = json.loads(path.read_text())
    assert 0 < len(data['wave']) <= 201 and data['airmass'] == pytest.approx(t.airmass)

    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from backend.app import app
    client = TestClient(app)
    got = client.get('/api/etc', params={'output_dir': str(tmp_path), 'target': t.name})
    assert got.status_code == 200 and got.json()['wave'] == data['wave']
    assert client.get('/api/etc', params={'output_dir': str(tmp_path),
                                          'target': '../x'}).status_code in (400, 404)


def _kast(tmp_path, *extra):
    import contextlib
    import io
    from night_planner.cli import generate_plan

    with contextlib.redirect_stdout(io.StringIO()):
        return generate_plan('kast', ['--targets-csv',
                                      str(REPO / 'test_targs' / 'autumn_ffffpz.csv'),
                                      '--output-dir', str(tmp_path), '--date',
                                      '2026-10-15', *extra])


def test_kast_empirical_by_default_and_etc_on_request(tmp_path):
    """Kast defaults to the empirical rule (pending a decision, 2026-11-07);
    --etc kast sizes exposures with the (faked) UCO ETC at S/N 10 with an
    airmass rule.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    from night_planner.estimate_kast_exposures import estimate_exposure

    sized = _kast(tmp_path / 'etc', '--etc', 'kast')
    assert sized.schedule
    assert any(t.airmass_rule for t in sized.schedule)
    assert sized.assumptions['target S/N'].startswith('10 ')
    assert any((tmp_path / 'etc' / 'etc').glob('*.json'))

    old = _kast(tmp_path / 'emp')
    full = [t for t in old.schedule if not (t.notes or '').startswith(('PARTIAL', 'FORCED'))]
    assert full
    for t in full:
        red, blue, _ = estimate_exposure(t.mag)
        assert (t.exposure_red, t.exposure_blue) == (red, blue)
        assert t.airmass_rule == ''
    assert 'empirical' in old.assumptions['exposure model']


@pytest.mark.network
def test_real_uco_etc_answers_for_lris():
    """One real call: the UCO ETC returns an LRIS spectrum with sensible S/N.

    Inputs: none (network).
    Outputs: none (asserts on success).
    """
    wave, s2n = etc.query_uco_etc('lris', 20.0, 600, 1.2, 0.8,
                                  {'grism': 'B600', 'grating': '600/7500',
                                   'dichroic': 'D560', 'slit': 1.0,
                                   'binning': '2x2'}, 'sdss_r.dat')
    assert len(wave) > 100 and etc.median_sn(wave, s2n, etc.RED_WINDOW) > 0
