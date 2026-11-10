"""
Calculate LST, twilight, airmass for Keck/LRIS Oct 6, 2026 night
and select targets for observation.

Target pool: Keck-2026B-02 (global FFFF-PZ). Slews and acquisition come
from keck_overheads.py (5 min base slew, 14 min Dec<+20 -> Dec>+20;
acquisition 5 min longslit, 10 min mask). MOS blocks get a +5 min buffer,
and only masks in MOS_MASKS_AVAILABLE are schedulable.

History:
- 2026-11-07 (T1.5): calibrations (arcs, flats) are no longer scheduled or
  reserved. They're taken when the observer chooses and are ticked off on
  the Observing log page. The flat 30 min "for calibrations" reserve became
  MORNING_RESERVE_MIN: just the closing slew to Feige 110 and the morning
  standard.
- 2026-11-07 (T1.1): detector readout is charged per frame for ETC/recipe
  exposures (instrument_params.readout_minutes, 80 s per frame at 2x2):
  block = slew + acq + on target + readout. MOS blocks and forced
  allocations are time budgets that already include readout, so nothing is
  added to them.
- 2026-11-07 (T3.6): Keck I zenith limit (88.9 deg) enforced in
  check_keck_limits; blocks passing above 85 deg get a guiding warning in
  their notes (_flag_near_zenith). Limits live in
  instrument_params.KECK_ELEVATION_LIMITS.
- 2026-11-07 (T1.6): priority tiers. The top tier runs the window-order
  greedy pass (_greedy_pass) over the whole night; lower tiers are inserted
  into its gaps (_insert_tier) with an exact slew fit, and the next target's
  slew is recomputed.
- 2026-11-07 (T3.3): a target table's t_target (minutes on target, the
  whole block, no readout added) overrides the ETC for that row; the ETC
  estimate is kept as etc_min. `required` is carried through, but LRIS has
  no partial backfill, so it changes nothing here yet.
- 2026-11-07 (T1.3, T3.4): exposures come from night_planner.etc (the UCO
  ETC by default, or --etc), re-run at the airmass the target gets over
  its scheduled science span (--airmass-rule, default worst) and
  re-placed when they grow (up to MAX_AIRMASS_ROUNDS). The night's best
  airmass is only the first guess. Per-target S/N spectra go to
  <plan>/etc/<target>.json.
- 2026-11-07 (T1.2): acquisition is its own term (keck_acquisition_minutes),
  between the slew and science: block = slew + acq + on target. Base slew
  5 min, crossing 14 min (keck_overheads.py).

Created by JXP and Claude
"""

import pandas as pd
import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord, EarthLocation, AltAz, get_sun
from astropy.time import Time
from datetime import datetime, timedelta, timezone
import os

from lris_etc import estimate_lris_exposure_real
from keck_overheads import (keck_slew_minutes, keck_slew_reason,
                             keck_acquisition_minutes, KECK_SLEW_BASE_MIN,
                             KECK_SLEW_DEC_CROSS_MIN)
from schedule_overrides import (resolve_start, fit_around_blocks, blocking_reason,
                                 push_past_blocks, _overlapping_block)
from night_planner.targets_io import load_targets

import sys
from pathlib import Path

# Repo-relative, so this runs wherever the checkout lives.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from night_planner.paths import plans_dir
from night_planner.instrument_params import (DEFAULT_CONFIG, ConfigError,
                                             add_config_args, readout_minutes,
                                             resolve_options)
from night_planner.sky import block_airmass

_PLANS = plans_dir()

# Flux standards (Dec in deg): telescope starts the science sequence at the
# evening standard and slews to the morning standard after the last target.
EVENING_STANDARD_DEC = 28.8640   # BD+28 4211
MORNING_STANDARD_DEC = -5.1656   # Feige 110
MORNING_STANDARD_MIN = 5

# Re-placements allowed when the ETC, re-run at the scheduled airmass, asks
# for a longer exposure (T1.3).
MAX_AIRMASS_ROUNDS = 3

# Time held back at the end of the night: the slew to Feige 110 plus the
# standard itself. Feige 110 is south of +20 deg, so that slew is never a
# S->N crossing and always costs the base slew. Calibrations aren't in here
# (2026-11-07, T1.5): the observer takes them and ticks them off on the
# Observing log page.
MORNING_RESERVE_MIN = (keck_slew_minutes(0.0, MORNING_STANDARD_DEC)
                       + MORNING_STANDARD_MIN)

# Keck Observatory coordinates (Maunakea summit)
# Verified against astropy's EarthLocation.of_site('keck') (IRAF Observatory
# Database), 2026-09-11: lat 19.828333 deg, lon -155.478333 deg, height 4160 m.
KECK = EarthLocation(lat=19.828333*u.deg, lon=-155.478333*u.deg, height=4160*u.m)

# Hawaii Standard Time (UTC-10, no DST)
HST = timezone(timedelta(hours=-10))


def utc_to_hst(utc_time):
    """Convert UTC time to HST (fixed UTC-10)."""
    return utc_time.astimezone(HST)


def hst_to_utc(hst_dt):
    """Convert HST datetime to UTC."""
    if hst_dt.tzinfo is None:
        hst_dt = hst_dt.replace(tzinfo=HST)
    return hst_dt.astimezone(timezone.utc)


def calculate_lst(utc_time, location=KECK):
    """Calculate LST for given UTC time at location."""
    t = Time(utc_time)
    lst = t.sidereal_time('apparent', longitude=location.lon)
    return lst


def find_twilight(date_str, location=KECK, twilight_alt=-18*u.deg):
    """
    Find evening and morning twilight times for given date at Keck.

    Parameters
    ----------
    date_str : str
        Date in format 'YYYY-MM-DD' (HST local date)
    location : EarthLocation
        Observatory location
    twilight_alt : Quantity
        Sun altitude for twilight definition (default -18° for astronomical)

    Returns
    -------
    dict with twilight info
    """
    # Start search at local noon HST
    local_date = datetime.strptime(date_str, '%Y-%m-%d')
    noon_hst = datetime(local_date.year, local_date.month,
                        local_date.day, 12, 0, 0, tzinfo=HST)

    # Search for evening twilight (sun going down)
    search_time = noon_hst
    evening_utc = None
    evening_hst = None
    evening_lst = None

    for i in range(600):  # search up to 10 hours
        utc_time = search_time.astimezone(timezone.utc)
        t = Time(utc_time)
        sun = get_sun(t)
        sun_altaz = sun.transform_to(AltAz(obstime=t, location=location))

        if sun_altaz.alt < twilight_alt:
            evening_utc = utc_time
            evening_hst = search_time
            evening_lst = calculate_lst(utc_time, location)
            break
        search_time += timedelta(minutes=1)

    if evening_hst is None:
        raise ValueError(f"Could not find evening twilight for {date_str}")

    # Search for morning twilight (sun coming up)
    search_time = evening_hst + timedelta(hours=8)  # Oct nights ~11h dark at Keck
    morning_utc = None
    morning_hst = None
    morning_lst = None

    for i in range(600):
        utc_time = search_time.astimezone(timezone.utc)
        t = Time(utc_time)
        sun = get_sun(t)
        sun_altaz = sun.transform_to(AltAz(obstime=t, location=location))

        if sun_altaz.alt > twilight_alt:
            morning_utc = utc_time
            morning_hst = search_time
            morning_lst = calculate_lst(utc_time, location)
            break
        search_time += timedelta(minutes=1)

    if morning_hst is None:
        raise ValueError(f"Could not find morning twilight for {date_str}")

    # Calculate dark time duration
    dark_hours = (morning_utc - evening_utc).total_seconds() / 3600

    return {
        'evening_hst': evening_hst,
        'evening_utc': evening_utc,
        'evening_lst': evening_lst,
        'morning_hst': morning_hst,
        'morning_utc': morning_utc,
        'morning_lst': morning_lst,
        'dark_hours': dark_hours
    }


def calculate_airmass(ra, dec, time_utc, location=KECK):
    """
    Calculate airmass for target at given time.

    Returns
    -------
    airmass : float
    alt : float (degrees)
    az : float (degrees)
    ha : float (hours)
    """
    coord = SkyCoord(ra=ra*u.deg, dec=dec*u.deg, frame='icrs')
    t = Time(time_utc)
    altaz = coord.transform_to(AltAz(obstime=t, location=location))

    # Calculate hour angle
    lst = calculate_lst(time_utc, location)
    ha = (lst.hour - ra/15.0) % 24
    if ha > 12:
        ha -= 24

    # Calculate airmass (simple sec(z) formula)
    if altaz.alt.deg > 0:
        airmass = 1.0 / np.sin(np.radians(altaz.alt.deg))
    else:
        airmass = 99.9

    return airmass, altaz.alt.deg, altaz.az.deg, ha


# Keck I Nasmyth-deck vignetting window (fixed in azimuth, independent of target).
# Source: Keck Telescope Pointing Limits,
# www2.keck.hawaii.edu/inst/common/TelLimits.html --
# Keck I: az 5.3-146.2 deg needs alt >= 33.3 deg (deck hit is N/E for Keck I;
# it's S/W for Keck II -- opposite side). Elsewhere the normal unvignetted
# floor is ~18 deg.
# One source of truth: instrument_params.KECK_ELEVATION_LIMITS (TelLimits
# page, fetched 2026-11-07).
from night_planner.instrument_params import KECK_ELEVATION_LIMITS as _KEL
KECK1_NASMYTH_AZ_MIN, KECK1_NASMYTH_AZ_MAX = _KEL['nasmyth_az']
KECK1_NASMYTH_ALT_MIN = _KEL['nasmyth_floor']
KECK1_ALT_MIN = _KEL['floor']
KECK1_ZENITH_MAX = _KEL['zenith_max']
KECK1_GUIDE_WARN = _KEL['guide_warn']


def check_keck1_nasmyth_vignetting(az, alt):
    """
    Check whether (az, alt) is clear of the Keck I Nasmyth deck.

    LRIS sits on Keck I, whose enclosure/Nasmyth deck blocks the beam in a
    fixed azimuth band (~5.3-146.2 deg, i.e. N through E to SE) unless the
    telescope is above ~33.3 deg altitude. A target rising in the NE/E sits
    in this band at low altitude and must climb to 33.3 deg before it clears
    the deck -- "wait for the target to rise". A target setting in the W/SW
    passes through the unobstructed side and can be tracked down to the
    normal ~18 deg floor, so setting targets are easier to catch.

    Parameters
    ----------
    az : float (degrees)
    alt : float (degrees)

    Returns
    -------
    clear : bool
    """
    if KECK1_NASMYTH_AZ_MIN <= az <= KECK1_NASMYTH_AZ_MAX:
        return alt >= KECK1_NASMYTH_ALT_MIN
    return alt >= KECK1_ALT_MIN


def check_keck_limits(ra, dec, ha, alt, az, ignore_zenith=False):
    """
    Check if target violates Keck I pointing/vignetting limits.

    Keck constraints:
    - Elevation <= 88.9° (zenith tracking limit, T3.6)
    - Dec > -37° (horizon limit at low dec)
    - HA limits: -5.5h to +5.5h (roughly)
    - Keck I Nasmyth-deck vignetting (see check_keck1_nasmyth_vignetting)

    Parameters
    ----------
    ra : float (degrees)
    dec : float (degrees)
    ha : float (hours)
    alt : float (degrees)
    az : float (degrees)

    ignore_zenith : bool
        Skip the 88.9° tracking limit. The window search uses this: the
        zenith keyhole lasts minutes, so it is handled as a per-target
        blocked interval (zenith_keyhole) rather than by cutting the
        target's window in two and keeping only the first half.

    Returns
    -------
    valid : bool
    reason : str (if invalid)
    """
    # Dec limit (Keck can see down to about -37° depending on HA)
    if dec < -37:
        return False, f"Dec {dec:.1f}° < -37° limit"

    # HA limits (Keck is more permissive than Shane)
    if ha < -5.5:
        return False, f"HA {ha:.2f}h < -5.5h limit (too far east)"

    if ha > 5.5:
        return False, f"HA {ha:.2f}h > +5.5h limit (too far west)"

    # Keck I can't track through the zenith (T3.6, 2026-11-07).
    if not ignore_zenith and alt > KECK1_ZENITH_MAX:
        return False, (f"alt {alt:.1f}° above the Keck I zenith limit "
                       f"({KECK1_ZENITH_MAX}°)")

    # Keck I Nasmyth deck vignetting
    if not check_keck1_nasmyth_vignetting(az, alt):
        return False, (f"Vignetted by Keck I Nasmyth deck (az {az:.0f}°, "
                        f"alt {alt:.0f}° - needs {KECK1_NASMYTH_ALT_MIN:.0f}° "
                        f"in az {KECK1_NASMYTH_AZ_MIN:.0f}-{KECK1_NASMYTH_AZ_MAX:.0f}°)")

    return True, ""


"""
LRIS Mode Summary:
------------------
1. LONGSLIT: mag ≤ 21 (practical limit for reasonable S/N in ~1h)
2. MOS (slitmask): mag > 21, requires pre-milled masks (weeks lead time)
3. IMAGING: Available for acquisition, photometry, or when no longslit targets

For this run: longslit mode, mag ≤ 21 targets only.
"""

LRIS_LONGSLIT_MAG_LIMIT = 21.0  # Fainter needs MOS mask

# MOS on-target time once a mask exists (per the author, 2026-09-10): a mag
# <=23 masked target needs about 1 hour; fainter needs 1.5-2 hours. Bucketed
# at 24 mag to split that 1.5-2h range (not independently specified by the
# author -- flagged as an assumption).
MOS_MAG_BRIGHT_LIMIT = 23.0
MOS_MAG_MID_LIMIT = 24.0
# Extra buffer on every MOS block, on top of the 1-2h allocation (which
# already includes mask-alignment overhead), per the author 2026-09-30.
MOS_MASK_BUFFER_MIN = 5

# Masks that exist or can still realistically be milled for this run (per the
# author 2026-09-30: new masks are hard to get this late). The 5 MOS
# candidates from the Keck-2026B-01 pull plus TGT0593, the one new mask
# that fills the mid-night gap. Any other mag>21 target is excluded.
MOS_MASKS_AVAILABLE = {
    'TGT0272', 'TGT0461', 'TGT0536', 'TGT0573',
    'TGT0579',  # Keck-2026B-01 pull
}

# mag>21 targets observed in LONGSLIT anyway because no mask will be milled
# (per the author 2026-10-01). S/N=10 per exposure is unreachable for these
# (TGT0593, mag 22.6, would need >3 x 7200 s per the real ETC), so the
# target keeps its original 1 h allocation as 3 x 1200 s. Real ETC per-exposure
# S/N at AM 1.05: blue 5.7, red 2.8 (combined ~9.9 / ~4.9).
LONGSLIT_FORCED = {
    'TGT0593': {'n_sub': 3, 'sub_len': 1200,
                     'note': 'no mask: longslit 3x1200, S/N/exp b5.7 r2.8'},
}


def forced_longslit_exposure(tns):
    """
    Exposure dict for a mag>21 target forced into longslit (LONGSLIT_FORCED).

    Parameters
    ----------
    tns : str

    Returns
    -------
    dict with 'red_exp', 'blue_exp', 'science_min', 'total_min', 'mode'
    """
    f = LONGSLIT_FORCED[tns]
    sci = f['n_sub'] * f['sub_len'] / 60.0
    exp = f"{f['n_sub']} x {f['sub_len']}"
    return {'red_exp': exp, 'blue_exp': exp, 'science_min': sci,
            'total_min': sci, 'mode': 'longslit',
            'n_sub': f['n_sub'], 'sub_len_s': f['sub_len']}


def estimate_mos_exposure(mag_r):
    """
    Estimate on-target time for a mag>21 target once a MOS mask exists.

    Not a physical S/N calculation (no real ETC support for MOS mode) --
    an operational time budget per the author's stated practice.

    Returns
    -------
    dict with 'red_exp', 'blue_exp', 'science_min', 'total_min', 'mode'
    """
    if mag_r <= MOS_MAG_BRIGHT_LIMIT:
        total_min = 60
    elif mag_r < MOS_MAG_MID_LIMIT:
        total_min = 90
    else:
        total_min = 120
    total_min += MOS_MASK_BUFFER_MIN
    return {
        'red_exp': 'MOS mask required',
        'blue_exp': 'MOS mask required',
        'science_min': total_min,
        'total_min': total_min,
        'mode': 'mos_required'
    }


def estimate_lris_exposure(mag_r, mode='longslit', airmass=1.2, config=None,
                           seeing=None, band='r'):
    """
    Estimate LRIS exposure times.

    Longslit exposures are computed with the real UCO/Lick LRIS S/N
    calculator (etc.ucolick.org -- see lris_etc.py), targeting median
    per-pixel continuum S/N = 10 *per single sub-exposure* in each arm
    (grism 600/4000 blue, grating 600/7500 red), taking the longer arm as
    the per-sub-exposure length, and always using >=3 sub-exposures (a
    cosmic-ray-rejection floor, not derived from S/N). This replaced a
    magnitude-bucket heuristic that had no basis in throughput/sky/read-noise
    physics (see KECK_LRIS_2026OCT06_SUMMARY.md, Prompt 7), and then a
    combined-S/N version that under-delivered S/N per individual frame
    (Prompt 8).

    Modes:
    - longslit: mag ≤ 21 (practical limit), real-ETC exposure time
    - imaging: 5 min per filter typically (unchanged, out of scope here)
    - mos: requires pre-milled masks (mask design, not an exposure-time
      question -- placeholder retained)

    Parameters
    ----------
    mag_r : float
    mode : str
    airmass : float
        Use the target's actual airmass at observation time.
    config : dict, optional
        Instrument configuration (grism, grating, dichroic, slit, binning);
        defaults to instrument_params.DEFAULT_CONFIG['lris'] (M4, T3.1).
    seeing : float, optional
        FWHM arcsec; defaults to lris_etc.DEFAULT_SEEING (T3.2).
    band : str
        Band of mag_r, mapped to the ETC filter file (T3.5).

    Returns
    -------
    dict with 'red_exp', 'blue_exp', 'total_min', 'mode'
    """
    if mode == 'imaging':
        return {
            'red_exp': '3 x 120',
            'blue_exp': '3 x 120',
            'science_min': 6,
            'total_min': 11,
            'mode': 'imaging'
        }

    # Longslit mode - check mag limit. This is *our own* mag-based check,
    # independent of whatever "mode" FFFF-PZ itself tags a target with --
    # FFFF-PZ tags everything pulled via num_targ_longslit as "longslit"
    # even when Pri_mag > 21 (verified 2026-09-10), so its mode column is
    # never read/trusted here.
    if mag_r > LRIS_LONGSLIT_MAG_LIMIT:
        return estimate_mos_exposure(mag_r)

    return estimate_lris_exposure_real(mag_r, airmass=airmass, config=config,
                                       seeing=seeing, band=band)


# Keck target-selection rule (10m aperture is wasted on targets Lick's 3m
# already covers): only take targets fainter than mag 19, unless the target
# is at Dec above the Lick/Shane pointing limit (82 deg) and so unreachable
# from Lick at any magnitude.
KECK_MAG_FAINT_LIMIT = 19.0
LICK_DEC_LIMIT = 82.0


def passes_keck_target_selection(mag, dec):
    """
    Keck target-selection rule: mag > 19, unless Dec > Lick's 82° limit.

    Returns
    -------
    keep : bool
    """
    return mag > KECK_MAG_FAINT_LIMIT or dec > LICK_DEC_LIMIT


def analyze_targets(targets_csv, date_str='2026-10-06', mapping=None,
                     assume_masks=False, time_overrides=None,
                     sn_overrides=None):
    """
    Analyze all targets for observability on given date at Keck.

    Parameters
    ----------
    targets_csv : str or DataFrame
        Any target table -- an FFFF-PZ pull or anything else. Columns are
        normalized by night_planner.targets_io, so this function only ever
        sees the canonical name/ra_deg/dec_deg/mag schema.
    mapping : targets_io.ColumnMapping, optional
        Explicit column mapping, for tables whose columns can't be
        detected automatically.
    assume_masks : bool
        By default a mag>21 target is only schedulable if its mask is
        already in MOS_MASKS_AVAILABLE. Set this to schedule every
        mask-needing target anyway, on the commitment that a mask will be
        milled before the run. It allocates the time; it does not make the
        mask exist, so the designs still have to be submitted.
    """
    # Read targets (any schema -> canonical); --set-time overrides t_target,
    # --set-sn target_sn
    from night_planner.targets_io import apply_sn_overrides, apply_time_overrides
    df = load_targets(targets_csv, mapping=mapping)
    try:
        df = apply_time_overrides(df, time_overrides)
        df = apply_sn_overrides(df, sn_overrides)
    except ValueError as err:
        raise SystemExit(f'error: {err}')

    # Apply Keck target-selection rule (mag > 19, unless Dec > Lick limit)
    n_before = len(df)
    df = df[df.apply(lambda r: passes_keck_target_selection(r['mag'], r['dec_deg']),
                      axis=1)].copy()
    print(f"\nKeck target selection: {len(df)}/{n_before} pass "
          f"(mag > {KECK_MAG_FAINT_LIMIT}, unless Dec > {LICK_DEC_LIMIT}° Lick limit)")

    # Calculate twilight
    twilight = find_twilight(date_str)

    print(f"\n=== TWILIGHT TIMES FOR {date_str} (KECK) ===")
    print(f"Evening 18° twilight: {twilight['evening_hst'].strftime('%H:%M HST')} "
          f"(LST {twilight['evening_lst'].to_string(precision=0)})")
    print(f"Morning 18° twilight: {twilight['morning_hst'].strftime('%H:%M HST')} "
          f"(LST {twilight['morning_lst'].to_string(precision=0)})")
    print(f"Dark time: {twilight['dark_hours']:.1f} hours")

    # Determine timeline start (round down to nearest 10 min before evening twilight)
    eve_minute = twilight['evening_hst'].minute
    start_minute = (eve_minute // 10) * 10
    start_hst = twilight['evening_hst'].replace(minute=start_minute, second=0)

    print(f"Timeline start: {start_hst.strftime('%H:%M HST')}")

    # Calculate observable RA range
    eve_lst = twilight['evening_lst'].hour
    mor_lst = twilight['morning_lst'].hour
    print(f"\nObservable RA range (HA ±5.5h):")
    print(f"  Evening: RA {(eve_lst - 5.5) % 24:.1f}h to {(eve_lst + 5.5) % 24:.1f}h")
    print(f"  Morning: RA {(mor_lst - 5.5) % 24:.1f}h to {(mor_lst + 5.5) % 24:.1f}h")

    # Calculate observability for each target
    results = []

    for idx, row in df.iterrows():
        tns = row['name']
        ra = row['ra_deg']
        dec = row['dec_deg']
        mag = row['mag']
        pox = row['pox']
        tags = row['tags'] if pd.notna(row['tags']) else ''
        dm = row['dm']
        mag_band = row.get('mag_band', '') or ''
        t_target = row.get('t_target', np.nan)
        target_sn = row.get('target_sn', np.nan)
        required = bool(row.get('required', False))

        # Calculate airmass at evening twilight
        am_eve, alt_eve, az_eve, ha_eve = calculate_airmass(
            ra, dec, twilight['evening_utc'])

        # Calculate airmass at morning twilight
        am_mor, alt_mor, az_mor, ha_mor = calculate_airmass(
            ra, dec, twilight['morning_utc'])

        # Find minimum airmass time during night
        # Sample every 15 minutes
        night_duration = twilight['dark_hours']
        n_samples = int(night_duration * 4)
        min_am = 99.9
        min_am_time = None
        min_am_ha = None
        min_am_alt = None
        min_am_az = None

        observable_hours = 0
        for i in range(n_samples):
            sample_time = twilight['evening_utc'] + timedelta(hours=i*0.25)
            am, alt, az, ha = calculate_airmass(ra, dec, sample_time)
            if am < min_am:
                min_am = am
                min_am_time = sample_time
                min_am_ha = ha
                min_am_az = az
                min_am_alt = alt
            # Count hours with airmass < 2.0 (or < 2.5 for bright targets)
            am_limit = 2.5 if mag < 17 else 2.0
            if am < am_limit:
                observable_hours += 0.25

        # Check pointing limits at minimum airmass time
        if min_am_ha is None:
            # Never above the horizon at any sample: no min-airmass point to check
            valid, reason = False, 'Below horizon all night'
        else:
            # The best-airmass point of a near-zenith target is the keyhole
            # itself; the keyhole is handled at placement (zenith_keyhole),
            # so it mustn't reject the whole target here.
            valid, reason = check_keck_limits(ra, dec, min_am_ha, min_am_alt,
                                              min_am_az, ignore_zenith=True)

        # Also check if observable at some point during the night
        # Bright targets (mag < 17) can tolerate higher airmass
        night_observable = observable_hours > 0.5  # At least 30 min

        # Determine LRIS mode from OUR OWN mag cut -- never from FFFF-PZ's
        # own "mode" column, which tags everything requested via
        # num_targ_longslit as "longslit" even when mag > 21 (verified
        # 2026-09-10). Always ask for masked targets (num_targ_mask > 0)
        # when building the FFFF-PZ Resource, but still re-derive mode here.
        if tns in LONGSLIT_FORCED:
            lris_mode = 'longslit (forced, no mask)'
            info = LONGSLIT_FORCED[tns]['note']
        elif mag > LRIS_LONGSLIT_MAG_LIMIT:
            lris_mode = 'MOS (mask required)'
            mos_est = estimate_mos_exposure(mag)
            info = (f"Mag {mag:.1f} > {LRIS_LONGSLIT_MAG_LIMIT:.0f}: MOS mask "
                    f"required (~{mos_est['total_min']/60:.1f}h once milled)")
        else:
            lris_mode = 'longslit'
            info = ''

        # A MOS target is only schedulable if its mask exists / can be milled
        needs_mask = lris_mode == 'MOS (mask required)'
        no_mask = (needs_mask and not assume_masks
                   and tns not in MOS_MASKS_AVAILABLE)
        no_mask_reason = (f"No mask available: mag {mag:.2f} > {LRIS_LONGSLIT_MAG_LIMIT:.0f} "
                          f"needs MOS, not in MOS_MASKS_AVAILABLE") if no_mask else ''
        if needs_mask and assume_masks and tns not in MOS_MASKS_AVAILABLE:
            info += ' | MASK TO BE MILLED: scheduled on the commitment that a mask exists by the run'

        results.append({
            'TNS': tns,
            'RA_deg': ra,
            'Dec_deg': dec,
            'RA_hours': ra/15.0,
            'mag_r': mag,
            'POx': pox,
            'tags': tags,
            'DM': dm,
            'mag_band': mag_band,
            't_target': t_target,
            'target_sn': target_sn,
            'required': required,
            'priority': row.get('priority', 1.0),
            'lris_mode': lris_mode,
            'info': info,
            'min_airmass': min_am,
            'min_am_time_hst': utc_to_hst(min_am_time) if min_am_time else None,
            'min_am_ha': min_am_ha,
            'min_am_alt': min_am_alt,
            'am_evening': am_eve,
            'ha_evening': ha_eve,
            'alt_evening': alt_eve,
            'am_morning': am_mor,
            'ha_morning': ha_mor,
            'alt_morning': alt_mor,
            'observable_hours': observable_hours,
            'observable': night_observable and valid and not no_mask,
            'limit_reason': reason if not valid else (
                'Below horizon all night' if not night_observable else (
                    no_mask_reason if no_mask else ''))
        })

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('RA_hours')

    return results_df, twilight, start_hst


# Step at which find_observable_window() samples the night. The
# scheduler reuses it as the grace it allows past a window edge,
# because that is exactly how precisely the edge is known.
WINDOW_SAMPLE_MIN = 10

def zenith_keyhole(ra, dec, twilight, step_min=2):
    """
    When a target is above the Keck I tracking limit (88.9°) tonight.

    Only targets within ~1.1° of the zenith (|Dec - latitude| < 1.1) ever
    get there, for a few minutes around transit.

    Parameters
    ----------
    ra, dec : float, degrees
    twilight : dict from calculate_twilight
    step_min : float

    Returns
    -------
    list of (start, end, reason) in HST, padded by one step either side;
    empty for almost every target.
    """
    lat = KECK.lat.deg
    if abs(dec - lat) >= 90.0 - KECK1_ZENITH_MAX:
        return []
    from night_planner.sky import track
    start = twilight['evening_utc']
    n = int(twilight['dark_hours'] * 60 / step_min) + 1
    times = [start + timedelta(minutes=i * step_min) for i in range(n)]
    alt = track(ra, dec, times, KECK)['alt']
    hot = [t for t, a in zip(times, alt) if a > KECK1_ZENITH_MAX]
    if not hot:
        return []
    pad = timedelta(minutes=step_min)
    return [(utc_to_hst(hot[0] - pad), utc_to_hst(hot[-1] + pad),
             f'zenith keyhole (> {KECK1_ZENITH_MAX}°)')]


def find_observable_window(ra, dec, twilight, mag=20.0):
    """
    Find the time window when target is observable.

    Airmass limit: < 2.0 for faint targets, < 2.5 for bright (mag < 17).

    Returns
    -------
    start_hst, end_hst, duration_hours
    """
    window_start = None
    window_end = None
    am_limit = 2.5 if mag < 17 else 2.0

    # Sample every 10 minutes
    n_samples = int(twilight['dark_hours'] * 60 / WINDOW_SAMPLE_MIN)

    for i in range(n_samples):
        sample_utc = twilight['evening_utc'] + timedelta(
            minutes=i * WINDOW_SAMPLE_MIN)
        am, alt, az, ha = calculate_airmass(ra, dec, sample_utc)

        if am < am_limit and check_keck_limits(ra, dec, ha, alt, az,
                                               ignore_zenith=True)[0]:
            if window_start is None:
                window_start = sample_utc
            window_end = sample_utc
        elif window_start is not None and window_end is not None:
            # Gap in observability - take first window
            break

    if window_start and window_end:
        duration = (window_end - window_start).total_seconds() / 3600
        return utc_to_hst(window_start), utc_to_hst(window_end), duration
    return None, None, 0


def _target_exposure(row, airmass, etc_opts=None):
    """
    Exposure dict for one results_df row, with the plan's ETC options.

    Parameters
    ----------
    row : mapping
        A results_df row ('mag_r', 'mag_band', ...).
    airmass : float
    etc_opts : dict, optional
        {'config', 'seeing', 'mag_band'} from instrument_params.resolve_options.
        The row's own mag_band wins over the plan-wide band.

    Returns
    -------
    dict, as from estimate_lris_exposure.
    """
    from night_planner.instrument_params import ETC_FILTERS

    if row['mag_r'] > LRIS_LONGSLIT_MAG_LIMIT:
        return estimate_mos_exposure(row['mag_r'])
    etc_opts = etc_opts or {}
    plan_band = etc_opts.get('mag_band') or 'r'
    band = row.get('mag_band')
    band = '' if band is None or (not isinstance(band, str) and pd.isna(band)) \
        else str(band).strip()
    if band and band not in ETC_FILTERS:
        print(f"  {row.get('TNS')}: mag_band {band!r} isn't an ETC band; "
              f"using the plan's {plan_band!r}")
        band = ''
    band = band or plan_band

    # Through the pluggable ETC interface (night_planner.etc, T3.4b): the
    # UCO/Lick ETC by default, or whatever --etc names.
    from night_planner import etc as etc_mod
    from night_planner.instrument_params import DEFAULT_SEEING
    from night_planner.targets_io import has_own_sn, row_target_sn
    # The row's own target_sn (column or --set-sn) beats the plan's.
    sn_goal = row_target_sn(row, etc_opts.get('target_sn')
                            or etc_mod.TARGET_SN['lris'])
    e = etc_mod.exposure(etc_opts.get('etc') or 'lris', row['mag_r'], band,
                         airmass, etc_opts.get('seeing') or DEFAULT_SEEING['lris'],
                         etc_opts.get('config') or DEFAULT_CONFIG['lris'],
                         sn_goal,
                         etc_opts.get('n_sub_min') or etc_mod.N_SUB_MIN['lris'])
    sn = e.pop('sn_sub', None) or {}
    comb = e.pop('sn_combined', None) or {}
    # The S/N spectrum is kept out of the row (it would land in
    # selected_targets.csv) and handed to run() via etc_opts, which writes
    # it to <plan>/etc/<target>.json for the viewer (T3.4a).
    spectrum = {'wave': e.pop('wave', []), 's2n': e.pop('s2n', [])}
    if etc_opts is not None and spectrum['wave']:
        etc_opts.setdefault('_spectra', {})[row['TNS']] = {
            **spectrum, 'airmass': airmass, 'sub_len_s': e.get('sub_len_s'),
            'n_sub': e.get('n_sub'), 'target_sn': sn_goal,
            'band': band}
    return {**e, 'mode': 'longslit', 'total_min': round(e['science_min'] + 5, 1),
            'achieved_sn_blue': sn.get('blue'), 'achieved_sn_red': sn.get('red'),
            'sn_sub_blue': sn.get('blue'), 'sn_sub_red': sn.get('red'),
            'sn_comb_blue': comb.get('blue'), 'sn_comb_red': comb.get('red'),
            'sn_goal': sn_goal, 'sn_goal_own': has_own_sn(row), 'band': band}


def append_forced_targets(selected, results_df, twilight, forced, prev_dec,
                           current_time, failures=None, etc_opts=None):
    """
    Place explicitly-forced targets after the normal schedule, truncated.

    Tried first because it disturbs nothing: everything the scheduler
    placed keeps its slot. It can only work for a target still up at
    the end of the night, though -- a fast-setting one shut hours
    earlier, and that is what reserve_forced_targets() is for.

    The scheduler refuses a target whose full allocation doesn't fit its
    window -- correct by default, but it throws away cases where a partial
    exposure is clearly worth taking (e.g. a mag 25.6 host rising into the
    best airmass of the night with 80 of its 125 nominal minutes left).
    This is the Keck equivalent of the Lick scheduler's forced_first
    override: the author asserts the target and the time, and the only
    thing checked here is that the telescope can legally point there.

    Parameters
    ----------
    forced : list of (tns, minutes)
    prev_dec : float
        Dec the telescope is left at by the normal schedule.
    current_time : datetime
        When the normal schedule finishes.

    Returns
    -------
    list of dict, rows to append to `selected`
    """
    rows = []
    res = results_df.set_index('TNS')

    def fail(tns, reason):
        """Report a forced target that could not be placed.

        Silence here is dangerous: the caller asked for this target
        specifically, so an unplaceable one has to say so rather than
        leave an apparently-unchanged plan.
        """
        if failures is not None:
            failures.append({'TNS': tns, 'reason': reason})
        print(f"  Forced {tns}: {reason}")

    for tns, minutes in forced:
        if tns not in res.index:
            fail(tns, 'not in the target table')
            continue
        row = res.loc[tns]
        slew_min = keck_slew_minutes(prev_dec, row['Dec_deg'])
        acq_min = keck_acquisition_minutes(row['lris_mode'])
        obs_start = current_time
        science_start = obs_start + timedelta(minutes=slew_min + acq_min)
        obs_end = science_start + timedelta(minutes=minutes)

        am, alt, az, ha = calculate_airmass(
            row['RA_deg'], row['Dec_deg'], science_start.astimezone(timezone.utc))
        valid, reason = check_keck_limits(row['RA_deg'], row['Dec_deg'], ha, alt, az)
        if not valid:
            fail(tns, f"cannot be appended after the last target: not "
                      f"pointable at {science_start.strftime('%H:%M')} "
                      f"-- {reason}")
            continue
        if obs_end > twilight['morning_hst']:
            over = (obs_end - twilight['morning_hst']).total_seconds() / 60
            print(f"  Forced {tns}: runs {over:.0f} min past morning twilight "
                  f"({twilight['morning_hst'].strftime('%H:%M')}) -- kept anyway, "
                  f"per the explicit request")

        exp = estimate_mos_exposure(row['mag_r']) if row['lris_mode'].startswith('MOS') \
            else _target_exposure(row, am, etc_opts)
        nominal = exp['science_min']
        entry = row.to_dict()
        entry.update(exp)
        entry.update({
            'TNS': tns,
            'slew_min': slew_min,
            'slew_reason': keck_slew_reason(prev_dec, row['Dec_deg']),
            'acq_min': acq_min,
            'on_target_min': float(minutes),
            'total_min': slew_min + acq_min + minutes,
            'scheduled_start': obs_start,
            'science_start': science_start,
            'scheduled_end': obs_end,
            'window_start': science_start,
            'window_end': obs_end,
            'info': (f"FORCED truncated exposure: {minutes:g} of {nominal:g} min "
                      f"nominal ({minutes / nominal:.0%}), AM {am:.2f}"),
        })
        rows.append(entry)
        print(f"  Forced {tns}: {science_start.strftime('%H:%M')}-"
              f"{obs_end.strftime('%H:%M')} ({minutes:g} min of {nominal:g} nominal, "
              f"AM {am:.2f})")
        prev_dec = row['Dec_deg']
        current_time = obs_end
    return rows


def reserve_forced_targets(results_df, twilight, forced, start_time, blocks,
                            failures=None, etc_opts=None):
    """
    Place explicitly-forced targets inside their own windows, before the
    normal scheduling pass runs.

    The scheduler refuses a target whose full allocation doesn't fit its
    window -- correct by default, but it throws away cases where a partial
    exposure is clearly worth taking (e.g. a mag 25.6 host rising into the
    best airmass of the night with 80 of its 125 nominal minutes left).
    The author asserts the target and the time; what is checked here is
    that the telescope can legally point there when it is placed.

    Placement is as late inside the target's own window as the requested
    time allows. That one rule covers both halves of the problem: a
    fast-setting target can only be at the top of the night, so it lands
    there, while a rising one lands at the end where it was going to be
    observed anyway. Appending after the whole schedule, which is what
    this used to do, only ever worked for the rising case -- for a setting
    target the window had shut hours before the schedule ended, so the
    rescue could not succeed.

    Parameters
    ----------
    forced : list of (tns, minutes)
    start_time : datetime
        Earliest the night can schedule science (after manual start/blocks).
    blocks : list of (start, end, reason)
    failures : list, optional
        Appended with {'TNS', 'reason'} for each target not placed.

    Returns
    -------
    (rows, reservations)
        Schedule rows, and (start, end, reason) tuples to add to `blocks`
        so the normal pass schedules around the reservations.
    """
    rows, reservations = [], []
    res = results_df.set_index('TNS')
    # The reservation covers the base slew in, and nothing after: the next
    # target's own fit already carries its slew inside its duration. Which
    # pointing precedes a forced target isn't known until the normal pass
    # runs, so a south->north crossing (KECK_SLEW_DEC_CROSS_MIN) would eat
    # ~10 min off the front of the exposure -- noted in the row's info
    # rather than reserved for, since reserving it costs a whole target.
    pad = timedelta(minutes=KECK_SLEW_BASE_MIN)

    def fail(tns, reason):
        """Report a forced target that could not be placed.

        Silence here is dangerous: the caller asked for this target
        specifically, so an unplaceable one has to say so rather than
        leave an apparently-unchanged plan.
        """
        if failures is not None:
            failures.append({'TNS': tns, 'reason': reason})
        print(f"  Forced {tns}: {reason}")

    for tns, minutes in forced:
        if tns not in res.index:
            fail(tns, 'not in the target table')
            continue
        row = res.loc[tns]
        window_start, window_end, _ = find_observable_window(
            row['RA_deg'], row['Dec_deg'], twilight, row['mag_r'])
        if window_start is None:
            fail(tns, 'never pointable tonight (Keck limits / airmass)')
            continue

        taken = list(blocks) + reservations
        earliest = push_past_blocks(max(start_time, window_start), taken)
        if earliest >= window_end:
            fail(tns, f"window closes {window_end.strftime('%H:%M')}, and the "
                      f"earliest clear slot is {earliest.strftime('%H:%M')}")
            continue

        science_start = max(earliest, window_end - timedelta(minutes=minutes))
        science_start = push_past_blocks(science_start, taken)
        obs_end = min(science_start + timedelta(minutes=minutes), window_end)
        hit = _overlapping_block(science_start, obs_end, taken)
        if hit is not None:
            obs_end = hit[0]
        got = (obs_end - science_start).total_seconds() / 60.0
        if got < 1:
            fail(tns, f"no usable time at {science_start.strftime('%H:%M')} "
                      f"before the next block or its "
                      f"{window_end.strftime('%H:%M')} window close")
            continue

        am, alt, az, ha = calculate_airmass(
            row['RA_deg'], row['Dec_deg'], science_start.astimezone(timezone.utc))
        valid, reason = check_keck_limits(row['RA_deg'], row['Dec_deg'], ha, alt, az)
        if not valid:
            fail(tns, f"not pointable at {science_start.strftime('%H:%M')} "
                      f"-- {reason}")
            continue

        exp = estimate_mos_exposure(row['mag_r']) if row['lris_mode'].startswith('MOS') \
            else _target_exposure(row, am, etc_opts)
        nominal = exp['science_min']
        entry = row.to_dict()
        entry.update(exp)
        acq_min = keck_acquisition_minutes(row['lris_mode'])
        entry.update({
            'TNS': tns,
            'slew_min': KECK_SLEW_BASE_MIN,
            'slew_reason': '',
            'acq_min': acq_min,
            'on_target_min': got,
            'total_min': KECK_SLEW_BASE_MIN + acq_min + got,
            'scheduled_start': science_start - timedelta(
                minutes=KECK_SLEW_BASE_MIN + acq_min),
            'science_start': science_start,
            'scheduled_end': obs_end,
            'window_start': window_start,
            'window_end': window_end,
            'info': (f"FORCED truncated exposure: {got:.0f} of {nominal:g} min "
                      f"nominal ({got / nominal:.0%}), AM {am:.2f}"),
        })
        rows.append(entry)
        reservations.append((science_start - pad - timedelta(minutes=acq_min),
                             obs_end, f'forced {tns}'))
        print(f"  Forced {tns}: {science_start.strftime('%H:%M')}-"
              f"{obs_end.strftime('%H:%M')} ({got:.0f} min of {nominal:g} nominal, "
              f"AM {am:.2f})")
    return rows, reservations

def _flag_near_zenith(selected, step_min=5):
    """
    Warn about blocks that pass above the Keck guiding limit (T3.6).

    Keck says stable guiding can't be guaranteed above ~85 deg elevation
    (TelLimits page). Such a block is legal, since it stays below the 88.9 deg
    tracking limit enforced in check_keck_limits, but the observer should
    know. The warning is appended to the row's 'info', which becomes the
    plan's notes.

    Parameters
    ----------
    selected : list of row dicts (modified in place)
    step_min : float

    Returns
    -------
    int : number of rows flagged.
    """
    from night_planner.sky import track

    n = 0
    for row in selected:
        t0, t1 = row.get('science_start'), row.get('scheduled_end')
        if t0 is None or t1 is None:
            continue
        steps = max(1, int(((t1 - t0).total_seconds() / 60) // step_min))
        times = [t0 + (t1 - t0) * i / steps for i in range(steps + 1)]
        alt = max(track(row['RA_deg'], row['Dec_deg'], times, KECK)['alt'])
        row['max_alt'] = alt
        if alt > KECK1_GUIDE_WARN:
            note = (f"passes {alt:.1f}° elevation (> {KECK1_GUIDE_WARN:g}°): "
                    f"stable guiding not guaranteed near zenith")
            row['info'] = f"{row.get('info') or ''} | {note}".strip(' |')
            row['zenith_warning'] = True
            n += 1
    return n


def _initial_exposure(row, etc_opts=None):
    """
    A target's first exposure guess and where its time comes from (T3.3).

    Parameters
    ----------
    row : mapping (a results_df row with its window)
    etc_opts : dict, optional

    Returns
    -------
    (exp, time_source, etc_min)
        exp : dict as from estimate_lris_exposure (science_min, recipes, ...)
        time_source : 'user' (t_target wins), 'MOS block', 'fixed recipe'
            or 'ETC' (sized at the night's best airmass for now)
        etc_min : the ETC's estimate, kept beside a user time unless
            --no-etc-for-user-times; None otherwise
    """
    user_t = row.get('t_target', np.nan)
    user_t = float(user_t) if pd.notna(user_t) else None
    etc_min = None
    if row['TNS'] in LONGSLIT_FORCED:
        exp, time_source = forced_longslit_exposure(row['TNS']), 'fixed recipe'
    elif str(row['lris_mode']).startswith('MOS'):
        exp, time_source = estimate_mos_exposure(row['mag_r']), 'MOS block'
    elif user_t is not None and (etc_opts or {}).get('no_etc_for_user_times'):
        exp, time_source = None, 'user'
    else:
        exp, time_source = _target_exposure(row, row['min_airmass'], etc_opts), 'ETC'
        etc_min = exp['science_min']
    if user_t is not None:
        exp = {'red_exp': f'{user_t:g} min (user)', 'blue_exp': f'{user_t:g} min (user)',
               'science_min': user_t, 'total_min': user_t,
               'mode': (exp or {}).get('mode', 'longslit')}
        time_source = 'user'
    return exp, time_source, etc_min


def _greedy_pass(observable, current_time, prev_dec, blocks, available_time,
                 total_time, max_targets, skip, etc_opts=None):
    """
    The LRIS window-order greedy pass (refactored out of
    select_targets_for_night for priority tiers, 2026-11-07, M8; the
    single-tier schedule is pinned by tests/snapshots/lris_single_tier.json).

    Parameters
    ----------
    observable : DataFrame with window_start / window_end
    current_time : datetime, where the pass may start
    prev_dec : float, where the telescope points first
    blocks : list of (start, end, reason)
    available_time, total_time : float minutes (budget, already used)
    max_targets : int
    skip : callable(tns, reason, window_start, window_end)
    etc_opts : dict, optional

    Returns
    -------
    (selected, total_time, current_time, prev_dec)
    """
    selected = []
    scheduled_targets = set()
    observable = observable.sort_values('window_start')

    # Schedule targets in window order
    for idx, row in observable.iterrows():
        if row['TNS'] in scheduled_targets:
            continue

        exp, time_source, etc_min = _initial_exposure(row, etc_opts)
        window_start = row['window_start']
        window_end = row['window_end']

        if window_start is None or window_end is None:
            skip(row['TNS'], "no observable window")
            continue

        # Skip if window already completely passed
        if current_time > window_end:
            skip(row['TNS'], f"window already passed (ended "
                              f"{window_end.strftime('%H:%M')}, now "
                              f"{current_time.strftime('%H:%M')})",
                 window_start, window_end)
            continue

        # Slew from the previous pointing (Keck rule, keck_overheads.py). The
        # slew replaces the flat +5 min "slew/acquisition" in lris_etc's
        # total_min, so on-target time is science_min (for MOS, science_min
        # is the full allocated block, mask alignment included).
        slew_min = keck_slew_minutes(prev_dec, row['Dec_deg'])
        # Acquisition follows the slew, before science (2026-11-07, T1.2).
        acq_min = keck_acquisition_minutes(row['lris_mode'])
        pre_min = slew_min + acq_min

        # Earliest the slew could start, ignoring blocks: slew and
        # acquisition done and the target is in its window (or wait for
        # the window to open).
        raw_slew_start = max(current_time, window_start - timedelta(minutes=pre_min))

        # Place, then re-run the ETC at the airmass the target actually gets
        # over its science span (T1.3, --airmass-rule), and re-place if the
        # exposure grew. The first guess uses the night's best airmass, and
        # under 'worst' the exposure only grows as the block lengthens, so
        # this settles within a few rounds. MOS blocks and fixed forced
        # recipes don't depend on airmass.
        airmass_aware = time_source == 'ETC'
        rule = (etc_opts or {}).get('airmass_rule', 'worst')
        am_used = row['min_airmass']
        settled = False
        tblocks = list(blocks) + list(row.get('keyhole') or [])
        # The block is always re-fitted to the latest exposure, so the
        # placement and the exposure can't disagree; iteration stops once
        # a re-run changes the exposure by <= 0.5 min.
        for _round in range(MAX_AIRMASS_ROUNDS + 1):
            on_target_min = exp['science_min']
            # Readout per frame (T1.1). None = NOT SET: charge nothing; the
            # adapter flags it in the plan's assumptions. MOS blocks are
            # allocations that already include readout.
            readout_min = 0.0
            if not str(row['lris_mode']).startswith('MOS'):
                readout_min = readout_minutes(
                    'lris', exp.get('red_exp'), exp.get('blue_exp'),
                    (etc_opts or {}).get('config') or DEFAULT_CONFIG['lris']) or 0.0
            block_min = on_target_min + readout_min
            # find_observable_window() samples every WINDOW_SAMPLE_MIN, so the
            # true edge of the airmass window lies somewhere inside the step
            # beyond the last good sample. One step of grace is the honest
            # width of that uncertainty -- it is not spare observing time,
            # and widening it would schedule above the airmass limit.
            obs_start, obs_end = fit_around_blocks(
                raw_slew_start, pre_min + block_min,
                window_end + timedelta(minutes=WINDOW_SAMPLE_MIN), tblocks)
            if (obs_start is None or not airmass_aware or settled
                    or _round == MAX_AIRMASS_ROUNDS):
                break
            sci0 = obs_start + timedelta(minutes=pre_min)
            am = block_airmass(row['RA_deg'], row['Dec_deg'], sci0,
                               sci0 + timedelta(minutes=on_target_min), rule,
                               KECK)
            if am is None:
                break
            new_exp = _target_exposure(row, am, etc_opts)
            settled = abs(new_exp['science_min'] - exp['science_min']) <= 0.5
            exp, am_used = new_exp, am

        if obs_start is None:
            reason = blocking_reason(raw_slew_start, pre_min + block_min, tblocks)
            am_note = (f" (exposure at {rule} airmass {am_used:.2f}; best "
                       f"{row['min_airmass']:.2f})"
                       if airmass_aware and am_used != row['min_airmass'] else '')
            if reason:
                skip(row['TNS'], f"{reason} -- doesn't clear before its window "
                                  f"closes ({window_end.strftime('%H:%M')})",
                     window_start, window_end)
            else:
                skip(row['TNS'],
                     f"needs {on_target_min:.0f} min on target{am_note} "
                     f"(+{slew_min} min slew, +{acq_min} min acquisition, "
                     f"+{readout_min:.0f} min readout) but only "
                     f"{(window_end - raw_slew_start).total_seconds()/60:.0f} min left in its "
                     f"AM<2.0 window ({window_start.strftime('%H:%M')}-{window_end.strftime('%H:%M')})",
                     window_start, window_end)
            continue

        science_start = obs_start + timedelta(minutes=pre_min)

        # Check if we have time budget
        obs_duration = pre_min + block_min
        if total_time + obs_duration > available_time:
            skip(row['TNS'], f"no time budget left "
                              f"({total_time:.0f}/{available_time:.0f} min used)",
                 window_start, window_end)
            continue

        row_dict = row.to_dict()
        row_dict.update(exp)
        row_dict['slew_min'] = slew_min
        row_dict['slew_reason'] = keck_slew_reason(prev_dec, row['Dec_deg'])
        row_dict['acq_min'] = acq_min
        row_dict['readout_min'] = readout_min
        row_dict['on_target_min'] = on_target_min
        row_dict['airmass_used'] = am_used
        row_dict['airmass_rule'] = rule if airmass_aware else ''
        row_dict['time_source'] = time_source
        # The ETC's estimate at the airmass used (for 'user' rows, the
        # first-guess estimate, shown beside the user's time).
        row_dict['etc_min'] = (exp['science_min'] if time_source == 'ETC'
                               else etc_min)
        row_dict['required'] = bool(row.get('required', False))
        row_dict['total_min'] = obs_duration
        row_dict['scheduled_start'] = obs_start  # slew start
        row_dict['science_start'] = science_start
        row_dict['scheduled_end'] = obs_end
        selected.append(row_dict)
        scheduled_targets.add(row['TNS'])
        total_time += obs_duration
        current_time = obs_end
        prev_dec = row['Dec_deg']

        if len(selected) >= max_targets:
            break

    return selected, total_time, current_time, prev_dec


def _insert_tier(pool, selected, tier, night_start, night_limit, blocks,
                 available_time, total_time, max_targets, skip, etc_opts=None):
    """
    Place one lower priority tier into the gaps the tiers above left
    (T1.6). Placed targets never move.

    The fit test is exact, not padded: Keck slews depend on the previous
    Dec, so putting X between A and B changes B's slew. X fits a gap when

        A.end + slew(A->X) + acq(X) + X (exposure + readout)
            + slew(X->B) + acq(B) <= B.science_start

    and X's science ends inside its own window (plus one sample of grace,
    as in the greedy pass). B's slew is then recomputed and its slew start
    moved; its science time is untouched.

    Parameters
    ----------
    pool : DataFrame, this tier's observable targets (with windows)
    selected : list of row dicts already placed (modified copies returned)
    tier : float
    night_start : datetime, start of science
    night_limit : datetime, latest end (morning twilight minus the
        closing slew + standard)
    blocks, available_time, total_time, max_targets, skip, etc_opts :
        as for _greedy_pass

    Returns
    -------
    (selected, total_time)
    """
    selected = [dict(r) for r in selected]
    for _, row in pool.sort_values('window_start').iterrows():
        ws, we = row['window_start'], row['window_end']
        if ws is None or we is None:
            skip(row['TNS'], f'priority P{tier:g}: no observable window')
            continue
        if len(selected) >= max_targets:
            skip(row['TNS'], f'priority P{tier:g}: max targets reached', ws, we)
            continue
        exp, time_source, etc_min = _initial_exposure(row, etc_opts)
        acq_x = keck_acquisition_minutes(row['lris_mode'])
        aware = time_source == 'ETC'
        rule = (etc_opts or {}).get('airmass_rule', 'worst')
        placed = sorted(selected, key=lambda r: r['scheduled_start'])
        prevs = [None] + placed
        nexts = placed + [None]
        done = False
        for a, b in zip(prevs, nexts):
            gap_start = a['scheduled_end'] if a else night_start
            prev_dec = a['Dec_deg'] if a else EVENING_STANDARD_DEC
            slew_x = keck_slew_minutes(prev_dec, row['Dec_deg'])
            pre_x = slew_x + acq_x
            if b is not None:
                slew_b = keck_slew_minutes(row['Dec_deg'], b['Dec_deg'])
                acq_b = b.get('acq_min', keck_acquisition_minutes(b.get('lris_mode')))
                latest = b['science_start'] - timedelta(minutes=slew_b + acq_b)
            else:
                slew_b = acq_b = 0
                latest = night_limit
            limit = min(latest, we + timedelta(minutes=WINDOW_SAMPLE_MIN))
            earliest = max(gap_start, ws - timedelta(minutes=pre_x))
            if earliest >= limit:
                continue
            e, am_used, settled = exp, row['min_airmass'], False
            for _round in range(MAX_AIRMASS_ROUNDS + 1):
                readout = 0.0
                if not str(row['lris_mode']).startswith('MOS'):
                    readout = readout_minutes(
                        'lris', e.get('red_exp'), e.get('blue_exp'),
                        (etc_opts or {}).get('config') or DEFAULT_CONFIG['lris']) or 0.0
                block = e['science_min'] + readout
                start, end = fit_around_blocks(
                    earliest, pre_x + block, limit,
                    list(blocks) + list(row.get('keyhole') or []))
                if start is None or not aware or settled or _round == MAX_AIRMASS_ROUNDS:
                    break
                sci0 = start + timedelta(minutes=pre_x)
                am = block_airmass(row['RA_deg'], row['Dec_deg'], sci0,
                                   sci0 + timedelta(minutes=e['science_min']), rule, KECK)
                if am is None:
                    break
                new = _target_exposure(row, am, etc_opts)
                settled = abs(new['science_min'] - e['science_min']) <= 0.5
                e, am_used = new, am
            if start is None:
                continue
            # B's new slew must not run into a blocked window either.
            if b is not None and _overlapping_block(
                    b['science_start'] - timedelta(minutes=slew_b + acq_b),
                    b['science_start'], blocks) is not None:
                continue
            delta_b = (slew_b - b['slew_min']) if b is not None else 0
            duration = pre_x + block
            if total_time + duration + delta_b > available_time:
                continue
            x = row.to_dict()
            x.update(e)
            x.update({
                'slew_min': slew_x, 'slew_reason': keck_slew_reason(prev_dec, row['Dec_deg']),
                'acq_min': acq_x, 'readout_min': readout,
                'on_target_min': e['science_min'], 'total_min': duration,
                'scheduled_start': start, 'science_start': start + timedelta(minutes=pre_x),
                'scheduled_end': end, 'airmass_used': am_used,
                'airmass_rule': rule if aware else '', 'time_source': time_source,
                'etc_min': e['science_min'] if time_source == 'ETC' else etc_min,
                'required': bool(row.get('required', False)),
            })
            if b is not None:
                b['slew_min'] = slew_b
                b['slew_reason'] = keck_slew_reason(row['Dec_deg'], b['Dec_deg'])
                b['scheduled_start'] = b['science_start'] - timedelta(minutes=slew_b + acq_b)
                b['total_min'] = b['total_min'] + delta_b
            selected.append(x)
            total_time += duration + delta_b
            done = True
            break
        if not done:
            skip(row['TNS'], f'priority P{tier:g}: no gap left by the higher tier(s) '
                             f'fits its {exp["science_min"]:.0f} min (+slew/acq) inside '
                             f'its window {ws:%H:%M}-{we:%H:%M}', ws, we)
    return selected, total_time


def select_targets_for_night(results_df, twilight, max_targets=8,
                              start_override=None, blocks=None, skip_log=None,
                              forced=None, forced_failures=None,
                              reserved=None, reservations=None, etc_opts=None):
    """
    Select targets for observation based on priority rules.

    Priority:
    1. Must be observable (airmass < 2.0 for >30 min)
    2. Schedule within observable window
    3. If target is setting early, observe first
    4. Cover RA range efficiently

    Parameters
    ----------
    start_override : datetime, optional
        Manual night-start override (e.g. telescope handed back after a
        ToO) -- see schedule_overrides.resolve_start(). Replaces the
        normal twilight+10min seed when given.
    blocks : list of (start, end, reason) tuples, optional
        Blacked-out windows (ToO, weather hold, engineering) the
        schedule must route around -- see schedule_overrides.py.
    skip_log : dict, optional
        Filled in place with TNS -> reason for every target this function
        declines to schedule. The same strings are still printed; this
        just makes them available structurally, so callers don't have to
        regex them back out of captured stdout.

    Returns
    -------
    selected : DataFrame with observing order and scheduled times
    """
    blocks = blocks or []

    def skip(tns, reason, window_start=None, window_end=None):
        """Record and print one skip, with the target's window if known."""
        if skip_log is not None:
            skip_log[tns] = {'reason': reason, 'window_start': window_start,
                             'window_end': window_end}
        print(f"  Skipped {tns}: {reason}")
    # Filter to observable targets. Per the author (2026-09-11): include
    # MOS-mask-required targets (mag > 21) in the night plan too, scheduled
    # with their real allocated time (estimate_mos_exposure(), ~1-2h --
    # estimate_lris_exposure() already dispatches to it below), on the
    # assumption a mask can be milled before the run (~4 weeks out from
    # 2026-10-06). Submitting mask designs promptly is still required --
    # this schedules the *time*, not a guarantee the mask exists yet.
    observable = results_df[results_df['observable']].copy()
    n_mos_included = int((observable['lris_mode'] == 'MOS (mask required)').sum())

    print(f"\n=== TARGET SELECTION ===")
    print(f"Sky-observable targets: {len(observable)} / {len(results_df)} "
          f"({n_mos_included} need a MOS mask, included below with allocated time)")

    if len(observable) == 0:
        print("No observable targets!")
        return pd.DataFrame()

    # Calculate observable windows
    windows = []
    for idx, row in observable.iterrows():
        start, end, duration = find_observable_window(
            row['RA_deg'], row['Dec_deg'], twilight, row['mag_r'])
        windows.append({
            'window_start': start,
            'window_end': end,
            'window_hours': duration,
            # Minutes near transit when it's above the tracking limit; a
            # block may not straddle them (T3.6).
            'keyhole': zenith_keyhole(row['RA_deg'], row['Dec_deg'], twilight),
        })

    window_df = pd.DataFrame(windows, index=observable.index)
    observable = pd.concat([observable, window_df], axis=1)

    # Sort by window end time (observe setting targets first)
    # This ensures targets about to set are prioritized
    observable = observable.sort_values('window_end')

    # Two-pass scheduling:
    # Pass 1: Schedule targets observable now or soon (setting targets)
    # Pass 2: Schedule targets that rise later (wait for window)
    selected = []
    default_start = twilight['evening_hst'] + timedelta(minutes=10)  # After standard + focus
    current_time = push_past_blocks(resolve_start(default_start, start_override), blocks)

    # Second pass only: forced targets that could not be appended already
    # hold a reserved slot, handed in as blocks so this pass fills the
    # night around them rather than over them.
    reserved = list(reserved or [])
    if reservations:
        blocks = list(blocks) + list(reservations)
        current_time = push_past_blocks(current_time, blocks)
        observable = observable[~observable['TNS'].isin(
            {r['TNS'] for r in reserved})]
    available_time = twilight['dark_hours'] * 60 - MORNING_RESERVE_MIN
    total_time = 0
    scheduled_targets = set()
    # Telescope is left pointed at the evening standard after standard + focus
    prev_dec = EVENING_STANDARD_DEC

    # Sort by window start for proper ordering
    observable = observable.sort_values('window_start')

    # Priority tiers (T1.6, 2026-11-07): the top tier is scheduled over the
    # whole night exactly as before; each lower tier only gets the gaps the
    # tiers above left, with every placed target immovable. One tier (no
    # priorities set) is the old behaviour unchanged.
    tiers = (sorted(observable['priority'].dropna().unique())
             if 'priority' in observable.columns else [])
    if len(tiers) <= 1:
        selected, total_time, current_time, prev_dec = _greedy_pass(
            observable, current_time, prev_dec, blocks, available_time,
            total_time, max_targets, skip, etc_opts)
    else:
        print(f"Scheduling in {len(tiers)} priority tiers: "
              + ', '.join(f'P{t:g}' for t in tiers))
        night_start = current_time
        selected, total_time, current_time, prev_dec = _greedy_pass(
            observable[observable['priority'] == tiers[0]], current_time,
            prev_dec, blocks, available_time, total_time, max_targets, skip,
            etc_opts)
        print(f"  P{tiers[0]:g}: {len(selected)} scheduled (whole night)")
        night_limit = twilight['morning_hst'] - timedelta(minutes=MORNING_RESERVE_MIN)
        for tier in tiers[1:]:
            before = len(selected)
            selected, total_time = _insert_tier(
                observable[observable['priority'] == tier], selected, tier,
                night_start, night_limit, blocks, available_time, total_time,
                max_targets, skip, etc_opts)
            print(f"  P{tier:g}: {len(selected) - before} inserted into gaps")
        if selected:
            last = max(selected, key=lambda r: r['scheduled_end'])
            current_time, prev_dec = last['scheduled_end'], last['Dec_deg']

    # Forced targets: append after the schedule if they are still up, which
    # costs nothing. Anything that cannot be appended -- the setting target
    # whose window shut hours before the schedule ended -- gets a reserved
    # slot inside its own window, and the whole night is scheduled again
    # around it. Only then is a failure real.
    if forced:
        append_failures = []
        appended = append_forced_targets(
            selected, results_df, twilight, forced, prev_dec, current_time,
            failures=append_failures, etc_opts=etc_opts)
        selected += appended
        placed = {r['TNS'] for r in appended}
        unplaced = [(tns, minutes) for tns, minutes in forced
                    if tns not in placed]
        if unplaced and reservations is None:
            print('  Retrying unplaceable forced targets with a reserved slot')
            rows, slots = reserve_forced_targets(
                results_df, twilight, unplaced,
                push_past_blocks(resolve_start(default_start, start_override),
                                  blocks),
                blocks, failures=forced_failures, etc_opts=etc_opts)
            if rows:
                # Pass 1's skips described a night that no longer exists.
                if skip_log is not None:
                    skip_log.clear()
                return select_targets_for_night(
                    results_df, twilight, max_targets=max_targets,
                    start_override=start_override, blocks=blocks,
                    skip_log=skip_log,
                    forced=[f for f in forced
                            if f[0] not in {r['TNS'] for r in rows}],
                    forced_failures=forced_failures,
                    reserved=rows, reservations=slots, etc_opts=etc_opts)
        elif unplaced and forced_failures is not None:
            forced_failures.extend(append_failures)
    selected += reserved
    _flag_near_zenith(selected)

    # Sort selected by scheduled start time
    selected_df = pd.DataFrame(selected)
    if len(selected_df) > 0:
        selected_df = selected_df.sort_values('scheduled_start')

    print(f"Selected {len(selected_df)} targets")
    print(f"Total observing time: {total_time:.0f} min ({total_time/60:.1f} h)")
    print(f"Available dark time: {available_time:.0f} min ({available_time/60:.1f} h)")

    return selected_df


def generate_starlist(selected_df, output_path):
    """
    Generate Keck starlist file.

    Format: name  HH MM SS.ss  ±DD MM SS.s  equinox  [keywords]
    """
    lines = []
    lines.append("# Keck/LRIS starlist for Oct 6, 2026")
    lines.append("# Created by JXP and Claude")
    lines.append("")
    lines.append("# === Standard Stars ===")
    # Add typical flux standards
    lines.append("BD28d4211  21 51 11.02 +28 51 50.4 2000.0 vmag=10.5 # Flux standard")
    lines.append("Feige110   23 19 58.40 -05 09 56.2 2000.0 vmag=11.8 # Flux standard")
    lines.append("")
    lines.append("# === Science Targets ===")

    for idx, row in selected_df.iterrows():
        # Parse RA/Dec to sexagesimal
        ra_deg = row['RA_deg']
        dec_deg = row['Dec_deg']

        ra_h = int(ra_deg / 15)
        ra_m = int((ra_deg / 15 - ra_h) * 60)
        ra_s = ((ra_deg / 15 - ra_h) * 60 - ra_m) * 60

        dec_sign = '+' if dec_deg >= 0 else '-'
        dec_abs = abs(dec_deg)
        dec_d = int(dec_abs)
        dec_m = int((dec_abs - dec_d) * 60)
        dec_s = ((dec_abs - dec_d) * 60 - dec_m) * 60

        # Format name (max 16 chars)
        name = row['TNS'][:16]

        # Format coordinates
        ra_str = f"{ra_h:02d} {ra_m:02d} {ra_s:05.2f}"
        dec_str = f"{dec_sign}{dec_d:02d} {dec_m:02d} {dec_s:04.1f}"

        # Keywords
        mag = row['mag_r']
        line = f"{name:<16}  {ra_str}  {dec_str}  2000.0  vmag={mag:.1f}"

        # Flag mask-required targets prominently -- these need a pre-milled
        # slitmask, not a plain longslit acquisition
        comment_bits = []
        if row.get('lris_mode') == 'MOS (mask required)':
            comment_bits.append('MASK REQUIRED')
        if row.get('tags'):
            comment_bits.append(str(row['tags']))
        if comment_bits:
            line += f"  # {' | '.join(comment_bits)}"

        lines.append(line)

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"\nStarlist written to: {output_path}")


def print_night_plan(selected_df, twilight, start_hst):
    """Print formatted night plan to console."""
    print("\n" + "="*70)
    print("KECK/LRIS NIGHT PLAN - October 6, 2026")
    print("="*70)

    print(f"\nEvening 18° twilight: {twilight['evening_hst'].strftime('%H:%M HST')}")
    print(f"Morning 18° twilight: {twilight['morning_hst'].strftime('%H:%M HST')}")
    print(f"Dark time: {twilight['dark_hours']:.1f} hours")
    print(f"Timeline start: {start_hst.strftime('%H:%M HST')}")

    print("\n--- TIMELINE ---")
    current_time = start_hst

    # Evening standard
    print(f"\n{current_time.strftime('%H:%M')} HST - Flux standard (BD28d4211) - 5 min")
    current_time += timedelta(minutes=5)

    # Focus
    print(f"{current_time.strftime('%H:%M')} HST - Focus check - 5 min")
    current_time += timedelta(minutes=5)

    # Science targets
    print("\n--- SCIENCE TARGETS ---")
    for idx, row in selected_df.iterrows():
        # Use scheduled times if available
        if 'scheduled_start' in row and pd.notna(row['scheduled_start']):
            obs_start = row['scheduled_start']
            obs_end = row['scheduled_end']
        else:
            obs_start = current_time
            obs_end = current_time + timedelta(minutes=row['total_min'])

        # Calculate HA at observation time
        obs_utc = obs_start.astimezone(timezone.utc)
        am, alt, _, ha = calculate_airmass(row['RA_deg'], row['Dec_deg'], obs_utc)

        mode_tag = " [MOS - MASK REQUIRED]" if row.get('lris_mode') == 'MOS (mask required)' else ""
        print(f"\n{obs_start.strftime('%H:%M')}-{obs_end.strftime('%H:%M')} HST: "
              f"{row['TNS']}{mode_tag}")
        print(f"  Slew: {row['slew_min']} min, acquisition: {row.get('acq_min', 0)} min, on target from "
              f"{row['science_start'].strftime('%H:%M')} ({row['on_target_min']} min)")
        print(f"  RA: {row['RA_hours']:.2f}h  Dec: {row['Dec_deg']:.1f}°  "
              f"mag_r: {row['mag_r']:.1f}")
        print(f"  HA: {ha:+.1f}h  Airmass: {am:.2f}  Alt: {alt:.0f}°")
        print(f"  Exposure: {row['red_exp']} (red), {row['blue_exp']} (blue)")
        print(f"  Duration: {row['total_min']} min (incl. slew + acquisition)")
        print(f"  Window: {row['window_start'].strftime('%H:%M')}-{row['window_end'].strftime('%H:%M')} HST")

        current_time = obs_end

    # Morning standard
    last_dec = selected_df['Dec_deg'].iloc[-1] if len(selected_df) else EVENING_STANDARD_DEC
    slew = keck_slew_minutes(last_dec, MORNING_STANDARD_DEC)
    print(f"\n{current_time.strftime('%H:%M')} HST - Slew to Feige110 - {slew} min")
    current_time += timedelta(minutes=slew)
    print(f"{current_time.strftime('%H:%M')} HST - Flux standard (Feige110) - "
          f"{MORNING_STANDARD_MIN} min")
    current_time += timedelta(minutes=MORNING_STANDARD_MIN)

    print("Calibrations: see the Observing log page (not scheduled).")

    print("\n" + "="*70)


def print_recommendations(selected_df, twilight, n_mos=0):
    """Print LRIS recommendations and night summary."""
    total_science_min = sum(row['on_target_min'] for _, row in selected_df.iterrows())
    total_slew_min = sum(row['slew_min'] for _, row in selected_df.iterrows())
    total_acq_min = sum(row.get('acq_min', 0) or 0 for _, row in selected_df.iterrows())
    dark_min = twilight['dark_hours'] * 60

    print("\n" + "="*70)
    print("RECOMMENDATIONS")
    print("="*70)
    print(f"""
LRIS Mode Summary:
  - LONGSLIT: mag ≤ 21 (all current targets OK)
  - MOS: mag > 21 requires pre-milled slitmasks (weeks lead time)
  - IMAGING: Available for acquisition, field verification, photometry

Night Utilization:
  - Science time: {total_science_min/60:.1f}h of {dark_min/60:.1f}h available ({100*total_science_min/dark_min:.0f}%)
  - Slew time: {total_slew_min:.0f} min (Keck rule: {KECK_SLEW_BASE_MIN} min base, {KECK_SLEW_DEC_CROSS_MIN} min Dec<+20 -> Dec>+20)
  - Acquisition: {total_acq_min:.0f} min (5 min longslit, 10 min mask)
  - Gaps in schedule: Could fill with imaging or backup targets

Target Recommendations:
  - Real LRIS exposures (S/N=10/exposure, 3x min) run ~19-58 min per target
    depending on magnitude -- request more targets from FFFF-PZ
    (num_targ_longslit above 20) to fill the remaining gap
  - Include imaging targets (status=NeedImage) for backup/gap filling
  - For mag > 21 targets: submit mask designs weeks before run ({n_mos}
    already in hand from this pull, sky-observable, just needing masks;
    ~1-2h on-target once milled, per magnitude)
""")


def parse_args(argv=None):
    """
    Parameters
    ----------
    argv : list of str, optional
        Defaults to sys.argv[1:]. Passed explicitly by night_planner.cli
        when this module is driven through the `night-planner` console
        command instead of run standalone.
    """
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', help='Path to a night-plan JSON config '
                   '(night_plan_io.NightPlanConfig). CLI flags below '
                   'override whatever the config contains.')
    p.add_argument('--start', help='Manual night-start override, HH:MM local '
                   '(Pacific/Honolulu) or full ISO datetime. This is the '
                   'telescope-handback time (e.g. after a ToO) -- standard '
                   'star + focus still run first, science begins 10 min '
                   'later.')
    p.add_argument('--block', action='append', default=[],
                   help='Blocked-out window, "HH:MM-HH:MM" or '
                   '"HH:MM-HH:MM@reason". Repeatable.')
    p.add_argument('--set-time', action='append', default=[],
                   help='Set a target\'s time on target, "TNS@MINUTES", as if '
                        'the table\'s t_target said so; it is then scheduled '
                        'normally. Repeatable.')
    p.add_argument('--set-sn', action='append', default=[],
                   help='Set a target\'s S/N per sub-exposure, "TNS@SN", as if '
                        'the table\'s target_sn said so. Repeatable.')
    p.add_argument('--force', action='append', default=[],
                   help='Force a target in after the normal schedule with a '
                   'truncated exposure: "TNS@MINUTES" (e.g. '
                   'TGT0461@80). Use when a partial spectrum is worth '
                   'more than the empty time the scheduler would leave. '
                   'Repeatable.')
    p.add_argument('--assume-masks', action='store_true',
                   help='Schedule every mag>21 target that needs a MOS mask, '
                        'including ones with no mask yet, on the commitment '
                        'that one will be milled before the run. Allocates '
                        'the time; the designs still have to be submitted.')
    p.add_argument('--targets-csv')
    p.add_argument('--output-dir')
    p.add_argument('--date')
    p.add_argument('--max-targets', type=int)
    add_config_args(p, 'lris')
    p.add_argument('--no-etc-for-user-times', action='store_true',
                   help='Skip the ETC for rows with a t_target (saves the '
                        'network calls; the plan then shows no ETC estimate '
                        'beside the user time).')
    return p.parse_args(argv)


def _parse_block_flag(spec):
    """Parse '--block HH:MM-HH:MM' or '--block HH:MM-HH:MM@reason'."""
    window, _, reason = spec.partition('@')
    start, end = window.split('-')
    return {'start': start, 'end': end, 'reason': reason or 'blocked'}


def run(args):
    """Execute the calculation pipeline for an already-parsed args namespace.

    Split out from main() so night_planner.cli can call this directly with
    its own argparse namespace, instead of re-parsing sys.argv a second
    time (which would collide with the CLI's own `--instrument` etc.).
    """
    from night_plan_io import load_config, resolve_local_dt, resolve_blocks, save_night_meta, OBSERVATORY_TZ

    # Defaults match the committed Oct 6 plan exactly when no flags/config
    # are given -- Keck-native FFFF-PZ pull (Keck-2026B-01 Resource kept as
    # the earlier record) superseded by the Keck-2026B-02 global pull
    # (2026-09-30: 10 mask + 20 longslit, Oct 6 HST window).
    if args.config:
        cfg = load_config(args.config)
    else:
        cfg = None

    targets_csv = (args.targets_csv or (cfg.targets_csv if cfg else None)
                   or f'{_PLANS}/Keck-2026B-02/Keck-2026B-02_targets.csv')
    date = args.date or (cfg.date if cfg else None) or '2026-10-06'
    output_dir = (args.output_dir or (cfg.output_dir if cfg else None)
                  or f'{_PLANS}/Keck-2026B-02')
    max_targets = args.max_targets or (cfg.max_targets if cfg else None) or 20
    try:
        etc_opts = resolve_options(args, cfg, 'lris')
    except ConfigError as err:
        raise SystemExit(f'error: {err}')
    etc_opts['no_etc_for_user_times'] = getattr(args, 'no_etc_for_user_times', False)

    start_spec = args.start or (cfg.start_override if cfg else None)
    block_specs = list(cfg.blocks) if cfg else []
    block_specs += [_parse_block_flag(b) for b in args.block]

    tz = OBSERVATORY_TZ['keck']
    start_override_local = (resolve_local_dt(date, start_spec, tz)
                             if start_spec else None)
    blocks = resolve_blocks(date, block_specs, tz)

    os.makedirs(output_dir, exist_ok=True)

    # Analyze all targets
    results_df, twilight, start_hst = analyze_targets(
        targets_csv, date, assume_masks=args.assume_masks,
        time_overrides=getattr(args, 'set_time', None),
        sn_overrides=getattr(args, 'set_sn', None))

    # A manual start overrides the timeline-start used for the standard
    # star / focus block too (not just the science scheduler) -- the
    # observer hands back the telescope at this clock time, then does
    # standard+focus, then science 10 min after that.
    if start_override_local is not None:
        start_hst = start_override_local
        science_start_override = start_hst + timedelta(minutes=10)
    else:
        science_start_override = None

    if blocks:
        print(f"\n=== BLOCKED WINDOWS ===")
        for b_start, b_end, reason in blocks:
            print(f"  {b_start.strftime('%H:%M')}-{b_end.strftime('%H:%M')} HST: {reason}")
    if start_override_local is not None:
        print(f"\nManual night start: {start_hst.strftime('%H:%M HST')} "
              f"(science begins {science_start_override.strftime('%H:%M HST')})")

    # Print full analysis
    print("\n=== ALL TARGETS (sorted by RA) ===")
    display_cols = ['TNS', 'RA_hours', 'Dec_deg', 'mag_r', 'lris_mode',
                    'min_airmass', 'observable', 'limit_reason', 'info']
    print(results_df[display_cols].to_string(index=False))

    # Check for MOS-required targets (still included in the schedule below,
    # with their allocated ~1-2h time -- flagged here as a reminder that
    # each needs a slitmask milled before the run, not as an exclusion)
    mos_targets = results_df[results_df['lris_mode'] == 'MOS (mask required)']
    if len(mos_targets) > 0:
        print(f"\n*** NOTE: {len(mos_targets)} targets need MOS masks (mag > 21) ***")
        print("Included in the night plan below with allocated time -- submit mask designs now:")
        print(mos_targets[['TNS', 'mag_r', 'info']].to_string(index=False))

    forced, forced_failures = [], []
    for spec in args.force:
        tns, _, minutes = spec.partition('@')
        forced.append((tns, float(minutes)))

    # Select targets for night
    skip_log = {}
    selected = select_targets_for_night(
        results_df, twilight, max_targets=max_targets,
        start_override=science_start_override, blocks=blocks,
        skip_log=skip_log, forced=forced, forced_failures=forced_failures,
        etc_opts=etc_opts)
    from night_planner.etc import write_spectra
    write_spectra(output_dir, list(selected['TNS']) if len(selected) else [],
                  etc_opts.pop('_spectra', {}))

    if len(selected) > 0:
        # Print night plan
        print_night_plan(selected, twilight, start_hst)

        # Print recommendations
        print_recommendations(selected, twilight, n_mos=len(mos_targets))

        # Generate starlist
        starlist_path = f'{output_dir}/keck_lris_oct06.starlist'
        generate_starlist(selected, starlist_path)

        # Save results
        results_df.to_csv(f'{output_dir}/target_analysis.csv', index=False)
        selected.to_csv(f'{output_dir}/selected_targets.csv', index=False)

        print(f"\nResults saved to {output_dir}/")
        print(f"  - target_analysis.csv: all targets with observability")
        print(f"  - selected_targets.csv: selected targets")
        print(f"  - keck_lris_oct06.starlist: Keck starlist")

    meta_path = save_night_meta(
        output_dir, start_local=start_hst,
        evening_twilight_local=twilight['evening_hst'],
        morning_twilight_local=twilight['morning_hst'],
        blocks=blocks, date=date)
    print(f"  - night_meta.json: resolved start/blocks for the Excel builder ({meta_path})")

    return {
        'results_df': results_df,
        'selected': selected,
        'twilight': twilight,
        'start_local': start_hst,
        'skips': skip_log,
        'forced_failures': forced_failures,
        'blocks': blocks,
        'targets_csv': targets_csv,
        'output_dir': output_dir,
        'date': date,
        'config': etc_opts['config'],
        'seeing': etc_opts['seeing'],
        'mag_band': etc_opts['mag_band'],
        'etc_opts': {k: etc_opts[k] for k in ('etc', 'target_sn', 'n_sub_min',
                                              'airmass_rule')},
    }


def main():
    """Standalone entry point: `python scripts/keck_2026oct06_calculations.py ...`."""
    return run(parse_args())


if __name__ == '__main__':
    main()
