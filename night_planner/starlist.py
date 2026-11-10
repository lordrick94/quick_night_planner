"""
Build a starlist from a plan, in the observatory's own dialect.

Keck and Lick starlists are genuinely different documents, not the same
file with different coordinates:

- **Keck**: two rows per target (target, `_S` offset star). The offset and
  slit angle ride on the rows as `raoffset=`/`decoffset=`/`rotdest=`/
  `rotmode=pa` keywords, Dec carries an explicit `+`, and `#` comments are
  allowed, so each row can say when and how it is observed.
- **Lick**: three rows per target (target, `_S` offset star, `_C` slit
  centre). The Mt Hamilton format takes no keywords and no comments, and
  positive Dec is unsigned. Timing and setup live in the target list
  instead.

Both follow what `chime_ffff_pz_starlist` emits for those observatories.

Slit centre: chime_ffff_pz derives Lick's `_C` from
`center_lick_kast_slits()`, which fits the slit through the two best host
candidates. These plans put the slit at the parallactic angle on a single
target instead, so the slit centre *is* the target.

Created by JXP and Claude
"""

import json
from pathlib import Path

from astropy import units as u
from astropy.coordinates import SkyCoord

from .standards import pick_bracketing_standards, starlist_row


def _finder_data(finder_dir, name):
    """Offset-star/PA JSON for one target, if the finder step produced it."""
    if not finder_dir:
        return None
    path = Path(finder_dir) / f'{name}_finder.json'
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _keck_block(target, coord, finder, when, has_star):
    """Keck rows: target + offset star, with keywords on both."""
    lines = []
    row = starlist_row(target.name, coord, style='keck').rstrip()
    row += f" rotdest={finder['slit_pa']:.2f} rotmode=pa"
    suffix = ' | mask set at the telescope' if target.mode.startswith('MOS') else ''
    if not has_star:
        suffix += ' | NO OFFSET STAR: acquire on the target'
    lines.append(f'{row}  # {when} | {target.mode}{suffix}')

    if has_star:
        star = SkyCoord(ra=finder['offset_star_ra'] * u.deg,
                        dec=finder['offset_star_dec'] * u.deg)
        offset = starlist_row(f'{target.name}_S', star, style='keck').rstrip()
        offset += (f" raoffset={finder['offset_ra']:.2f} "
                   f"decoffset={finder['offset_dec']:.2f} "
                   f"rotdest={finder['slit_pa']:.2f} rotmode=pa")
        lines.append(offset)
    return lines


def _lick_block(target, coord, finder, has_star):
    """
    Lick rows: target, offset star, slit centre.

    Per the author: Lick rows take `exptime=` (total integration in
    seconds) after the epoch. **PA is not a real Mt Hamilton keyword**, so
    it goes behind a `#` with the rest of the annotation -- the telescope
    would not act on it either way, and leaving it bare invites the next
    reader to think it would.

    exptime and the PA note go on both the target row and the `_C`
    slit-centre row, since either can be the row actually selected when
    the exposure is set up.

    The target row's comment also carries the Cassegrain tub readout when
    the finder computed one. The tub, not the sky PA, is what is set at
    the Shane, and the two differ by ~13 per cent -- dialling 108.9 where
    94.8 was meant puts the slit 16 degrees off.
    """
    seconds = int(round(target.on_target_min * 60))
    pa_note = f'#PA={finder["slit_pa"]:.2f}'
    setup = f'exptime={seconds} {pa_note}'

    tub = finder.get('cass_tub')
    # One '#' opens the comment; the tub rides inside it rather than
    # opening a second one.
    tub_note = (f" TUB = {tub['tub']:.2f} or {tub['alt_tub']:.2f}"
                if tub else '')

    lines = [starlist_row(target.name, coord, style='lick') + setup + tub_note]

    if has_star:
        star = SkyCoord(ra=finder['offset_star_ra'] * u.deg,
                        dec=finder['offset_star_dec'] * u.deg)
        lines.append(
            starlist_row(f'{target.name}_S', star, style='lick')
            + f"#RA_OFFSET = {finder['offset_ra']:.2f} and "
              f"DECOFFSET = {finder['offset_dec']:.2f}")

    # Parallactic slit on one target, so its centre is the target itself.
    lines.append(starlist_row(f'{target.name}_C', coord, style='lick') + setup)
    return lines


def build_starlist(plan, include_standards=True, location=None,
                    library=None, finder_dir=None, max_airmass=2.0,
                    style='keck'):
    """
    Render a starlist for a plan.

    Parameters
    ----------
    plan : PlanResult
    include_standards : bool
    location : astropy EarthLocation
        Required when include_standards is set.
    finder_dir : str or Path, optional
        Directory of `<target>_finder.json` files, supplying offset stars
        and slit angles.
    style : {'keck', 'lick'}
        Which observatory's starlist dialect to emit.

    Returns
    -------
    (text, notes)
    """
    notes = []
    comment = '#' if style == 'keck' else '#'
    lines = [
        f'{comment} {plan.telescope} starlist for {plan.date} '
        f'({Path(plan.output_dir).name})',
        f'{comment} Created by JXP and Claude -- night-planner, schedule order',
    ]
    if style == 'lick':
        lines.append(f'{comment} rows per target: target, _S offset star, '
                     f'_C slit centre (parallactic slit, centred on target)')
        lines.append(f'{comment} exptime = total integration (s). Everything '
                     f'after a # is a note, not a keyword:')
        lines.append(f'{comment}   PA = slit position angle on the sky; '
                     f'offsets run star -> target (arcsec)')
        lines.append(f'{comment}   TUB = Cassegrain tub readout to dial (two '
                     f'settings 180 deg apart; the sky PA is NOT the tub)')
    else:
        lines.append(f'{comment} _S rows = offset star; raoffset/decoffset = '
                     f'star -> target (arcsec)')

    standards = None
    if include_standards:
        if location is None:
            raise ValueError('include_standards needs a site location')
        standards = pick_bracketing_standards(plan, location, library,
                                               max_airmass=max_airmass)
    lines.append('')

    if standards and standards.get('evening'):
        s = standards['evening']
        lines.append(starlist_row(
            s['name'], s['coord'], style=style,
            comment=f"Evening flux standard, {s['when']:%H:%M} "
                    f"(AM {s['airmass']:.2f})"))
        if style == 'lick':
            notes.append(f"Evening standard {s['name']} at {s['when']:%H:%M} "
                         f"(airmass {s['airmass']:.2f}).")
        lines.append('')
    elif include_standards:
        notes.append('No standard was observable at the start of the night '
                     f'below airmass {max_airmass}.')

    missing_finders, no_star = [], []
    for target in plan.schedule:
        coord = SkyCoord(ra=target.ra_deg * u.deg, dec=target.dec_deg * u.deg)
        finder = _finder_data(finder_dir, target.name)
        has_pa = finder and finder.get('slit_pa') is not None
        has_star = finder and finder.get('offset_star_ra') is not None

        if not has_pa:
            missing_finders.append(target.name)
            lines.append(starlist_row(target.name, coord, style=style,
                                       comment='NO FINDER: no offset star/PA'))
            continue

        if not has_star:
            no_star.append(target.name)

        when = (f'{target.science_start:%H:%M}-{target.end:%H:%M}, '
                f'{target.exposure_red or target.mode}')
        if style == 'lick':
            lines += _lick_block(target, coord, finder, has_star)
        else:
            lines += _keck_block(target, coord, finder, when, has_star)

    if standards and standards.get('morning'):
        s = standards['morning']
        lines += ['', starlist_row(
            s['name'], s['coord'], style=style,
            comment=f"Morning flux standard, {s['when']:%H:%M} "
                    f"(AM {s['airmass']:.2f})")]
        if style == 'lick':
            notes.append(f"Morning standard {s['name']} at {s['when']:%H:%M} "
                         f"(airmass {s['airmass']:.2f}).")
    elif include_standards:
        notes.append('No standard was observable at the end of the night '
                     f'below airmass {max_airmass}.')

    if style == 'lick':
        notes.append('Lick rows carry no keywords or per-row comments, per the '
                     'Mt Hamilton format -- timing and slit angles are in the '
                     'plan, not the starlist.')
    if no_star:
        notes.append('No offset star found within range for '
                     + ', '.join(no_star)
                     + ' -- acquisition has to be on the target itself.')
    if missing_finders:
        notes.append('No finder output for ' + ', '.join(missing_finders)
                     + ' -- those rows carry coordinates only.')

    return '\n'.join(lines) + '\n', notes
