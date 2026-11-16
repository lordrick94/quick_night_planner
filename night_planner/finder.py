"""
Finder charts for targets that aren't in FFFF-PZ.

For an arbitrary target table the given coordinates *are* the thing to
point at, so there is no host-candidate question to resolve and no need
for the FFFF-PZ record. That leaves: fetch an image, find an offset star,
and draw the slit.

The slit is drawn at the parallactic angle for the target's own scheduled
exposure (night_planner.parallactic), not fitted through a second
candidate -- so it holds the dispersed spectrum in the slit rather than
chasing a companion. The FFFF-PZ path, which does fit two candidates,
stays available behind its own switch.

Created by JXP and Claude
"""

import json
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS

# Longslit length actually drawn on the chart. LRIS's is ~2.9', matching
# what chime_ffff_pz_finder draws, so the two charts are comparable.
DEFAULT_SLIT_LENGTH_ARCMIN = 2.9
DEFAULT_SLIT_WIDTH_ARCSEC = 1.0
DEFAULT_FOV_ARCMIN = 4.0

# An offset star wants to be close enough to stay in the guider's reach,
# bright enough to acquire quickly, and not so bright it saturates.
OFFSET_MIN_MAG = 13.0
OFFSET_MAX_MAG = 19.0
OFFSET_MAX_SEP_ARCSEC = 100.0


# Second-best host candidate, as carried by the PATH columns of a target
# table (Sec_RA/Sec_Dec/...). Drawn in orange, matching chime_ffff_pz_finder,
# where orange is also the second target.
SECONDARY_COLOR = 'tab:orange'

# Marker radii, on the sky. A host candidate gets a tight ring so a close
# pair stays resolved; the offset star is isolated, so it can be wider.
CANDIDATE_RING_ARCSEC = 2.0
STAR_RING_ARCSEC = 4.0

# Below this separation the two candidates are a handful of pixels apart
# on a full-field chart, so the chart gets a zoomed inset as well.
ZOOM_SEP_ARCSEC = 12.0

# Image and catalogue services, tried in order (2026-11-10: CDS's hips2fits
# stopped answering from Lick-run machines while STScI kept working, and a
# single service left every chart blank). A dead service is given
# SERVICE_TIMEOUT_S before the next one is tried.
SERVICE_TIMEOUT_S = 12
PS1_SCALE_ARCSEC = 0.25          # Pan-STARRS cutout pixel scale
PS1_MIN_DEC = -30.0              # Pan-STARRS 3pi survey limit


def load_secondaries(targets_csv):
    """
    Second-ranked host candidates from the plan's own target table.

    A PATH run ranks the candidates it considered, and the runner-up is
    worth seeing on the chart: it says how crowded the field is, whether
    the slit happens to catch both, and which object you are *not*
    pointing at. It is read from the table the plan was built from rather
    than fetched, so an offline table carries its own candidates.

    Only an FFFF-PZ table is read. PATH ranks the host candidates of a
    *burst*, so a second candidate means nothing for a supernova or a
    DLA sightline, and a generic table that happens to carry a Sec_RA
    column is describing something else -- a neighbour, a placeholder --
    which must not be turned into a slit angle.

    Parameters
    ----------
    targets_csv : str or Path
        Any target table. Tables without Sec_RA/Sec_Dec simply have no
        secondaries, which is not an error.

    Returns
    -------
    dict : target name -> {'name', 'coord', 'mag', 'pox', 'is_frb'}
    """
    import pandas as pd

    from .targets_io import detect_mapping

    from .targets_io import detect_format

    df = pd.read_csv(targets_csv)
    if detect_format(df)['format'] != 'ffff-pz':
        return {}

    lower = {c.lower(): c for c in df.columns}
    ra_col, dec_col = lower.get('sec_ra'), lower.get('sec_dec')
    if ra_col is None or dec_col is None:
        return {}

    name_col = detect_mapping(df).columns.get('name')
    if name_col is None:
        return {}

    out = {}
    for _, row in df.iterrows():
        ra, dec = row[ra_col], row[dec_col]
        if pd.isna(ra) or pd.isna(dec):
            continue
        entry = {'coord': SkyCoord(ra=float(ra) * u.deg, dec=float(dec) * u.deg)}
        for key, column in (('name', 'sec_name'), ('mag', 'sec_mag'),
                             ('pox', 'sec_pox')):
            value = row.get(lower.get(column, ''), None)
            entry[key] = None if value is None or pd.isna(value) else value
        out[row[name_col]] = entry
    return out


def _hips2fits_image(coord, fov_arcmin, pixels, survey='CDS/P/PanSTARRS/DR1/r'):
    """
    Cutout from CDS hips2fits.

    Inputs: coord (SkyCoord), fov_arcmin (float), pixels (int), survey (HiPS id).
    Outputs: (data, wcs).
    """
    from astroquery.hips2fits import conf, hips2fits

    with conf.set_temp('timeout', SERVICE_TIMEOUT_S):
        result = hips2fits.query(
            hips=survey, width=pixels, height=pixels,
            ra=coord.ra, dec=coord.dec, fov=fov_arcmin * u.arcmin,
            projection='TAN', format='fits')
    return result[0].data, WCS(result[0].header)


def _ps1_image(coord, fov_arcmin, band='r'):
    """
    Pan-STARRS1 stacked cutout from STScI (Dec > -30).

    Inputs: coord (SkyCoord), fov_arcmin (float), band (str).
    Outputs: (data, wcs).
    """
    import io

    import requests
    from astropy.io import fits
    from astropy.table import Table

    if coord.dec.deg < PS1_MIN_DEC:
        raise ValueError(f'Dec {coord.dec.deg:.1f} is south of Pan-STARRS')
    ra, dec = coord.ra.deg, coord.dec.deg
    listing = requests.get('https://ps1images.stsci.edu/cgi-bin/ps1filenames.py',
                           params={'ra': ra, 'dec': dec, 'filters': band},
                           timeout=SERVICE_TIMEOUT_S)
    listing.raise_for_status()
    files = Table.read(listing.text, format='ascii')
    if not len(files):
        raise ValueError('no Pan-STARRS image covers this position')
    size = int(round(fov_arcmin * 60 / PS1_SCALE_ARCSEC))
    cut = requests.get('https://ps1images.stsci.edu/cgi-bin/fitscut.cgi',
                       params={'ra': ra, 'dec': dec, 'size': size,
                               'format': 'fits', 'red': files['filename'][0]},
                       timeout=4 * SERVICE_TIMEOUT_S)
    cut.raise_for_status()
    with fits.open(io.BytesIO(cut.content)) as hdul:
        return hdul[0].data.astype(float), WCS(hdul[0].header)


def _dss_image(coord, fov_arcmin):
    """
    DSS2 red cutout from STScI (all sky).

    Inputs: coord (SkyCoord), fov_arcmin (float).
    Outputs: (data, wcs).
    """
    import io

    import requests
    from astropy.io import fits

    resp = requests.get('https://archive.stsci.edu/cgi-bin/dss_search',
                        params={'v': 'poss2ukstu_red', 'r': coord.ra.deg,
                                'd': coord.dec.deg, 'e': 'J2000',
                                'h': fov_arcmin, 'w': fov_arcmin, 'f': 'fits'},
                        timeout=4 * SERVICE_TIMEOUT_S)
    resp.raise_for_status()
    with fits.open(io.BytesIO(resp.content)) as hdul:
        return hdul[0].data.astype(float), WCS(hdul[0].header)


# (label shown on the chart, fetcher(coord, fov_arcmin, pixels))
IMAGE_SOURCES = (
    ('Pan-STARRS r (CDS hips2fits)',
     lambda c, fov, px: _hips2fits_image(c, fov, px)),
    ('Pan-STARRS r (STScI)', lambda c, fov, px: _ps1_image(c, fov)),
    ('DSS2 red (STScI)', lambda c, fov, px: _dss_image(c, fov)),
)


def fetch_image(coord, fov_arcmin=DEFAULT_FOV_ARCMIN, pixels=600, sources=None):
    """
    Grab an image cutout around a position, trying each service in turn.

    Parameters
    ----------
    coord : SkyCoord
    fov_arcmin : float
    pixels : int
        Output size for services that resample (hips2fits).
    sources : sequence of (label, fetcher), optional
        Default IMAGE_SOURCES: CDS hips2fits Pan-STARRS, STScI Pan-STARRS,
        STScI DSS2 (the all-sky fallback).

    Returns
    -------
    (data, wcs, label) : the first service that answered, and its name.

    Raises
    ------
    RuntimeError listing every service's failure when none answered.
    """
    failures = []
    for label, fetch in (sources or IMAGE_SOURCES):
        try:
            data, wcs = fetch(coord, fov_arcmin, pixels)
            if data is None or not np.isfinite(data).any():
                raise ValueError('empty image')
            return data, wcs, label
        except Exception as err:
            failures.append(f'{label}: {type(err).__name__}: {str(err)[:120]}')
    raise RuntimeError('no image service answered -- ' + ' | '.join(failures))


def _vizier_gaia(server):
    """
    A Gaia DR3 cone search on one VizieR server.

    Inputs: server (str hostname).
    Outputs: callable(coord, radius_arcsec, min_mag, max_mag) ->
        (ra_deg, dec_deg, gmag) numpy arrays.
    """
    def query(coord, radius_arcsec, min_mag, max_mag):
        from astroquery.vizier import Vizier

        vizier = Vizier(columns=['RA_ICRS', 'DE_ICRS', 'Gmag'],
                        column_filters={'Gmag': f'>{min_mag} && <{max_mag}'},
                        vizier_server=server, timeout=SERVICE_TIMEOUT_S)
        vizier.ROW_LIMIT = 200
        tables = vizier.query_region(coord, radius=radius_arcsec * u.arcsec,
                                      catalog='I/355/gaiadr3')
        if not tables:
            return np.array([]), np.array([]), np.array([])
        t = tables[0]
        return (np.asarray(t['RA_ICRS'], float), np.asarray(t['DE_ICRS'], float),
                np.asarray(t['Gmag'], float))
    return query


def _esa_gaia(coord, radius_arcsec, min_mag, max_mag):
    """
    A Gaia DR3 cone search on the ESA Gaia archive (TAP, synchronous).

    Inputs: coord (SkyCoord), radius_arcsec, min_mag, max_mag (float).
    Outputs: (ra_deg, dec_deg, gmag) numpy arrays.
    """
    import requests
    from astropy.table import Table

    # The magnitude cut is applied here, not in the ADQL: on the archive it
    # defeats the positional index (2.6 s -> 50 s for a 100" cone).
    adql = (f'SELECT TOP 5000 ra, dec, phot_g_mean_mag FROM gaiadr3.gaia_source '
            f'WHERE 1=CONTAINS(POINT(ra, dec), CIRCLE({coord.ra.deg:.7f}, '
            f'{coord.dec.deg:.7f}, {radius_arcsec / 3600.0:.7f}))')
    resp = requests.post('https://gea.esac.esa.int/tap-server/tap/sync',
                         data={'REQUEST': 'doQuery', 'LANG': 'ADQL',
                               'FORMAT': 'csv', 'QUERY': adql},
                         timeout=2 * SERVICE_TIMEOUT_S)
    resp.raise_for_status()
    t = Table.read(resp.text, format='ascii.csv')
    if not len(t):
        return np.array([]), np.array([]), np.array([])
    g = np.asarray(np.ma.filled(t['phot_g_mean_mag'], np.nan), float)
    keep = (g > min_mag) & (g < max_mag)
    return (np.asarray(t['ra'], float)[keep], np.asarray(t['dec'], float)[keep],
            g[keep])


def _mast_ps1_stars(coord, radius_arcsec, min_mag, max_mag):
    """
    Point sources from the Pan-STARRS1 DR2 mean catalogue at MAST (Dec > -30).

    Point-like means rPSF - rKron < 0.05 mag (the PS1 star/galaxy rule of
    thumb: a galaxy's PSF magnitude is fainter than its Kron magnitude;
    stars scatter slightly negative); an offset star must not be a galaxy.

    Inputs: coord (SkyCoord), radius_arcsec, min_mag, max_mag (float, r band).
    Outputs: (ra_deg, dec_deg, rmag) numpy arrays.
    """
    import requests
    from astropy.table import Table

    if coord.dec.deg < PS1_MIN_DEC:
        raise ValueError(f'Dec {coord.dec.deg:.1f} is south of Pan-STARRS')
    resp = requests.get(
        'https://catalogs.mast.stsci.edu/api/v0.1/panstarrs/dr2/mean.csv',
        params={'ra': coord.ra.deg, 'dec': coord.dec.deg,
                'radius': radius_arcsec / 3600.0, 'nDetections.gte': 5,
                'columns': '[raMean,decMean,rMeanPSFMag,rMeanKronMag]'},
        timeout=2 * SERVICE_TIMEOUT_S)
    resp.raise_for_status()
    t = Table.read(resp.text, format='ascii.csv')
    if not len(t):
        return np.array([]), np.array([]), np.array([])
    psf = np.asarray(t['rMeanPSFMag'], float)
    kron = np.asarray(t['rMeanKronMag'], float)
    keep = ((psf > min_mag) & (psf < max_mag) & (kron > 0)
            & (psf - kron < 0.05))
    return (np.asarray(t['raMean'], float)[keep],
            np.asarray(t['decMean'], float)[keep], psf[keep])


# (label, band of the magnitude, query), tried in order. The CfA VizieR
# mirror is deliberately absent: on 2026-11-10 it served Gaia DR3 as a
# malformed table that astroquery reads as "no stars" -- a silent failure,
# worse than an error -- while CDS gave 404 and ESA was intermittent (503,
# timeouts). Pan-STARRS at MAST (STScI) is the backstop.
GAIA_SOURCES = (
    ('Gaia DR3 (VizieR CDS)', 'G', _vizier_gaia('vizier.cds.unistra.fr')),
    ('Gaia DR3 (ESA archive)', 'G', _esa_gaia),
    ('Pan-STARRS1 DR2 (MAST)', 'r', _mast_ps1_stars),
)


def gaia_stars(coord, radius_arcsec, min_mag, max_mag, sources=None):
    """
    Gaia DR3 stars in a cone, from the first catalogue service that answers.

    Parameters
    ----------
    coord : SkyCoord
    radius_arcsec, min_mag, max_mag : float
    sources : sequence of (label, band, query), optional; default GAIA_SOURCES

    Returns
    -------
    (ra_deg, dec_deg, mag, label, band)

    Raises
    ------
    RuntimeError listing every service's failure when none answered.
    """
    failures = []
    for label, band, query in (sources or GAIA_SOURCES):
        try:
            ra, dec, mag = query(coord, radius_arcsec, min_mag, max_mag)
            return ra, dec, mag, label, band
        except Exception as err:
            failures.append(f'{label}: {type(err).__name__}: {str(err)[:100]}')
    raise RuntimeError('no star catalogue answered -- ' + ' | '.join(failures))


def find_offset_star(coord, max_sep_arcsec=OFFSET_MAX_SEP_ARCSEC,
                      min_mag=OFFSET_MIN_MAG, max_mag=OFFSET_MAX_MAG):
    """
    Nearest usable offset star: Gaia DR3, or Pan-STARRS1 when no Gaia
    service answers.

    Returns
    -------
    dict with 'coord', 'mag', 'sep_arcsec', 'offset_ra', 'offset_dec'
    (offsets run star -> target, in arcsec, matching the starlist
    convention), 'catalog' (which service answered) and 'band' (of
    'mag': G for Gaia, r for Pan-STARRS), or None if
    nothing suitable is in range.

    Raises
    ------
    RuntimeError when no catalogue service answered (so a caller can tell
    "no star" from "no catalogue").
    """
    ra, dec, gmag, label, band = gaia_stars(coord, max_sep_arcsec, min_mag, max_mag)
    if not len(ra):
        return None
    stars = SkyCoord(ra, dec, unit='deg')
    seps = coord.separation(stars).arcsec

    # Nearest first: a short offset is easier to trust than a bright one.
    for i in np.argsort(seps):
        if seps[i] < 1.0:        # that's the target itself
            continue
        star = stars[i]
        d_ra, d_dec = star.spherical_offsets_to(coord)
        return {
            'coord': star,
            'mag': float(gmag[i]),
            'sep_arcsec': float(seps[i]),
            'offset_ra': float(d_ra.arcsec),
            'offset_dec': float(d_dec.arcsec),
            'catalog': label,
            'band': band,
        }
    return None


def _read_sidecar(sidecar):
    """The JSON beside a finder chart, or {} if it isn't readable."""
    try:
        with open(sidecar) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _existing_mode(sidecar):
    """
    The slit mode a previously generated chart was drawn in.

    Returns None when there is no sidecar, which is treated as "unknown"
    and therefore stale -- an old chart without a recorded mode cannot be
    shown to match the one being asked for.
    """
    if not Path(sidecar).exists():
        return None
    return _read_sidecar(sidecar).get('slit_mode')


def _tub_note(tub):
    """Caption line for a Shane tub setting, or '' when there isn't one."""
    if not tub:
        return ''
    return (f"Cass tub readout = {tub['tub']:.2f} "
            f"(or {tub['alt_tub']:.2f} at PA {tub['alt_pa']:.1f})")


def draw_finder(coord, name, out_path, slit_pa, data=None, wcs=None,
                 offset_star=None, secondary=None,
                 fov_arcmin=DEFAULT_FOV_ARCMIN,
                 slit_length_arcmin=DEFAULT_SLIT_LENGTH_ARCMIN,
                 slit_width_arcsec=DEFAULT_SLIT_WIDTH_ARCSEC,
                 subtitle='', slit_note='', rotator_note='', image_label='',
                 tub=None, slit_centre=None):
    """
    Render the finder chart: image, target, secondary candidate, offset
    star, slit.

    Parameters
    ----------
    coord : SkyCoord
    slit_pa : float
        Position angle east of north, degrees.
    out_path : str or Path
    slit_note : str, optional
        How this angle was chosen, printed with it in the caption.
    rotator_note : str, optional
        What to set at the telescope, when that is not the sky PA.
    image_label : str, optional
        The image's source, printed on the chart (fetched here when data is
        None, which also sets it).
    tub : dict, optional
        lick_tub.tub_settings() output; with it, the PA box on the image
        also gives the Cass tub readout.
    slit_centre : SkyCoord, optional
        Where the slit is centred; default the target. A slit through both
        candidates is centred midway between them (the starlist's _C row).
    secondary : dict, optional
        Second-ranked host candidate, as load_secondaries() returns it.
        Labelled on the chart rather than only ringed: at the eyepiece the
        question is which of two nearby objects the slit is on, and a bare
        circle doesn't answer it.

    Returns
    -------
    Path
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from astropy.visualization import ZScaleInterval
    from astropy.visualization.wcsaxes import SphericalCircle

    if data is None:
        data, wcs, image_label = fetch_image(coord, fov_arcmin)

    vmin, vmax = ZScaleInterval().get_limits(np.nan_to_num(data))

    fig = plt.figure(figsize=(7.5, 8.2))
    ax = fig.add_subplot(111, projection=wcs)
    ax.imshow(data, cmap='gray_r', origin='lower', vmin=vmin, vmax=vmax)

    # Circles are drawn at a fixed angular radius rather than a fixed
    # number of points, as chime_ffff_pz_finder does: a PATH primary and
    # its runner-up can be 3" apart, and a marker sized in points swallows
    # both at any plausible field of view, which is precisely the case
    # where the chart has to tell them apart.
    def ring(axes, c, radius_arcsec, color, label=None, lw=1.6):
        circle = SphericalCircle((c.ra, c.dec), radius_arcsec * u.arcsec,
                                  transform=axes.get_transform('icrs'),
                                  edgecolor=color, facecolor='none', lw=lw,
                                  label=label)
        axes.add_patch(circle)

    ring(ax, coord, CANDIDATE_RING_ARCSEC, 'red', name)

    # Labels are pushed apart along the line joining the pair, so a close
    # secondary doesn't print its letter on top of the primary's.
    away = (16, 10)
    if secondary is not None:
        px = np.array(wcs.world_to_pixel(coord))
        ps = np.array(wcs.world_to_pixel(secondary['coord']))
        delta = ps - px
        norm = np.hypot(*delta)
        if norm > 0:
            away = tuple(-18 * delta / norm)

    ax.annotate('P', xy=(coord.ra.deg, coord.dec.deg),
                xycoords=ax.get_transform('world'),
                xytext=away, textcoords='offset points',
                ha='center', va='center',
                color='red', fontsize=11, fontweight='bold')

    if secondary is not None:
        sec = secondary['coord']
        label = 'secondary'
        if secondary.get('name'):
            label += f" {secondary['name']}"
        if secondary.get('mag') is not None:
            label += f" ({secondary['mag']:.1f})"
        ring(ax, sec, CANDIDATE_RING_ARCSEC, SECONDARY_COLOR, label)
        ax.annotate('S', xy=(sec.ra.deg, sec.dec.deg),
                    xycoords=ax.get_transform('world'),
                    xytext=tuple(-np.array(away)), textcoords='offset points',
                    ha='center', va='center',
                    color=SECONDARY_COLOR, fontsize=11, fontweight='bold')

    if offset_star is not None:
        star = offset_star['coord']
        ring(ax, star, STAR_RING_ARCSEC, 'tab:cyan',
             f"offset star {offset_star.get('band', 'G')}={offset_star['mag']:.1f}")

    # A close pair is only a few pixels apart at full field, so show it
    # again at a scale that separates it. Which of two neighbouring
    # objects the slit is on is the one question a finder has to settle.
    sep = coord.separation(secondary['coord']).arcsec if secondary else None
    if sep is not None and sep < ZOOM_SEP_ARCSEC:
        from astropy.nddata import Cutout2D

        sec = secondary['coord']
        mid = coord.directional_offset_by(coord.position_angle(sec),
                                           (sep / 2) * u.arcsec)
        box = max(6 * sep, 12.0)
        try:
            cut = Cutout2D(data, mid, box * u.arcsec, wcs=wcs, mode='partial',
                           fill_value=np.nan)
            inset = fig.add_axes([0.655, 0.115, 0.235, 0.235],
                                  projection=cut.wcs)
            inset.imshow(cut.data, cmap='gray_r', origin='lower',
                         vmin=vmin, vmax=vmax)
            ring(inset, coord, CANDIDATE_RING_ARCSEC, 'red', lw=2.0)
            ring(inset, sec, CANDIDATE_RING_ARCSEC, SECONDARY_COLOR, lw=2.0)
            # Vertical offsets here, not the main chart's radial ones: the
            # inset is small enough that a radial label lands on the frame.
            inset.annotate('P', xy=(coord.ra.deg, coord.dec.deg),
                           xycoords=inset.get_transform('world'),
                           xytext=(0, 15), textcoords='offset points',
                           ha='center', va='center', color='red',
                           fontsize=11, fontweight='bold')
            inset.annotate('S', xy=(sec.ra.deg, sec.dec.deg),
                           xycoords=inset.get_transform('world'),
                           xytext=(0, -15), textcoords='offset points',
                           ha='center', va='center', color=SECONDARY_COLOR,
                           fontsize=11, fontweight='bold')
            for axis in inset.coords:
                axis.set_ticklabel_visible(False)
                axis.set_ticks_visible(False)
                axis.set_axislabel('')
            for spine in inset.spines.values():
                spine.set_edgecolor('tab:purple')
                spine.set_linewidth(1.4)
            inset.set_title(f'zoom, {box:.0f}" across', fontsize=8,
                            color='0.25', pad=3)
        except Exception as err:          # cutout off the image edge
            print(f'{name}: no zoom inset ({type(err).__name__}: {err})')

    # The slit: a rectangle centred on slit_centre (default the target),
    # long axis at slit_pa measured east of north.
    centre = coord if slit_centre is None else slit_centre
    half = (slit_length_arcmin / 2) * u.arcmin
    width = (slit_width_arcsec / 2) * u.arcsec
    pa = slit_pa * u.deg
    ends = [centre.directional_offset_by(pa, half),
            centre.directional_offset_by(pa + 180 * u.deg, half)]
    if slit_centre is not None:
        ax.plot(centre.ra.deg, centre.dec.deg, marker='+', ms=12, mew=1.5,
                color='tab:purple', transform=ax.get_transform('world'),
                label='slit centre (_C)')
    corners = []
    for end, sign in ((ends[0], 1), (ends[1], -1)):
        for perp in (pa + 90 * u.deg, pa - 90 * u.deg)[::sign]:
            corners.append(end.directional_offset_by(perp, width))
    corners.append(corners[0])
    ax.plot([c.ra.deg for c in corners], [c.dec.deg for c in corners],
            transform=ax.get_transform('world'), color='tab:purple', lw=1.3)

    # The two numbers set at the telescope, where the eye lands first.
    box = f'PA = {slit_pa:.1f}\N{DEGREE SIGN}'
    if tub:
        box += (f"\nTUB = {tub['tub']:.2f}"
                f"\n(or {tub['alt_tub']:.2f} at PA {tub['alt_pa']:.1f}\N{DEGREE SIGN})")
    ax.text(0.02, 0.98, box, transform=ax.transAxes, ha='left', va='top',
            fontsize=12, fontweight='bold', color='tab:purple',
            bbox={'boxstyle': 'round', 'facecolor': 'white', 'alpha': 0.85,
                  'edgecolor': 'tab:purple'})

    ax.set_xlabel('RA (J2000)')
    ax.set_ylabel('Dec (J2000)')
    ax.grid(color='0.8', ls=':', lw=0.6)
    ax.legend(loc='upper right', fontsize=8, framealpha=0.9)

    title = f'{name}\n{coord.to_string("hmsdms", sep=":", precision=2)}'
    if subtitle:
        title += f'\n{subtitle}'
    ax.set_title(title, fontsize=10)

    caption = (f'slit {slit_length_arcmin:.1f}\' x {slit_width_arcsec:.1f}" '
               f'at PA = {slit_pa:.1f} deg ({slit_note or "parallactic"})')
    if rotator_note:
        caption += f'\n{rotator_note}'
    if secondary is not None:
        pox = secondary.get('pox')
        caption += (f"\nsecondary (orange) {sep:.1f}\" from the target"
                    + (f', P(O|x) = {pox:.3g}' if pox is not None else ''))
    if offset_star is not None:
        caption += (f'\noffset star -> target: '
                    f"{offset_star['offset_ra']:+.2f}\", "
                    f"{offset_star['offset_dec']:+.2f}\" "
                    f"({offset_star['sep_arcsec']:.1f}\" away)")
        if slit_centre is not None:
            d_ra, d_dec = offset_star['coord'].spherical_offsets_to(slit_centre)
            caption += (f'; -> slit centre _C: {d_ra.arcsec:+.2f}", '
                        f'{d_dec.arcsec:+.2f}"')
    if image_label:
        caption += f'\nimage: {image_label}'
    # Anchored below the axes (not at a fixed figure height), so a longer
    # caption never runs into the RA axis label; savefig's tight bbox
    # grows the figure to fit it.
    ax.text(0.5, -0.09, caption, transform=ax.transAxes, ha='center',
            va='top', fontsize=8.5, color='0.25')

    out_path = Path(out_path)
    fig.savefig(out_path, dpi=130, bbox_inches='tight')
    plt.close(fig)
    return out_path


def generate_for_plan(plan, location, out_dir, targets=None,
                       fov_arcmin=DEFAULT_FOV_ARCMIN,
                       slit_length_arcmin=DEFAULT_SLIT_LENGTH_ARCMIN,
                       slit_width_arcsec=DEFAULT_SLIT_WIDTH_ARCSEC,
                       targets_csv=None, slit_mode='parallactic',
                       rotator=None, progress=None, overwrite=False):
    """
    Finder chart + offset star + slit for each scheduled target.

    By default the slit angle is the dispersion-weighted mean parallactic
    angle over that target's own exposure -- the single fixed angle that
    loses the least light across the block actually being taken. With
    slit_mode='candidates' it is instead the line joining the two PATH
    candidates, which buys both spectra in one exposure at a dispersion
    cost that every chart and sidecar reports.

    Parameters
    ----------
    plan : PlanResult
    location : astropy EarthLocation
    out_dir : str or Path
        Finder PNGs and JSON sidecars are written here.
    targets : list of str, optional
        Restrict to these names; default is every scheduled target.
    targets_csv : str or Path, optional
        The table the plan was built from. Its Sec_RA/Sec_Dec columns,
        where present, put the second-ranked host candidate on the chart.
    slit_mode : {'parallactic', 'candidates'}
        'parallactic' sets the slit to lose the least light to
        atmospheric dispersion. 'candidates' instead lays it along the
        line joining the two PATH candidates, catching both spectra in
        one exposure at a cost in blue light that each chart reports. A
        target with no secondary falls back to parallactic, and says so.
    rotator : str, optional
        'cass_tub' adds the Shane's Cassegrain tub readout, which is the
        number a Lick observer actually dials -- not the sky PA.
    progress : callable, optional
        Called as progress(done, total, name) before each target. Each
        chart costs an image fetch and a catalogue query, so a run of ten
        takes a minute or two and the caller needs to be able to say how
        far along it is.
    overwrite : bool
        Re-render charts that already exist.

    Returns
    -------
    list of dict, one per target: name, png, pa, offset star info, error
    """
    from .parallactic import average_parallactic

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    secondaries = {}
    if targets_csv:
        try:
            secondaries = load_secondaries(targets_csv)
        except Exception as err:          # a table without PATH columns
            print(f'no secondary candidates read from {targets_csv}: {err}')

    if slit_mode not in ('parallactic', 'candidates'):
        raise ValueError(f"slit_mode must be 'parallactic' or 'candidates', "
                         f'not {slit_mode!r}')

    wanted = set(targets) if targets else None
    queue = [t for t in plan.schedule
             if not wanted or t.name in wanted]
    results = []

    for done, target in enumerate(queue):
        if progress is not None:
            progress(done, len(queue), target.name)

        png = out_dir / f'{target.name}_finder.png'
        sidecar = out_dir / f'{target.name}_finder.json'

        # What this target would get, decided before the skip check: a
        # chart drawn at the parallactic angle is not "already exists"
        # when candidates were asked for -- it is the wrong chart, and
        # silently keeping it would leave the slit angle disagreeing with
        # what the observer believes they chose.
        secondary = secondaries.get(target.name)
        mode = 'candidates' if (slit_mode == 'candidates'
                                 and secondary is not None) else 'parallactic'

        if png.exists() and not overwrite and _existing_mode(sidecar) == mode:
            # Hand back what the existing chart says rather than a bare
            # "skipped": the report is meant to answer "what angle is
            # each chart at", and that is true whether or not this run
            # drew it.
            keep = _read_sidecar(sidecar)
            keep.update({'name': target.name, 'png': str(png),
                         'slit_mode': mode, 'skipped': 'already exists'})
            results.append(keep)
            continue

        coord = SkyCoord(ra=target.ra_deg * u.deg, dec=target.dec_deg * u.deg)
        pa = average_parallactic(target.ra_deg, target.dec_deg,
                                  target.science_start, target.end, location)

        slit_pa = pa['mean_pa']
        if mode == 'candidates':
            # Both candidates on the slit axis: the angle is the line
            # joining them, and the dispersion penalty is whatever it is.
            slit_pa = float(coord.position_angle(secondary['coord']).deg) % 180

        # requested_mode is what the observer asked for when this chart was
        # drawn. Kept so a report merged across runs (one card re-rendered
        # later) can still tell "fell back" from "drawn at parallactic on
        # purpose in an earlier run".
        entry = {'name': target.name, 'slit_pa': slit_pa,
                 'slit_mode': mode, 'requested_mode': slit_mode,
                 'parallactic_pa': pa['mean_pa'],
                 'pa_vs_parallactic': float(
                     abs((slit_pa - pa['mean_pa'] + 90) % 180 - 90)),
                 'slit_length_arcmin': slit_length_arcmin,
                 'slit_width_arcsec': slit_width_arcsec,
                 'pa_swing': pa['max_offset'],
                 'pa_weighted_offset': pa['weighted_offset'],
                 'primary_ra': target.ra_deg, 'primary_dec': target.dec_deg}

        if rotator == 'cass_tub':
            from .lick_tub import tub_settings
            entry['cass_tub'] = tub_settings(slit_pa)

        if mode == 'parallactic' and slit_mode == 'candidates':
            entry['fallback_reason'] = (
                'not an FFFF-PZ target with PATH candidates -- nothing to '
                'align a two-candidate slit on' if not secondaries else
                'no second PATH candidate for this target')

        if secondary is not None:
            entry.update({
                'secondary_name': secondary.get('name'),
                'secondary_ra': float(secondary['coord'].ra.deg),
                'secondary_dec': float(secondary['coord'].dec.deg),
                'secondary_mag': secondary.get('mag'),
                'secondary_pox': secondary.get('pox'),
                'secondary_sep_arcsec': float(
                    coord.separation(secondary['coord']).arcsec),
            })

        # A slit through both candidates is centred midway between them, so
        # a pair wider than half the slit still fits (the starlist's _C).
        centre = None
        if mode == 'candidates':
            sec = secondary['coord']
            centre = coord.directional_offset_by(coord.position_angle(sec),
                                                 coord.separation(sec) / 2)
            entry.update({'slit_centre_ra': float(centre.ra.deg),
                          'slit_centre_dec': float(centre.dec.deg)})

        try:
            star = find_offset_star(coord)
        except Exception as err:               # catalogue unreachable
            star, entry['offset_star_error'] = None, str(err)[:600]

        if star is not None:
            entry.update({
                'offset_star_ra': float(star['coord'].ra.deg),
                'offset_star_dec': float(star['coord'].dec.deg),
                'offset_star_mag': star['mag'],
                'offset_star_offset': star['sep_arcsec'],
                'offset_ra': star['offset_ra'],
                'offset_dec': star['offset_dec'],
                'offset_star_catalog': star.get('catalog'),
                'offset_star_band': star.get('band', 'G'),
            })
            if centre is not None:
                d_ra, d_dec = star['coord'].spherical_offsets_to(centre)
                entry.update({'offset_ra_centre': float(d_ra.arcsec),
                              'offset_dec_centre': float(d_dec.arcsec)})

        try:
            # Every chart shows the longslit at parallactic, mask targets
            # included: the mask itself is configured at the telescope, so a
            # finder's job here is just to get you onto the right object.
            mask_note = (' · mask configured at the telescope'
                         if target.mode.startswith('MOS') else '')
            if mode == 'candidates':
                how = (f"longslit through both candidates, "
                       f"{entry['pa_vs_parallactic']:.1f} deg off parallactic")
                note = (f'both candidates; parallactic would be '
                        f"{pa['mean_pa']:.1f}")
            else:
                how = (f"longslit at parallactic, holds to "
                       f"{pa['weighted_offset']:.1f} deg")
                note = 'parallactic'
                if slit_mode == 'candidates':
                    how += ' (no secondary to align on)'
                    note += ', no secondary to align on'
            subtitle = (f"{target.science_start:%H:%M}-{target.end:%H:%M} · "
                        f"{how}{mask_note}")
            data, wcs, image_label = fetch_image(coord, fov_arcmin)
            entry['image_source'] = image_label
            draw_finder(coord, target.name, png, slit_pa, data=data, wcs=wcs,
                        image_label=image_label, tub=entry.get('cass_tub'),
                        slit_centre=centre,
                        offset_star=star, secondary=secondary,
                        fov_arcmin=fov_arcmin,
                        slit_length_arcmin=slit_length_arcmin,
                        slit_width_arcsec=slit_width_arcsec,
                        subtitle=subtitle, slit_note=note,
                        rotator_note=_tub_note(entry.get('cass_tub')))
            entry['png'] = str(png)
        except Exception as err:               # image service unreachable
            entry['error'] = f'{type(err).__name__}: {str(err)[:600]}'

        with open(sidecar, 'w') as f:
            json.dump(entry, f, indent=2)
        results.append(entry)

    if progress is not None:
        progress(len(queue), len(queue), None)
    return results


def slit_report(results, slit_mode):
    """
    Plain-language account of what each chart was actually drawn at.

    Asking for both candidates and quietly getting a parallactic slit is
    the failure that matters here: the observer would set an angle they
    did not choose. So the report names every target that fell back and
    why, and for the rest states what the choice cost in degrees off
    parallactic.

    Parameters
    ----------
    results : list of dict
        What generate_for_plan() returned.
    slit_mode : str
        The mode that was requested.

    Returns
    -------
    dict with 'requested', 'rows', 'fell_back', 'lines'
    """
    rows, fell_back, lines = [], [], []
    for entry in results:
        if entry.get('error'):
            lines.append(f"{entry['name']}: FAILED -- {entry['error']}")
            continue

        mode = entry.get('slit_mode', 'parallactic')
        row = {
            'name': entry['name'],
            'slit_mode': mode,
            'slit_pa': entry.get('slit_pa'),
            'parallactic_pa': entry.get('parallactic_pa'),
            'off_parallactic': entry.get('pa_vs_parallactic'),
            'secondary_name': entry.get('secondary_name'),
            'secondary_sep_arcsec': entry.get('secondary_sep_arcsec'),
            'reason': entry.get('fallback_reason'),
            'skipped': entry.get('skipped'),
        }
        rows.append(row)

        # Judge each chart against what was asked for when *it* was drawn;
        # sidecars written before requested_mode existed fall back to this
        # run's request, which was the old behaviour.
        requested = entry.get('requested_mode') or slit_mode
        if row['slit_pa'] is None:
            lines.append(f"{entry['name']}: unchanged ({entry.get('skipped')})")
        elif requested == 'candidates' and mode != 'candidates':
            fell_back.append(entry['name'])
            lines.append(f"{entry['name']}: parallactic "
                         f"{row['slit_pa']:.2f} deg -- {row['reason']}")
        elif mode == 'candidates':
            lines.append(
                f"{entry['name']}: both candidates, PA {row['slit_pa']:.2f} "
                f"deg ({row['off_parallactic']:.1f} deg off parallactic; "
                f"secondary {row['secondary_sep_arcsec']:.1f}\" away)")
        else:
            lines.append(f"{entry['name']}: parallactic "
                         f"{row['slit_pa']:.2f} deg")

    return {'requested': slit_mode, 'rows': rows, 'fell_back': fell_back,
            'lines': lines}


def plan_slit_entries(plan, out_dir, fresh):
    """
    Every scheduled target's finder entry: this run's where it drew one,
    otherwise what the chart already on disk records.

    Created by JXP and Claude

    Re-rendering one card used to rewrite slit_report.txt with that card
    alone, erasing the record of every other chart's angle. Merging with
    the sidecars keeps the file a whole-night record.

    Inputs
    ------
    plan : PlanResult
    out_dir : str or Path
        The plan's finders/ directory.
    fresh : list of dict
        What generate_for_plan() returned for this run.

    Outputs
    -------
    list of dict in schedule order, ready for slit_report(). Targets never
    drawn (no sidecar) are left out; a sidecar that recorded a failure is
    kept, so the failure stays on the record.
    """
    out_dir = Path(out_dir)
    by_name = {e['name']: e for e in fresh}
    merged = []
    for target in plan.schedule:
        if target.name in by_name:
            merged.append(by_name[target.name])
            continue
        sidecar = out_dir / f'{target.name}_finder.json'
        old = _read_sidecar(sidecar) if sidecar.exists() else {}
        if not old:
            continue
        old = dict(old, name=target.name)
        if not old.get('error'):
            old['skipped'] = 'drawn earlier'
        merged.append(old)
    return merged


def write_slit_report(finder_dir, plan, report):
    """
    Save the slit report beside the charts.

    Written to disk as well as returned because it is the record of what
    angle each chart was drawn at, and that question comes up again days
    later when a spectrum looks wrong.

    Inputs: finder_dir (str/Path), plan (PlanResult), report (slit_report()).
    Outputs: none; writes <finder_dir>/slit_report.txt.
    """
    path = Path(finder_dir) / 'slit_report.txt'
    header = [f'Slit angles for {plan.date} ({Path(plan.output_dir).name})',
              f'Requested: {report["requested"]}',
              'Created by JXP and Claude -- night-planner', '']
    if report['fell_back']:
        header += [f'Fell back to parallactic (not from FFFF-PZ): '
                   f'{", ".join(report["fell_back"])}', '']
    try:
        path.write_text('\n'.join(header + report['lines']) + '\n')
    except OSError:
        pass        # the report is a convenience; never fail a render for it
