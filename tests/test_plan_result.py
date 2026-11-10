"""Tests for the instrument-independent plan layer (Phase 0 of the GUI work).

Covers the two pieces every downstream page depends on: sun-event times
and the idle-gap derivation.

Created by JXP and Claude.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from astropy import units as u
from astropy.coordinates import EarthLocation

from night_planner.plan_result import PlanResult, ScheduledTarget, SunEvents
from night_planner.sun_events import find_sun_events

KECK = EarthLocation(lat=19.828333 * u.deg, lon=-155.478333 * u.deg,
                     height=4160 * u.m)
LICK = EarthLocation(lat=37.3414 * u.deg, lon=-121.6429 * u.deg,
                     height=1283 * u.m)
HST = ZoneInfo('Pacific/Honolulu')
PACIFIC = ZoneInfo('America/Los_Angeles')


def test_sun_events_match_keck_scripts():
    """18 deg twilight agrees with keck_2026oct06_calculations' own search.

    Inputs: none (fixed site/date).
    Outputs: none (asserts on success).
    """
    sun = find_sun_events('2026-10-06', KECK, HST)
    # That script's minute-stepping search reports 19:19 / 05:02; the
    # interpolated crossing lands within a minute of it (and is the more
    # precise of the two, since the search always rounds late).
    assert sun.dusk_astronomical.strftime('%H:%M') in ('19:18', '19:19')
    assert sun.dawn_astronomical.strftime('%H:%M') in ('05:01', '05:02')


def test_sun_events_match_lick_sunset_definition():
    """Sunset/sunrise use -0.833 deg, matching the Lick night-2 diagnostic.

    Inputs: none (fixed site/date).
    Outputs: none (asserts on success).
    """
    sun = find_sun_events('2026-09-15', LICK, PACIFIC)
    assert sun.sunset.strftime('%H:%M') == '19:14'
    assert sun.sunrise.strftime('%H:%M') == '06:50'


def test_sun_events_are_ordered_and_dst_aware():
    """Events run sunset -> dawn in order, and Lick resolves to PDT in September.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    sun = find_sun_events('2026-09-15', LICK, PACIFIC)
    ordered = [sun.sunset, sun.dusk_nautical, sun.dusk_astronomical,
               sun.dawn_astronomical, sun.dawn_nautical, sun.sunrise]
    assert ordered == sorted(ordered)
    assert sun.sunset.utcoffset() == timedelta(hours=-7)  # PDT, not PST


def _target(start_h, start_m, dur_min, slew_min=0):
    start = datetime(2026, 10, 6, start_h, start_m, tzinfo=HST)
    science = start + timedelta(minutes=slew_min)
    return ScheduledTarget(
        name='T', ra_deg=0.0, dec_deg=0.0, mag=20.0, mode='longslit',
        start=start, science_start=science,
        end=science + timedelta(minutes=dur_min),
        slew_min=slew_min, on_target_min=dur_min)


def _plan(schedule, blocks=()):
    return PlanResult(
        instrument='lris', telescope='Keck I', date='2026-10-06',
        output_dir='/tmp', timezone=str(HST),
        sun=SunEvents(*[datetime(2026, 10, 6, 20, 0, tzinfo=HST)] * 6),
        night_start=datetime(2026, 10, 6, 20, 0, tzinfo=HST),
        night_end=datetime(2026, 10, 7, 4, 0, tzinfo=HST),
        schedule=list(schedule), blocks=list(blocks))


def test_idle_gaps_exclude_scheduled_and_blocked_time():
    """Idle is the complement of science, slew and blocked windows.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    plan = _plan(
        schedule=[_target(20, 30, 60, slew_min=10),   # 20:30 slew -> 21:40
                  _target(23, 0, 60)],                 # 23:00 -> 00:00
        blocks=[(datetime(2026, 10, 6, 22, 0, tzinfo=HST),
                 datetime(2026, 10, 6, 22, 30, tzinfo=HST), 'ToO')])
    gaps = [(a.strftime('%H:%M'), b.strftime('%H:%M')) for a, b in plan.idle_gaps()]
    assert gaps == [('20:00', '20:30'), ('21:40', '22:00'),
                    ('22:30', '23:00'), ('00:00', '04:00')]


def test_summary_counts_slew_separately_from_on_target():
    """Slew time is reported but doesn't inflate on-target or utilization.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    plan = _plan(schedule=[_target(20, 30, 60, slew_min=10)])
    summary = plan.summary()
    assert summary['on_target_min'] == 60
    assert summary['slew_min'] == 10
    assert summary['n_scheduled'] == 1
    # 480 min night, 60 on target, 70 min busy -> 410 idle
    assert summary['idle_min'] == 410
    assert round(summary['utilization'], 3) == round(60 / 480, 3)


def test_plan_result_is_json_serializable():
    """to_dict() produces something json.dumps can take (the API contract).

    Inputs: none.
    Outputs: none (asserts on success).
    """
    import json

    plan = _plan(schedule=[_target(20, 30, 60, slew_min=10)])
    json.dumps(plan.to_dict())
