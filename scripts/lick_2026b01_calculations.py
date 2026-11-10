"""
Calculate LST, twilight, airmass for Lick 2026B-01 night 1 (Aug 13, 2026)
and select targets for observation.

Created by JXP and Claude
"""

import pandas as pd
import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
from astropy.time import Time
from datetime import datetime, timedelta, timezone
import pytz

import sys
from pathlib import Path

# Repo-relative, so this runs wherever the checkout lives.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from night_planner.paths import plans_dir

_PLANS = plans_dir()

# Lick Observatory coordinates
LICK = EarthLocation(lat=37.3414*u.deg, lon=-121.6429*u.deg, height=1283*u.m)

# Lick calendar uses PST (UTC-8) year-round, NOT PDT
# Use fixed offset to match calendar convention
PST = timezone(timedelta(hours=-8))
PACIFIC_DST = pytz.timezone('America/Los_Angeles')  # For display only

def utc_to_pst(utc_time):
    """Convert UTC time to PST (fixed UTC-8 per Lick calendar)."""
    return utc_time.astimezone(PST)

def pst_to_utc(pst_dt):
    """Convert PST datetime to UTC (PST = UTC-8 fixed)."""
    if pst_dt.tzinfo is None:
        pst_dt = pst_dt.replace(tzinfo=PST)
    return pst_dt.astimezone(timezone.utc)

def calculate_lst(utc_time, location=LICK):
    """Calculate LST for given UTC time at location."""
    t = Time(utc_time)
    lst = t.sidereal_time('apparent', longitude=location.lon)
    return lst

def find_twilight(date_str, twilight_alt=-18*u.deg):
    """
    Find evening and morning twilight times for given date.

    Parameters
    ----------
    date_str : str
        Date in format 'YYYY-MM-DD' (local date)
    twilight_alt : Quantity
        Sun altitude for twilight definition (default -18° for astronomical)

    Returns
    -------
    dict with 'evening_pst', 'evening_utc', 'evening_lst',
             'morning_pst', 'morning_utc', 'morning_lst'
    """
    from astropy.coordinates import get_sun

    # Start search at local noon PST (UTC-8)
    local_date = datetime.strptime(date_str, '%Y-%m-%d')
    noon_pst = datetime(local_date.year, local_date.month,
                        local_date.day, 12, 0, 0, tzinfo=PST)

    # Search for evening twilight (sun going down)
    search_time = noon_pst
    evening_utc = None
    evening_pst = None
    evening_lst = None

    for i in range(600):  # search up to 10 hours
        utc_time = search_time.astimezone(timezone.utc)
        t = Time(utc_time)
        sun = get_sun(t)
        sun_altaz = sun.transform_to(AltAz(obstime=t, location=LICK))

        if sun_altaz.alt < twilight_alt:
            evening_utc = utc_time
            evening_pst = search_time
            evening_lst = calculate_lst(utc_time)
            break
        search_time += timedelta(minutes=1)

    if evening_pst is None:
        raise ValueError(f"Could not find evening twilight for {date_str}")

    # Search for morning twilight (sun coming up)
    # Start from evening + 6 hours (Aug nights ~7-8h dark)
    search_time = evening_pst + timedelta(hours=6)
    morning_utc = None
    morning_pst = None
    morning_lst = None

    for i in range(600):
        utc_time = search_time.astimezone(timezone.utc)
        t = Time(utc_time)
        sun = get_sun(t)
        sun_altaz = sun.transform_to(AltAz(obstime=t, location=LICK))

        if sun_altaz.alt > twilight_alt:
            morning_utc = utc_time
            morning_pst = search_time
            morning_lst = calculate_lst(utc_time)
            break
        search_time += timedelta(minutes=1)

    if morning_pst is None:
        raise ValueError(f"Could not find morning twilight for {date_str}")

    return {
        'evening_pst': evening_pst,
        'evening_utc': evening_utc,
        'evening_lst': evening_lst,
        'morning_pst': morning_pst,
        'morning_utc': morning_utc,
        'morning_lst': morning_lst
    }

def calculate_airmass(ra, dec, time_utc, location=LICK):
    """
    Calculate airmass for target at given time.

    Parameters
    ----------
    ra : float
        RA in degrees
    dec : float
        Dec in degrees
    time_utc : datetime
        UTC time
    location : EarthLocation
        Observatory location

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

def check_pointing_limits(ra, dec, ha):
    """
    Check if target violates Shane 3m pointing limits.

    Constraints:
    - Dec ≤ 82° (polar limit)
    - HA limits: -5h ≤ HA ≤ +3.75h
      - HA < -5h: too far EAST of meridian (>5h before transit)
      - HA > +3.75h: too far WEST of meridian (>3.75h after transit)

    Note: NO RA limits - only what's up depends on time of year.

    Parameters
    ----------
    ra : float (degrees)
    dec : float (degrees)
    ha : float (hours)

    Returns
    -------
    valid : bool
    reason : str (if invalid)
    """
    if dec > 82:
        return False, f"Dec {dec:.1f}° > 82° limit"

    if ha < -5.0:
        return False, f"HA {ha:.2f}h < -5h limit (too far east)"

    if ha > 3.75:
        return False, f"HA {ha:.2f}h > +3.75h limit (too far west)"

    return True, ""

def analyze_targets(targets_csv, date_str='2026-08-13'):
    """
    Analyze all targets for observability on given date.

    Parameters
    ----------
    targets_csv : str
        Path to targets CSV file
    date_str : str
        Observing date (local)

    Returns
    -------
    DataFrame with target info and observability
    """
    # Read targets
    df = pd.read_csv(targets_csv)

    # Filter by Dec limit
    df = df[df['Pri_Dec'] <= 82.0].copy()

    # Calculate twilight
    twilight = find_twilight(date_str)

    print(f"\n=== TWILIGHT TIMES FOR {date_str} ===")
    print(f"Evening 18° twilight: {twilight['evening_pst'].strftime('%H:%M PST')} "
          f"(LST {twilight['evening_lst'].to_string(precision=0)})")
    print(f"Morning 18° twilight: {twilight['morning_pst'].strftime('%H:%M PST')} "
          f"(LST {twilight['morning_lst'].to_string(precision=0)})")
    print(f"(Note: Using PST = UTC-8 year-round per Lick calendar convention)")

    # Determine timeline start (round down to nearest 30 min before evening twilight)
    eve_minute = twilight['evening_pst'].minute
    if eve_minute < 30:
        start_pst = twilight['evening_pst'].replace(minute=0, second=0)
    else:
        start_pst = twilight['evening_pst'].replace(minute=30, second=0)

    print(f"\nTimeline start: {start_pst.strftime('%H:%M PST')}")

    # Calculate observability for each target
    results = []

    for idx, row in df.iterrows():
        tns = row['TNS']
        ra = row['Pri_RA']
        dec = row['Pri_Dec']
        mag = row['Pri_mag']
        pox = row['Pri_POx']
        tags = row['FRB_tags']
        dm = row['FRB_DM']

        # Calculate airmass at evening twilight
        am_eve, alt_eve, az_eve, ha_eve = calculate_airmass(
            ra, dec, twilight['evening_utc'])

        # Calculate airmass at morning twilight
        am_mor, alt_mor, az_mor, ha_mor = calculate_airmass(
            ra, dec, twilight['morning_utc'])

        # Find time of transit (HA = 0)
        lst_transit = ra / 15.0  # hours

        # Find minimum airmass time during night
        # Sample every 15 minutes
        night_duration = (twilight['morning_utc'] - twilight['evening_utc']).total_seconds() / 3600
        n_samples = int(night_duration * 4)
        min_am = 99.9
        min_am_time = None
        min_am_ha = None

        for i in range(n_samples):
            sample_time = twilight['evening_utc'] + timedelta(hours=i*0.25)
            am, alt, az, ha = calculate_airmass(ra, dec, sample_time)
            if am < min_am:
                min_am = am
                min_am_time = sample_time
                min_am_ha = ha

        # Check pointing limits at minimum airmass time
        valid, reason = check_pointing_limits(ra, dec, min_am_ha)

        results.append({
            'TNS': tns,
            'RA_deg': ra,
            'Dec_deg': dec,
            'RA_hours': ra/15.0,
            'mag_r': mag,
            'POx': pox,
            'tags': tags,
            'DM': dm,
            'min_airmass': min_am,
            'min_am_time_pst': utc_to_pst(min_am_time),
            'min_am_ha': min_am_ha,
            'am_evening': am_eve,
            'ha_evening': ha_eve,
            'am_morning': am_mor,
            'ha_morning': ha_mor,
            'observable': valid,
            'limit_reason': reason
        })

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('RA_hours')

    return results_df, twilight, start_pst

def select_targets_for_night(results_df, n_targets=6):
    """
    Select targets for observation based on priority rules.

    Priority:
    1. Must be observable (no pointing limit violations)
    2. If target is setting (HA approaching -3.75h limit), observe first
    3. Prefer coverage across RA range
    4. Generally prefer low airmass

    Parameters
    ----------
    results_df : DataFrame
        Results from analyze_targets
    n_targets : int
        Number of targets to select

    Returns
    -------
    selected : DataFrame
        Selected targets in observing order
    """
    # Filter to observable targets
    observable = results_df[results_df['observable']].copy()

    print(f"\n=== TARGET SELECTION ===")
    print(f"Total viable targets (Dec ≤ 82°, observable): {len(observable)}")

    # Identify setting targets (HA < -2 at evening or approaching limit)
    observable['setting_priority'] = 0
    observable.loc[observable['ha_evening'] < -2, 'setting_priority'] = 1

    # Sort by: setting priority (desc), then min airmass (asc)
    observable = observable.sort_values(['setting_priority', 'min_airmass'],
                                        ascending=[False, True])

    # Select top n_targets with good RA coverage
    # Try to spread across RA range
    selected = observable.head(n_targets)

    print(f"Selected {len(selected)} targets for night 1:")
    for idx, row in selected.iterrows():
        print(f"  {row['TNS']}: RA {row['RA_hours']:.2f}h, "
              f"min_AM {row['min_airmass']:.2f} at {row['min_am_time_pst'].strftime('%H:%M PST')}, "
              f"mag_r {row['mag_r']:.2f}")
        if row['setting_priority'] == 1:
            print(f"    → SETTING TARGET (HA_eve = {row['ha_evening']:.2f}h)")

    return selected

def estimate_exposure_time(mag_r):
    """
    Estimate exposure times based on r-band magnitude.

    Rules from Q&A:
    - r ≤ 15: 30 min + overhead
    - r ≤ 17: 3×900 red, 2×1350 blue (~45 min + overhead)
    - r 17-19: 4×900 red, 2×1800 blue (~60 min)
    - r 19-20.5: 6×900 red, 3×1800 blue (~90 min)
    - ~30% overhead

    Returns
    -------
    dict with 'red_exp', 'blue_exp', 'total_min'
    """
    if mag_r <= 15:
        red = "2 x 900"
        blue = "1 x 1800"
        total = 30 + 10  # 30 min science + 10 min overhead
    elif mag_r <= 17:
        red = "3 x 900"
        blue = "2 x 1350"
        total = 45 + 15
    elif mag_r <= 19:
        red = "4 x 900"
        blue = "2 x 1800"
        total = 60 + 20
    else:  # 19-20.5
        red = "6 x 900"
        blue = "3 x 1800"
        total = 90 + 30

    return {
        'red_exp': red,
        'blue_exp': blue,
        'total_min': total
    }

def main():
    """Main execution."""
    targets_csv = f'{_PLANS}/Lick-2026B-01/Lick-2026B-01_targets.csv'
    date = '2026-08-13'

    # Analyze all targets
    results_df, twilight, start_pst = analyze_targets(targets_csv, date)

    # Print full analysis
    print("\n=== ALL TARGETS (sorted by RA) ===")
    print(results_df[['TNS', 'RA_hours', 'Dec_deg', 'mag_r', 'min_airmass',
                      'min_am_ha', 'observable', 'limit_reason']].to_string(index=False))

    # Select targets for night
    selected = select_targets_for_night(results_df, n_targets=6)

    # Add exposure time estimates
    print("\n=== EXPOSURE TIME ESTIMATES ===")
    for idx, row in selected.iterrows():
        exp = estimate_exposure_time(row['mag_r'])
        print(f"{row['TNS']}: mag_r={row['mag_r']:.2f} → "
              f"red: {exp['red_exp']}, blue: {exp['blue_exp']}, "
              f"total ~{exp['total_min']} min")

    # Save results
    output_dir = f'{_PLANS}/Lick-2026B-01'
    results_df.to_csv(f'{output_dir}/target_analysis.csv', index=False)
    selected.to_csv(f'{output_dir}/selected_targets_night1.csv', index=False)

    print(f"\nResults saved to {output_dir}/")
    print(f"  - target_analysis.csv: all targets with observability")
    print(f"  - selected_targets_night1.csv: selected targets for night 1")

    return results_df, selected, twilight, start_pst

if __name__ == '__main__':
    results, selected, twilight, start_pst = main()
