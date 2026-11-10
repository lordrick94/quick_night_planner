"""Telescope limits (Milestone 9, T3.6).

Created by JXP and Claude.

Keck I: no tracking above 88.9 deg; a guiding warning above 85 deg. Shane:
every slit PA has a Cassegrain tub setting (helpful_scripts/calcint.c).
"""

import contextlib
import io
import sys

import pandas as pd
import pytest

from tests.lris_offline import REPO

sys.path.insert(0, str(REPO / 'scripts'))


def test_keck_zenith_limit_rejects_above_88_9():
    """check_keck_limits refuses 89.5 deg elevation and accepts 80 deg.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    import keck_2026oct06_calculations as keck
    ok, reason = keck.check_keck_limits(0, 20, 0.0, 89.5, 180.0)
    assert not ok and 'zenith' in reason
    assert keck.check_keck_limits(0, 20, 0.0, 80.0, 180.0)[0]


def test_tub_settings_cover_every_pa():
    """For PA 0-360 both tub settings stay inside calcint.c's table range.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    from night_planner.lick_tub import tub_settings
    for pa in range(0, 361, 5):
        t = tub_settings(pa)
        for v in (t['tub'], t['alt_tub']):
            assert 17.45 - 1e-6 <= v <= 330.64 + 1e-6, (pa, v)


def _one_target(tmp_path, name, ra, dec, mag=20.0):
    df = pd.DataFrame([{'name': name, 'ra_deg': ra, 'dec_deg': dec, 'mag': mag}])
    path = tmp_path / f'{name}.csv'
    df.to_csv(path, index=False)
    from night_planner.cli import generate_plan
    with contextlib.redirect_stdout(io.StringIO()):
        return generate_plan('lris', ['--targets-csv', str(path), '--output-dir',
                                      str(tmp_path / name), '--date', '2026-10-15'])


def test_near_zenith_block_is_flagged_and_far_one_is_not(tmp_path):
    """A target transiting at ~87 deg during its block gets the guiding
    warning; one transiting at ~60 deg doesn't.

    Keck is at latitude +19.83, so Dec +22.8 transits at ~87 deg. RA is set
    to the LST at 19:45 HST, so transit falls inside the first block.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from night_planner.adapters import SITES
    from night_planner.sky import lst_hours

    # Put transit early in the night, so the first (and only) block spans it.
    when = datetime(2026, 10, 15, 19, 45, tzinfo=ZoneInfo('Pacific/Honolulu'))
    ra = float(lst_hours([when], SITES['lris']['location'])[0]) * 15.0
    near = _one_target(tmp_path, 'NEARZEN', ra, 22.8)
    far = _one_target(tmp_path, 'FARZEN', ra, 50.0)
    assert near.schedule and far.schedule
    assert 'stable guiding not guaranteed' in near.schedule[0].notes
    assert 'guiding' not in far.schedule[0].notes


def test_blocks_never_straddle_the_zenith_keyhole(tmp_path):
    """A target transiting at ~89.6 deg (Dec +20.2) is still scheduled, but
    its block never includes the minutes above 88.9 deg.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from night_planner.adapters import SITES
    from night_planner.sky import lst_hours, track

    loc = SITES['lris']['location']
    when = datetime(2026, 10, 15, 20, 30, tzinfo=ZoneInfo('Pacific/Honolulu'))
    ra = float(lst_hours([when], loc)[0]) * 15.0
    plan = _one_target(tmp_path, 'KEYHOLE', ra, 20.2)
    assert plan.schedule, 'a near-zenith target must still be schedulable'
    t = plan.schedule[0]
    n = int((t.end - t.start).total_seconds() // 60)
    times = [t.start + timedelta(minutes=i) for i in range(n + 1)]
    assert max(track(ra, 20.2, times, loc)['alt']) <= 88.9
