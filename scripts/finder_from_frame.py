"""
Draw a finder chart showing how a Kast frame was *actually* observed.

Planning finders answer "where should the slit go". This answers the
other question, the one that comes up when a reduced spectrum looks
wrong: where did the slit actually lie? Everything here is read back out
of the frame's own header -- the pointing, the exposure, the slit width,
and `TUB`, the Cassegrain tub readout -- so the chart is a record rather
than a proposal.

The tub is inverted through `calcint.c` to a sky position angle. Because
the Shane is equatorial the tub does not track, so a block set at the
parallactic angle drifts away from it as the target moves; the caption
reports both the angle used and the parallactic angle at the start and
end of the exposure, which is what tells you how much blue light the
block lost.

Usage
-----
python scripts/finder_from_frame.py FRAME.fits [--out DIR]
                                    [--ra DEG --dec DEG]

Created by JXP and Claude
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from night_planner.adapters import SITES  # noqa: E402
from night_planner.finder import draw_finder, find_offset_star  # noqa: E402
from night_planner.parallactic import (  # noqa: E402
    parallactic_angle, parallactic_angle_from_ha)
from scripts.tub_from_header import _dms, pa_from_tub, sexagesimal_hours  # noqa: E402

LICK_LAT = 37.3414


def frame_geometry(path, ra_deg=None, dec_deg=None):
    """
    Everything needed to redraw the slit of one frame.

    Parameters
    ----------
    path : str or Path
    ra_deg, dec_deg : float, optional
        Catalogue position to use instead of the telescope pointing. The
        two normally agree to a few arcsec; the catalogue one centres the
        chart on the host rather than on wherever the telescope sat.

    Returns
    -------
    dict
    """
    header = fits.getheader(str(path))

    pointing = SkyCoord(ra=sexagesimal_hours(header['RA']) * 15.0 * u.deg,
                        dec=_dms(header['DEC']) * u.deg)
    coord = (SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg)
             if ra_deg is not None else pointing)

    start = datetime.fromisoformat(header['DATE-OBS']).replace(
        tzinfo=timezone.utc)
    exptime = float(header.get('EXPTIME') or 0.0)
    end = start + timedelta(seconds=exptime)

    location = SITES['kast']['location']
    tub = float(header['TUB'])
    slit_pa = pa_from_tub(tub)

    return {
        'header': header,
        'object': str(header.get('OBJECT', '')).strip(),
        'coord': coord,
        'pointing': pointing,
        'offset_from_pointing': float(coord.separation(pointing).arcsec),
        'start': start, 'end': end, 'exptime': exptime,
        'slit_width': _slit_width(header),
        'tub': tub,
        'slit_pa': slit_pa,
        'parallactic_at_start': parallactic_angle_from_ha(
            sexagesimal_hours(header['HA']), coord.dec.deg, LICK_LAT),
        'parallactic_at_end': parallactic_angle(
            coord.ra.deg, coord.dec.deg, end, location),
        'airmass': header.get('AIRMASS'),
    }


def _slit_width(header):
    """Slit width in arcsec from SLIT_N ('2.0 arcsec'), defaulting to 2."""
    try:
        return float(str(header.get('SLIT_N', '2.0')).split()[0])
    except (ValueError, IndexError):
        return 2.0


def build(path, out_dir, ra_deg=None, dec_deg=None):
    """
    Write the chart and return what was drawn.

    Parameters
    ----------
    path : str or Path
    out_dir : str or Path
    ra_deg, dec_deg : float, optional

    Returns
    -------
    dict
    """
    g = frame_geometry(path, ra_deg, dec_deg)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f'{g["object"] or Path(path).stem}_{Path(path).stem}_observed.png'

    try:
        star = find_offset_star(g['coord'])
    except Exception as err:                       # catalogue unreachable
        star = None
        print(f'  no offset star ({type(err).__name__}: {err})')

    drift = abs((g['parallactic_at_end'] - g['parallactic_at_start'] + 90)
                % 180 - 90)
    subtitle = (f"observed {g['start']:%Y-%m-%d %H:%M} UT · {g['exptime']:.0f} s "
                f"· TUB {g['tub']:.2f} → PA {g['slit_pa'] % 180:.2f}")
    note = (f"as observed; parallactic was "
            f"{g['parallactic_at_start']:.1f} deg at the start")

    draw_finder(g['coord'], g['object'] or Path(path).stem, png,
                g['slit_pa'] % 180.0,
                offset_star=star,
                slit_length_arcmin=SITES['kast']['slit_length_arcmin'],
                slit_width_arcsec=g['slit_width'],
                subtitle=subtitle, slit_note=note,
                rotator_note=(f"Cass tub as recorded = {g['tub']:.2f}; "
                              f"parallactic drifted {drift:.1f} deg during "
                              f"the exposure"))
    g['png'] = str(png)
    return g


def main():
    """Draw the chart and print what the header said."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('frame')
    ap.add_argument('--out', default='.')
    ap.add_argument('--ra', type=float, default=None,
                    help='catalogue RA in degrees, overriding the pointing')
    ap.add_argument('--dec', type=float, default=None)
    args = ap.parse_args()

    g = build(args.frame, args.out, args.ra, args.dec)
    print(f"{g['object']}  {Path(args.frame).name}")
    print(f"  observed   : {g['start']:%Y-%m-%d %H:%M:%S} UT, "
          f"{g['exptime']:.0f} s, airmass {g['airmass']:.2f}")
    print(f"  slit        : {g['slit_width']:.1f}\" wide")
    print(f"  TUB         : {g['tub']:.2f}")
    print(f"  sky PA      : {g['slit_pa'] % 180:.2f} deg "
          f"(or {g['slit_pa'] % 180 + 180:.2f})")
    print(f"  parallactic : {g['parallactic_at_start']:.2f} deg at the start, "
          f"{g['parallactic_at_end']:.2f} at the end")
    # A supplied position that disagrees with where the telescope was
    # actually pointed is far more likely to be a bad catalogue row than
    # a mispointed telescope -- an FRB's *burst* coordinate standing in
    # for its host, most often, which is a few arcsec away and misses a
    # 2" slit completely.
    slop = g['offset_from_pointing']
    if slop > g['slit_width']:
        print(f"  WARNING: the position given is {slop:.1f}\" from where the "
              f"telescope was pointed,\n           which is more than the "
              f"{g['slit_width']:.1f}\" slit width. The frame cannot show "
              f"both.\n           Check it is the host position and not the "
              f"burst position.")
    elif slop > 1:
        print(f"  chart centred {slop:.1f}\" from the telescope pointing "
              f"(position given on the command line used)")
    print(f"  wrote {g['png']}")


if __name__ == '__main__':
    main()
