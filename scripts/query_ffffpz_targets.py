#!/usr/bin/env python
"""
Query FFFF-PZ API for suitable targets for a given night.
Created by JXP and Claude.
"""

import sys
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
from night_planner.paths import ffffpz_root
sys.path.insert(0, str(ffffpz_root()))

from chime_ffff_pz.utils import ffff_pz_utils
import pandas as pd
from datetime import datetime
import pytz

# Night parameters
PST = pytz.timezone('US/Pacific')
night_date = PST.localize(datetime(2026, 8, 13, 20, 38))

# Shane constraints
DEC_MAX = 82.0  # degrees
# Canonical values live in lick_2026b02_calculations; kept as
# literals here because this script is a standalone one-off.
HA_MIN = -(5 + 40 / 60)   # -05:40, adopted 2026-10-14
HA_MAX = 3 + 45 / 60      # +03:45

# Get evening/morning LST (from fix_ha_limits.py output)
EVENING_LST = 17.03  # hours
MORNING_LST = 1.80   # hours

def calculate_observable_ra_ranges(evening_lst, morning_lst, ha_min, ha_max):
    """
    Calculate which RA ranges are observable during the night.

    Returns:
        List of (ra_min, ra_max) tuples in hours
    """
    # At evening twilight: can observe HA_MIN to HA_MAX
    # RA = LST - HA
    eve_ra_max = evening_lst - ha_min  # Most eastward (highest RA)
    eve_ra_min = evening_lst - ha_max  # Most westward (lowest RA)

    # At morning twilight
    morn_ra_max = morning_lst - ha_min
    morn_ra_min = morning_lst - ha_max

    # Wrap to 0-24
    def wrap(ra):
        while ra < 0:
            ra += 24
        while ra >= 24:
            ra -= 24
        return ra

    eve_ra_min = wrap(eve_ra_min)
    eve_ra_max = wrap(eve_ra_max)
    morn_ra_min = wrap(morn_ra_min)
    morn_ra_max = wrap(morn_ra_max)

    print(f"Observable RA at evening twilight (LST={evening_lst:.2f}h):")
    print(f"  RA range: {eve_ra_min:.2f}h to {eve_ra_max:.2f}h")
    print(f"Observable RA at morning twilight (LST={morning_lst:.2f}h):")
    print(f"  RA range: {morn_ra_min:.2f}h to {morn_ra_max:.2f}h")
    print()

    # Full observable range spans from most westward in evening to most eastward in morning
    # Because LST increases through night, observable RA window shifts
    return (eve_ra_min, morn_ra_max)

def is_observable(ra_hours, ra_range):
    """Check if RA falls within observable range (handles wrap-around)."""
    ra_min, ra_max = ra_range

    # If range crosses 0h (e.g., 22h to 2h)
    if ra_max < ra_min:
        return ra_hours >= ra_min or ra_hours <= ra_max
    else:
        return ra_min <= ra_hours <= ra_max

def main():
    print("=" * 70)
    print("QUERYING FFFF-PZ FOR LICK 2026-08-13 TARGETS")
    print("=" * 70)
    print()

    # Calculate observable RA range
    ra_range = calculate_observable_ra_ranges(EVENING_LST, MORNING_LST, HA_MIN, HA_MAX)

    print(f"Full night RA range: {ra_range[0]:.2f}h to {ra_range[1]:.2f}h")
    print()

    # Query FFFF-PZ
    print("Querying FFFF-PZ API...")
    frbs = ffff_pz_utils.get_transients()
    df = pd.DataFrame(frbs)

    print(f"Total FRBs: {len(df)}")

    # Filter by Dec
    df = df[df['dec'] < DEC_MAX]
    print(f"After Dec < {DEC_MAX}°: {len(df)}")

    # Add RA in hours
    df['ra_hours'] = df['ra'] / 15.0

    # Filter by observable RA
    df['observable'] = df['ra_hours'].apply(lambda ra: is_observable(ra, ra_range))
    df_obs = df[df['observable']].copy()
    print(f"After RA range filter: {len(df_obs)}")
    print()

    # Summary stats
    print("Summary stats:")
    if 'repeater' in df_obs.columns:
        n_rep = df_obs['repeater'].sum()
        print(f"  Repeaters: {n_rep}")
    if 'P_Ux' in df_obs.columns:
        high_pux = (df_obs['P_Ux'] > 0.5).sum()
        print(f"  High P_Ux (>0.5): {high_pux}")
    print()

    # Sort by RA
    df_obs = df_obs.sort_values('ra_hours')

    # Show top candidates
    print("=" * 70)
    print("TOP 20 CANDIDATES (sorted by RA)")
    print("=" * 70)

    cols_to_show = ['name', 'ra_hours', 'dec']
    if 'P_Ux' in df_obs.columns:
        cols_to_show.append('P_Ux')
    if 'DM' in df_obs.columns:
        cols_to_show.append('DM')
    if 'repeater' in df_obs.columns:
        cols_to_show.append('repeater')

    for i, (idx, row) in enumerate(df_obs.head(20).iterrows()):
        name = row.get('name', 'N/A')
        ra_h = row['ra_hours']
        dec = row['dec']
        pux = row.get('P_Ux', -1)
        dm = row.get('DM', -1)
        repeater = row.get('repeater', False)
        rep_str = 'R' if repeater else ' '

        print(f"{i+1:2d}. {name:15s} RA={ra_h:6.2f}h Dec={dec:6.1f}° DM={dm:6.1f} P_Ux={pux:.3f} {rep_str}")

    # Save to CSV
    outfile = 'Night_plans/Lick-2026B-01/ffffpz_candidates.csv'
    df_obs[cols_to_show].to_csv(outfile, index=False)
    print()
    print(f"Saved {len(df_obs)} candidates to: {outfile}")

if __name__ == '__main__':
    main()
