"""API fields the interface fixes rely on (Milestone 7, T2.1-T2.8).

Created by JXP and Claude.

The frontend has no JS test harness; this checks the data it reads.
"""

import sys

import pytest

from tests.lris_offline import REPO, generate_lris

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402

client = TestClient(app)


def test_plan_payload_has_lst_assumptions_and_tags(monkeypatch, tmp_path):
    """GET /api/plan carries lst_start_h/lst_end_h (T2.3), the assumptions
    (T2.8) and per-target tags/dm (T2.5).

    Inputs: monkeypatch, tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    generate_lris(monkeypatch, tmp_path)
    data = client.get('/api/plan', params={'output_dir': str(tmp_path)}).json()
    assert 0 <= data['lst_start_h'] < 24 and 0 <= data['lst_end_h'] < 24
    # A ~10 h night advances LST by ~10 sidereal hours.
    span = (data['lst_end_h'] - data['lst_start_h']) % 24
    assert 8 < span < 13
    for key in ('configuration', 'readout [s per frame]', 'slew [min]',
                'acquisition [min]', 'airmass rule', 'target S/N', 'seeing [arcsec]'):
        assert key in data['assumptions'], key
    t = data['schedule'][0]
    assert 'tags' in t and 'dm' in t and t['dm'] is not None


def test_target_columns_match_the_loader():
    """GET /api/targets/columns lists exactly targets_io's fields (T2.4).

    Inputs: none.
    Outputs: none (asserts on success).
    """
    from night_planner.targets_io import OPTIONAL_FIELDS, REQUIRED_FIELDS

    cols = client.get('/api/targets/columns').json()
    assert cols['required'] == list(REQUIRED_FIELDS)
    assert cols['optional'] == list(OPTIONAL_FIELDS)
    assert 'pri_ra' in cols['aliases']['ra']


def test_inspect_preview_has_tags_and_dm():
    """The priorities page can show FFFF-PZ tags and DM (T2.5).

    Inputs: none.
    Outputs: none (asserts on success).
    """
    data = client.post('/api/targets/inspect', params={
        'path': str(REPO / 'test_targs' / 'autumn_ffffpz.csv')}).json()
    row = data['preview'][0]
    assert row['tags'] and row['dm'] is not None


def test_timeline_palette_is_colourblind_safe():
    """Every pair of timeline colours stays >= dE2000 12 under normal,
    protan and deutan vision (T2.1).

    Inputs: none.
    Outputs: none (asserts on success).
    """
    sys.path.insert(0, str(REPO / 'scripts'))
    from check_palette import TOKENS, check, read_tokens

    colors = read_tokens()
    assert set(colors) == set(TOKENS)
    _, failures = check(colors, 12.0)
    assert not failures, failures
