"""
Generate synthetic FRB target lists for testing edge cases.

Created by JXP and Claude
"""

import pandas as pd
import numpy as np
from pathlib import Path

# Output directory
TEST_DATA_DIR = Path(__file__).parent
TEST_DATA_DIR.mkdir(exist_ok=True, parents=True)

def generate_test_frbs(
    name,
    ra_list,
    dec_list=None,
    mag_list=None,
    description="",
):
    """
    Generate test FRB CSV.

    Parameters
    ----------
    name : str
        Test case name (used for filename)
    ra_list : list of float
        RA values in degrees
    dec_list : list of float, optional
        Dec values in degrees (random if None)
    mag_list : list of float, optional
        r-band magnitudes (random 16-20 if None)
    description : str
        Description of test case

    Returns
    -------
    DataFrame
    """
    n = len(ra_list)

    if dec_list is None:
        # Random decs between -30° (southern limit for Lick) and +82° (Shane limit)
        dec_list = np.random.uniform(-30, 75, n)

    if mag_list is None:
        # Random mags 16-20
        mag_list = np.random.uniform(16, 20, n)

    # Generate TNS names
    tns_names = [f"FRB20{26 + i//100:02d}{(i%12)+1:02d}{(i%28)+1:02d}{chr(65 + i%26)}"
                 for i in range(n)]

    # Create DataFrame matching FFFF-PZ format
    df = pd.DataFrame({
        'TNS': tns_names,
        'FRB_RA': ra_list,
        'FRB_Dec': dec_list,
        'FRB_DM': np.random.uniform(100, 1000, n),
        'FRB_survey': ['CHIME'] * n,
        'FRB_tags': ['CHIME-Blind'] * n,
        'Pri_name': [f'SDSS_J{i:08d}' for i in range(n)],
        'Pri_RA': ra_list,  # Same as FRB for simplicity
        'Pri_Dec': dec_list,
        'Pri_POx': np.random.uniform(0.8, 0.99, n),
        'Pri_mag': mag_list,
        'Pri_filter': ['r'] * n,
        'Sec_name': [''] * n,
        'Sec_RA': [np.nan] * n,
        'Sec_Dec': [np.nan] * n,
        'Sec_POx': [np.nan] * n,
        'Sec_mag': [np.nan] * n,
        'Sec_filter': [''] * n,
        'mode': ['longslit'] * n,
        'Resource': [f'Test-{name}'] * n,
    })

    # Save
    output_file = TEST_DATA_DIR / f'test_{name}.csv'
    df.to_csv(output_file, index=False)

    print(f"Generated {name}:")
    print(f"  {description}")
    print(f"  {n} targets, RA range {min(ra_list)/15:.1f}-{max(ra_list)/15:.1f}h")
    print(f"  Saved to {output_file}")
    print()

    return df

# ============================================================================
# Test Case 1: August with DEADTIME GAP
# ============================================================================
# All targets at RA 6-9h - too far west at evening, too far east at morning
# Creates a full-night gap

ra_deg = np.array([6, 7, 8, 9]) * 15  # 6h, 7h, 8h, 9h
generate_test_frbs(
    name='aug_deadtime_gap',
    ra_list=list(ra_deg),
    description="August - all targets RA 6-9h, creates full-night deadtime gap"
)

# ============================================================================
# Test Case 2: August EVENING ONLY
# ============================================================================
# All targets RA 14-17h - only observable in evening

ra_deg = np.linspace(14, 17, 10) * 15
generate_test_frbs(
    name='aug_evening_only',
    ra_list=list(ra_deg),
    description="August - all RA 14-17h, only evening observable"
)

# ============================================================================
# Test Case 3: August MORNING ONLY
# ============================================================================
# All targets RA 0-4h - only observable in morning

ra_deg = np.linspace(0, 4, 10) * 15
generate_test_frbs(
    name='aug_morning_only',
    ra_list=list(ra_deg),
    description="August - all RA 0-4h, only morning observable"
)

# ============================================================================
# Test Case 4: CLUSTERED RAs
# ============================================================================
# All targets within 0.5h RA range - tests scheduling dense fields

ra_deg = np.random.uniform(15.0, 15.5, 15) * 15
generate_test_frbs(
    name='aug_clustered_ra',
    ra_list=list(ra_deg),
    mag_list=np.random.uniform(16, 20.5, 15),
    description="August - 15 targets clustered at RA 15.0-15.5h"
)

# ============================================================================
# Test Case 5: SPARSE COVERAGE
# ============================================================================
# Targets spread across full observable window

ra_deg = [0.5, 2, 4, 15, 16, 17, 21, 22] * 15  # hours * 15
generate_test_frbs(
    name='aug_sparse_coverage',
    ra_list=list(ra_deg),
    description="August - sparse coverage across observable window"
)

# ============================================================================
# Test Case 6: HA LIMIT EDGE CASES
# ============================================================================
# Targets right at HA limits to test boundary conditions

# For August LST 18h (evening):
# HA = -5h: RA = LST - HA = 18 - (-5) = 23h
# HA = +3.75h: RA = LST - HA = 18 - 3.75 = 14.25h

# For August LST 1h (morning):
# HA = -5h: RA = 1 - (-5) = 6h
# HA = +3.75h: RA = 1 - 3.75 = -2.75 → 21.25h

ra_deg = np.array([14.25, 14.5, 15.0,  # Just inside west limit at evening
                   21.25, 21.5, 22.0,  # Just inside west limit at morning
                   23.0, 0.5, 1.0,     # Just inside east limit at evening/morning
                   6.0, 6.5, 7.0])     # Just inside east limit at morning

ra_deg = ra_deg * 15  # Convert to degrees
generate_test_frbs(
    name='aug_ha_limits',
    ra_list=list(ra_deg),
    description="August - targets at HA limit boundaries"
)

# ============================================================================
# Test Case 7: EXTREME DECLINATIONS
# ============================================================================
# Test airmass calculations at various decs

ra_deg = np.linspace(14, 17, 8) * 15  # Evening observable RAs
dec_deg = [-25, -10, 0, 10, 30, 50, 70, 81]  # Range from south to near-pole

generate_test_frbs(
    name='aug_extreme_decs',
    ra_list=list(ra_deg),
    dec_list=dec_deg,
    description="August - declinations from -25° to +81° (near Shane limit)"
)

# ============================================================================
# Test Case 8: DEC > 82° (all rejected)
# ============================================================================

ra_deg = np.linspace(14, 17, 5) * 15
dec_deg = [83, 84, 85, 86, 87]

generate_test_frbs(
    name='aug_over_dec_limit',
    ra_list=list(ra_deg),
    dec_list=dec_deg,
    description="August - all Decs > 82° (should all be rejected)"
)

# ============================================================================
# Test Case 9: WINTER (Feb) - different LST window
# ============================================================================
# Feb 15 LST range: evening ~8h, morning ~14h
# Observable RAs: ~3h-11h (evening to morning)

ra_deg = np.array([3, 4, 5, 6, 7, 8, 9, 10, 11]) * 15
generate_test_frbs(
    name='feb_observable',
    ra_list=list(ra_deg),
    description="February - RA 3-11h should be observable"
)

# ============================================================================
# Test Case 10: WINTER with WRONG RAs (Aug targets in Feb)
# ============================================================================
# Try to observe August targets (RA 14-17h, 0-4h) in February - should fail

ra_deg = np.array([0, 1, 2, 14, 15, 16, 17, 22, 23]) * 15
generate_test_frbs(
    name='feb_wrong_ras',
    ra_list=list(ra_deg),
    description="February - August RAs (should be unobservable in Feb)"
)

# ============================================================================
# Test Case 11: SPRING EQUINOX (Mar 20) - LST ≈ 0h at sunset
# ============================================================================
# Evening LST ~6h, morning LST ~13h
# Observable: RA 1-13h roughly

ra_deg = np.linspace(1, 13, 12) * 15
generate_test_frbs(
    name='mar_equinox',
    ra_list=list(ra_deg),
    description="March equinox - RA 1-13h coverage"
)

# ============================================================================
# Test Case 12: MIXED MAGNITUDES (bright to faint)
# ============================================================================
# Test exposure time scaling

ra_deg = np.linspace(14, 17, 10) * 15
mag_list = [14.5, 15.5, 16.5, 17.5, 18.5, 19.0, 19.5, 20.0, 20.3, 20.5]

generate_test_frbs(
    name='aug_mixed_mags',
    ra_list=list(ra_deg),
    mag_list=mag_list,
    description="August - magnitudes 14.5-20.5 (exposure time range)"
)

# ============================================================================
# Test Case 13: ALL FAINT (long exposures)
# ============================================================================

ra_deg = np.linspace(14, 17, 8) * 15
mag_list = [19.5, 19.8, 20.0, 20.1, 20.2, 20.3, 20.4, 20.5]

generate_test_frbs(
    name='aug_all_faint',
    ra_list=list(ra_deg),
    mag_list=mag_list,
    description="August - all faint (r > 19.5), tests long exposure scheduling"
)

# ============================================================================
# Test Case 14: ALL BRIGHT (short exposures)
# ============================================================================

ra_deg = np.linspace(14, 17, 8) * 15
mag_list = [14.5, 15.0, 15.5, 16.0, 16.2, 16.5, 16.8, 17.0]

generate_test_frbs(
    name='aug_all_bright',
    ra_list=list(ra_deg),
    mag_list=mag_list,
    description="August - all bright (r < 17), many short exposures"
)

# ============================================================================
# Test Case 15: EXACTLY 0 OBSERVABLE (worst case)
# ============================================================================
# All targets at RA 8-13h for August - all violate HA limits all night

ra_deg = np.linspace(8, 13, 10) * 15

generate_test_frbs(
    name='aug_zero_observable',
    ra_list=list(ra_deg),
    description="August - RA 8-13h, ZERO targets observable (all too far west)"
)

# ============================================================================
# Test Case 16: EXACTLY 1 OBSERVABLE
# ============================================================================
# Only one target in observable window

ra_deg = [15.5] + list(np.linspace(8, 13, 9) * 15)  # 1 good + 9 bad

generate_test_frbs(
    name='aug_one_observable',
    ra_list=ra_deg,
    description="August - only 1 of 10 targets observable"
)

# ============================================================================
# Test Case 17: NORTH POLE TARGETS (Dec ≈ +90°, always up but high airmass)
# ============================================================================
# Circumpolar targets - always above horizon but may have high airmass

ra_deg = np.linspace(0, 23, 12) * 15  # All RAs
dec_deg = [88] * 12  # Just below pole

generate_test_frbs(
    name='aug_circumpolar',
    ra_list=list(ra_deg),
    dec_list=dec_deg,
    description="August - Dec +88° circumpolar targets (high airmass)"
)

# ============================================================================
# Summary
# ============================================================================

print("="*80)
print("GENERATED 17 TEST CASES:")
print("="*80)
print("""
1.  aug_deadtime_gap     - Full-night gap (RA 6-9h)
2.  aug_evening_only     - Only evening targets (RA 14-17h)
3.  aug_morning_only     - Only morning targets (RA 0-4h)
4.  aug_clustered_ra     - 15 targets in 0.5h RA range
5.  aug_sparse_coverage  - Spread across observable window
6.  aug_ha_limits        - Right at HA boundary conditions
7.  aug_extreme_decs     - Dec -25° to +81°
8.  aug_over_dec_limit   - All Dec > 82° (all rejected)
9.  feb_observable       - February good RAs (3-11h)
10. feb_wrong_ras        - August RAs in February (bad)
11. mar_equinox          - March 20 coverage (RA 1-13h)
12. aug_mixed_mags       - Full magnitude range 14.5-20.5
13. aug_all_faint        - All r > 19.5 (long exposures)
14. aug_all_bright       - All r < 17 (short exposures)
15. aug_zero_observable  - RA 8-13h (nothing observable)
16. aug_one_observable   - Only 1/10 targets good
17. aug_circumpolar      - Dec +88° circumpolar high airmass

Files written to: tests/test_data/test_*.csv
""")

print(f"Total files: {len(list(TEST_DATA_DIR.glob('test_*.csv')))}")
