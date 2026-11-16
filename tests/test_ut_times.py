"""Tests for UT times in blocked windows and manual starts.

Created by JXP and Claude, 2026-11-11.

'HH:MM UT' (also 'UTC', 'Z', with or without a space) is placed on the
night as the one instant between local noon on the evening date and local
noon the next day with that UT clock reading. The setup page's
"Times in: UT" switch sends block times this way. Synthetic targets only.
"""

import contextlib
import io
import sys
from datetime import datetime, timedelta, timezone

import pytest

from tests.lris_offline import REPO

sys.path.insert(0, str(REPO / 'scripts'))
from night_plan_io import OBSERVATORY_TZ, resolve_local_dt  # noqa: E402

LICK, KECK = OBSERVATORY_TZ['lick'], OBSERVATORY_TZ['keck']


@pytest.mark.parametrize('date, spec, tz, local', [
    ('2026-11-10', '06:30UT', LICK, '2026-11-10T22:30:00-08:00'),     # PST
    ('2026-11-10', '06:30 ut', LICK, '2026-11-10T22:30:00-08:00'),
    ('2026-11-10', '10:15 UTC', LICK, '2026-11-11T02:15:00-08:00'),   # after midnight
    ('2026-09-15', '04:00Z', LICK, '2026-09-15T21:00:00-07:00'),      # PDT
    ('2026-11-10', '06:30 UT', KECK, '2026-11-10T20:30:00-10:00'),
    ('2026-11-10', '14:00 UT', KECK, '2026-11-11T04:00:00-10:00'),
])
def test_ut_times_land_on_the_night(date, spec, tz, local):
    """A UT clock time becomes the right local instant on that night.

    Inputs: date, spec, tz, local (parametrized).
    Outputs: none (asserts on success).
    """
    got = resolve_local_dt(date, spec, tz)
    assert got.isoformat() == local
    want_utc = spec.upper().replace('UTC', '').replace('UT', '').replace('Z', '').strip()
    assert got.astimezone(timezone.utc).strftime('%H:%M') == want_utc.zfill(5)


def test_local_and_iso_times_are_unchanged():
    """Plain HH:MM stays local (next day before noon); ISO is used as given.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    assert resolve_local_dt('2026-11-10', '22:30', LICK).isoformat() == '2026-11-10T22:30:00-08:00'
    assert resolve_local_dt('2026-11-10', '01:00', LICK).isoformat() == '2026-11-11T01:00:00-08:00'
    iso = resolve_local_dt('2026-11-10', '2026-11-11T06:30Z', LICK)
    assert iso == datetime(2026, 11, 11, 6, 30, tzinfo=timezone.utc)


def test_kast_ut_block_matches_the_same_block_in_local_time(tmp_path):
    """--block in UT and the same window in local time give the same plan.

    2026-10-15 at Lick is PDT (UTC-7): 06:30-07:30 UT = 23:30-00:30 local.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    from night_planner.cli import generate_plan

    def plan(block, out):
        with contextlib.redirect_stdout(io.StringIO()):
            return generate_plan('kast', [
                '--targets-csv', str(REPO / 'test_targs' / 'autumn_ffffpz.csv'),
                '--output-dir', str(tmp_path / out), '--date', '2026-10-15',
                '--block', block])

    ut = plan('06:30 UT-07:30 UT@ToO', 'ut')
    local = plan('23:30-00:30@ToO', 'local')
    start, end = ut.blocks[0][0], ut.blocks[0][1]      # (start, end, reason)
    assert (start.strftime('%H:%M'), end.strftime('%H:%M')) == ('23:30', '00:30')
    assert start.utcoffset() == timedelta(hours=-7)
    assert [(t.name, t.start) for t in ut.schedule] == [(t.name, t.start) for t in local.schedule]
    # No science inside the block. (The 5-min slew + acquisition before a
    # target can still sit at the block's end -- see the 2026-11-11 log.)
    for t in ut.schedule:
        assert t.end <= start or t.science_start >= end
