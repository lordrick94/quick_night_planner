"""Tests for the Finders page buttons' server side.

Created by JXP and Claude, 2026-11-11.

Re-rendering one card used to rewrite slit_report.txt with that card
alone, and two runs could draw into one folder at once. These pin the
fixes: a single-card run keeps the whole-night report, charts drawn
earlier are judged against what was asked for *then*, and a second run on
the same plan is refused. Network-free: generate_for_plan is faked.
"""

import json
from types import SimpleNamespace

import pytest

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

import backend.app as backend
from night_planner import finder

client = TestClient(backend.app)


def _plan(tmp_path, names=('SIM_A', 'SIM_B', 'SIM_C')):
    """A stand-in PlanResult with just what the finder endpoint reads."""
    return SimpleNamespace(
        schedule=[SimpleNamespace(name=n) for n in names],
        instrument='kast', date='2026-11-11', output_dir=str(tmp_path),
        request={})


def _entry(name, pa, mode='parallactic', requested='parallactic', **extra):
    """One generate_for_plan() result."""
    return dict({'name': name, 'slit_pa': pa, 'slit_mode': mode,
                 'requested_mode': requested, 'parallactic_pa': pa,
                 'pa_vs_parallactic': 0.0}, **extra)


def _sidecar(folder, entry):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{entry['name']}_finder.json").write_text(json.dumps(entry))


def test_earlier_parallactic_chart_is_not_called_a_fallback():
    """A chart drawn at parallactic on request is not 'fell back' later.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    report = finder.slit_report(
        [_entry('SIM_A', 10.0, skipped='drawn earlier'),
         _entry('SIM_B', 20.0, requested='candidates',
                fallback_reason='no second PATH candidate for this target')],
        'candidates')
    assert report['fell_back'] == ['SIM_B']


def test_plan_slit_entries_merges_fresh_with_sidecars(tmp_path):
    """Fresh results win, sidecars fill the rest, never-drawn are left out.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    folder = tmp_path / 'finders'
    _sidecar(folder, _entry('SIM_A', 10.0))
    _sidecar(folder, _entry('SIM_B', 99.0))
    merged = finder.plan_slit_entries(
        _plan(tmp_path), folder, [_entry('SIM_B', 20.0)])
    assert [e['name'] for e in merged] == ['SIM_A', 'SIM_B']
    assert merged[0]['skipped'] == 'drawn earlier'
    assert merged[1]['slit_pa'] == 20.0


def test_failed_sidecar_stays_on_the_record(tmp_path):
    """A sidecar recording a failure is kept, and reported as FAILED.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    folder = tmp_path / 'finders'
    _sidecar(folder, _entry('SIM_C', 30.0, error='TimeoutError: down'))
    merged = finder.plan_slit_entries(_plan(tmp_path), folder, [])
    lines = finder.slit_report(merged, 'parallactic')['lines']
    assert lines == ['SIM_C: FAILED -- TimeoutError: down']


@pytest.fixture
def fake_backend(tmp_path, monkeypatch):
    """Point the endpoint at a fake plan and a fake chart generator."""
    plan = _plan(tmp_path)
    monkeypatch.setattr(backend, '_require_plan', lambda output_dir: plan)
    calls = []

    def fake_generate(plan, location, out_dir, targets=None, **kwargs):
        calls.append(targets)
        out = [_entry(t.name, 42.0) for t in plan.schedule
               if not targets or t.name in targets]
        for e in out:
            _sidecar(out_dir, e)
        return out

    monkeypatch.setattr(finder, 'generate_for_plan', fake_generate)
    return SimpleNamespace(plan=plan, dir=tmp_path, calls=calls)


def test_one_card_keeps_the_whole_night_report(fake_backend):
    """Re-rendering one card leaves every chart's line in slit_report.txt.

    Inputs: fake_backend (fixture).
    Outputs: none (asserts on success).
    """
    out = str(fake_backend.dir)
    assert client.post('/api/finders/generate',
                       json={'output_dir': out}).status_code == 200
    resp = client.post('/api/finders/generate',
                       json={'output_dir': out, 'targets': ['SIM_B'],
                             'overwrite': True})
    assert resp.status_code == 200
    # The response is just this run; the file is the whole night.
    assert [r['name'] for r in resp.json()['report']['rows']] == ['SIM_B']
    text = (fake_backend.dir / 'finders' / 'slit_report.txt').read_text()
    for name in ('SIM_A', 'SIM_B', 'SIM_C'):
        assert f'{name}: parallactic' in text
    assert 'for SIM_B; other charts as drawn earlier' in text


def test_second_run_on_the_same_plan_is_refused(fake_backend):
    """A run already in flight for this plan makes a second one 409.

    Inputs: fake_backend (fixture).
    Outputs: none (asserts on success).
    """
    key = str(fake_backend.dir.resolve() / 'finders')
    backend._FINDER_RUNNING.add(key)
    try:
        resp = client.post('/api/finders/generate',
                           json={'output_dir': str(fake_backend.dir)})
    finally:
        backend._FINDER_RUNNING.discard(key)
    assert resp.status_code == 409
    assert fake_backend.calls == []
    # And the lock is released after a normal run.
    assert client.post('/api/finders/generate',
                       json={'output_dir': str(fake_backend.dir)}).status_code == 200
    assert key not in backend._FINDER_RUNNING
