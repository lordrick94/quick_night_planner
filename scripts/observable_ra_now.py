"""
Report the observable RA range "right now" (current date) at both
observatories this project plans for: Lick (Shane/Kast) and Keck (Keck I/LRIS).

Reuses each site's own HA mount limits and 18-degree twilight definition.
Observable RA at any clock time t is RA = LST(t) - HA, swept over the
site's [HA_MIN, HA_MAX] legal range; the night's full observable RA window
is the union of that interval from evening to morning twilight.

Created by JXP and Claude
"""

import numpy as np
from datetime import datetime, timedelta, timezone
from astropy.coordinates import EarthLocation, get_sun, AltAz
from astropy.time import Time
from astropy import units as u

# --- Site definitions -------------------------------------------------

LICK = EarthLocation(lat=37.3414 * u.deg, lon=-121.6429 * u.deg, height=1283 * u.m)
PST = timezone(timedelta(hours=-8))  # Lick calendar convention: fixed PST year-round
LICK_HA_MIN, LICK_HA_MAX = -(5 + 40 / 60), 3 + 45 / 60  # -05:40..+03:45

# Verified against astropy's EarthLocation.of_site('keck') (IRAF Observatory
# Database): lat 19.828333 deg, lon -155.478333 deg, height 4160 m.
KECK = EarthLocation(lat=19.828333 * u.deg, lon=-155.478333 * u.deg, height=4160 * u.m)
HST = timezone(timedelta(hours=-10))  # Hawaii Standard Time, no DST
KECK_HA_MIN, KECK_HA_MAX = -5.5, 5.5  # Keck I practical HA limits (hours)


def find_twilight_lst(date_str, location, tzinfo, twilight_alt=-18 * u.deg):
    """Find LST at evening and morning 18-degree twilight for a site/date."""
    local_date = datetime.strptime(date_str, '%Y-%m-%d')
    noon_local = datetime(local_date.year, local_date.month, local_date.day,
                           12, 0, 0, tzinfo=tzinfo)

    search_time = noon_local
    evening_lst = None
    for _ in range(600):
        utc_time = search_time.astimezone(timezone.utc)
        t = Time(utc_time)
        sun_altaz = get_sun(t).transform_to(AltAz(obstime=t, location=location))
        if sun_altaz.alt < twilight_alt:
            evening_lst = t.sidereal_time('apparent', longitude=location.lon).hour
            break
        search_time += timedelta(minutes=1)

    search_time = noon_local + timedelta(hours=18)
    morning_lst = None
    for _ in range(600):
        utc_time = search_time.astimezone(timezone.utc)
        t = Time(utc_time)
        sun_altaz = get_sun(t).transform_to(AltAz(obstime=t, location=location))
        if sun_altaz.alt > twilight_alt:
            morning_lst = t.sidereal_time('apparent', longitude=location.lon).hour
            break
        search_time += timedelta(minutes=1)

    return evening_lst, morning_lst


def ra_window(lst, ha_min, ha_max):
    """RA = LST - HA; sweeping HA in [ha_min, ha_max] gives the RA window."""
    ra_lo = (lst - ha_max) % 24
    ra_hi = (lst - ha_min) % 24
    return ra_lo, ra_hi


def format_ra_range(ra_lo, ra_hi):
    if ra_hi > ra_lo:
        return f"{ra_lo:.1f}h - {ra_hi:.1f}h"
    return f"{ra_lo:.1f}h - 24h and 0h - {ra_hi:.1f}h (wraps through 0h)"


def report(name, date_str, location, tzinfo, ha_min, ha_max):
    eve_lst, morn_lst = find_twilight_lst(date_str, location, tzinfo)

    eve_ra = ra_window(eve_lst, ha_min, ha_max)
    morn_ra = ra_window(morn_lst, ha_min, ha_max)

    # Full-night union: sample LST every ~10 min from evening to morning twilight
    morn_lst_unwrapped = morn_lst if morn_lst > eve_lst else morn_lst + 24
    n_samples = int((morn_lst_unwrapped - eve_lst) * 6) + 1
    lsts = np.linspace(eve_lst, morn_lst_unwrapped, max(n_samples, 2)) % 24

    # Track min/max of the window's "center" edges across the night.
    # Since the window width (ha_max - ha_min) is fixed, the union across a
    # night without a full 24h LST sweep is just the min RA_lo to max RA_hi
    # swept continuously -- safe because the window only slides, not jumps.
    los = [ra_window(lst, ha_min, ha_max)[0] for lst in lsts]
    his = [ra_window(lst, ha_min, ha_max)[1] for lst in lsts]

    print(f"\n=== {name} — {date_str} ===")
    print(f"Evening 18deg twilight LST: {eve_lst:.2f}h -> observable RA {format_ra_range(*eve_ra)}")
    print(f"Morning 18deg twilight LST: {morn_lst:.2f}h -> observable RA {format_ra_range(*morn_ra)}")
    print(f"HA mount limits: {ha_min:+.2f}h to {ha_max:+.2f}h")
    print(f"RA window at evening twilight: {format_ra_range(*eve_ra)}")
    print(f"RA window at morning twilight: {format_ra_range(*morn_ra)}")


if __name__ == '__main__':
    import sys
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')

    report("Lick (Shane 3m / Kast)", date_str, LICK, PST, LICK_HA_MIN, LICK_HA_MAX)
    report("Keck (Keck I / LRIS)", date_str, KECK, HST, KECK_HA_MIN, KECK_HA_MAX)
