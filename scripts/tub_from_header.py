"""
Recover the sky position angle a Kast frame was taken at, from its TUB.

A Kast header records `TUB`, the Cassegrain tub readout, and not the slit
position angle. To know where the slit actually lay you have to invert
`calcint.c`'s table -- and that inversion is only trustworthy if the tub
reads zero at sky north, which `calcint.c` implies but no observation had
confirmed.

A frame with TUB, HA and Dec all recorded settles it. If the observer set
the slit to the parallactic angle, as is standard for a faint host, then
the parallactic angle computed from HA and Dec is the sky PA, and the
offset between it and the tub-implied angle is the zero point.

Usage
-----
python scripts/tub_from_header.py FRAME.fits [FRAME.fits ...]

Created by JXP and Claude
"""

import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from night_planner.lick_tub import cass_tub_readout  # noqa: E402
from night_planner.parallactic import parallactic_angle_from_ha  # noqa: E402

LICK_LAT = 37.3414

# calcint.c is linear: readout = 0.87 * PA + 0.05.
TUB_SCALE, TUB_OFFSET = 0.87, 0.05


def sexagesimal_hours(text):
    """
    Parse 'HH:MM:SS.ss' (or a signed version) into hours.

    Parameters
    ----------
    text : str

    Returns
    -------
    float
    """
    sign = -1.0 if str(text).strip().startswith('-') else 1.0
    parts = [abs(float(p)) for p in str(text).strip().lstrip('+-').split(':')]
    while len(parts) < 3:
        parts.append(0.0)
    return sign * (parts[0] + parts[1] / 60.0 + parts[2] / 3600.0)


def pa_from_tub(tub):
    """
    Sky position angle implied by a tub readout, inverting calcint.c.

    Parameters
    ----------
    tub : float

    Returns
    -------
    float : degrees, 0-360
    """
    return ((tub - TUB_OFFSET) / TUB_SCALE) % 360.0


def read_frame(path):
    """
    Pull what matters out of one Kast frame.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    dict
    """
    h = fits.getheader(str(path))
    ha_hours = sexagesimal_hours(h['HA'])
    dec_deg = sexagesimal_hours(h['DEC']) * 15.0 if ':' not in str(h['DEC']) \
        else _dms(h['DEC'])

    parallactic = parallactic_angle_from_ha(ha_hours, dec_deg, LICK_LAT)
    implied = pa_from_tub(float(h['TUB']))

    return {
        'file': Path(path).name,
        'object': h.get('OBJECT'),
        'date_obs': h.get('DATE-OBS'),
        'exptime': h.get('EXPTIME'),
        'ra': h.get('RA'),
        'dec': h.get('DEC'),
        'ha_hours': ha_hours,
        'dec_deg': dec_deg,
        'airmass': h.get('AIRMASS'),
        'slit': h.get('SLIT_N'),
        'tub': float(h['TUB']),
        'pa_from_tub': implied,
        'parallactic': parallactic,
        # Folded onto a slit axis, since a slit has no head or tail.
        'tub_minus_parallactic': float(
            abs((implied - parallactic + 90) % 180 - 90)),
        'tub_if_parallactic': cass_tub_readout(parallactic),
    }


def _dms(text):
    """Parse '+DD:MM:SS.s' into degrees."""
    sign = -1.0 if str(text).strip().startswith('-') else 1.0
    parts = [abs(float(p)) for p in str(text).strip().lstrip('+-').split(':')]
    while len(parts) < 3:
        parts.append(0.0)
    return sign * (parts[0] + parts[1] / 60.0 + parts[2] / 3600.0)


def main():
    """Report each frame, and what it says about the tub zero point."""
    paths = sys.argv[1:]
    if not paths:
        raise SystemExit('usage: tub_from_header.py FRAME.fits [...]')

    rows = [read_frame(p) for p in paths]
    for r in rows:
        print(f"{r['file']}  {r['object']}  {r['date_obs']}  "
              f"{r['exptime']:g}s  slit {r['slit']}")
        print(f"   RA {r['ra']}  Dec {r['dec']}  HA {r['ha_hours']:+.4f} h  "
              f"airmass {r['airmass']:.2f}")
        print(f"   TUB recorded        : {r['tub']:.2f}")
        print(f"   -> sky PA (calcint) : {r['pa_from_tub']:.2f} deg "
              f"(axis {r['pa_from_tub'] % 180:.2f})")
        print(f"   parallactic then    : {r['parallactic']:.2f} deg")
        print(f"   difference          : {r['tub_minus_parallactic']:.2f} deg")
        print(f"   TUB if parallactic  : {r['tub_if_parallactic']:.2f}")
        print()

    diffs = np.array([r['tub_minus_parallactic'] for r in rows])
    print(f'Across {len(rows)} frame(s): tub-implied PA differs from '
          f'parallactic by {diffs.mean():.2f} deg '
          f'(spread {diffs.std():.2f}).')
    print('A difference near zero means calcint.c\'s zero point is right '
          'and the\nslit was set to parallactic. A consistent non-zero '
          'offset is the tub\nzero point, and belongs in '
          'night_planner/lick_tub.py.')


if __name__ == '__main__':
    main()
