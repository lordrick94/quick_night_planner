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


def fetch_image(coord, fov_arcmin=DEFAULT_FOV_ARCMIN, pixels=600,
                 survey='CDS/P/PanSTARRS/DR1/r'):
    """
    Grab an image cutout around a position.

    Parameters
    ----------
    coord : SkyCoord
    fov_arcmin : float
    pixels : int
    survey : str
        HiPS identifier. Pan-STARRS r covers Dec > -30; DSS2 is the
        all-sky fallback.

    Returns
    -------
    (data, wcs)
    """
    from astroquery.hips2fits import hips2fits

    result = hips2fits.query(
        hips=survey, width=pixels, height=pixels,
        ra=coord.ra, dec=coord.dec, fov=fov_arcmin * u.arcmin,
        projection='TAN', format='fits')
    return result[0].data, WCS(result[0].header)


def find_offset_star(coord, max_sep_arcsec=OFFSET_MAX_SEP_ARCSEC,
                      min_mag=OFFSET_MIN_MAG, max_mag=OFFSET_MAX_MAG):
    """
    Nearest usable offset star from Gaia DR3.

    Returns
    -------
    dict with 'coord', 'mag', 'sep_arcsec', 'offset_ra', 'offset_dec'
    (offsets run star -> target, in arcsec, matching the starlist
    convention), or None if nothing suitable is in range.
    """
    from astroquery.vizier import Vizier

    vizier = Vizier(columns=['RA_ICRS', 'DE_ICRS', 'Gmag'],
                    column_filters={'Gmag': f'>{min_mag} && <{max_mag}'})
    vizier.ROW_LIMIT = 200
    tables = vizier.query_region(coord, radius=max_sep_arcsec * u.arcsec,
                                  catalog='I/355/gaiadr3')
    if not tables:
        return None

    table = tables[0]
    stars = SkyCoord(table['RA_ICRS'], table['DE_ICRS'], unit='deg')
    seps = coord.separation(stars).arcsec

    # Nearest first: a short offset is easier to trust than a bright one.
    order = np.argsort(seps)
    for i in order:
        if seps[i] < 1.0:        # that's the target itself
            continue
        star = stars[i]
        d_ra, d_dec = star.spherical_offsets_to(coord)
        return {
            'coord': star,
            'mag': float(table['Gmag'][i]),
            'sep_arcsec': float(seps[i]),
            'offset_ra': float(d_ra.arcsec),
            'offset_dec': float(d_dec.arcsec),
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
                 subtitle='', slit_note='', rotator_note=''):
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
        data, wcs = fetch_image(coord, fov_arcmin)

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
             f"offset star G={offset_star['mag']:.1f}")

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

    # The slit: a rectangle centred on the target, long axis at slit_pa
    # measured east of north.
    half = (slit_length_arcmin / 2) * u.arcmin
    width = (slit_width_arcsec / 2) * u.arcsec
    pa = slit_pa * u.deg
    ends = [coord.directional_offset_by(pa, half),
            coord.directional_offset_by(pa + 180 * u.deg, half)]
    corners = []
    for end, sign in ((ends[0], 1), (ends[1], -1)):
        for perp in (pa + 90 * u.deg, pa - 90 * u.deg)[::sign]:
            corners.append(end.directional_offset_by(perp, width))
    corners.append(corners[0])
    ax.plot([c.ra.deg for c in corners], [c.dec.deg for c in corners],
            transform=ax.get_transform('world'), color='tab:purple', lw=1.3)

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
    fig.text(0.5, 0.02, caption, ha='center', fontsize=8.5, color='0.25')

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

        entry = {'name': target.name, 'slit_pa': slit_pa,
                 'slit_mode': mode,
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

        try:
            star = find_offset_star(coord)
        except Exception as err:               # catalogue unreachable
            star, entry['offset_star_error'] = None, str(err)[:200]

        if star is not None:
            entry.update({
                'offset_star_ra': float(star['coord'].ra.deg),
                'offset_star_dec': float(star['coord'].dec.deg),
                'offset_star_mag': star['mag'],
                'offset_star_offset': star['sep_arcsec'],
                'offset_ra': star['offset_ra'],
                'offset_dec': star['offset_dec'],
            })

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
            draw_finder(coord, target.name, png, slit_pa,
                        offset_star=star, secondary=secondary,
                        fov_arcmin=fov_arcmin,
                        slit_length_arcmin=slit_length_arcmin,
                        slit_width_arcsec=slit_width_arcsec,
                        subtitle=subtitle, slit_note=note,
                        rotator_note=_tub_note(entry.get('cass_tub')))
            entry['png'] = str(png)
        except Exception as err:               # image service unreachable
            entry['error'] = f'{type(err).__name__}: {str(err)[:200]}'

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

        if row['slit_pa'] is None:
            lines.append(f"{entry['name']}: unchanged ({entry.get('skipped')})")
        elif slit_mode == 'candidates' and mode != 'candidates':
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
