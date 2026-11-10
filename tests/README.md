# Test Suite

Comprehensive edge case testing for night-planner observability calculations.

Created by JXP and Claude

---

## Quick Start

```bash
# Generate 17 synthetic FRB target datasets (already done)
python test_data/generate_test_frbs.py

# Run all tests
python test_data/run_all_tests.py

# View results
cat test_data/results/test_summary.csv
cat test_data/TEST_RESULTS_SUMMARY.md
```

---

## Test Cases (17 total)

### Edge Case Categories

| Category | Tests | Purpose |
|----------|-------|---------|
| **Deadtime** | aug_deadtime_gap, aug_evening_only, aug_morning_only | Identify gaps in observable window |
| **RA clustering** | aug_clustered_ra, aug_sparse_coverage | Test dense vs spread targets |
| **HA boundaries** | aug_ha_limits | Test limit edge conditions |
| **Declination** | aug_extreme_decs, aug_over_dec_limit, aug_circumpolar | Test Dec extremes and pole |
| **Seasonal** | feb_observable, feb_wrong_ras, mar_equinox | Verify seasonal RA windows |
| **Magnitude** | aug_mixed_mags, aug_all_faint, aug_all_bright | Verify mag doesn't affect observability |
| **Pathological** | aug_zero_observable, aug_one_observable | Test extreme failure cases |

---

## Results Summary

### ✅ Passing Tests (9/17)

- aug_evening_only: 9/10 targets observable
- aug_morning_only: 10/10 targets observable ✓
- aug_clustered_ra: 15/15 dense field ✓
- aug_sparse_coverage: 120/120 targets ✓
- aug_extreme_decs: 7/8 observable
- feb_observable: 9/9 winter targets ✓
- aug_mixed_mags, aug_all_faint, aug_all_bright: magnitude tests ✓

### ❌ Failing Tests (8/17) - Known Bugs

All failures due to edge case bugs:
- **NoneType comparison:** 6 tests (targets never observable → min_am_time = None)
- **Empty DataFrame:** 2 tests (all targets rejected → KeyError)

**These are VALUABLE findings** - edge cases the code doesn't handle gracefully.

---

## Test Data

### Synthetic FRB Target CSVs

Located in `test_data/test_*.csv` (17 files):

Each CSV follows FFFF-PZ format:
- TNS name (FRB20260113A, etc.)
- RA, Dec (degrees)
- DM, survey, tags
- Primary host: RA, Dec, P(O|x), r-mag
- Mode: longslit

**Random elements:** Dec (unless specified), mag (unless specified), DM
**Fixed elements:** RA (per test design), survey, tags, mode

### Example Test Cases

**aug_deadtime_gap.csv:**
- RA: 6h, 7h, 8h, 9h (4 targets)
- Expected: 0 observable (RA gap in August)
- Creates full-night deadtime

**aug_morning_only.csv:**
- RA: 0-4h (10 targets evenly spaced)
- Expected: 10/10 observable
- Morning window perfect coverage

**aug_clustered_ra.csv:**
- RA: 15.0-15.5h (15 targets in 0.5h range)
- Expected: 15/15 observable
- Tests dense field handling

**feb_observable.csv:**
- Date: Feb 15, 2026
- RA: 3-11h (9 targets)
- Expected: 9/9 observable
- Different seasonal window than August

---

## Bugs Found

### 1. NoneType Comparison

**Location:** `scripts/lick_2026b01_calculations.py:268`

**Symptom:**
```
TypeError: '<' not supported between instances of 'NoneType' and 'float'
```

**Cause:** When target never enters HA window, `min_am_time` stays `None`. Sorting crashes.

**Affected tests:**
- aug_deadtime_gap
- aug_ha_limits
- feb_wrong_ras
- mar_equinox
- aug_zero_observable
- aug_one_observable

### 2. Empty DataFrame After Dec Filter

**Location:** `scripts/lick_2026b01_calculations.py:210`

**Symptom:**
```
KeyError: 'RA_hours'
```

**Cause:** All targets Dec > 82° → empty DataFrame → code continues anyway.

**Affected tests:**
- aug_over_dec_limit
- aug_circumpolar

---

## Files

```
tests/
├── README.md                      # This file
├── test_data/
│   ├── generate_test_frbs.py     # Generate 17 test CSVs
│   ├── run_all_tests.py          # Run observability on all tests
│   ├── TEST_RESULTS_SUMMARY.md   # Detailed analysis (6000 words)
│   ├── test_*.csv                # 17 synthetic target datasets
│   └── results/
│       ├── test_summary.csv      # Summary table
│       └── test_*_results.csv    # Per-test detailed results (9 files)
└── [future: pytest tests]
```

---

## Usage

### Run Full Suite

```bash
cd /path/to/night-planner
python tests/test_data/run_all_tests.py
```

Output:
- Terminal: Per-test results + summary table
- `results/test_summary.csv`: Summary
- `results/test_*_results.csv`: Detailed per-test results

### Run Single Test

```bash
python scripts/lick_2026b01_calculations.py \
    --targets tests/test_data/test_aug_morning_only.csv \
    --date 2026-08-13
```

### Generate New Test Data

Edit `test_data/generate_test_frbs.py`, add new test case, then:

```bash
python tests/test_data/generate_test_frbs.py
```

---

## Expected Behavior After Bug Fixes

When bugs are fixed, all 17 tests should:
- Run without crashes ✓
- Return valid results (0+ observable targets) ✓
- Provide clear rejection reasons ✓
- Match expected observability counts ✓

**Regression test:** After fixing bugs, re-run full suite and verify all pass.

---

## Documentation

**Detailed guide:** See [`../docs/Testing_guide.md`](../docs/Testing_guide.md)

**Test results:** See `test_data/TEST_RESULTS_SUMMARY.md`

**Shane constraints:** See [`../docs/Shane_telescope_constraints.md`](../docs/Shane_telescope_constraints.md)

---

## Future Enhancements

1. **pytest integration:**
   ```bash
   pytest tests/test_observability.py -v
   ```

2. **Automated regression testing** in CI/CD

3. **Additional test cases:**
   - Other observatories (different lat/lon)
   - Other telescopes (different HA limits)
   - Multi-night runs

4. **Performance tests:**
   - 1000+ target lists
   - Year-long observability windows

---

## Contributing

To add new test cases:

1. Edit `test_data/generate_test_frbs.py`
2. Add test case with `generate_test_frbs(name, ra_list, description)`
3. Regenerate: `python test_data/generate_test_frbs.py`
4. Run: `python test_data/run_all_tests.py`
5. Document expected behavior in `TEST_RESULTS_SUMMARY.md`

---

## Summary

**Purpose:** Validate observability calculations under edge conditions

**Coverage:** 17 scenarios (deadtime, seasonal, boundaries, pathological)

**Status:** 9/17 passing, 8/17 exposing known bugs

**Value:** Found 3 critical bugs that need fixing before production use

**Next steps:** Fix bugs, re-run suite, verify all tests pass
