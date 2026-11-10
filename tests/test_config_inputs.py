"""Tests for configuration, seeing and band as inputs (Milestone 4).

Created by JXP and Claude.

No network: the ETC is replaced by a recorder or by tests/lris_offline's
stub.
"""

import contextlib
import io

import pandas as pd
import pytest

from night_planner import instrument_params as ip
from tests.lris_offline import REPO, generate_lris


def test_validate_config_names_the_allowed_values():
    """An ETC-unsupported grism is refused with the allowed list.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    with pytest.raises(ip.ConfigError, match='B300, B600'):
        ip.validate_config('lris', {'grism': 'B400'})
    assert ip.validate_config('lris', {'slit': '1.0'})['slit'] == 1.0
    # Kast's real d57 is accepted, and run through the ETC as d55.
    ip.validate_config('kast', {'dichroic': 'd57'})
    cfg, notes = ip.etc_config('kast', {'dichroic': 'd57'})
    assert cfg['dichroic'] == 'd55' and notes


def test_band_maps_to_the_etc_filter_file():
    """Lowercase ugriz are SDSS; uppercase R/I are Cousins.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    assert ip.etc_filter('g') == 'sdss_g.dat'
    assert ip.etc_filter('R') == 'Cousins_R.dat'
    with pytest.raises(ip.ConfigError):
        ip.etc_filter('K')


def test_api_refuses_an_unsupported_grism_readably():
    """POST /api/generate with grism B400 -> 400 naming the allowed values.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from backend.app import app

    resp = TestClient(app).post('/api/generate', json={
        'instrument': 'lris',
        'targets_csv': str(REPO / 'test_targs' / 'autumn_ffffpz.csv'),
        'output_dir': 'pytest_never_created', 'grism': 'B400'})
    assert resp.status_code == 400
    assert 'B300' in resp.json()['detail']
    assert not (REPO / 'Night_plans' / 'pytest_never_created').exists()


def test_api_offers_the_etc_options():
    """GET /api/instruments/kast/options lists the ETC values and defaults.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from backend.app import app

    data = TestClient(app).get('/api/instruments/kast/options').json()
    assert data['options']['grism'] == ['G2', 'G3']
    assert data['defaults']['dichroic'] == 'd57'
    assert data['grism_names']['G2'] == '600/4310'


def test_worse_seeing_gives_longer_exposures(monkeypatch, tmp_path):
    """Seeing 1.2" plans longer exposures than 0.6" for the same targets.

    Inputs: monkeypatch, tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    good = generate_lris(monkeypatch, tmp_path / 'good', extra=['--seeing', '0.6'])
    bad = generate_lris(monkeypatch, tmp_path / 'bad', extra=['--seeing', '1.2'])
    good_t = {t.name: t.on_target_min for t in good.schedule
              if not t.mode.startswith('MOS')}
    bad_t = {t.name: t.on_target_min for t in bad.schedule
             if not t.mode.startswith('MOS')}
    common = set(good_t) & set(bad_t)
    assert common
    assert all(bad_t[n] > good_t[n] for n in common)
    assert good.config['seeing'] == 0.6
    assert good.assumptions['seeing [arcsec]'] == '0.6'


def test_row_band_beats_the_plan_band(monkeypatch, tmp_path):
    """One row with mag_band=g reaches the ETC as sdss_g.dat; every other
    row uses the plan-wide r band.

    Inputs: monkeypatch, tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    from night_planner.cli import generate_plan

    table = pd.read_csv(REPO / 'test_targs' / 'autumn_ffffpz.csv')
    mag_col = next(c for c in table.columns if c.lower() in ('pri_mag', 'mag_r', 'mag'))
    name_col = next(c for c in table.columns if c.lower() in ('tns', 'name'))
    bright = table[(table[mag_col] > 19) & (table[mag_col] <= 21)].index
    table['mag_band'] = ''
    table.loc[bright[0], 'mag_band'] = 'g'
    g_name = table.loc[bright[0], name_col]
    path = tmp_path / 'with_band.csv'
    table.to_csv(path, index=False)

    from tests import fake_etc
    fake_etc.CALLS.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        generate_plan('lris', ['--targets-csv', str(path), '--output-dir',
                               str(tmp_path / 'out'), '--date', '2026-10-15',
                               '--etc', 'tests.fake_etc:etc'])

    g_mag = round(float(table.loc[bright[0], mag_col]), 3)
    bands = {c['band'] for c in fake_etc.CALLS if c['mag'] == g_mag}
    others = {c['band'] for c in fake_etc.CALLS if c['mag'] != g_mag}
    assert bands == {'g'}, f'{g_name} should go to the ETC in g'
    assert others == {'r'}


def test_ffffpz_filter_strings_reduce_to_the_band():
    """FFFF-PZ's Pri_filter ('Blanco:DECam-r') reads as band 'r'; empty
    cells are '' (never the string 'nan').

    Inputs: none.
    Outputs: none (asserts on success).
    """
    import math
    from night_planner.targets_io import normalize_band

    assert normalize_band('Blanco:DECam-r') == 'r'
    assert normalize_band('Pan-STARRS1:GPC1-r') == 'r'
    assert normalize_band(' g ') == 'g'
    assert normalize_band(math.nan) == '' and normalize_band(None) == ''
