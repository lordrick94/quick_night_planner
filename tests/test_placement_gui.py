"""Tests for the GUI side of placement, previous plans and limits (2026-11-15).

Created by JXP and Claude.

The setup page sends `placement`, `previous_plan` and `limits` to
/api/generate, and the plan page's re-solve (/api/regenerate) anchors on the
plan's own start times. These tests check what reaches the pipeline's argv,
without writing into the real plans directory: generate_plan is replaced by
a stub that records its arguments.
"""

import contextlib
import io
import json

import pytest

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

import backend.app as app_module
from tests.lris_offline import REPO

client = TestClient(app_module.app)
TABLE = REPO / 'test_targs' / 'autumn_ffffpz.csv'


class _Stop(Exception):
    """Raised by the stub so the endpoint stops right after argv is built."""


@pytest.fixture
def captured(monkeypatch, tmp_path):
    """Plans root moved to tmp_path; generate_plan records argv and stops.

    Inputs: monkeypatch, tmp_path (pytest).
    Outputs: dict that receives 'instrument' and 'argv'.
    """
    seen = {}
    monkeypatch.setattr(app_module, 'PLANS_ROOT', tmp_path)

    def stub(instrument, argv):
        seen.update(instrument=instrument, argv=list(argv))
        raise _Stop()

    monkeypatch.setattr(app_module, 'generate_plan', stub)
    return seen


def _post(path, body):
    """POST that tolerates the stub's deliberate stop.

    Inputs: path, JSON body. Outputs: response, or None if the stub stopped it.
    """
    try:
        return client.post(path, json=body)
    except _Stop:
        return None


def _base(**extra):
    """A Kast generate request with the new fields merged in.

    Inputs: keyword fields. Outputs: dict.
    """
    return {'instrument': 'kast', 'targets_csv': str(TABLE),
            'output_dir': 'pytest-plan', 'date': '2026-10-19', **extra}


def test_options_offer_placement_and_limits_for_kast_only():
    """Kast's options carry placements and the file's limits; LRIS's do not.

    Inputs: none. Outputs: none (asserts on success).
    """
    kast = client.get('/api/instruments/kast/options').json()
    assert kast['placements'] == ['airmass', 'earliest']
    assert kast['default_placement'] == 'airmass'
    assert kast['limits']['dec_max']['value'] == 82.0
    assert kast['limits']['airmass_max']['value'] is None
    assert kast['limits']['dec_max']['source']
    lris = client.get('/api/instruments/lris/options').json()
    assert 'placements' not in lris


def test_new_fields_reach_argv(captured, tmp_path):
    """placement, previous_plan and changed limits become CLI flags.

    Inputs: captured fixture, tmp_path. Outputs: none (asserts on success).
    """
    prev = tmp_path / 'older-plan'
    prev.mkdir()
    (prev / 'plan_result.json').write_text('{}')
    _post('/api/generate', _base(placement='earliest', previous_plan='older-plan',
                                 limits={'dec_max': 72, 'airmass_max': 1.7,
                                         'dec_min': None}))
    argv = captured['argv']
    assert argv[argv.index('--placement') + 1] == 'earliest'
    assert argv[argv.index('--previous-plan') + 1] == str(prev.resolve())
    limits = [argv[i + 1] for i, a in enumerate(argv) if a == '--limit']
    assert sorted(limits) == ['airmass_max=1.7', 'dec_max=72', 'dec_min=none']


@pytest.mark.parametrize('extra, words', [
    ({'placement': 'latest'}, 'placement must be'),
    ({'limits': {'dec_max': 'high'}}, 'pointing limits'),
    ({'limits': {'ha_east': 5}}, 'pointing limits'),
    ({'previous_plan': '/etc'}, 'previous plan must be under'),
    ({'previous_plan': 'no-such-plan'}, 'no saved plan'),
])
def test_bad_values_are_refused_before_running(captured, extra, words):
    """Each bad field is a 400 that says what is wrong; nothing runs.

    Inputs: captured fixture, extra fields, expected words.
    Outputs: none (asserts on success).
    """
    r = _post('/api/generate', _base(**extra))
    assert r is not None and r.status_code == 400 and words in r.json()['detail']
    assert 'argv' not in captured


def test_lris_refuses_placement(captured):
    """The LRIS pipeline does not take the flags yet, and says so.

    Inputs: captured fixture. Outputs: none (asserts on success).
    """
    r = _post('/api/generate', {**_base(placement='airmass'), 'instrument': 'lris'})
    assert r is not None and r.status_code == 400 and 'placement' in r.json()['detail']


def test_regenerate_anchors_on_its_own_plan(tmp_path, monkeypatch):
    """A re-solve from the plan page keeps the plan's own starts.

    Inputs: tmp_path, monkeypatch (pytest). Outputs: none (asserts on success).
    """
    from night_planner.cli import generate_plan
    out = tmp_path / 'plan'
    with contextlib.redirect_stdout(io.StringIO()):
        generate_plan('kast', ['--targets-csv', str(TABLE), '--output-dir', str(out),
                               '--date', '2026-10-19', '--etc', 'empirical'])
    seen = {}

    def stub(instrument, argv):
        seen['argv'] = list(argv)
        raise _Stop()

    monkeypatch.setattr(app_module, 'generate_plan', stub)
    _post('/api/regenerate', {'output_dir': str(out), 'forced': []})
    argv = seen['argv']
    assert argv.count('--previous-plan') == 1
    assert argv[argv.index('--previous-plan') + 1] == str(out.resolve())
    saved = json.loads((out / 'plan_result.json').read_text())
    assert 'placement' in saved['assumptions'] and 'pointing limits' in saved['assumptions']
