"""Tests for a per-target S/N goal: the target_sn column and --set-sn.

Created by JXP and Claude, 2026-11-10.

A row's target_sn (table column, or --set-sn NAME@SN from the plan page via
/api/regenerate's `sns` list) is the S/N per sub-exposure the ETC sizes that
target for, in place of the plan-wide --target-sn. On Kast's default
empirical rule (which has no S/N), such a target is sized by the Kast ETC.
All targets are synthetic (test_targs/); the ETC is faked by conftest.py,
with S/N ~ sqrt(t), so a higher goal means a longer exposure.
"""

import contextlib
import io

import numpy as np
import pandas as pd
import pytest

from night_planner.instrument_params import recipe_frames
from night_planner.targets_io import (apply_sn_overrides, detect_mapping,
                                      field_coercions, has_own_sn,
                                      load_targets, row_target_sn)
from tests.lris_offline import REPO, generate_lris

TABLE = REPO / 'test_targs' / 'autumn_ffffpz.csv'
DATE = '2026-10-15'


def _kast(out, table=TABLE, extra=()):
    """Run the Kast pipeline (empirical rule by default), quietly."""
    from night_planner.cli import generate_plan
    with contextlib.redirect_stdout(io.StringIO()):
        return generate_plan('kast', ['--targets-csv', str(table), '--output-dir',
                                      str(out), '--date', DATE, *extra])


def _sub_seconds(recipe):
    """'3 x 600' -> 600.0 (seconds per sub-exposure)."""
    n, total = recipe_frames(recipe)
    return total / n


def test_column_is_read_and_unreadable_values_reported():
    """A target_sn column is detected, parsed, and bad cells fall back to unset.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    df = pd.DataFrame({'name': ['A', 'B', 'C'], 'ra': [10.5, 20.0, 30.0],
                       'dec': [40.0, 41.0, 42.0], 'mag': [19.0, 20.0, 21.0],
                       'target_sn': [15, 'lots', None]})
    assert detect_mapping(df).columns['target_sn'] == 'target_sn'
    out = load_targets(df)
    assert out['target_sn'].iloc[0] == 15
    assert np.isnan(out['target_sn'].iloc[1]) and np.isnan(out['target_sn'].iloc[2])
    assert field_coercions(df)['target_sn']['n_coerced'] == 1
    # A bare 'snr' column is a measured S/N, not a goal: not picked up.
    assert 'target_sn' not in detect_mapping(df.rename(columns={'target_sn': 'snr'})).columns


def test_overrides_and_goal_resolution():
    """--set-sn sets target_sn; unknown names refuse; the row beats the plan.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    df = load_targets(TABLE)
    name = df['name'].iloc[0]
    out = apply_sn_overrides(df, [f'{name}@20'])
    row = out.set_index('name').loc[name]
    assert row['target_sn'] == 20 and has_own_sn(row)
    assert row_target_sn(row, 10.0) == 20.0
    other = out.set_index('name').iloc[1]
    assert not has_own_sn(other) and row_target_sn(other, 10.0) == 10.0
    with pytest.raises(ValueError, match='NOT_A_TARGET'):
        apply_sn_overrides(df, ['NOT_A_TARGET@10'])
    with pytest.raises(ValueError):
        apply_sn_overrides(df, [f'{name}@0'])


@pytest.fixture(scope='module')
def lris_baseline(tmp_path_factory):
    """One LRIS plan at the plan-wide S/N, and an ETC-sized longslit target."""
    mp = pytest.MonkeyPatch()
    plan = generate_lris(mp, tmp_path_factory.mktemp('lris_base'))
    # The shortest, so a higher goal still fits the night.
    target = min((t for t in plan.schedule if t.time_source == 'ETC'),
                 key=lambda t: t.on_target_min)
    return plan, target


def test_lris_set_sn_lengthens_only_that_target(tmp_path, monkeypatch, lris_baseline):
    """Doubling one target's S/N goal lengthens its sub-exposures; the
    others keep the plan-wide goal.

    Inputs: tmp_path, monkeypatch (pytest), lris_baseline (fixture).
    Outputs: none (asserts on success).
    """
    base, target = lris_baseline
    assert target.target_sn == pytest.approx(10) and not target.target_sn_own
    plan = generate_lris(monkeypatch, tmp_path, extra=['--set-sn', f'{target.name}@20'])
    t = {x.name: x for x in plan.schedule}[target.name]
    assert t.target_sn == pytest.approx(20) and t.target_sn_own
    assert _sub_seconds(t.exposure_red) > _sub_seconds(target.exposure_red)
    others = [x for x in plan.schedule if x.name != target.name and x.time_source == 'ETC']
    assert others and all(x.target_sn == pytest.approx(10) for x in others)


def test_kast_empirical_plan_sends_an_sn_target_to_the_etc(tmp_path):
    """On the empirical Kast rule, a target with its own S/N is sized by the
    Kast ETC at that goal; every other target stays empirical.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    base = _kast(tmp_path / 'base')
    # A bright one: a faint host at S/N 8 needs hours and is (rightly) rejected.
    target = min((t for t in base.schedule if t.time_source == 'empirical'),
                 key=lambda t: t.mag)
    assert target.target_sn is None
    plan = _kast(tmp_path / 'sn', extra=['--set-sn', f'{target.name}@8'])
    by_name = {x.name: x for x in plan.schedule}
    t = by_name[target.name]
    assert t.time_source == 'ETC' and t.target_sn == pytest.approx(8)
    assert t.target_sn_own and t.airmass is not None
    assert all(x.time_source in ('empirical', 'user') or x.name == target.name
               or (x.notes or '').startswith(('PARTIAL', 'FORCED'))
               for x in plan.schedule)
    assert plan.request['argv'][-2:] == ['--set-sn', f'{target.name}@8']


def test_kast_table_column_and_user_time_wins(tmp_path):
    """A target_sn column works like --set-sn; a t_target on the same row
    still sets the time (the S/N goal is then not used).

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    df = pd.read_csv(TABLE)
    df['target_sn'] = np.nan
    df['t_target'] = np.nan
    df.loc[0, 'target_sn'] = 8
    df.loc[1, ['target_sn', 't_target']] = [8, 30]
    table = tmp_path / 'with_sn.csv'
    df.to_csv(table, index=False)
    plan = _kast(tmp_path / 'out', table=table)
    by_name = {x.name: x for x in plan.schedule}
    first, second = df['TNS'].iloc[0], df['TNS'].iloc[1]
    if first in by_name:
        assert by_name[first].time_source == 'ETC'
        assert by_name[first].target_sn == pytest.approx(8)
    if second in by_name:
        assert by_name[second].time_source == 'user'
        assert by_name[second].on_target_min == pytest.approx(30)
        assert by_name[second].target_sn is None
    assert first in by_name or second in by_name


def test_unknown_target_stops_the_run(tmp_path):
    """--set-sn on a name that isn't in the table exits with that name.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    with pytest.raises(SystemExit, match='NOT_A_TARGET'):
        _kast(tmp_path, extra=['--set-sn', 'NOT_A_TARGET@10'])


def test_regenerate_sns_set_keep_and_clear(tmp_path, monkeypatch, lris_baseline):
    """/api/regenerate: `sns` replaces --set-sn; a request with only `times`
    keeps it; an empty `sns` clears it; an unknown name is a 400.

    Inputs: tmp_path, monkeypatch (pytest), lris_baseline (fixture).
    Outputs: none (asserts on success).
    """
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    import backend.app as backend

    _, target = lris_baseline
    monkeypatch.setattr(backend, 'PLANS_ROOT', tmp_path)
    client = TestClient(backend.app)
    generate_lris(monkeypatch, tmp_path / 'night')
    d = str(tmp_path / 'night')

    def regen(**body):
        resp = client.post('/api/regenerate', json={'output_dir': d, **body})
        assert resp.status_code == 200, resp.text
        return resp.json()

    data = regen(sns=[{'target': target.name, 'sn': 12}])
    assert ['--set-sn', f'{target.name}@12'] == data['request']['argv'][-2:]
    sched = {t['name']: t for t in data['schedule']}
    assert sched[target.name]['target_sn'] == pytest.approx(12)
    assert sched[target.name]['target_sn_own']

    data = regen(times=[])                  # time edits only: S/N goal kept
    assert f'{target.name}@12' in data['request']['argv']

    data = regen(sns=[])                    # cleared
    assert '--set-sn' not in data['request']['argv']

    bad = client.post('/api/regenerate', json={
        'output_dir': d, 'sns': [{'target': 'NOT_A_TARGET', 'sn': 10}]})
    assert bad.status_code == 400 and 'NOT_A_TARGET' in bad.text
