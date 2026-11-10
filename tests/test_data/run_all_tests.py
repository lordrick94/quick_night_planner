"""
Run observability analysis on all test cases and generate report.

Created by JXP and Claude
"""

import sys
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta, timezone

# Import calculation functions
from scripts.lick_2026b01_calculations import (
    analyze_targets,
    find_twilight,
    PST,
)

TEST_DATA_DIR = Path(__file__).parent
OUTPUT_DIR = TEST_DATA_DIR / 'results'
OUTPUT_DIR.mkdir(exist_ok=True)

# Test configurations: (filename, date, description)
TEST_CASES = [
    ('test_aug_deadtime_gap.csv', '2026-08-13', 'August - RA 6-9h deadtime gap'),
    ('test_aug_evening_only.csv', '2026-08-13', 'August - evening only'),
    ('test_aug_morning_only.csv', '2026-08-13', 'August - morning only'),
    ('test_aug_clustered_ra.csv', '2026-08-13', 'August - clustered RA'),
    ('test_aug_sparse_coverage.csv', '2026-08-13', 'August - sparse coverage'),
    ('test_aug_ha_limits.csv', '2026-08-13', 'August - HA limit edges'),
    ('test_aug_extreme_decs.csv', '2026-08-13', 'August - extreme Decs'),
    ('test_aug_over_dec_limit.csv', '2026-08-13', 'August - all Dec > 82°'),
    ('test_feb_observable.csv', '2026-02-15', 'February - good RAs'),
    ('test_feb_wrong_ras.csv', '2026-02-15', 'February - wrong RAs'),
    ('test_mar_equinox.csv', '2026-03-20', 'March equinox'),
    ('test_aug_mixed_mags.csv', '2026-08-13', 'August - mixed mags'),
    ('test_aug_all_faint.csv', '2026-08-13', 'August - all faint'),
    ('test_aug_all_bright.csv', '2026-08-13', 'August - all bright'),
    ('test_aug_zero_observable.csv', '2026-08-13', 'August - zero observable'),
    ('test_aug_one_observable.csv', '2026-08-13', 'August - one observable'),
    ('test_aug_circumpolar.csv', '2026-08-13', 'August - circumpolar'),
]

def analyze_test_case(csv_file, date_str, description):
    """Run analysis on one test case."""

    print(f"\n{'='*80}")
    print(f"TEST: {description}")
    print(f"File: {csv_file}")
    print(f"Date: {date_str}")
    print(f"{'='*80}")

    # Run analysis
    try:
        results_df, twilight, start_pst = analyze_targets(
            str(TEST_DATA_DIR / csv_file),
            date_str
        )
    except Exception as e:
        print(f"ERROR: {e}")
        return None

    # Count observable
    n_total = len(results_df)
    n_observable = results_df['observable'].sum()
    n_rejected = n_total - n_observable

    print(f"\nRESULTS:")
    print(f"  Total targets: {n_total}")
    print(f"  Observable: {n_observable}")
    print(f"  Rejected: {n_rejected}")

    if n_observable > 0:
        obs = results_df[results_df['observable']]
        print(f"\n  Observable RA range: {obs['RA_hours'].min():.2f}h - {obs['RA_hours'].max():.2f}h")
        print(f"  Observable Dec range: {obs['Dec_deg'].min():.1f}° - {obs['Dec_deg'].max():.1f}°")
        print(f"  Min airmass range: {obs['min_airmass'].min():.2f} - {obs['min_airmass'].max():.2f}")

        # Check for HA limit violations in "observable" targets (shouldn't happen!)
        bad_obs = obs[
            (obs['min_am_ha'] < -5.0) | (obs['min_am_ha'] > 3.75)
        ]
        if len(bad_obs) > 0:
            print(f"\n  WARNING: {len(bad_obs)} 'observable' targets violate HA limits!")
            for idx, row in bad_obs.iterrows():
                print(f"    {row['TNS']}: HA {row['min_am_ha']:.2f}h")

    if n_rejected > 0:
        rej = results_df[~results_df['observable']]
        reason_counts = rej['limit_reason'].value_counts()
        print(f"\n  Rejection reasons:")
        for reason, count in reason_counts.items():
            print(f"    {count:2d} targets: {reason}")

    # Save detailed results
    output_file = OUTPUT_DIR / csv_file.replace('.csv', '_results.csv')
    results_df.to_csv(output_file, index=False)
    print(f"\n  Saved to: {output_file}")

    return {
        'test': description,
        'date': date_str,
        'n_total': n_total,
        'n_observable': n_observable,
        'n_rejected': n_rejected,
        'pct_observable': 100 * n_observable / n_total if n_total > 0 else 0,
        'twilight_eve': twilight['evening_pst'].strftime('%H:%M'),
        'twilight_morn': twilight['morning_pst'].strftime('%H:%M'),
        'lst_eve': twilight['evening_lst'].hour,
        'lst_morn': twilight['morning_lst'].hour,
    }

def main():
    """Run all tests."""

    print("="*80)
    print("RUNNING OBSERVABILITY TESTS ON ALL EDGE CASES")
    print("="*80)

    summary_data = []

    for csv_file, date_str, description in TEST_CASES:
        result = analyze_test_case(csv_file, date_str, description)
        if result is not None:
            summary_data.append(result)

    # Create summary table
    summary_df = pd.DataFrame(summary_data)

    print("\n" + "="*80)
    print("SUMMARY TABLE")
    print("="*80)
    print(summary_df.to_string(index=False))

    # Save summary
    summary_file = OUTPUT_DIR / 'test_summary.csv'
    summary_df.to_csv(summary_file, index=False)
    print(f"\nSummary saved to: {summary_file}")

    # Highlight interesting cases
    print("\n" + "="*80)
    print("INTERESTING CASES:")
    print("="*80)

    # Zero observable
    zero_obs = summary_df[summary_df['n_observable'] == 0]
    if len(zero_obs) > 0:
        print(f"\nZERO OBSERVABLE ({len(zero_obs)} cases):")
        for _, row in zero_obs.iterrows():
            print(f"  - {row['test']}")

    # Partial observable (< 50%)
    partial = summary_df[
        (summary_df['pct_observable'] > 0) &
        (summary_df['pct_observable'] < 50)
    ]
    if len(partial) > 0:
        print(f"\nPARTIAL OBSERVABLE < 50% ({len(partial)} cases):")
        for _, row in partial.iterrows():
            print(f"  - {row['test']}: {row['n_observable']}/{row['n_total']} ({row['pct_observable']:.0f}%)")

    # All observable (100%)
    all_obs = summary_df[summary_df['pct_observable'] == 100]
    if len(all_obs) > 0:
        print(f"\nALL OBSERVABLE ({len(all_obs)} cases):")
        for _, row in all_obs.iterrows():
            print(f"  - {row['test']}: {row['n_observable']}/{row['n_total']}")

    print("\n" + "="*80)
    print("TEST SUITE COMPLETE")
    print("="*80)
    print(f"Results in: {OUTPUT_DIR}/")

if __name__ == '__main__':
    main()
