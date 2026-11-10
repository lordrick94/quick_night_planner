"""
The synthetic tables in test_targs/ behave as their README claims.

These guard the test set itself. The `bad_` tables matter most: they
exist to prove the planner refuses an ambiguous table rather than
guessing, and a regression that makes them "work" would be invisible
everywhere else.

Created by JXP and Claude
"""

from pathlib import Path

import pytest

from night_planner.targets_io import TargetTableError, load_targets

TABLE_DIR = Path(__file__).resolve().parents[1] / 'test_targs'
TABLES = sorted(TABLE_DIR.glob('*.csv'))


def test_tables_exist():
    """Regenerate with scripts/make_test_target_tables.py if this fails."""
    assert len(TABLES) >= 10


@pytest.mark.parametrize('path', [p for p in TABLES
                                   if not p.name.startswith('bad_')],
                          ids=lambda p: p.name)
def test_good_tables_load(path):
    """Every non-bad table loads and yields usable coordinates."""
    df = load_targets(path)
    assert len(df)
    assert df['ra_deg'].between(0, 360).all()
    assert df['dec_deg'].between(-90, 90).all()
    assert df['mag'].notna().all()


@pytest.mark.parametrize('path', [p for p in TABLES
                                   if p.name.startswith('bad_')],
                          ids=lambda p: p.name)
def test_bad_tables_are_refused(path):
    """Guessing is the dangerous outcome, so these must raise."""
    with pytest.raises(TargetTableError):
        load_targets(path)


def test_load_accepts_a_path_not_just_a_str():
    """A caller naturally holds a Path; it used to fail inside pandas."""
    assert len(load_targets(TABLE_DIR / 'summer_minimal.csv'))


def test_seasonal_tables_cluster_where_the_readme_says():
    """Each seasonal table sits near the RA transiting at midnight."""
    from scripts.make_test_target_tables import SEASONS

    for season, info in SEASONS.items():
        df = load_targets(TABLE_DIR / f'{season}_ffffpz.csv')
        # Circular mean, since the autumn table straddles RA 0h.
        angles = df['ra_deg'].to_numpy() * 3.141592653589793 / 180.0
        import numpy as np
        mean_h = (np.degrees(np.arctan2(np.sin(angles).mean(),
                                         np.cos(angles).mean())) / 15.0) % 24
        offset = abs((mean_h - info['ra_centre'] + 12) % 24 - 12)
        assert offset < 1.5, f'{season}: mean RA {mean_h:.1f}h'


# Declared rather than inferred from filenames: the point of these tests
# is that detection agrees with what each table is meant to be, and a
# filename rule would just restate the detector's own answer.
FFFFPZ_TABLES = {
    'autumn_ffffpz.csv', 'winter_ffffpz.csv', 'spring_ffffpz.csv',
    'summer_ffffpz.csv', 'allsky_frb_ffffpz.csv', 'dec_limits.csv',
    'faint_mos_split.csv', 't_target_required.csv',
}


def test_detected_format_matches_what_each_table_is():
    """Every table is recognised as the format it was written in."""
    import pandas as pd

    from night_planner.targets_io import detect_format

    for path in TABLE_DIR.glob('*.csv'):
        if path.name.startswith('bad_'):
            continue
        fmt = detect_format(pd.read_csv(path))
        expected = 'ffff-pz' if path.name in FFFFPZ_TABLES else 'generic'
        assert fmt['format'] == expected, path.name
        assert fmt['has_candidates'] == (expected == 'ffff-pz'), path.name


def test_ffffpz_tables_hold_only_frbs():
    """PATH ranks the hosts of a burst, so these are FRBs or nothing.

    This is the guard that stops a two-candidate slit being fitted to a
    supernova: the planner trusts the format, so the format has to be
    telling the truth.
    """
    import pandas as pd

    for name in FFFFPZ_TABLES:
        frame = pd.read_csv(TABLE_DIR / name)
        assert frame['TNS'].str.contains('FRB').all(), name


def test_secondaries_are_only_read_from_ffffpz_tables():
    """load_secondaries() refuses a generic table even if Sec_* exists."""
    from night_planner.finder import load_secondaries

    assert load_secondaries(TABLE_DIR / 'allsky_mixed.csv') == {}
    assert len(load_secondaries(TABLE_DIR / 'allsky_frb_ffffpz.csv')) > 0


def test_shane_ha_limits_are_the_published_ones():
    """East -05:40, west +03:45 -- the asymmetric Shane mount limits.

    Pinned because the east limit was -5.0 until 2026-10-14 and the
    difference is 40 minutes of window on every target that rises into
    the night. A silent revert would quietly shorten every Lick plan.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from scripts.lick_2026b02_calculations import HA_MAX, HA_MIN

    assert HA_MIN == pytest.approx(-(5 + 40 / 60))
    assert HA_MAX == pytest.approx(3 + 45 / 60)


def test_a_night_with_nothing_up_produces_an_empty_plan(tmp_path):
    """"Nothing is observable tonight" is an answer, not a crash.

    Run a winter table on a June date and no target is ever inside the
    Shane's HA window. The scheduler used to build a frame whose rows
    had no start_pst at all -- the column was absent, not empty -- and
    the run died in its own summary print.
    """
    from night_planner.cli import generate_plan

    plan = generate_plan('kast', [
        '--targets-csv', str(TABLE_DIR / 'winter_ffffpz.csv'),
        '--output-dir', str(tmp_path / 'empty'),
        '--date', '2026-06-21'])

    assert plan.schedule == []
    assert plan.decisions, 'every target should still be accounted for'
    assert all(d.status == 'rejected' for d in plan.decisions)
    assert all((d.reason or '').strip() for d in plan.decisions)


def test_a_night_crossing_a_dst_change_keeps_time_moving_forward(tmp_path):
    """Clocks changing mid-night must not reorder or shrink blocks.

    2026-03-07 at Lick: the night starts in PST and ends in PDT. Adding
    a timedelta to a DST-aware datetime is wall-clock arithmetic, so
    01:30 + 90 min lands on 03:00 -- only 30 minutes later in real time.
    That produced overlapping blocks and a 60-minute exposure spanning
    five minutes of UTC. Everything here is asserted in UTC, because
    local labels legitimately jump an hour.
    """
    from datetime import timezone

    from night_planner.cli import generate_plan

    plan = generate_plan('kast', [
        '--targets-csv', str(TABLE_DIR / 'allsky_frb_ffffpz.csv'),
        '--output-dir', str(tmp_path / 'dst'),
        '--date', '2026-03-07',
        '--start', '22:00', '--block', '01:00-02:00@weather'])

    assert len(plan.schedule) >= 3, 'need a few blocks to test ordering'
    utc = lambda when: when.astimezone(timezone.utc)      # noqa: E731

    previous = None
    for target in sorted(plan.schedule, key=lambda t: t.start):
        assert utc(target.end) > utc(target.science_start)
        elapsed = (utc(target.end)
                   - utc(target.science_start)).total_seconds() / 60
        # The block holds the exposures and their readout (T1.1, 2026-11-07).
        expected = target.on_target_min + target.readout_min
        assert elapsed == pytest.approx(expected, abs=1), (
            f'{target.name}: {elapsed:.0f} min elapsed for a '
            f'{expected:.0f} min exposure + readout')
        if previous is not None:
            assert utc(target.start) >= utc(previous.end)
        previous = target
