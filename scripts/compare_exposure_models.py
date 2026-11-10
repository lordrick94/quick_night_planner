"""
Compare this planner's exposure estimates with UCSC AstroScheduler's.

Both ask the same question -- how long does a host of magnitude m need?
-- and answer it from a table rather than from photons, so the only way
to judge them is side by side. The comparison matters because the two
disagree most at the faint end, which is where a night is won or lost.

Kast is dual-beam: the red and blue arms expose simultaneously through
the dichroic, so wall-clock science time is ONE arm's total, not the
sum. Both projects get that right; they differ on how much time to
spend.

Usage
-----
python scripts/compare_exposure_models.py

Created by JXP and Claude
"""

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from night_planner.estimate_kast_exposures import estimate_exposure

# scheduler.py constants, transcribed so this runs without importing it.
BLUE_ERASE, RED_ERASE = 5.0, 20.0
BLUE_READOUT, RED_READOUT = 30.0, 22.0

THEIR_KAST = {
    13.0: (637.0, 1, 300.0, 2), 13.5: (637.0, 1, 300.0, 2),
    14.0: (637.0, 1, 300.0, 2), 14.5: (637.0, 1, 300.0, 2),
    15.0: (637.0, 1, 300.0, 2), 15.5: (937.0, 1, 450.0, 2),
    16.0: (937.0, 1, 450.0, 2), 16.5: (937.0, 1, 450.0, 2),
    17.0: (1237.0, 1, 600.0, 2), 17.5: (1570.0, 1, 500.0, 3),
    18.0: (1845.0, 1, 600.0, 3), 18.5: (1230.0, 2, 600.0, 4),
    19.0: (1560.0, 2, 600.0, 5), 19.5: (1845.0, 2, 600.0, 6),
    20.0: (2145.0, 2, 600.0, 7),
}


def their_kast_minutes(mag):
    """
    AstroScheduler's Kast block length for a magnitude, in minutes.

    Mirrors get_target_exposure_details(): round the magnitude to the
    nearest 0.5, clamp to [13, 20], look the sequence up, take the
    longer arm including erase and readout, and add a flat 7 minutes of
    overhead.

    Returns
    -------
    (red_str, blue_str, block_minutes, clamped)
    """
    rounded = min(20.0, max(13.0, round(mag * 2.0) / 2.0))
    blue_exp, blue_num, red_exp, red_num = THEIR_KAST[rounded]

    t_red = red_num * (red_exp + RED_ERASE) + (red_num - 1) * RED_READOUT
    t_blue = blue_num * (blue_exp + BLUE_ERASE) + (blue_num - 1) * BLUE_READOUT
    t_seq = max(t_red, t_blue)
    return (f'{red_num} x {red_exp:.0f}', f'{blue_num} x {blue_exp:.0f}',
            7 + math.ceil(t_seq / 60.0), not 13.0 <= mag <= 20.0)


def our_kast_minutes(mag):
    """
    This planner's Kast block length, in minutes.

    estimate_exposure() returns the wall-clock science seconds; the Lick
    scheduler adds a 5-minute slew around it.

    Returns
    -------
    (red_str, blue_str, block_minutes)
    """
    red, blue, seconds = estimate_exposure(mag)
    return red, blue, 5 + math.ceil(seconds / 60.0)


def compare(mags=(13, 15, 16, 17, 18, 18.6, 19, 19.5, 20, 21, 22, 23)):
    """
    Side-by-side table for a range of magnitudes.

    Returns
    -------
    DataFrame
    """
    rows = []
    for mag in mags:
        their_red, their_blue, their_min, clamped = their_kast_minutes(mag)
        our_red, our_blue, our_min = our_kast_minutes(mag)
        rows.append({
            'mag': mag,
            'theirs_red': their_red, 'theirs_blue': their_blue,
            'theirs_min': their_min,
            'ours_red': our_red, 'ours_blue': our_blue, 'ours_min': our_min,
            'ratio': our_min / their_min,
            'their_table_clamped': clamped,
        })
    return pd.DataFrame(rows)


def main():
    """Print the comparison and the headline differences."""
    df = compare()
    print('Kast block length (science + overhead), minutes\n')
    print(df.round(2).to_string(index=False))

    faint = df[df['their_table_clamped']]
    print(f'\nTheir Kast table is clamped to magnitude 20, so the '
          f'{len(faint)} rows above it all return the same block '
          f'({faint["theirs_min"].iloc[0]} min) however faint the host is.')
    print('Their LRIS table is clamped at magnitude 24 and tops out at '
          '2400 s\n(40 min) -- our LRIS ETC needs 3 x 7200 s for a mag 22.6 '
          'host and\nstill only reaches S/N 5.7 per exposure.')


if __name__ == '__main__':
    main()
