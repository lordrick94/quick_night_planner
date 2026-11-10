"""
Sky tracks for a whole night: airmass, altitude, hour angle, LST, moon.

This lives in the library rather than in an instrument script because
every site needs the same arithmetic and none of it is instrument
specific. The viewer used to reach into `INSTRUMENTS[...]['calc']` for
`calculate_airmass()`, which only the Keck and Lick-2026B-01 modules
happen to define -- so the airmass page raised a 500 for every Kast
plan. One vectorised implementation, used by both endpoints, removes
that whole class of failure.

Vectorised on purpose: a night chart wants every scheduled target
sampled across the night, and transforming one coordinate at a time
turns a page load into seconds of AltAz setup repeated per sample.

Created by JXP and Claude
"""

import math
from datetime import timedelta, timezone

import numpy as np
from astropy import units as u
from astropy.coordinates import AltAz, SkyCoord, get_body
from astropy.time import Time

# Airmass is meaningless below the horizon and runs away just above it;
# anything fainter than this is reported as None so a chart draws a gap.
MAX_USEFUL_AIRMASS = 6.0


def advance(when, minutes):
    """
    Move a local time forward by real elapsed minutes.

    Adding a timedelta to a DST-aware datetime does *wall-clock*
    arithmetic: Python adds to the naive fields and lets the zone
    re-derive the offset. Across a spring-forward gap that makes time
    run backwards -- 01:30 plus 90 minutes lands on 03:00, only 30
    minutes later in real time -- and a night scheduled that way comes
    out with overlapping blocks and exposures minutes long.

    Converting to UTC, adding there and converting back gives elapsed
    time, which is what an exposure and a slew actually consume. On a
    night that crosses no transition the two are identical.

    Parameters
    ----------
    when : datetime (tz-aware)
    minutes : float
        May be negative.

    Returns
    -------
    datetime, in the same timezone as `when`.
    """
    moved = when.astimezone(timezone.utc) + timedelta(minutes=minutes)
    return moved.astimezone(when.tzinfo)


def night_grid(start, end, step_min=5):
    """
    Evenly spaced sample times across a night.

    Parameters
    ----------
    start, end : datetime (tz-aware)
    step_min : int

    Returns
    -------
    list of datetime
    """
    times, when = [], start
    while when <= end:
        times.append(when)
        when += timedelta(minutes=step_min)
    return times


def _altaz(coord, times, location):
    """AltAz frame transform for one coordinate over many times."""
    frame = AltAz(obstime=Time([t for t in times]), location=location)
    return coord.transform_to(frame)


def lst_hours(times, location):
    """
    Apparent local sidereal time at each sample, in hours.

    Parameters
    ----------
    times : list of datetime (tz-aware)
    location : astropy EarthLocation

    Returns
    -------
    ndarray
    """
    return Time([t for t in times]).sidereal_time(
        'apparent', longitude=location.lon).hour


def track(ra_deg, dec_deg, times, location, lst=None):
    """
    Airmass, altitude, azimuth and hour angle for one target.

    Parameters
    ----------
    ra_deg, dec_deg : float
    times : list of datetime (tz-aware)
    location : astropy EarthLocation
    lst : ndarray, optional
        Precomputed sidereal times, to avoid recomputing per target.

    Returns
    -------
    dict of lists: 'airmass' (None below the horizon or above
    MAX_USEFUL_AIRMASS), 'alt', 'az', 'ha'
    """
    coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg)
    altaz = _altaz(coord, times, location)

    alt = np.asarray(altaz.alt.deg, dtype=float)
    az = np.asarray(altaz.az.deg, dtype=float)
    with np.errstate(divide='ignore', invalid='ignore'):
        airmass = 1.0 / np.sin(np.radians(alt))
    usable = (alt > 0) & (airmass <= MAX_USEFUL_AIRMASS)

    sidereal = lst_hours(times, location) if lst is None else lst
    ha = (sidereal - ra_deg / 15.0) % 24.0
    ha = np.where(ha > 12.0, ha - 24.0, ha)

    return {
        'airmass': [round(float(a), 3) if ok else None
                    for a, ok in zip(airmass, usable)],
        'alt': [round(float(a), 2) for a in alt],
        'az': [round(float(a), 2) for a in az],
        'ha': [round(float(h), 3) for h in ha],
    }


def moon_track(times, location):
    """
    The moon's airmass through the night, and how lit it is.

    Worth drawing: a bright moon near a target costs sky background that
    no amount of exposure time fully buys back, and the first thing an
    observer wants to know is simply whether it is up.

    Parameters
    ----------
    times : list of datetime (tz-aware)
    location : astropy EarthLocation

    Returns
    -------
    dict with 'airmass' (list, None below the horizon), 'alt' (list),
    'illumination' (0-1, at the middle of the night)
    """
    obstime = Time([t for t in times])
    moon = get_body('moon', obstime, location)
    altaz = moon.transform_to(AltAz(obstime=obstime, location=location))

    alt = np.asarray(altaz.alt.deg, dtype=float)
    with np.errstate(divide='ignore', invalid='ignore'):
        airmass = 1.0 / np.sin(np.radians(alt))
    usable = (alt > 0) & (airmass <= MAX_USEFUL_AIRMASS)

    # Illuminated fraction from the sun-moon elongation at mid-night.
    middle = obstime[len(obstime) // 2]
    sun = get_body('sun', middle, location)
    moon_mid = get_body('moon', middle, location)
    elongation = sun.separation(moon_mid).rad
    illumination = float((1.0 - np.cos(elongation)) / 2.0)

    return {
        'airmass': [round(float(a), 3) if ok else None
                    for a, ok in zip(airmass, usable)],
        'alt': [round(float(a), 2) for a in alt],
        'illumination': round(illumination, 3),
    }


def separation_deg(ra_deg, dec_deg, other):
    """
    Angular separation between a target and another SkyCoord, degrees.

    Parameters
    ----------
    ra_deg, dec_deg : float
    other : SkyCoord

    Returns
    -------
    float
    """
    coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg)
    return float(coord.separation(other).deg)


AIRMASS_RULES = ('worst', 'mid', 'best')


def block_airmass(ra_deg, dec_deg, t0, t1, rule, location, step_min=5):
    """
    The airmass to run the ETC at for a block of science (T1.3).

    Created by JXP and Claude

    Parameters
    ----------
    ra_deg, dec_deg : float
    t0, t1 : datetime (tz-aware)
        The science span, science_start to end.
    rule : str
        'worst' (highest airmass in the span; conservative, the default),
        'mid' (at the midpoint) or 'best' (lowest in the span).
    location : astropy EarthLocation
    step_min : float
        Sampling step; both ends are always sampled.

    Returns
    -------
    float, or None if the target is never usefully up in the span. Samples
    below the horizon or past MAX_USEFUL_AIRMASS count as MAX_USEFUL_AIRMASS
    for 'worst', so a span that dips out of view is never called good.
    """
    if rule not in AIRMASS_RULES:
        raise ValueError(f'airmass rule must be one of {", ".join(AIRMASS_RULES)}')
    if rule == 'mid':
        times = [t0 + (t1 - t0) / 2]
    else:
        n = max(1, int(math.ceil((t1 - t0).total_seconds() / 60 / step_min)))
        times = [t0 + (t1 - t0) * i / n for i in range(n + 1)]
    values = track(ra_deg, dec_deg, times, location)['airmass']
    good = [v for v in values if v is not None]
    if not good:
        return None
    if rule == 'best':
        return min(good)
    if rule == 'worst' and len(good) < len(values):
        return MAX_USEFUL_AIRMASS
    return max(good)
