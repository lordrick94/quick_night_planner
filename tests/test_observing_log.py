"""Tests for the Observing log (with its calibrations checklist), the
Markdown night report and the FFFF-PZ CSV refactor (Milestone 1).

Created by JXP and Claude.

Synthetic plans only, except the FFFF-PZ regression test, which reads
the committed Keck-2026B-02 plan. Nothing here touches the network, and
nothing writes outside pytest's tmp_path.
"""

import io
import json
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from night_planner import observing_log as olog
from night_planner.observing_report import build_ffffpz_rows, render_markdown
from night_planner.paths import plan_dir
from night_planner.plan_result import PlanResult, ScheduledTarget, SunEvents
from night_planner.plan_store import save_plan

REPO = Path(__file__).resolve().parent.parent
# Real (private) plan: present only where NIGHT_PLANNER_PLANS/pvt_Nighplans is.
KECK_PLAN_DIR = plan_dir('Keck-2026B-02')
HST = ZoneInfo('Pacific/Honolulu')
PACIFIC = ZoneInfo('America/Los_Angeles')


def _t(name, start_h, start_m, dur_min, mode='longslit', exp='3 x 600',
       tz=HST, day=6):
    start = datetime(2026, 10, day, start_h, start_m, tzinfo=tz)
    return ScheduledTarget(
        name=name, ra_deg=30.0, dec_deg=10.0, mag=20.0, mode=mode,
        start=start, science_start=start + timedelta(minutes=10),
        end=start + timedelta(minutes=10 + dur_min), slew_min=10,
        on_target_min=dur_min, exposure_red=exp, exposure_blue=exp)


def _plan(schedule, instrument='lris', output_dir='/tmp', tz=HST):
    """A small synthetic plan with the two Keck standards as overheads."""
    night_start = datetime(2026, 10, 6, 19, 0, tzinfo=tz)
    night_end = datetime(2026, 10, 7, 5, 0, tzinfo=tz)
    overheads = [
        (night_start, night_start + timedelta(minutes=5),
         'Evening standard (BD+28 4211)'),
        (night_start + timedelta(minutes=5), night_start + timedelta(minutes=10),
         'Focus check'),
        (night_end - timedelta(minutes=5), night_end,
         'Morning standard (Feige 110)'),
    ]
    return PlanResult(
        instrument=instrument,
        telescope='Keck I' if instrument == 'lris' else 'Shane 3m (Lick)',
        date='2026-10-06', output_dir=str(output_dir), timezone=str(tz),
        sun=SunEvents(*[night_start] * 6), night_start=night_start,
        night_end=night_end, schedule=list(schedule),
        overheads=overheads if instrument == 'lris' else [])


def _lris_two_masks(output_dir='/tmp'):
    return _plan([_t('LS1', 20, 0, 30),
                  _t('MASK_A', 21, 0, 65, mode='MOS (mask required)',
                     exp='MOS mask required'),
                  _t('MASK_B', 23, 0, 65, mode='MOS (mask required)',
                     exp='MOS mask required')], output_dir=output_dir)


# --------------------------------------------------------------------
# Calibrations checklist
# --------------------------------------------------------------------

def test_lris_one_config_two_masks_gives_six_calibrations():
    """Flats + arcs per config (2) plus flats + arcs per mask (2 x 2).

    Inputs: none.
    Outputs: none (asserts on success).
    """
    plan = _lris_two_masks()
    items = olog.calibration_items(plan, olog.default_configs(plan))
    assert len(items) == 6
    assert [i['scope'] for i in items] == ['config'] * 2 + ['mask'] * 4
    assert {i['id'] for i in items if i['scope'] == 'mask'} == {
        'flat:mask:MASK_A', 'arc:mask:MASK_A',
        'flat:mask:MASK_B', 'arc:mask:MASK_B'}


def test_kast_one_config_gives_bias_flat_arc():
    """Kast needs biases, flats and arcs for its one configuration.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    plan = _plan([_t('K1', 20, 0, 30, tz=PACIFIC)], instrument='kast',
                 tz=PACIFIC)
    items = olog.calibration_items(plan, olog.default_configs(plan))
    assert [i['kind'] for i in items] == ['bias', 'flat', 'arc']
    assert all(i['scope'] == 'config' for i in items)


# --------------------------------------------------------------------
# New log, edits, merge
# --------------------------------------------------------------------

def test_new_log_has_a_pending_row_per_target_and_standard():
    """One pending row per scheduled target, plus the two standards.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    log = olog.new_log(_lris_two_masks())
    kinds = [r['kind'] for r in sorted(log['targets'].values(),
                                       key=lambda r: r['order'])]
    assert kinds == ['standard', 'science', 'science', 'science', 'standard']
    assert all(r['status'] == 'pending' for r in log['targets'].values())
    assert 'focus' in log['night_checklist']
    # Calibrations aren't asked for twice.
    assert not any('calib' in i['label'].lower()
                   for i in log['night_checklist'].values())


def test_set_field_validates_and_records_provenance():
    """Bad values are refused; good ones record updated_ut and source.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    plan = _lris_two_masks()
    log = olog.new_log(plan)
    with pytest.raises(olog.LogEditError):
        olog.set_field(log, plan, ['targets', 'LS1', 'status'], 'maybe')
    with pytest.raises(olog.LogEditError):
        olog.set_field(log, plan, ['targets', 'LS1', 'planned'], {})
    with pytest.raises(olog.LogEditError):
        olog.set_field(log, plan, ['calibrations', 'nope', 'done'], True)

    olog.set_field(log, plan, ['targets', 'LS1', 'status'], 'observed',
                   now='2026-10-07T07:00:00Z')
    key = json.dumps(['targets', 'LS1', 'status'])
    assert log['edits'][key] == {'updated_ut': '2026-10-07T07:00:00Z',
                                 'source': 'manual'}


def test_bare_ut_time_lands_on_the_right_night():
    """'06:30' UT on an HST night of Oct 6 is Oct 7 UT, not Oct 6.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    plan = _lris_two_masks()
    assert olog.resolve_ut(plan, '06:30') == '2026-10-07T06:30Z'
    assert olog.resolve_ut(plan, '') == ''
    with pytest.raises(olog.LogEditError):
        olog.resolve_ut(plan, '25:00')


def test_edits_survive_save_and_load(tmp_path):
    """A target field and a calibration tick survive a disk round trip.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    plan = _lris_two_masks(tmp_path)
    log = olog.open_log(plan, str(tmp_path))
    olog.set_field(log, plan, ['targets', 'LS1', 'frames'], 'r0045-0047')
    olog.set_field(log, plan, ['calibrations', 'arc:mask:MASK_A', 'done'], True)
    olog.save_log(str(tmp_path), log)

    again = olog.open_log(plan, str(tmp_path))
    assert again['targets']['LS1']['frames'] == 'r0045-0047'
    assert again['calibrations']['arc:mask:MASK_A']['done'] is True


def test_merge_keeps_user_input_for_a_dropped_mask():
    """Regenerating without MASK_A keeps its filled row and ticked
    calibration as not_in_plan, drops untouched ones, and adds new targets.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    plan = _lris_two_masks()
    log = olog.new_log(plan)
    olog.set_field(log, plan, ['targets', 'MASK_A', 'comments'], 'half done')
    olog.set_field(log, plan, ['calibrations', 'flat:mask:MASK_A', 'done'], True)

    regenerated = _plan([_t('LS1', 20, 0, 30),
                         _t('MASK_B', 23, 0, 65, mode='MOS (mask required)',
                            exp='MOS mask required'),
                         _t('NEW', 1, 0, 30, day=7)])
    olog.merge_log(log, regenerated)

    assert log['targets']['MASK_A']['not_in_plan'] is True
    assert log['targets']['MASK_A']['comments'] == 'half done'
    assert log['calibrations']['flat:mask:MASK_A']['not_in_plan'] is True
    assert log['calibrations']['flat:mask:MASK_A']['done'] is True
    # Untouched item for the dropped mask is gone.
    assert 'arc:mask:MASK_A' not in log['calibrations']
    assert log['targets']['NEW']['status'] == 'pending'
    assert olog.calibration_status(log) == (0, 4)


# --------------------------------------------------------------------
# Markdown report
# --------------------------------------------------------------------

def _filled_log(plan):
    log = olog.new_log(plan)
    olog.set_field(log, plan, ['targets', 'LS1', 'status'], 'observed', now='x')
    olog.set_field(log, plan, ['targets', 'LS1', 'exposures_red'], '3 x 600', now='x')
    olog.set_field(log, plan, ['targets', 'LS1', 'frames'], 'r45-47', now='x')
    olog.set_field(log, plan, ['targets', 'MASK_A', 'status'], 'partial', now='x')
    olog.set_field(log, plan, ['targets', 'MASK_A', 'reason'], 'weather', now='x')
    olog.set_field(log, plan, ['targets', 'MASK_B', 'status'], 'not_observed', now='x')
    olog.set_field(log, plan, ['targets', 'MASK_B', 'reason'], 'ran_out_of_time',
                   now='x')
    olog.set_field(log, plan, ['calibrations', 'arc:config:'
                               + log['configs'][0]['label'], 'done'], True, now='x')
    olog.set_field(log, plan, ['conditions'],
                   [{'ut': '06:00', 'sky': 'clear', 'seeing': '0.8', 'note': ''}],
                   now='x')
    return log


def _section(md, title):
    body = md.split(f'## {title}\n', 1)[1]
    return body.split('\n## ', 1)[0]


def test_report_sorts_rows_into_sections_and_warns():
    """Observed / partial / not-observed rows land in the right sections;
    calibrations show taken / not taken; a pending standard is warned about.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    plan = _lris_two_masks()
    md = render_markdown(plan, _filled_log(plan))

    observed = _section(md, 'Observed targets')
    missed = _section(md, 'Not observed or partial')
    assert 'LS1' in observed and 'MASK_B' not in observed
    assert 'MASK_A (partial)' in observed
    assert 'MASK_A' in missed and 'MASK_B' in missed and 'LS1' not in missed
    assert 'ran out of time' in missed

    cals = _section(md, 'Standards and calibrations')
    assert 'Calibrations taken: **1 / 6**' in cals
    assert '| NO |' in cals and '| yes |' in cals

    assert '> **Warnings**' in md
    assert 'Evening standard (BD+28 4211): still pending' in md
    # MASK_A is partial with no frames recorded.
    assert 'MASK_A: partial but no frame numbers' in md


def test_report_is_deterministic():
    """Same plan + log -> same Markdown, byte for byte.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    plan = _lris_two_masks()
    log = _filled_log(plan)
    assert render_markdown(plan, log) == render_markdown(plan, json.loads(
        json.dumps(log)))


# --------------------------------------------------------------------
# FFFF-PZ CSV
# --------------------------------------------------------------------

def test_ffffpz_rows_from_a_page_log_skip_unobserved_and_standards():
    """Only observed/partial science rows (and unplanned ones) are reported.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    plan = _lris_two_masks()
    log = _filled_log(plan)
    olog.set_field(log, plan, ['night', 'ffffpz_conditions'], 'Good', now='x')
    olog.set_field(log, plan, ['unplanned'],
                   [{'name': 'EXTRA1', 'exposures_red': '2 x 300',
                     'success': 'no'}], now='x')
    rows, notes = build_ffffpz_rows(plan, log, resource='R')
    assert [r['TNS'] for r in rows] == ['LS1', 'MASK_A', 'EXTRA1']
    assert rows[0]['texp'] == 1800 and rows[0]['Conditions'] == 'Good'
    assert rows[2]['texp'] == 600 and rows[2]['success'] is False
    assert any('MASK_A' in n and 'allocated block' in n for n in notes)


@pytest.mark.skipif(not (KECK_PLAN_DIR / 'report_extra.txt').exists(),
                    reason='no private Keck plan / report_extra.txt on disk')
def test_refactored_script_reproduces_the_committed_report(tmp_path):
    """make_observing_report.py, now routed through build_ffffpz_rows,
    reproduces Keck-2026B-02_report.csv byte for byte from the private
    plan and the flags used for it (--conditions Fair --extra NAME:SECONDS).
    The real target name lives in the private report_extra.txt, not here.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    sys.path.insert(0, str(REPO / 'scripts'))
    import make_observing_report

    extra = (KECK_PLAN_DIR / 'report_extra.txt').read_text().strip()
    out = tmp_path / 'report.csv'
    make_observing_report.main(['--plan-dir', str(KECK_PLAN_DIR),
                                '--conditions', 'Fair',
                                '--extra', extra,
                                '--out', str(out)])
    assert out.read_bytes() == (KECK_PLAN_DIR / 'Keck-2026B-02_report.csv').read_bytes()


# --------------------------------------------------------------------
# API
# --------------------------------------------------------------------

@pytest.fixture
def api_plan_dir(tmp_path):
    """A saved synthetic plan in a directory the API is allowed to read."""
    plan = _lris_two_masks(tmp_path)
    save_plan(plan, str(tmp_path))
    return tmp_path


def test_api_log_patch_and_report(api_plan_dir):
    """GET creates the log, PATCH sets a field, POST writes the report, and
    the export zip carries observing_log.json.

    Inputs: api_plan_dir (fixture).
    Outputs: none (asserts on success).
    """
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from backend.app import app

    client = TestClient(app)
    d = str(api_plan_dir)

    data = client.get('/api/log', params={'output_dir': d}).json()
    assert data['derived']['calibrations'] == {'taken': 0, 'total': 6}

    resp = client.patch('/api/log', json={
        'output_dir': d, 'path': ['targets', 'LS1', 'status'], 'value': 'observed'})
    assert resp.status_code == 200
    resp = client.patch('/api/log', json={
        'output_dir': d, 'path': 'calibrations.flat:mask:MASK_A.done', 'value': True})
    assert resp.json()['derived']['calibrations']['taken'] == 1
    bad = client.patch('/api/log', json={
        'output_dir': d, 'path': ['targets', 'LS1', 'status'], 'value': 'nope'})
    assert bad.status_code == 400

    report = client.post('/api/log/report', json={'output_dir': d}).json()
    assert Path(report['markdown_path']).parent == api_plan_dir
    assert Path(report['markdown_path']).name == 'observing_report_2026-10-06.md'
    assert 'LS1' in report['markdown']
    assert report['warnings']

    names = zipfile.ZipFile(io.BytesIO(client.get(
        '/api/export', params={'output_dir': d, 'name': 'log_export'}).content)
    ).namelist()
    assert 'observing_log.json' in names


# --------------------------------------------------------------------
# 1a: calibrations are no longer scheduled
# --------------------------------------------------------------------

def test_keck_overheads_have_no_arcs_or_flats():
    """The Keck plan's closing overheads stop at the morning standard.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    sys.path.insert(0, str(REPO / 'scripts'))
    from night_planner.adapters import _keck_overheads

    plan = _lris_two_masks()
    labels = [o[2].lower() for o in _keck_overheads(plan.night_start, plan.schedule)]
    assert labels[-1].startswith('morning standard')
    assert not any(w in l for l in labels for w in ('arc', 'flat', 'bias'))


def test_lris_end_of_night_reserve_is_slew_plus_standard():
    """The old flat 30 min calibration reserve is now just the closing slew
    to Feige 110 plus the standard (base slew, never a S->N crossing).

    Inputs: none.
    Outputs: none (asserts on success).
    """
    sys.path.insert(0, str(REPO / 'scripts'))
    import keck_2026oct06_calculations as keck
    from keck_overheads import KECK_SLEW_BASE_MIN

    assert keck.MORNING_RESERVE_MIN == KECK_SLEW_BASE_MIN + keck.MORNING_STANDARD_MIN
    assert keck.MORNING_RESERVE_MIN < 30
