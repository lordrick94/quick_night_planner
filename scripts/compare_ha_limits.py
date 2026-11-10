"""
What the Shane's east hour-angle limit is worth, in minutes on sky.

The planner used HA >= -5.0 until 2026-10-14, when the author adopted the
published -05:40. Both numbers appear in circulation (UCSC AstroScheduler
uses -05:40 too), so this quantifies the difference rather than leaving it
as a matter of belief: for each target it reports how much longer the
observable window becomes, and which targets cross from never-legal to
legal.

The gain is not a flat 40 minutes. A target already up at dusk gains
nothing, because its window was never clipped at the east limit; the ones
that gain are those still east of the meridian when the night starts, and
a late riser can gain the whole 40.

Usage
-----
python scripts/compare_ha_limits.py [targets.csv] [YYYY-MM-DD]

Created by JXP and Claude
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from scripts import lick_2026b02_calculations as lick  # noqa: E402
from night_planner.targets_io import load_targets  # noqa: E402

OLD_HA_MIN = -5.0
NEW_HA_MIN = -(5 + 40 / 60)


def windows_under(ha_min, df, twilight):
    """
    Observable window per target with the east limit set to `ha_min`.

    Parameters
    ----------
    ha_min : float
        East hour-angle limit, hours (negative).
    df : DataFrame
        Canonical target table (name/ra_deg/dec_deg).
    twilight : dict
        As returned by find_twilight().

    Returns
    -------
    dict : name -> window length in minutes (0 when never legal)
    """
    original = lick.HA_MIN
    lick.HA_MIN = ha_min
    try:
        out = {}
        for _, row in df.iterrows():
            window = lick.target_window(row['ra_deg'] / 15.0,
                                         row['dec_deg'], twilight)
            out[row['name']] = (0.0 if window is None else
                                (window[1] - window[0]).total_seconds() / 60.0)
        return out
    finally:
        lick.HA_MIN = original


def compare(targets_csv, date_str):
    """
    Per-target window gain from widening the east limit.

    Returns
    -------
    DataFrame, biggest gain first.
    """
    df = load_targets(targets_csv)
    twilight = lick.find_twilight(date_str)

    old = windows_under(OLD_HA_MIN, df, twilight)
    new = windows_under(NEW_HA_MIN, df, twilight)

    rows = [{'name': name,
             'dec': float(df.loc[df['name'] == name, 'dec_deg'].iloc[0]),
             'window_old_min': old[name],
             'window_new_min': new[name],
             'gain_min': new[name] - old[name],
             'newly_legal': old[name] == 0 and new[name] > 0}
            for name in old]
    return pd.DataFrame(rows).sort_values('gain_min', ascending=False)


def main():
    """Print the comparison for a table and date."""
    targets = (sys.argv[1] if len(sys.argv) > 1 else
               'Night_plans/Lick-2026B-03/Lick-2026B-03_targets.csv')
    date_str = sys.argv[2] if len(sys.argv) > 2 else '2026-10-12'

    df = compare(targets, date_str)
    print(f'East HA limit {OLD_HA_MIN:+.3f} h -> {NEW_HA_MIN:+.3f} h '
          f'({Path(targets).name}, {date_str})\n')
    print(df.round(1).to_string(index=False))

    gained = df[df['gain_min'] > 0]
    print(f'\n{len(gained)} of {len(df)} targets gain window; '
          f'{int(df["newly_legal"].sum())} become observable at all.')
    print(f'Total extra window across the table: '
          f'{df["gain_min"].sum():.0f} min.')


if __name__ == '__main__':
    main()
