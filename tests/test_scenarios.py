"""Several plans per night, as tabs (Milestone 10, T4.1).

Created by JXP and Claude.

Drives POST /api/generate with scenarios, with the plans root pointed at
tmp_path so nothing lands in Night_plans/.
"""

import json
from pathlib import Path

import pytest

from tests.lris_offline import REPO

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient  # noqa: E402

import backend.app as backend  # noqa: E402

SEEING = [{'name': 'good seeing', 'seeing': 0.6},
          {'name': 'median seeing', 'seeing': 0.8},
          {'name': 'poor seeing', 'seeing': 1.2}]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, 'PLANS_ROOT', tmp_path)
    return TestClient(backend.app)


def _generate(client, scenarios, table='faint_mos_split.csv', extra=None):
    body = {'instrument': 'lris', 'date': '2026-10-15', 'output_dir': 'night',
            'targets_csv': str(REPO / 'test_targs' / table),
            'assume_masks': True, 'scenarios': scenarios, **(extra or {})}
    resp = client.post('/api/generate', json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_three_seeing_scenarios_make_three_plans(client, tmp_path):
    """Three scenarios -> three plan directories and an index; poor seeing
    never gets shorter exposures than good for the same target.

    Inputs: client (fixture), tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    data = _generate(client, SEEING)
    base = tmp_path / 'night'
    index = json.loads((base / 'scenarios.json').read_text())['scenarios']
    assert [e['slug'] for e in index] == ['good-seeing', 'median-seeing', 'poor-seeing']
    for e in index:
        assert (base / e['slug'] / 'plan_result.json').exists()
    assert data['output_dir'] == str(base / 'good-seeing')

    plans = {e['slug']: client.get('/api/plan', params={
        'output_dir': str(base / e['slug'])}).json() for e in index}
    good = {t['name']: t for t in plans['good-seeing']['schedule']}
    poor = {t['name']: t for t in plans['poor-seeing']['schedule']}
    common = [n for n in set(good) & set(poor) if good[n]['time_source'] == 'ETC']
    assert common
    assert all(poor[n]['on_target_min'] >= good[n]['on_target_min'] for n in common)
    assert plans['poor-seeing']['config']['seeing'] == 1.2

    tabs = client.get('/api/scenarios', params={'output_dir': str(base / 'poor-seeing')}).json()
    assert tabs['active'] == 'poor-seeing' and len(tabs['scenarios']) == 3
    assert all('on_target_h' in s and 'unique' in s for s in tabs['scenarios'])


def test_one_log_per_night_with_union_calibrations(client, tmp_path):
    """The log lives at the scenario base, whichever tab opens it, and its
    calibrations cover every scenario's masks.

    Inputs: client (fixture), tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    _generate(client, [{'name': 'all night'},
                       {'name': 'lost first half',
                        'blocks': [{'start': 'night', 'end': '00:00',
                                    'reason': 'lost first half'}]}])
    base = tmp_path / 'night'
    a = client.get('/api/log', params={'output_dir': str(base / 'all-night')}).json()
    assert (base / 'observing_log.json').exists()
    assert not (base / 'all-night' / 'observing_log.json').exists()

    masks = set()
    for slug in ('all-night', 'lost-first-half'):
        plan = client.get('/api/plan', params={'output_dir': str(base / slug)}).json()
        masks |= {t['name'] for t in plan['schedule'] if t['mode'].startswith('MOS')}
    logged = {c['scope_name'] for c in a['log']['calibrations'].values()
              if c['scope'] == 'mask'}
    assert masks and logged == masks

    # A tick from the other tab lands in the same log.
    client.patch('/api/log', json={'output_dir': str(base / 'lost-first-half'),
                                   'path': ['night', 'observers'], 'value': 'LK'})
    again = client.get('/api/log', params={'output_dir': str(base / 'all-night')}).json()
    assert again['log']['night']['observers'] == 'LK'


def test_lost_first_half_blocks_until_midnight(client, tmp_path):
    """The preset blocks from the start of the night to local midnight.

    Inputs: client (fixture), tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    _generate(client, [{'name': 'lost first half',
                        'blocks': [{'start': 'night', 'end': '00:00',
                                    'reason': 'lost first half'}]}])
    plan = client.get('/api/plan', params={
        'output_dir': str(tmp_path / 'night' / 'lost-first-half')}).json()
    assert plan['blocks'] and plan['blocks'][0]['reason'] == 'lost first half'
    assert plan['blocks'][0]['end'][11:16] == '00:00'
    assert all(t['science_start'] >= plan['blocks'][0]['end'] for t in plan['schedule'])
