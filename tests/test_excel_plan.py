"""Tests for the general Excel night-plan builder (night_planner.excel_plan).

Created by JXP and Claude

All plans here are synthetic (made-up names and positions). The format being
reproduced is documented in docs/excel_night_plan_format.md.
"""

import io
import shutil
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import openpyxl
import pytest

from night_planner import excel_plan as xp
from night_planner.plan_result import PlanResult, ScheduledTarget, SunEvents
from night_planner.plan_store import save_plan

HST = ZoneInfo('Pacific/Honolulu')
PACIFIC = ZoneInfo('America/Los_Angeles')


def _target(name, start, slew, science, tz, ra=150.0, dec=20.0):
    """A made-up scheduled target: `slew` then `science` minutes from `start`."""
    return ScheduledTarget(
        name=name, ra_deg=ra, dec_deg=dec, mag=20.5, mode='longslit',
        start=start, science_start=start + timedelta(minutes=slew),
        end=start + timedelta(minutes=slew + science), slew_min=slew,
        on_target_min=science, exposure_red='3 x 600', exposure_blue='1 x 1800',
        tags='TEST-TAG')


def _plan(instrument='lris', date='2026-10-06', tz=HST, blocks=()):
    """
    A synthetic one-night plan: two standards/focus overheads, three targets
    with a gap between the 2nd and 3rd, and optional blocks.

    Inputs: instrument, date (YYYY-MM-DD), tz, blocks [(start, end, reason)].
    Outputs: PlanResult.
    """
    y, m, d = map(int, date.split('-'))
    t0 = datetime(y, m, d, 19, 30, tzinfo=tz)
    end = datetime(y, m, d, 5, 0, tzinfo=tz) + timedelta(days=1)
    sun = SunEvents(sunset=t0 - timedelta(minutes=70),
                    dusk_nautical=t0 - timedelta(minutes=40),
                    dusk_astronomical=t0 - timedelta(minutes=10),
                    dawn_astronomical=end, dawn_nautical=end + timedelta(minutes=25),
                    sunrise=end + timedelta(minutes=70))
    overheads = [(t0, t0 + timedelta(minutes=5), 'Evening standard (BD+28 4211)'),
                 (t0 + timedelta(minutes=5), t0 + timedelta(minutes=10), 'Focus check')]
    schedule = [
        _target('SIMA', t0 + timedelta(minutes=10), 10, 60, tz),
        _target('SIMB', t0 + timedelta(minutes=80), 5, 90, tz, ra=200.0, dec=-10.5),
        _target('SIMC', t0 + timedelta(minutes=240), 8, 45, tz, ra=330.25, dec=45.0),
    ]
    return PlanResult(
        instrument=instrument, telescope='Keck I' if instrument == 'lris' else 'Shane 3m (Lick)',
        date=date, output_dir='/tmp', timezone=str(tz), sun=sun,
        night_start=t0, night_end=end, schedule=schedule,
        overheads=overheads, blocks=list(blocks))


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------

@pytest.mark.parametrize('date,name', [('2026-05-15', 'May 15th'), ('2026-10-01', 'Oct 1st'),
                                        ('2026-10-02', 'Oct 2nd'), ('2026-08-23', 'Aug 23rd'),
                                        ('2026-08-11', 'Aug 11th'), ('2026-08-12', 'Aug 12th'),
                                        ('2026-08-13', 'Aug 13th'), ('2026-08-21', 'Aug 21st')])
def test_sheet_names_follow_the_reference_style(date, name):
    """'May 15th' style, including the 11th-13th exceptions.

    Inputs: date, expected name (parametrized).
    Outputs: none (asserts on success).
    """
    assert xp.sheet_name_for(date) == name


def test_coordinates_are_sexagesimal_text():
    """RA in hours, Dec signed; both strings, never numbers.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    assert xp.ra_text(150.0) == '10:00:00.00'
    assert xp.dec_text(-10.5) == '-10:30:00.0'
    assert xp.dec_text(5.0).startswith('+05:')
    assert xp.ra_text(None) == '' and xp.dec_text(float('nan')) == ''


@pytest.mark.parametrize('date,tz,ut', [('2026-10-06', HST, 10.0),
                                         ('2026-05-15', PACIFIC, 7.0),
                                         ('2026-12-15', PACIFIC, 8.0)])
def test_ut_offset_follows_zone_and_daylight_saving(date, tz, ut):
    """UT - local is computed per night: HST +10, PDT +7, PST +8.

    Inputs: date, tz, expected offset in hours (parametrized).
    Outputs: none (asserts on success).
    """
    plan = _plan(date=date, tz=tz)
    got, lst, _ = xp.time_offsets(plan, None)
    assert got == pytest.approx(ut) and lst is None


# --------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------

def test_timeline_is_contiguous_and_covers_the_night():
    """Each row starts where the previous ends; idle fills the gaps; the
    durations add up to (night end - first row start).

    Inputs: none.
    Outputs: none (asserts on success).
    """
    plan = _plan()
    rows = xp.timeline_rows(plan)
    for a, b in zip(rows, rows[1:]):
        assert a['start'] + timedelta(minutes=a['minutes']) == b['start']
    total = sum(r['minutes'] for r in rows)
    assert rows[0]['start'] + timedelta(minutes=total) == plan.night_end
    actions = [r['action'] for r in rows]
    assert actions[0] == 'Start (~12 deg twilight)'
    assert actions[-1] == 'End of night'
    assert actions.count(xp.SCIENCE) == 3
    assert actions.count(xp.SLEW) == 3
    assert 'idle (nothing scheduled)' in actions
    std = next(r for r in rows if r['action'] == xp.STANDARD)
    assert std['target'] == 'BD+28 4211'


def test_slew_precedes_science_with_the_plans_durations():
    """A target is a slew row (slew_min) then a science row (the rest).

    Inputs: none.
    Outputs: none (asserts on success).
    """
    rows = xp.timeline_rows(_plan())
    i = next(i for i, r in enumerate(rows) if r.get('target') == 'SIMB')
    assert rows[i]['action'] == xp.SLEW and rows[i]['minutes'] == 5
    sci = rows[i + 1]
    assert sci['action'] == xp.SCIENCE and sci['minutes'] == 90
    assert sci['ra'] == '13:20:00.00' and sci['dec'] == '-10:30:00.0'
    assert sci['red'] == '3 x 600' and sci['blue'] == '1 x 1800'
    assert 'TEST-TAG' in sci['comment']


def test_blocks_get_their_own_rows():
    """Blocked time is a 'blocked: <reason>' row, not idle.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    t = datetime(2026, 10, 7, 2, 0, tzinfo=HST)
    rows = xp.timeline_rows(_plan(blocks=[(t, t + timedelta(minutes=30), 'clouds')]))
    blocked = [r for r in rows if r['action'] == 'blocked: clouds']
    assert len(blocked) == 1 and blocked[0]['minutes'] == 30


# --------------------------------------------------------------------
# Workbook
# --------------------------------------------------------------------

@pytest.fixture
def two_night_book(tmp_path):
    """A two-night Lick workbook (one PDT night, one PST night)."""
    plans = [_plan('kast', '2026-10-30', PACIFIC), _plan('kast', '2026-11-02', PACIFIC)]
    path = xp.build_workbook(plans, tmp_path / 'run.xlsx', sec_mags={'SIMA': 21.3})
    return openpyxl.load_workbook(path)


def test_workbook_sheets_in_reference_order(two_night_book):
    """Checklist, one sheet per night, summary, tracking -- no hidden sheet.

    Inputs: two_night_book (fixture).
    Outputs: none (asserts on success).
    """
    assert two_night_book.sheetnames == ['Observing Checklist', 'Oct 30th', 'Nov 2nd',
                                         'FRB Observing Summary', 'Post Observing Tracking']
    assert all(ws.sheet_state == 'visible' for ws in two_night_book.worksheets)


def test_night_sheet_headers_formulas_and_zone(two_night_book):
    """Real zone in headers (PDT before, PST after the change); C chains to E
    above; E = C + D; A and B reference the offset cells.

    Inputs: two_night_book (fixture).
    Outputs: none (asserts on success).
    """
    pdt, pst = two_night_book['Oct 30th'], two_night_book['Nov 2nd']
    assert pdt['C1'].value == 'Start (PDT)' and pst['C1'].value == 'Start (PST)'
    assert pdt['V3'].value.hour == 7 and pst['V3'].value.hour == 8
    ws = pdt
    assert [ws.cell(1, c).value for c in (6, 7, 8, 9, 12, 13, 15)] == [
        'Action', 'target', 'RA', 'DEC', 'red side', 'blue side', 'Comments']
    assert ws['D2'].value == 'Only edit this column'
    r = xp.FIRST_ROW + 1
    assert ws[f'C{r}'].value == f'=E{r - 1}'
    assert ws[f'E{r}'].value == f'=C{r}+D{r}'
    assert ws[f'B{r}'].value == f'=MOD(C{r}+$V$3,1)'
    assert ws[f'A{r}'].value.startswith(f'=MOD(C{r}+$V$4+(C{r}-$V$5)*')


def test_coordinates_written_as_text(two_night_book):
    """RA/Dec cells hold strings with the text format, so no spreadsheet
    can turn them into times.

    Inputs: two_night_book (fixture).
    Outputs: none (asserts on success).
    """
    ws = two_night_book['Oct 30th']
    cells = [ws.cell(r, 9) for r in range(xp.FIRST_ROW, ws.max_row + 1)
             if ws.cell(r, 6).value == xp.SCIENCE]
    assert len(cells) == 3
    assert all(isinstance(c.value, str) and c.number_format == '@' for c in cells)
    sec = [ws.cell(r, 11).value for r in range(xp.FIRST_ROW, ws.max_row + 1)
           if ws.cell(r, 7).value == 'SIMA' and ws.cell(r, 6).value == xp.SCIENCE]
    assert sec == [21.3]


def test_checklist_and_tracking_are_ready_to_use(two_night_book):
    """Done boxes start FALSE with a TRUE/FALSE drop-down; the tracking sheet
    has its five drop-downs and the targets pre-filled.

    Inputs: two_night_book (fixture).
    Outputs: none (asserts on success).
    """
    ck = two_night_book['Observing Checklist']
    done = [c.value for c in ck['B'] if isinstance(c.value, bool)]
    assert done and not any(done)
    assert len(done) == len(xp.CHECKLIST_PRE) + len(xp.CHECKLIST_POST)
    assert ck.data_validations.dataValidation
    tr = two_night_book['Post Observing Tracking']
    assert len(tr.data_validations.dataValidation) == 5
    assert [tr.cell(r, 1).value for r in (2, 3, 4)] == ['SIMA', 'SIMB', 'SIMC']
    assert tr.freeze_panes == 'A2'


def test_write_plan_excel_and_staleness(tmp_path):
    """Builds <dir>_Night_plan.xlsx beside plan_result.json; stale when the
    plan is newer than the workbook.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    d = tmp_path / 'SIM-RUN'
    save_plan(_plan(), str(d))
    assert xp.excel_is_stale(d)
    path = xp.write_plan_excel([d])
    assert path == d / 'SIM-RUN_Night_plan.xlsx' and path.exists()
    assert not xp.excel_is_stale(d)


def test_export_zip_carries_the_excel(tmp_path):
    """GET /api/export builds the workbook if needed and zips it.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from backend.app import app

    save_plan(_plan(), str(tmp_path))
    resp = TestClient(app).get('/api/export', params={'output_dir': str(tmp_path)})
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    assert f'{tmp_path.name}_Night_plan.xlsx' in names


@pytest.mark.skipif(shutil.which('soffice') is None, reason='LibreOffice not installed')
def test_formulas_recalculate_to_the_plan_times(tmp_path):
    """LibreOffice recalculation of the sheet reproduces local, UT and LST
    times for every row (scripts/verify_excel_plan.py).

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    import importlib.util
    from pathlib import Path
    d = tmp_path / 'SIM-RUN'
    save_plan(_plan(), str(d))
    path = xp.write_plan_excel([d])
    script = Path(__file__).resolve().parent.parent / 'scripts' / 'verify_excel_plan.py'
    spec = importlib.util.spec_from_file_location('verify_excel_plan', script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # In-process, so the session's offline IERS settings apply.
    _, nrows, worst = mod.verify(d, path)
    assert nrows > 5 and mod.agrees(worst), worst
