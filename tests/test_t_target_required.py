"""Tests for per-target t_target and the required flag (Milestone 6, T3.3).

Created by JXP and Claude.

Fixture: test_targs/t_target_required.csv (the autumn table plus a 25 min
user time on SIMFRB64349, and a required 500 min SIMFRB54531 that can never
fit).
"""

import contextlib
import io

import pandas as pd
import pytest

from night_planner.targets_io import field_coercions, load_targets
from tests.lris_offline import REPO, generate_lris

TABLE = REPO / 'test_targs' / 't_target_required.csv'
USER, REQUIRED = 'SIMFRB64349', 'SIMFRB54531'


def test_columns_load():
    """t_target is minutes (NaN when blank); required is a bool.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    df = load_targets(TABLE).set_index('name')
    assert df.loc[USER, 't_target'] == 25
    assert df.loc[REQUIRED, 'required'] and not df.loc[USER, 'required']
    assert df['t_target'].isna().sum() == len(df) - 2


def test_bad_values_are_reported(tmp_path):
    """Unreadable t_target / required values are counted, like priority.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    df = pd.read_csv(TABLE)
    df['t_target'] = df['t_target'].astype(object)
    df.loc[0, 't_target'] = 'soon'
    df['required'] = df['required'].astype(object)
    df.loc[1, 'required'] = 'maybe'
    report = field_coercions(df)
    assert report['t_target']['n_coerced'] == 1 and report['t_target']['examples'] == ['soon']
    assert report['required']['n_coerced'] == 1


def test_lris_user_time_is_used_exactly(monkeypatch, tmp_path):
    """The t_target row gets exactly 25 min, marked 'user', with the ETC
    estimate kept beside it; --no-etc-for-user-times drops the estimate.

    Inputs: monkeypatch, tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    plan = generate_lris(monkeypatch, tmp_path / 'a', table=TABLE.name)
    t = {x.name: x for x in plan.schedule}[USER]
    assert t.on_target_min == pytest.approx(25) and t.time_source == 'user'
    assert t.etc_min is not None and t.readout_min == 0
    others = [x for x in plan.schedule if x.name != USER and not x.mode.startswith('MOS')]
    assert all(x.time_source == 'ETC' for x in others)

    plan = generate_lris(monkeypatch, tmp_path / 'b', table=TABLE.name,
                         extra=['--no-etc-for-user-times'])
    t = {x.name: x for x in plan.schedule}[USER]
    assert t.on_target_min == pytest.approx(25) and t.etc_min is None


def _kast(table, out):
    from night_planner.cli import generate_plan
    with contextlib.redirect_stdout(io.StringIO()):
        return generate_plan('kast', ['--targets-csv', str(table), '--output-dir',
                                      str(out), '--date', '2026-10-15'])


def test_required_kast_row_is_rejected_not_truncated(tmp_path):
    """Without `required`, the 500 min row is backfilled as a partial; with
    it, the row is rejected with a 'required:' reason.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    # Just the long row and one other, so its HA window has idle time a
    # partial could use.
    small = pd.read_csv(TABLE)
    small = small[small['TNS'].isin([REQUIRED, USER])]
    req_path = tmp_path / 'req.csv'
    small.to_csv(req_path, index=False)
    loose = small.copy()
    loose['required'] = ''
    loose_path = tmp_path / 'loose.csv'
    loose.to_csv(loose_path, index=False)

    plan = _kast(loose_path, tmp_path / 'loose')
    partial = {t.name: t for t in plan.schedule}.get(REQUIRED)
    assert partial is not None and partial.notes.startswith('PARTIAL'), \
        'fixture must make the long row a partial when not required'

    plan = _kast(req_path, tmp_path / 'req')
    assert REQUIRED not in {t.name for t in plan.schedule}
    reason = {d.name: d for d in plan.decisions}[REQUIRED].reason
    assert 'required: needs 500 min' in reason


def test_inspect_round_trips_the_new_columns():
    """POST /api/targets/inspect previews t_target and required.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from backend.app import app

    data = TestClient(app).post('/api/targets/inspect',
                                params={'path': str(TABLE)}).json()
    rows = {r['name']: r for r in data['preview']}
    assert rows[USER]['t_target'] == 25 and rows[REQUIRED]['required'] is True
    assert data['mapping']['columns']['t_target'] == 't_target'
    assert data['field_coercions']['required']['n_coerced'] == 0
