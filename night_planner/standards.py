"""
Flux standards for a night, drawn from the PypeIt reduction library.

The library lives in chime-ffff-pz
(`chime_ffff_pz/pypeit_reduce/standard_star_library.py`) and is read from
there rather than copied, so a standard added for the reduction side is
automatically available for planning. That package isn't installed in this
environment, so it is imported by path.

Created by JXP and Claude
"""

import importlib.util
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import AltAz, SkyCoord
from astropy.time import Time

from .paths import ffffpz_module


# Resolved lazily rather than at import: a machine without the FFFF-PZ
# checkout must still be able to import this module -- only the callers that
# actually read the library should fail, and then with a message naming the
# variable to set.
def library_path():
    """Path to the PypeIt standard-star library in the FFFF-PZ checkout.

    Created by JXP and Claude

    Inputs
    ------
    none (reads FFFF_PZ_REPO via night_planner.paths).

    Outputs
    -------
    Path to standard_star_library.py.
    """
    return ffffpz_module('pypeit_reduce', 'standard_star_library.py')


def load_library(path=None):
    """
    Load the PypeIt standard-star library.

    Parameters
    ----------
    path : Path, optional
        Defaults to library_path(), i.e. wherever FFFF_PZ_REPO points.

    Returns
    -------
    dict : name -> SkyCoord

    Raises
    ------
    FileNotFoundError
        If the chime-ffff-pz checkout isn't where it's expected.
    """
    path = Path(path) if path else library_path()
    if not path.exists():
        raise FileNotFoundError(
            f'standard-star library not found at {path} -- it lives in the '
            f'chime-ffff-pz repo; pass an explicit path if that moved')

    spec = importlib.util.spec_from_file_location('standard_star_library', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault('standard_star_library', module)
    spec.loader.exec_module(module)
    return {name: star.coord
            for name, star in module.load_standard_star_library().items()}


def airmass_at(coord, when, location):
    """
    Airmass and altitude of a coordinate at one instant.

    Returns
    -------
    (airmass, alt_deg, az_deg) -- airmass is None below the horizon.
    """
    altaz = coord.transform_to(AltAz(obstime=Time(when), location=location))
    alt = float(altaz.alt.deg)
    if alt <= 0:
        return None, alt, float(altaz.az.deg)
    return 1.0 / np.sin(np.radians(alt)), alt, float(altaz.az.deg)


def rank_standards(when, location, library=None, max_airmass=2.0, limit=None):
    """
    Standards observable at a given time, best (lowest airmass) first.

    Parameters
    ----------
    when : datetime (tz-aware)
    location : astropy EarthLocation
    library : dict, optional
        name -> SkyCoord; loaded from the PypeIt library if omitted.
    max_airmass : float
    limit : int, optional
        Keep only the best N.

    Returns
    -------
    list of dict with 'name', 'coord', 'airmass', 'alt', 'az'
    """
    library = library if library is not None else load_library()

    ranked = []
    for name, coord in library.items():
        airmass, alt, az = airmass_at(coord, when, location)
        if airmass is None or airmass > max_airmass:
            continue
        ranked.append({'name': name, 'coord': coord, 'airmass': airmass,
                       'alt': alt, 'az': az})

    ranked.sort(key=lambda s: s['airmass'])
    return ranked[:limit] if limit else ranked


def pick_bracketing_standards(plan, location, library=None, max_airmass=2.0):
    """
    Choose one standard for the start of the night and one for the end.

    A flux standard wants to be taken close in time *and* airmass to the
    science frames it calibrates, so these are picked at the moments they
    would actually be observed rather than from a fixed pair.

    Parameters
    ----------
    plan : PlanResult
    location : astropy EarthLocation

    Returns
    -------
    dict with 'evening' and 'morning', each a ranked-standard dict or None
    """
    library = library if library is not None else load_library()

    evening_at = plan.night_start + timedelta(minutes=2)
    morning_at = (max(t.end for t in plan.schedule) + timedelta(minutes=10)
                  if plan.schedule else plan.night_end)

    evening = rank_standards(evening_at, location, library, max_airmass, limit=1)
    morning = rank_standards(morning_at, location, library, max_airmass, limit=1)
    return {
        'evening': {**evening[0], 'when': evening_at} if evening else None,
        'morning': {**morning[0], 'when': morning_at} if morning else None,
    }


def starlist_row(name, coord, comment='', style='keck'):
    """
    One starlist row, in the requested observatory's dialect.

    The two differ in more than cosmetics, so the style is explicit:

    - keck: Dec carries an explicit '+', and rows may take trailing
      keywords (rotdest/raoffset) and '#' comments.
    - lick: Dec is unsigned when positive and rows are bare -- the Mt
      Hamilton format takes no keywords, and the schedule annotations
      live in the target list rather than the starlist.
      (mthamilton.ucolick.org/techdocs/telescopes/starlistFormat.html)
    """
    ra = coord.ra.to_string(unit=u.hour, sep=' ', precision=2, pad=True)
    dec = coord.dec.to_string(sep=' ', precision=1, pad=True,
                               alwayssign=(style == 'keck'))
    if style == 'lick':
        return f'{name:<16} {ra} {dec} 2000.0 '
    row = f'{name:<16}{ra} {dec} 2000.0'
    return f'{row}  # {comment}' if comment else row
