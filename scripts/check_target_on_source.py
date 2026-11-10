"""
Is the position we point at actually on a source?

A finder chart can be geometrically perfect and still be wrong, because
the slit is drawn around whatever coordinate it was given. If that
coordinate is a few arcsec off the galaxy -- a stale catalogue row, the
burst position used instead of the host, a sign slip in an offset -- the
chart looks convincing and the spectrum comes back empty.

This measures it: detect sources in the image cutout and report how far
each supplied position sits from the nearest one. It compares candidate
positions against each other too, which is what distinguishes "the
catalogue is wrong" from "the telescope was pointed wrong".

Usage
-----
python scripts/check_target_on_source.py RA DEC [--also RA DEC --label NAME]

Created by JXP and Claude
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.stats import sigma_clipped_stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from night_planner.finder import fetch_image  # noqa: E402


def detect_sources(data, wcs, fwhm=3.0, threshold_sigma=5.0):
    """
    Find point-like sources in a cutout.

    Parameters
    ----------
    data : ndarray
    wcs : astropy WCS
    fwhm : float
        Expected FWHM in pixels.
    threshold_sigma : float

    Returns
    -------
    (SkyCoord array, ndarray of peak values); empty arrays if none found.
    """
    from photutils.detection import DAOStarFinder

    clean = np.nan_to_num(data.astype(float))
    _, median, std = sigma_clipped_stats(clean, sigma=3.0)
    finder = DAOStarFinder(fwhm=fwhm, threshold=threshold_sigma * std)
    found = finder(clean - median)
    if found is None or not len(found):
        return SkyCoord([], [], unit='deg'), np.array([])

    coords = wcs.pixel_to_world(np.asarray(found['xcentroid']),
                                np.asarray(found['ycentroid']))
    return coords, np.asarray(found['peak'])


def nearest(position, sources, peaks):
    """
    Nearest detected source to a position.

    Returns
    -------
    dict with 'sep_arcsec', 'coord', 'peak', or None when nothing found.
    """
    if not len(sources):
        return None
    seps = position.separation(sources).arcsec
    i = int(np.argmin(seps))
    return {'sep_arcsec': float(seps[i]), 'coord': sources[i],
            'peak': float(peaks[i])}


def check(positions, fov_arcmin=2.0, survey='CDS/P/PanSTARRS/DR1/r'):
    """
    Compare each labelled position with the nearest detected source.

    Parameters
    ----------
    positions : list of (label, SkyCoord)
    fov_arcmin : float
        Small by default -- this is about a few arcsec, not the field.

    Returns
    -------
    list of dict
    """
    centre = positions[0][1]
    data, wcs = fetch_image(centre, fov_arcmin=fov_arcmin, pixels=600,
                             survey=survey)
    pixel_scale = fov_arcmin * 60.0 / 600.0

    sources, peaks = detect_sources(data, wcs)
    rows = []
    for label, position in positions:
        hit = nearest(position, sources, peaks)
        rows.append({'label': label, 'position': position, 'nearest': hit})
    return rows, len(sources), pixel_scale


def main():
    """Report how far each position is from real light."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('ra', type=float)
    ap.add_argument('dec', type=float)
    ap.add_argument('--label', default='position 1')
    ap.add_argument('--also', nargs=2, type=float, action='append',
                    default=[], metavar=('RA', 'DEC'))
    ap.add_argument('--also-label', action='append', default=[])
    ap.add_argument('--fov', type=float, default=2.0)
    args = ap.parse_args()

    positions = [(args.label, SkyCoord(ra=args.ra * u.deg,
                                        dec=args.dec * u.deg))]
    for i, (ra, dec) in enumerate(args.also):
        label = (args.also_label[i] if i < len(args.also_label)
                 else f'position {i + 2}')
        positions.append((label, SkyCoord(ra=ra * u.deg, dec=dec * u.deg)))

    rows, n_sources, scale = check(positions, args.fov)
    print(f'{n_sources} sources detected in a {args.fov:.1f}\' cutout '
          f'({scale:.2f}"/pixel)\n')
    for row in rows:
        hit = row['nearest']
        print(f"{row['label']}: "
              f"{row['position'].to_string('hmsdms', sep=':', precision=2)}")
        if hit is None:
            print('   no source detected anywhere in the cutout')
            continue
        print(f"   nearest source {hit['sep_arcsec']:.2f}\" away at "
              f"{hit['coord'].to_string('hmsdms', sep=':', precision=2)}")

    if len(rows) > 1:
        a, b = rows[0]['position'], rows[1]['position']
        print(f"\n{rows[0]['label']} to {rows[1]['label']}: "
              f"{a.separation(b).arcsec:.2f}\"")


if __name__ == '__main__':
    main()
