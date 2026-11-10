"""Tests for setting a scheduled target's time from the GUI (--set-time).

Created by JXP and Claude, 2026-11-10.

--set-time NAME@MIN sets that target's t_target as if the table said so, so
the target keeps its normal place in the night with the new time. The plan
page sends these through /api/regenerate's `times` list. All targets here are
synthetic (test_targs/).
"""

import contextlib
import io

import pytest

from night_planner.targets_io import (apply_time_overrides, load_targets,
                                      parse_time_spec)
from tests.lris_offline import REPO

TABLE = REPO / 'test_targs' / 'autumn_ffffpz.csv'
DATE = '2026-10-15'


def _kast(out, extra=()):
    """Run the Kast pipeline on the autumn table, quietly."""
    from night_planner.cli import generate_plan
    with contextlib.redirect_stdout(io.StringIO()):
        return generate_plan('kast', ['--targets-csv', str(TABLE), '--output-dir',
                                      str(out), '--date', DATE, *extra])


def test_parse_time_spec():
    """NAME@MIN splits on the last '@'; bad or non-positive minutes refuse.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    assert parse_time_spec('SIMX@45') == ('SIMX', 45.0)
    assert parse_time_spec('odd@name@30') == ('odd@name', 30.0)
    for bad in ('SIMX', '@30', 'SIMX@0', 'SIMX@soon'):
        with pytest.raises(ValueError):
            parse_time_spec(bad)


def test_overrides_set_t_target_and_refuse_unknown_names():
    """The named row gets t_target; an unknown name is an error, not ignored.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    df = load_targets(TABLE)
    name = df['name'].iloc[0]
    out = apply_time_overrides(df, [f'{name}@37'])
    assert out.set_index('name').loc[name, 't_target'] == 37
    assert df['t_target'].isna().all()          # the input is not modified
    with pytest.raises(ValueError, match='NOT_A_TARGET'):
        apply_time_overrides(df, ['NOT_A_TARGET@10'])


@pytest.fixture(scope='module')
def baseline(tmp_path_factory):
    """One plain Kast plan, and a target it scheduled at full time."""
    plan = _kast(tmp_path_factory.mktemp('base'))
    target = next(t for t in plan.schedule
                  if t.time_source != 'user' and not (t.notes or '').startswith(('PARTIAL', 'FORCED')))
    return plan, target


def test_kast_set_time_keeps_target_in_its_place(tmp_path, baseline):
    """A scheduled target given a new time is still scheduled normally (not
    appended like --force), with exactly that time, marked 'user'.

    Inputs: tmp_path (pytest), baseline (fixture).
    Outputs: none (asserts on success).
    """
    _, target = baseline
    new = max(10, round(target.on_target_min) - 10)
    plan = _kast(tmp_path, ['--set-time', f'{target.name}@{new}'])
    t = {x.name: x for x in plan.schedule}[target.name]
    assert t.on_target_min == pytest.approx(new) and t.time_source == 'user'
    assert not (t.notes or '').startswith('FORCED')
    assert plan.request['argv'][-2:] == ['--set-time', f'{target.name}@{new}']


def test_unknown_target_stops_the_run(tmp_path):
    """--set-time on a name that isn't in the table exits with that name.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    with pytest.raises(SystemExit, match='NOT_A_TARGET'):
        _kast(tmp_path, ['--set-time', 'NOT_A_TARGET@10'])


def test_lris_parser_accepts_set_time():
    """The Keck pipeline takes the same flag.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    import sys
    sys.path.insert(0, str(REPO / 'scripts'))
    import keck_2026oct06_calculations as kc
    args = kc.parse_args(['--set-time', 'SIMX@20', '--set-time', 'SIMY@35'])
    assert args.set_time == ['SIMX@20', 'SIMY@35']


def test_regenerate_sets_keeps_and_clears_times(tmp_path, monkeypatch, baseline):
    """/api/regenerate: `times` replaces --set-time; a request with only
    `forced` keeps it; an empty `times` clears it.

    Inputs: tmp_path, monkeypatch (pytest), baseline (fixture).
    Outputs: none (asserts on success).
    """
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    import backend.app as backend

    _, target = baseline
    monkeypatch.setattr(backend, 'PLANS_ROOT', tmp_path)
    client = TestClient(backend.app)
    _kast(tmp_path / 'night')
    d = str(tmp_path / 'night')
    new = max(10, round(target.on_target_min) - 10)

    def regen(**body):
        resp = client.post('/api/regenerate', json={'output_dir': d, **body})
        assert resp.status_code == 200, resp.text
        return {t['name']: t for t in resp.json()['schedule']}, resp.json()

    sched, data = regen(times=[{'target': target.name, 'minutes': new}])
    assert sched[target.name]['on_target_min'] == pytest.approx(new)
    assert sched[target.name]['time_source'] == 'user'

    sched, data = regen(forced=[])          # rejections page: times untouched
    assert sched[target.name]['on_target_min'] == pytest.approx(new)
    assert f'{target.name}@{new}' in data['request']['argv']

    sched, data = regen(times=[])           # cleared: back to the planner's own time
    assert '--set-time' not in data['request']['argv']
    assert sched[target.name]['time_source'] == target.time_source

    bad = client.post('/api/regenerate', json={
        'output_dir': d, 'times': [{'target': 'NOT_A_TARGET', 'minutes': 10}]})
    assert bad.status_code == 400 and 'NOT_A_TARGET' in bad.text


def test_lris_set_time_overrides_the_tables_t_target(monkeypatch, tmp_path):
    """On LRIS, --set-time wins over a t_target already in the table
    (25 min in t_target_required.csv -> 40 min).

    Inputs: monkeypatch, tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    from tests.lris_offline import generate_lris
    user = 'SIMFRB64349'
    plan = generate_lris(monkeypatch, tmp_path, table='t_target_required.csv',
                         extra=['--set-time', f'{user}@40'])
    t = {x.name: x for x in plan.schedule}[user]
    assert t.on_target_min == pytest.approx(40) and t.time_source == 'user'
