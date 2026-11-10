"""
Sun-altitude crossings for a night: sunset/sunrise (0 deg), nautical
twilight (-12 deg) and astronomical twilight (-18 deg).

The instrument scripts each compute their own -18 deg twilight with a
minute-stepping search, which is fine for one threshold but gets slow and
repetitive at six. This computes the sun's altitude once across the whole
local day (vectorized) and interpolates every crossing out of that single
curve, so all six points cost about the same as one of the old searches
and land on sub-minute precision instead of the search step.

Created by JXP and Claude
"""

import numpy as np
from astropy import units as u
from astropy.coordinates import AltAz, get_sun
from astropy.time import Time
from datetime import datetime, timedelta, timezone

from .plan_result import SunEvents

# Altitudes (deg) defining each event, dusk and dawn alike. Sunset/sunrise
# is the standard -0.833 deg (upper limb, refraction-corrected), matching
# what lick_2026b02_night2_calculations.py's sunset/sunrise diagnostic
# already uses -- not a naive 0 deg, which lands ~4 min off.
SUNSET_ALT = -0.833
NAUTICAL_ALT = -12.0
ASTRONOMICAL_ALT = -18.0

_STEP_MINUTES = 2  # sampling of the altitude curve; crossings are interpolated


def sun_altitude_curve(date_str, location, tz, step_minutes=_STEP_MINUTES):
    """
    Sun altitude from local noon to local noon the next day.

    Parameters
    ----------
    date_str : str
        Local calendar date of the *evening*, 'YYYY-MM-DD'.
    location : astropy EarthLocation
    tz : tzinfo
        Local timezone (DST-aware for Lick, fixed for Keck).
    step_minutes : int

    Returns
    -------
    times_local : list of datetime (tz-aware)
    alt_deg : ndarray
    """
    local_date = datetime.strptime(date_str, '%Y-%m-%d')
    noon_local = datetime(local_date.year, local_date.month, local_date.day,
                          12, 0, 0, tzinfo=tz)
    noon_utc = noon_local.astimezone(timezone.utc)

    n = int(24 * 60 / step_minutes) + 1
    offsets = np.arange(n) * step_minutes
    times = Time(noon_utc) + offsets * u.min
    alt = get_sun(times).transform_to(
        AltAz(obstime=times, location=location)).alt.deg

    times_local = [(noon_utc + timedelta(minutes=int(o))).astimezone(tz)
                   for o in offsets]
    return times_local, alt


def _crossing(times_local, alt, threshold, descending):
    """
    First time the altitude curve crosses `threshold`, linearly interpolated.

    Parameters
    ----------
    descending : bool
        True for the evening (dusk) crossing, False for morning (dawn).

    Returns
    -------
    datetime (tz-aware), rounded to the nearest minute, or None if the sun
    never crosses that altitude on this date (polar sites / midsummer).
    """
    above = alt > threshold
    for i in range(len(alt) - 1):
        crossed_down = above[i] and not above[i + 1]
        crossed_up = not above[i] and above[i + 1]
        if not (crossed_down if descending else crossed_up):
            continue
        # Linear interpolation between the two bracketing samples.
        a0, a1 = alt[i], alt[i + 1]
        frac = 0.0 if a1 == a0 else (threshold - a0) / (a1 - a0)
        span = (times_local[i + 1] - times_local[i]).total_seconds()
        crossed = times_local[i] + timedelta(seconds=frac * span)
        return (crossed + timedelta(seconds=30)).replace(second=0, microsecond=0)
    return None


def find_sun_events(date_str, location, tz, step_minutes=_STEP_MINUTES):
    """
    All six sun events for one night at one site.

    Parameters
    ----------
    date_str : str
        Local calendar date of the evening, 'YYYY-MM-DD'.
    location : astropy EarthLocation
    tz : tzinfo

    Returns
    -------
    SunEvents
    """
    times_local, alt = sun_altitude_curve(date_str, location, tz, step_minutes)
    return SunEvents(
        sunset=_crossing(times_local, alt, SUNSET_ALT, descending=True),
        dusk_nautical=_crossing(times_local, alt, NAUTICAL_ALT, descending=True),
        dusk_astronomical=_crossing(times_local, alt, ASTRONOMICAL_ALT, descending=True),
        dawn_astronomical=_crossing(times_local, alt, ASTRONOMICAL_ALT, descending=False),
        dawn_nautical=_crossing(times_local, alt, NAUTICAL_ALT, descending=False),
        sunrise=_crossing(times_local, alt, SUNSET_ALT, descending=False),
    )
