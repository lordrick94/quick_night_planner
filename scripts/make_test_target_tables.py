"""
Build synthetic target tables for exercising the night planner.

Nothing here is a real object. Every name carries a SIM prefix and every
position is drawn from a seeded generator, so these tables can never be
mistaken for observing targets -- they exist to drive the software.

What they are for
-----------------
Three axes get covered, because each breaks something different:

1. **Season.** A night plan is mostly decided by which RAs are up, so
   there is a table per season, clustered on the RA that transits near
   local midnight (Oct ~ 1h, Jan ~ 7h, Apr ~ 13h, Jul ~ 19h). Run the
   wrong season's table against a date and nearly everything should be
   rejected -- which is itself a test.

2. **Format.** FFFF-PZ spellings (Pri_RA/Pri_Dec), bare ones (RA/Dec),
   sexagesimal strings, RA in hours, extra columns that must survive
   untouched.

3. **Tables that must be refused.** Three of them are designed to fail
   detect_mapping(), because silently guessing is the dangerous outcome:
   ambiguous RA units, a burst position with no host position, and
   headers no alias covers. A release that "reads" these is broken.

Usage
-----
python scripts/make_test_target_tables.py [out_dir]

Created by JXP and Claude
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from astropy import units as u
from astropy.coordinates import SkyCoord

SEED = 20261014

# RA that transits around local midnight, by month of a Lick/Keck run.
SEASONS = {
    'autumn': {'month': 'October', 'ra_centre': 1.0},
    'winter': {'month': 'January', 'ra_centre': 7.0},
    'spring': {'month': 'April', 'ra_centre': 13.0},
    'summer': {'month': 'July', 'ra_centre': 19.0},
}

# Object classes, with the magnitude range each plausibly occupies. The
# spread matters: it drives the exposure estimator and, at Keck, the
# longslit/MOS split at mag 21.
KINDS = {
    'FRB': {'mag': (16.0, 23.5), 'tag': 'FRB host candidate'},
    'SN': {'mag': (14.5, 19.5), 'tag': 'supernova'},
    'DLA': {'mag': (17.5, 20.5), 'tag': 'DLA sightline quasar'},
    'TDE': {'mag': (18.0, 21.0), 'tag': 'tidal disruption event'},
    'GRB': {'mag': (19.0, 23.0), 'tag': 'GRB afterglow host'},
}


def make_targets(rng, n, ra_centre_hours, ra_spread_hours=3.0,
                  dec_range=(-10, 70), kinds=None):
    """
    Draw a batch of synthetic targets around an RA.

    Parameters
    ----------
    rng : numpy Generator
    n : int
    ra_centre_hours : float
        RA the batch clusters on, hours.
    ra_spread_hours : float
        Half-width of the uniform RA spread.
    dec_range : (float, float)
    kinds : list of str, optional
        Restrict to these object classes.

    Returns
    -------
    DataFrame with the canonical-ish columns plus a secondary candidate.
    """
    kinds = kinds or list(KINDS)
    rows = []
    for i in range(n):
        kind = str(rng.choice(kinds))
        lo, hi = KINDS[kind]['mag']

        ra_h = (ra_centre_hours
                + rng.uniform(-ra_spread_hours, ra_spread_hours)) % 24
        ra_deg = ra_h * 15.0
        dec_deg = rng.uniform(*dec_range)
        mag = rng.uniform(lo, hi)

        # A second PATH candidate a few arcsec off, fainter than the
        # primary -- the geometry the finder's 'candidates' slit mode and
        # its zoom inset are there to handle.
        sep = rng.uniform(1.5, 45.0) * u.arcsec
        angle = rng.uniform(0, 360) * u.deg
        primary = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg)
        secondary = primary.directional_offset_by(angle, sep)

        pox = float(rng.uniform(0.55, 0.999))
        rows.append({
            'name': f'SIM{kind}{rng.integers(10000, 99999)}',
            'kind': kind,
            'ra_deg': ra_deg,
            'dec_deg': dec_deg,
            'mag': mag,
            'pox': pox,
            'sec_ra': float(secondary.ra.deg),
            'sec_dec': float(secondary.dec.deg),
            'sec_mag': mag + rng.uniform(1.0, 4.5),
            'sec_pox': float(rng.uniform(0.0005, 0.08)),
            'dm': float(rng.uniform(220, 1400)) if kind == 'FRB' else np.nan,
            'tag': KINDS[kind]['tag'],
        })
    frame = pd.DataFrame(rows)
    # Unique names: a duplicate would mask a real bug in target matching.
    frame['name'] = [f'{n}_{i:02d}' if dup else n
                     for i, (n, dup) in enumerate(
                         zip(frame['name'], frame['name'].duplicated(keep=False)))]
    return frame


def write_ffffpz(df, path, resource):
    """
    FFFF-PZ spellings, degrees, with PATH candidates.

    FRBs only, and the assertion is the point. PATH ranks the host
    candidates of a *burst*, so a supernova row in this format would be
    claiming a second candidate it cannot have -- and the planner,
    trusting the format, would fit a slit through it.
    """
    assert (df['kind'] == 'FRB').all(), (
        'an FFFF-PZ table holds localised FRBs only; got '
        f"{sorted(set(df['kind']) - {'FRB'})}")
    out = pd.DataFrame({
        'TNS': df['name'],
        'FRB_RA': df['ra_deg'] + 0.0004,   # burst position, slightly off host
        'FRB_Dec': df['dec_deg'] - 0.0003,
        'FRB_DM': df['dm'],
        'FRB_tags': df['tag'],
        'Pri_name': _jnames(df['ra_deg'], df['dec_deg']),
        'Pri_RA': df['ra_deg'],
        'Pri_Dec': df['dec_deg'],
        'Pri_POx': df['pox'],
        'Pri_mag': df['mag'],
        'Pri_filter': 'r',
        'Sec_name': _jnames(df['sec_ra'], df['sec_dec']),
        'Sec_RA': df['sec_ra'],
        'Sec_Dec': df['sec_dec'],
        'Sec_POx': df['sec_pox'],
        'Sec_mag': df['sec_mag'],
        'Sec_filter': 'r',
        'mode': 'spectroscopy',
        'Resource': resource,
    })
    out.to_csv(path, index=False)
    return out


def write_sexagesimal(df, path):
    """Plain spreadsheet: Name / RA / Dec as hms dms strings / mag."""
    coords = SkyCoord(ra=df['ra_deg'].values * u.deg,
                      dec=df['dec_deg'].values * u.deg)
    out = pd.DataFrame({
        'Name': df['name'],
        'Type': df['kind'],
        'RA': coords.ra.to_string(unit=u.hour, sep=':', precision=2, pad=True),
        'Dec': coords.dec.to_string(sep=':', precision=1, pad=True,
                                     alwayssign=True),
        'mag': df['mag'].round(2),
        'Notes': df['tag'],
    })
    out.to_csv(path, index=False)
    return out


def write_ra_hours(df, path):
    """RA in hours, explicitly named, plus columns that must pass through."""
    out = pd.DataFrame({
        'target_name': df['name'],
        'ra_hours': (df['ra_deg'] / 15.0).round(6),
        'dec_deg': df['dec_deg'].round(6),
        'r_mag': df['mag'].round(2),
        'P_Ox': df['pox'].round(4),
        'programme': 'SIM-TEST',
        'priority': np.where(df['mag'] < 18, 'A', 'B'),
    })
    out.to_csv(path, index=False)
    return out


def write_generic(df, path):
    """
    A mixed-class observing list in nobody's particular format.

    Deliberately carries no FRB_* or Sec_* columns: these are supernovae,
    DLA quasars, TDEs and GRB hosts, which have no PATH association to
    rank. Asking for a two-candidate slit against this table must fall
    back to parallactic for every row.
    """
    out = pd.DataFrame({
        'Name': df['name'],
        'Type': df['kind'],
        'RA_deg': df['ra_deg'].round(6),
        'Dec_deg': df['dec_deg'].round(6),
        'mag': df['mag'].round(2),
        'Notes': df['tag'],
    })
    out.to_csv(path, index=False)
    return out


def write_minimal(df, path):
    """The smallest table that should still work."""
    out = pd.DataFrame({
        'object': df['name'],
        'ra_deg': df['ra_deg'].round(6),
        'dec_deg': df['dec_deg'].round(6),
        'magnitude': df['mag'].round(2),
    })
    out.to_csv(path, index=False)
    return out


def write_ambiguous_ra(df, path):
    """MUST FAIL: bare 'ra', numeric, every value <= 24. Hours or degrees?"""
    out = pd.DataFrame({
        'name': df['name'],
        'ra': (df['ra_deg'] / 15.0).round(5),   # hours, but nothing says so
        'dec': df['dec_deg'].round(5),
        'mag': df['mag'].round(2),
    })
    out.to_csv(path, index=False)
    return out


def write_burst_only(df, path):
    """MUST FAIL: burst position only, no host. Pointing here is wrong."""
    out = pd.DataFrame({
        'TNS': df['name'],
        'FRB_RA': df['ra_deg'].round(5),
        'FRB_Dec': df['dec_deg'].round(5),
        'FRB_DM': df['dm'].round(1),
        'Pri_mag': df['mag'].round(2),
    })
    out.to_csv(path, index=False)
    return out


def write_odd_headers(df, path):
    """MUST FAIL: journal-style headers no alias covers."""
    coords = SkyCoord(ra=df['ra_deg'].values * u.deg,
                      dec=df['dec_deg'].values * u.deg)
    out = pd.DataFrame({
        'Object Name': df['name'],
        'R.A. (J2000)': coords.ra.to_string(unit=u.hour, sep=' ', precision=2),
        'Decl. (J2000)': coords.dec.to_string(sep=' ', precision=1,
                                               alwayssign=True),
        'V (mag)': df['mag'].round(2),
    })
    out.to_csv(path, index=False)
    return out


def _jnames(ra_deg, dec_deg):
    """J-names from coordinates, as PATH tables carry them."""
    coords = SkyCoord(ra=np.asarray(ra_deg) * u.deg,
                      dec=np.asarray(dec_deg) * u.deg)
    return ['J' + c.to_string('hmsdms', sep='', precision=2)
            .replace(' ', '').replace('h', '').replace('m', '')
            .replace('s', '').replace('d', '')
            for c in coords]


def build(out_dir):
    """
    Write the whole set.

    Parameters
    ----------
    out_dir : str or Path

    Returns
    -------
    list of (filename, rows, note)
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    written = []

    for season, info in SEASONS.items():
        df = make_targets(rng, 18, info['ra_centre'], dec_range=(-5, 72),
                           kinds=['FRB'])
        name = f'{season}_ffffpz.csv'
        write_ffffpz(df, out_dir / name, f'SIM-{season.title()}-01')
        written.append((name, len(df),
                        f"FFFF-PZ columns (FRBs only), RA near "
                        f"{info['ra_centre']:.0f}h ({info['month']} run)"))

    # One format per file, so a failure points at one thing.
    winter = make_targets(rng, 12, 7.0, dec_range=(10, 65))
    write_sexagesimal(winter, out_dir / 'winter_sexagesimal.csv')
    written.append(('winter_sexagesimal.csv', len(winter),
                    'hh:mm:ss / +dd:mm:ss strings, bare Name/RA/Dec/mag'))

    spring = make_targets(rng, 15, 13.0, dec_range=(-5, 60))
    write_ra_hours(spring, out_dir / 'spring_ra_hours.csv')
    written.append(('spring_ra_hours.csv', len(spring),
                    'RA in hours (ra_hours), extra columns to pass through'))

    summer = make_targets(rng, 9, 19.0, dec_range=(5, 68))
    write_minimal(summer, out_dir / 'summer_minimal.csv')
    written.append(('summer_minimal.csv', len(summer),
                    'smallest workable table: object/ra_deg/dec_deg/magnitude'))

    # All-sky: whatever the date, part of this is up and part is not.
    # Generic format, because it is a mixed bag of SNe, DLAs, TDEs and
    # GRB hosts -- none of which has PATH candidates.
    allsky = make_targets(rng, 60, 12.0, ra_spread_hours=12.0,
                           dec_range=(-25, 78))
    write_generic(allsky, out_dir / 'allsky_mixed.csv')
    written.append(('allsky_mixed.csv', len(allsky),
                    'generic format, all RAs, all object classes, Dec '
                    '-25..+78 -- the general workout, and no PATH candidates'))

    allsky_frb = make_targets(rng, 40, 12.0, ra_spread_hours=12.0,
                               dec_range=(-20, 78), kinds=['FRB'])
    write_ffffpz(allsky_frb, out_dir / 'allsky_frb_ffffpz.csv', 'SIM-AllSky-02')
    written.append(('allsky_frb_ffffpz.csv', len(allsky_frb),
                    'FFFF-PZ format, all RAs -- the table to test the '
                    'two-candidate slit against'))

    # Declination edges: the Shane cannot point above +82 at all, and
    # nothing far south ever clears airmass 2 from either site.
    extreme = pd.concat([
        make_targets(rng, 6, 2.0, dec_range=(83, 89), kinds=['FRB']),
        make_targets(rng, 6, 2.0, dec_range=(75, 82), kinds=['FRB']),
        make_targets(rng, 6, 2.0, dec_range=(-35, -20), kinds=['FRB']),
    ], ignore_index=True)
    write_ffffpz(extreme, out_dir / 'dec_limits.csv', 'SIM-DecLimits-01')
    written.append(('dec_limits.csv', len(extreme),
                    'Dec +83..+89 (above the Shane limit), +75..+82 (just '
                    'under), and -35..-20 (never up) -- rejection paths'))

    # Faint end: at Keck everything above mag 21 needs a MOS mask.
    faint = make_targets(rng, 10, 1.0, dec_range=(15, 55), kinds=['FRB'])
    faint['mag'] = np.linspace(19.5, 23.4, len(faint))
    write_ffffpz(faint, out_dir / 'faint_mos_split.csv', 'SIM-Faint-01')
    written.append(('faint_mos_split.csv', len(faint),
                    'mag 19.5..23.4 across the mag-21 longslit/MOS boundary'))

    # The three that must be refused.
    bad = make_targets(rng, 8, 1.0)
    write_ambiguous_ra(bad, out_dir / 'bad_ambiguous_ra_units.csv')
    written.append(('bad_ambiguous_ra_units.csv', len(bad),
                    'MUST FAIL: bare numeric "ra", all values <= 24'))
    write_burst_only(bad, out_dir / 'bad_burst_position_only.csv')
    written.append(('bad_burst_position_only.csv', len(bad),
                    'MUST FAIL: FRB_RA/FRB_Dec only, no host position'))
    write_odd_headers(bad, out_dir / 'bad_odd_headers.csv')
    written.append(('bad_odd_headers.csv', len(bad),
                    'MUST FAIL: "R.A. (J2000)" style headers'))

    _write_readme(out_dir, written)
    return written


def _write_readme(out_dir, written):
    """Describe the set, including what each file is meant to prove."""
    lines = [
        '# Synthetic target tables',
        '',
        'Generated by `scripts/make_test_target_tables.py` '
        f'(seed {SEED}); regenerate with',
        '',
        '```bash',
        'python scripts/make_test_target_tables.py',
        '```',
        '',
        '**None of these objects are real.** Every name starts with `SIM` '
        'and every position is drawn from a seeded random generator. They '
        'exist to exercise the planner, not to be observed.',
        '',
        '| file | rows | what it covers |',
        '|------|------|----------------|',
    ]
    lines += [f'| `{name}` | {rows} | {note} |' for name, rows, note in written]
    lines += [
        '',
        '## Seasons',
        '',
        'A plan is mostly decided by which RAs are up, so each seasonal '
        'table clusters on the RA transiting near local midnight. Running '
        "one against the wrong date should reject nearly everything -- that "
        'is a test, not a bug.',
        '',
        '| table | RA centre | run month |',
        '|-------|-----------|-----------|',
    ]
    lines += [f"| `{s}_ffffpz.csv` | {i['ra_centre']:.0f}h | {i['month']} |"
              for s, i in SEASONS.items()]
    lines += [
        '',
        '## The three that must fail',
        '',
        'Silently guessing is the dangerous outcome, so these exist to '
        'prove the planner refuses rather than guesses. If a release reads '
        'any of them without complaint, that release is broken.',
        '',
        '- `bad_ambiguous_ra_units.csv` -- a bare numeric `ra` whose values '
        'are all <= 24 is either hours or degrees, and the two differ by a '
        'factor of 15.',
        '- `bad_burst_position_only.csv` -- `FRB_RA`/`FRB_Dec` is where the '
        'burst was, not where the host is. Pointing there observes blank '
        'sky.',
        '- `bad_odd_headers.csv` -- journal-style headers that no alias '
        'covers; the column-mapping path should be offered instead.',
        '',
        '## Example',
        '',
        '```bash',
        'night-planner calc --instrument kast \\',
        '    --targets-csv test_targs/autumn_ffffpz.csv \\',
        '    --output-dir Night_plans/SIM-Autumn-01 \\',
        '    --date 2026-10-20',
        '```',
        '',
    ]
    (out_dir / 'README.md').write_text('\n'.join(lines))


def main():
    """Write the tables and print what was made."""
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else 'test_targs')
    written = build(out_dir)
    for name, rows, note in written:
        print(f'  {name:32s} {rows:3d} rows   {note}')
    print(f'\nWrote {len(written)} tables + README.md to {out_dir}')


if __name__ == '__main__':
    main()
