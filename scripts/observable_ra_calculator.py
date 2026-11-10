"""
Calculate observable RA ranges for Shane telescope given HA limits and date.

Created by JXP and Claude
"""

import numpy as np
from datetime import datetime, timedelta, timezone
from astropy import units as u
from astropy.coordinates import EarthLocation, get_sun, AltAz
from astropy.time import Time
import matplotlib.pyplot as plt

import sys
from pathlib import Path

# Repo-relative, so this runs wherever the checkout lives.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from night_planner.paths import plans_dir

_PLANS = plans_dir()

# Lick Observatory
LICK = EarthLocation(lat=37.3414*u.deg, lon=-121.6429*u.deg, height=1283*u.m)
PST = timezone(timedelta(hours=-8))

# Shane 3m HA limits
HA_MIN = -(5 + 40 / 60)  # hours, -05:40 east limit (adopted 2026-10-14)
HA_MAX = 3.75  # hours (west limit)

def find_twilight_lst(date_str, twilight_alt=-18*u.deg):
    """
    Find LST at evening and morning 18° twilight.

    Parameters
    ----------
    date_str : str
        Date in 'YYYY-MM-DD' format
    twilight_alt : Quantity
        Sun altitude for twilight (default -18° astronomical)

    Returns
    -------
    dict with 'evening_lst', 'morning_lst' in hours
    """
    from astropy.coordinates import get_sun

    local_date = datetime.strptime(date_str, '%Y-%m-%d')
    noon_pst = datetime(local_date.year, local_date.month,
                        local_date.day, 12, 0, 0, tzinfo=PST)

    # Search for evening twilight
    search_time = noon_pst
    for i in range(600):
        utc_time = search_time.astimezone(timezone.utc)
        t = Time(utc_time)
        sun = get_sun(t)
        sun_altaz = sun.transform_to(AltAz(obstime=t, location=LICK))

        if sun_altaz.alt < twilight_alt:
            evening_lst = t.sidereal_time('apparent', longitude=LICK.lon).hour
            break
        search_time += timedelta(minutes=1)

    # Search for morning twilight
    search_time = noon_pst + timedelta(hours=18)
    for i in range(600):
        utc_time = search_time.astimezone(timezone.utc)
        t = Time(utc_time)
        sun = get_sun(t)
        sun_altaz = sun.transform_to(AltAz(obstime=t, location=LICK))

        if sun_altaz.alt > twilight_alt:
            morning_lst = t.sidereal_time('apparent', longitude=LICK.lon).hour
            break
        search_time += timedelta(minutes=1)

    return {
        'evening_lst': evening_lst,
        'morning_lst': morning_lst
    }

def calculate_observable_ra_range(lst, ha_min, ha_max):
    """
    Calculate observable RA range at given LST.

    HA = LST - RA, so:
    RA = LST - HA

    For HA in [ha_min, ha_max]:
    RA in [LST - ha_max, LST - ha_min]

    Parameters
    ----------
    lst : float
        LST in hours
    ha_min : float
        Minimum HA (hours, east limit)
    ha_max : float
        Maximum HA (hours, west limit)

    Returns
    -------
    ra_min, ra_max : tuple of floats (may wrap around 24h)
    """
    ra_min = lst - ha_max
    ra_max = lst - ha_min

    # Wrap to [0, 24)
    ra_min = ra_min % 24
    ra_max = ra_max % 24

    return ra_min, ra_max

def format_ra_range(ra_min, ra_max):
    """Format RA range, handling wrap."""
    if ra_max > ra_min:
        return f"[{ra_min:.2f}h, {ra_max:.2f}h]"
    else:
        # Wraps around 0h
        return f"[{ra_min:.2f}h, 24h] ∪ [0h, {ra_max:.2f}h]"

def observable_ra_for_night(date_str):
    """
    Calculate observable RA ranges throughout a night.

    Parameters
    ----------
    date_str : str
        Observing date (local evening date)

    Returns
    -------
    dict with evening/morning LST and RA ranges
    """
    twilight = find_twilight_lst(date_str)
    eve_lst = twilight['evening_lst']
    morn_lst = twilight['morning_lst']

    # Observable RAs at twilights
    ra_min_eve, ra_max_eve = calculate_observable_ra_range(eve_lst, HA_MIN, HA_MAX)
    ra_min_morn, ra_max_morn = calculate_observable_ra_range(morn_lst, HA_MIN, HA_MAX)

    # Union of ranges during night
    # Any RA observable at ANY point during the night
    lst_range = np.linspace(eve_lst, morn_lst if morn_lst > eve_lst else morn_lst + 24, 100)
    all_ra_min = []
    all_ra_max = []

    for lst in lst_range:
        ra_min, ra_max = calculate_observable_ra_range(lst % 24, HA_MIN, HA_MAX)
        all_ra_min.append(ra_min)
        all_ra_max.append(ra_max)

    # Overall range (simplified - actual is union)
    overall_min = min(all_ra_min)
    overall_max = max(all_ra_max)

    return {
        'date': date_str,
        'evening_lst': eve_lst,
        'morning_lst': morn_lst,
        'evening_ra_range': (ra_min_eve, ra_max_eve),
        'morning_ra_range': (ra_min_morn, ra_max_morn),
        'night_ra_range_approx': (overall_min, overall_max)
    }

def plot_observable_ra_vs_month(year=2026, output_file=None):
    """
    Plot observable RA ranges throughout the year.

    Parameters
    ----------
    year : int
        Year to plot
    output_file : str, optional
        Path to save plot
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    months = range(1, 13)
    dates = [f"{year}-{m:02d}-15" for m in months]  # Mid-month

    fig, ax = plt.subplots(figsize=(14, 8))

    for i, date_str in enumerate(dates):
        result = observable_ra_for_night(date_str)

        # Plot evening and morning RA ranges
        ra_min_eve, ra_max_eve = result['evening_ra_range']
        ra_min_morn, ra_max_morn = result['morning_ra_range']

        # Evening range
        if ra_max_eve > ra_min_eve:
            width = ra_max_eve - ra_min_eve
            rect = Rectangle((ra_min_eve, i - 0.3), width, 0.3,
                           facecolor='blue', alpha=0.5, label='Evening' if i == 0 else '')
            ax.add_patch(rect)
        else:
            # Wraps
            rect1 = Rectangle((ra_min_eve, i - 0.3), 24 - ra_min_eve, 0.3,
                            facecolor='blue', alpha=0.5)
            rect2 = Rectangle((0, i - 0.3), ra_max_eve, 0.3,
                            facecolor='blue', alpha=0.5)
            ax.add_patch(rect1)
            ax.add_patch(rect2)

        # Morning range
        if ra_max_morn > ra_min_morn:
            width = ra_max_morn - ra_min_morn
            rect = Rectangle((ra_min_morn, i), width, 0.3,
                           facecolor='red', alpha=0.5, label='Morning' if i == 0 else '')
            ax.add_patch(rect)
        else:
            # Wraps
            rect1 = Rectangle((ra_min_morn, i), 24 - ra_min_morn, 0.3,
                            facecolor='red', alpha=0.5)
            rect2 = Rectangle((0, i), ra_max_morn, 0.3,
                            facecolor='red', alpha=0.5)
            ax.add_patch(rect1)
            ax.add_patch(rect2)

    ax.set_xlim(0, 24)
    ax.set_ylim(-0.5, 11.5)
    ax.set_xlabel('Right Ascension (hours)', fontsize=12)
    ax.set_ylabel('Month', fontsize=12)
    ax.set_yticks(range(12))
    ax.set_yticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
    ax.set_title(f'Observable RA Ranges at Lick (Shane 3m) Throughout {year}\n'
                 f'HA limits: [{HA_MIN:.2f}h, +{HA_MAX:.2f}h]', fontsize=14)
    ax.grid(True, alpha=0.3, axis='x')
    ax.legend()

    plt.tight_layout()

    if output_file:
        plt.savefig(output_file, dpi=150)
        print(f"Plot saved to {output_file}")
    else:
        plt.show()

def main():
    """Main execution."""

    # Example: August 13, 2026
    date = '2026-08-13'
    result = observable_ra_for_night(date)

    print(f"\n{'='*60}")
    print(f"OBSERVABLE RA RANGES FOR {date.upper()}")
    print(f"Shane 3m HA Limits: [{HA_MIN:.2f}h, +{HA_MAX:.2f}h]")
    print(f"{'='*60}\n")

    print(f"Evening 18° twilight: LST = {result['evening_lst']:.2f}h")
    ra_min_eve, ra_max_eve = result['evening_ra_range']
    print(f"  Observable RAs: {format_ra_range(ra_min_eve, ra_max_eve)}")

    print(f"\nMorning 18° twilight: LST = {result['morning_lst']:.2f}h")
    ra_min_morn, ra_max_morn = result['morning_ra_range']
    print(f"  Observable RAs: {format_ra_range(ra_min_morn, ra_max_morn)}")

    print(f"\nNight duration: {result['morning_lst'] - result['evening_lst']:.2f}h")
    print(f"(Approximate overall RA range: "
          f"{format_ra_range(result['night_ra_range_approx'][0], result['night_ra_range_approx'][1])})")

    # Generate year plot
    print(f"\n{'='*60}")
    print("Generating year-round RA observability plot...")
    print(f"{'='*60}\n")

    output_file = f'{_PLANS}/Lick-2026B-01/observable_ra_2026.png'
    plot_observable_ra_vs_month(2026, output_file)

if __name__ == '__main__':
    main()
