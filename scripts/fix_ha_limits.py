#!/usr/bin/env python
"""
Fix HA limit violations in night plan.
Created by JXP and Claude.

Clips observable windows to Shane pointing limits: -5:40 ≤ HA ≤ +3:45
"""

import pandas as pd
import numpy as np
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation
from astropy import units as u
from datetime import datetime, timedelta
import pytz

# Shane telescope location
lick = EarthLocation.from_geodetic(
    lon=-121.6429 * u.deg,
    lat=37.3414 * u.deg,
    height=1283 * u.m
)

# HA limits (hours). Canonical values live in
# lick_2026b02_calculations; kept as literals here because this
# script is a standalone one-off.
HA_MIN = -(5 + 40 / 60)   # -05:40, adopted 2026-10-14
HA_MAX = 3 + 45 / 60      # +03:45

# Night parameters for 2026-08-13/14
PST = pytz.timezone('US/Pacific')
evening_twilight = PST.localize(datetime(2026, 8, 13, 20, 38))
morning_twilight = PST.localize(datetime(2026, 8, 14, 5, 23))

def ha_to_time(ra_hours, ha_target, lst_ref_hours, time_ref):
    """
    Calculate time when target reaches specific HA.

    Args:
        ra_hours: RA in hours
        ha_target: Target HA in hours
        lst_ref_hours: Reference LST in hours
        time_ref: Reference UTC time (datetime)

    Returns:
        datetime when HA = ha_target
    """
    # HA = LST - RA
    # LST_target = RA + HA_target
    lst_target_hours = ra_hours + ha_target

    # Wrap to 0-24
    while lst_target_hours < 0:
        lst_target_hours += 24
    while lst_target_hours >= 24:
        lst_target_hours -= 24

    # Calculate LST difference
    dlst = lst_target_hours - lst_ref_hours

    # If negative, target LST occurs later tonight (wrap around)
    if dlst < 0:
        dlst += 24

    # Convert LST difference to time difference (sidereal to solar)
    # 1 sidereal hour = 0.9973 solar hours
    dt_hours = dlst * 0.9973

    target_time = time_ref + timedelta(hours=dt_hours)
    return target_time

def main():
    # Read selected targets
    df = pd.read_csv('Night_plans/Lick-2026B-01/selected_targets_night1.csv')

    print("=" * 70)
    print("FIXING HA LIMIT VIOLATIONS")
    print("=" * 70)
    print(f"Shane HA limits: {HA_MIN}h to {HA_MAX}h")
    print(f"Evening twilight: {evening_twilight.strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"Morning twilight: {morning_twilight.strftime('%Y-%m-%d %H:%M %Z')}")
    print()

    # Convert twilight times to astropy Time
    evening_time = Time(evening_twilight)
    morning_time = Time(morning_twilight)

    # Get LST at twilight times
    evening_lst = evening_time.sidereal_time('apparent', longitude=lick.lon)
    morning_lst = morning_time.sidereal_time('apparent', longitude=lick.lon)

    print(f"Evening LST: {evening_lst.hour:.2f}h")
    print(f"Morning LST: {morning_lst.hour:.2f}h")

    # Process each target
    results = []
    for idx, row in df.iterrows():
        tns = row['TNS']
        ra_hours = row['RA_hours']
        dec_deg = row['Dec_deg']
        priority = row['setting_priority']

        print(f"\n{tns} (RA={ra_hours:.2f}h, Dec={dec_deg:.1f}°)")
        print(f"  CSV values: HA_eve={row['ha_evening']:.2f}h, HA_morn={row['ha_morning']:.2f}h")

        # Calculate HA at twilights
        ha_eve = (evening_lst.hour - ra_hours)
        ha_morn = (morning_lst.hour - ra_hours)

        print(f"  Calculated: HA_eve={ha_eve:.2f}h (before wrap), HA_morn={ha_morn:.2f}h (before wrap)")

        # Wrap to -12 to +12
        while ha_eve > 12:
            ha_eve -= 24
        while ha_eve < -12:
            ha_eve += 24
        while ha_morn > 12:
            ha_morn -= 24
        while ha_morn < -12:
            ha_morn += 24

        # For morning targets (rising from east), prefer negative HA
        # For evening targets (setting to west), keep positive HA
        if priority == 1 and ha_eve > 0:
            ha_eve -= 24  # Morning target: object rising, use negative HA
        if priority == 0 and ha_morn < 0:
            ha_morn += 24  # Evening target: object setting, use positive HA

        print(f"  After priority adjustment: HA_eve={ha_eve:.2f}h, HA_morn={ha_morn:.2f}h")

        # Determine clipped times
        if priority == 1:  # Morning target
            # Clip start to HA_MIN
            if ha_eve < HA_MIN:
                start_time = ha_to_time(ra_hours, HA_MIN, evening_lst.hour, evening_twilight)
                start_ha = HA_MIN
                print(f"  → Clipping start: HA={ha_eve:.2f}h < {HA_MIN}h")
                print(f"  → New start: {start_time.strftime('%H:%M %Z')} at HA={start_ha:.2f}h")
            else:
                start_time = evening_twilight
                start_ha = ha_eve

            end_time = morning_twilight
            end_ha = ha_morn

        else:  # Evening target
            # Clip end to HA_MAX
            start_time = evening_twilight
            start_ha = ha_eve

            if ha_morn > HA_MAX:
                end_time = ha_to_time(ra_hours, HA_MAX, evening_lst.hour, evening_twilight)
                end_ha = HA_MAX
                print(f"  → Clipping end: HA={ha_morn:.2f}h > {HA_MAX}h")
                print(f"  → New end: {end_time.strftime('%H:%M %Z')} at HA={end_ha:.2f}h")
            else:
                end_time = morning_twilight
                end_ha = ha_morn

        # Calculate duration
        duration_min = (end_time - start_time).total_seconds() / 60

        results.append({
            'TNS': tns,
            'RA_hours': ra_hours,
            'Dec_deg': dec_deg,
            'mag_r': row['mag_r'],
            'setting_priority': priority,
            'start_time_pst': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_time_pst': end_time.strftime('%Y-%m-%d %H:%M'),
            'start_ha': start_ha,
            'end_ha': end_ha,
            'duration_min': duration_min
        })

        print(f"  → Observable: {start_time.strftime('%H:%M')} to {end_time.strftime('%H:%M')} ({duration_min:.0f} min)")

    # Create output dataframe
    out_df = pd.DataFrame(results)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    evening_df = out_df[out_df['setting_priority']==0]
    morning_df = out_df[out_df['setting_priority']==1]

    print(f"Evening targets: {len(evening_df)} ({evening_df['duration_min'].sum():.0f} min total window)")
    for _, row in evening_df.iterrows():
        print(f"  {row['TNS']}: {row['duration_min']:.0f} min")

    print(f"\nMorning targets: {len(morning_df)} ({morning_df['duration_min'].sum():.0f} min total window)")
    for _, row in morning_df.iterrows():
        print(f"  {row['TNS']}: {row['duration_min']:.0f} min")

    night_duration = (morning_twilight - evening_twilight).total_seconds() / 60
    print(f"\nNight duration: {night_duration:.0f} min ({night_duration/60:.1f} hours)")
    print("Note: Total windows sum > night duration because targets overlap.")

    # Save corrected targets
    outfile = 'Night_plans/Lick-2026B-01/selected_targets_ha_corrected.csv'
    out_df.to_csv(outfile, index=False)
    print(f"\nWrote: {outfile}")

if __name__ == '__main__':
    main()
