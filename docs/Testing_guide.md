# Testing Guide

**night-planner** test suite for edge case validation

Created by JXP and Claude

---

## Overview

The test suite provides **17 synthetic FRB target datasets** covering edge cases:
- Deadtime gaps
- Seasonal variations
- HA limit boundaries
- Extreme declinations
- Zero/one observable targets
- Dense vs sparse RA coverage
- Magnitude extremes

---

## Quick Start

```bash
# Generate test datasets (already done, but can regenerate)
cd night-planner   # wherever you cloned it
python tests/test_data/generate_test_frbs.py

# Run all tests
python tests/test_data/run_all_tests.py

# View results
cat tests/test_data/results/test_summary.csv
cat tests/test_data/TEST_RESULTS_SUMMARY.md
```

---

## Test Cases

### ✅ Successful Tests (9/17)

These tests expose expected behavior and validate correct handling:

| Test | Description | Targets | Observable | % |
|------|-------------|---------|------------|---|
| **aug_evening_only** | RA 14-17h (evening window) | 10 | 9 | 90% |
| **aug_morning_only** | RA 0-4h (morning window) | 10 | 10 | 100% |
| **aug_clustered_ra** | 15 targets in 0.5h range | 15 | 15 | 100% |
| **aug_sparse_coverage** | 120 targets RA 0-1.5h | 120 | 120 | 100% |
| **aug_extreme_decs** | Dec -25° to +81° | 8 | 7 | 88% |
| **feb_observable** | February RA 3-11h | 9 | 9 | 100% |
| **aug_mixed_mags** | r=14.5-20.5 range | 10 | 9 | 90% |
| **aug_all_faint** | All r > 19.5 | 8 | 7 | 88% |
| **aug_all_bright** | All r < 17 | 8 | 7 | 88% |

**Insights:**
- Morning-only targets (RA 0-4h) achieve 100% observability in August
- Dense fields with 15 targets in 0.5h work perfectly
- Seasonal windows differ dramatically (Aug vs Feb)
- Magnitude doesn't affect observability (only exposure times)

### ❌ Failed Tests - Known Bugs (8/17)

These tests **correctly expose edge case bugs** that need fixing:

| Test | Error | Root Cause |
|------|-------|------------|
| **aug_deadtime_gap** | `NoneType < float` | RA 6-9h never observable |
| **aug_ha_limits** | `NoneType < float` | Targets at HA boundaries |
| **aug_over_dec_limit** | `KeyError: 'RA_hours'` | All Dec > 82° rejected |
| **feb_wrong_ras** | `NoneType < float` | Aug RAs unobservable in Feb |
| **mar_equinox** | `NoneType < float` | March 20 edge case |
| **aug_zero_observable** | `NoneType < float` | RA 8-13h (all rejected) |
| **aug_one_observable** | `NoneType < float` | Only 1/10 good |
| **aug_circumpolar** | `KeyError: 'RA_hours'` | Dec +88° circumpolar |

**What these reveal:**
1. Code doesn't handle targets that **never enter observable window** (min_am_time = None)
2. Empty DataFrames crash when **all targets rejected** by Dec filter
3. Need graceful degradation for pathological cases

---

## Test Case Details

### 1. aug_deadtime_gap (RA 6-9h)

**Purpose:** Test full-night gap when no targets are observable

**Setup:**
- 4 targets at RA 6h, 7h, 8h, 9h
- Date: Aug 13, 2026

**Expected behavior:**
- In August (LST 18h-1h), RA 6-9h has:
  - Evening: HA = +9h to +12h (too far west)
  - Morning: HA = +5h to +8h (still too far west)
- Targets never enter [-5h, +3.75h] window
- Should return "0 observable targets"

**Current bug:** Crashes with `NoneType < float` when trying to sort by None `min_am_time`

---

### 2. aug_evening_only (RA 14-17h)

**Purpose:** Test evening-accessible targets only

**Result:** 9/10 observable (90%)
- RA 14h has HA = +4.03h at evening (just over +3.75h limit)
- RA 14.33-17h all observable

**Insight:** Only the westernmost edge of the evening window fails.

---

### 3. aug_morning_only (RA 0-4h)

**Purpose:** Test morning-accessible targets only

**Result:** 10/10 observable (100%)

**Insight:** Perfect morning window - all targets become observable before dawn.

---

### 4. aug_clustered_ra (RA 15.0-15.5h)

**Purpose:** Test dense field scheduling

**Setup:** 15 targets within 0.5h RA range

**Result:** 15/15 observable (100%)

**Insight:** Scheduler can handle dense fields - no need to spread targets across RA.

---

### 5. aug_sparse_coverage (RA 0-1.5h)

**Purpose:** Test many targets spread across observable window

**Setup:** 120 targets RA 0.03-1.47h

**Result:** 120/120 observable (100%)

**Insight:** Can handle large target lists if they're in the right RA range.

---

### 6. aug_ha_limits (HA boundaries)

**Purpose:** Test edge conditions at HA = ±5h, ±3.75h

**Setup:** Targets placed right at limit boundaries for evening/morning

**Current bug:** Crashes - likely due to targets exactly at limits or just outside.

**Fix needed:** Handle boundary conditions gracefully.

---

### 7. aug_extreme_decs (Dec -25° to +81°)

**Purpose:** Test airmass at extreme declinations

**Result:** 7/8 observable (88%)

**Insight:** Dec range mostly OK; only RA-based rejections occur.

---

### 8. aug_over_dec_limit (All Dec > 82°)

**Purpose:** Test pathological case where all targets rejected

**Setup:** 5 targets at Dec 83-87°

**Current bug:** Crashes with `KeyError: 'RA_hours'` when DataFrame is empty after Dec filter

**Fix needed:**
```python
df = df[df['Pri_Dec'] <= 82.0].copy()
if len(df) == 0:
    print("WARNING: All targets rejected by Dec > 82° limit!")
    return pd.DataFrame(), twilight, start_pst
```

---

### 9. feb_observable (Feb 15, RA 3-11h)

**Purpose:** Test winter observable window

**Result:** 9/9 observable (100%)

**LST range:** Evening 4.87h, Morning 15.11h (10.2h night - much longer than August!)

**Insight:** Winter nights are longer with completely different RA window.

---

### 10. feb_wrong_ras (August RAs in February)

**Purpose:** Verify seasonal dependence - August targets should fail in Feb

**Setup:** RA 0-2h, 14-17h, 22-23h (August-optimal RAs)

**Expected:** Should be unobservable in February

**Current bug:** Crashes (targets never observable)

**Insight:** Confirms seasonal dependence is critical.

---

### 11. mar_equinox (March 20)

**Purpose:** Test spring equinox window (LST ~7.5h-16.5h at twilights)

**Current bug:** Crashes

**Needs:** Verification of which RAs are observable at spring equinox.

---

### 12-14. Magnitude Tests

**Purpose:** Verify magnitude doesn't affect observability calculations

**Results:**
- **aug_mixed_mags** (r=14.5-20.5): 9/10 observable
- **aug_all_faint** (r>19.5): 7/8 observable
- **aug_all_bright** (r<17): 7/8 observable

**Insight:** Magnitude only affects exposure times, not constraints. ✓

---

### 15. aug_zero_observable (RA 8-13h)

**Purpose:** Worst-case scenario - nothing observable

**Setup:** 10 targets at RA 8-13h (always HA > +3.75h in August)

**Expected:** 0 observable targets

**Current bug:** Crashes

**This is the "RA gap" in August** - all targets too far west all night.

---

### 16. aug_one_observable (1/10 good)

**Purpose:** Test sparse success case

**Setup:** 1 target at RA 15.5h (good) + 9 at RA 8-13h (bad)

**Expected:** 1/10 observable

**Current bug:** Crashes

**Insight:** Mix of good/bad targets exposes sorting bug.

---

### 17. aug_circumpolar (Dec +88°)

**Purpose:** Test circumpolar targets (always above horizon but high airmass)

**Setup:** 12 targets at Dec +88°, all RAs 0-23h

**Expected:** All observable but with high airmass (always up)

**Current bug:** Crashes

**Needs:** Investigation of astropy's AltAz behavior for circumpolar coordinates.

---

## Bugs Found

### Bug 1: NoneType Comparison

**Symptom:**
```
TypeError: '<' not supported between instances of 'NoneType' and 'float'
```

**Cause:**
When target never enters observable window, `min_am_time` remains `None`. Later sorting crashes.

**Fix:**
```python
# Option 1: Set sentinel value
if min_am_time is None:
    min_am = 99.9
    min_am_time = twilight['evening_utc']
    min_am_ha = 99.9

# Option 2: Filter before sorting
results_df = results_df[results_df['min_am_time'].notna()]
```

### Bug 2: Empty DataFrame After Filtering

**Symptom:**
```
KeyError: 'RA_hours'
```

**Cause:**
All targets rejected by Dec filter → empty DataFrame → later code assumes columns exist.

**Fix:**
```python
df = df[df['Pri_Dec'] <= 82.0].copy()
if len(df) == 0:
    print("\nWARNING: All targets rejected by Dec > 82° limit!")
    print(f"No observable targets for {date_str}")
    return pd.DataFrame(), twilight, start_pst
```

### Bug 3: Circumpolar Handling

**Needs investigation:** Check how astropy's AltAz handles circumpolar targets (Dec > 90° - lat).

---

## Running Individual Tests

```bash
# Test a single case
python scripts/lick_2026b01_calculations.py \
    --targets tests/test_data/test_aug_morning_only.csv \
    --date 2026-08-13

# Compare two dates
python scripts/lick_2026b01_calculations.py \
    --targets tests/test_data/test_feb_observable.csv \
    --date 2026-02-15
```

---

## Creating New Test Cases

Edit `tests/test_data/generate_test_frbs.py`:

```python
# Add new test case
ra_deg = np.array([your_ras]) * 15  # Convert hours to degrees
dec_deg = [your_decs]              # Optional
mag_list = [your_mags]             # Optional

generate_test_frbs(
    name='your_test_name',
    ra_list=list(ra_deg),
    dec_list=dec_deg,
    mag_list=mag_list,
    description="Your test description"
)
```

Regenerate:
```bash
python tests/test_data/generate_test_frbs.py
python tests/test_data/run_all_tests.py
```

---

## Interpreting Results

### Success Criteria

- ✅ All expected observable targets pass HA limits
- ✅ All rejected targets have valid rejection reasons
- ✅ No crashes on edge cases
- ✅ Timeline has no unexpected gaps

### Failure Investigation

1. **Check rejection reasons:**
   ```bash
   grep "limit_reason" tests/test_data/results/test_*.csv
   ```

2. **Verify HA calculations:**
   - Calculate by hand: `HA = LST - RA`
   - Check if HA is in [-5h, +3.75h] range

3. **Cross-reference seasonal windows:**
   ```bash
   python scripts/observable_ra_calculator.py
   ```

---

## Regression Testing

After fixing bugs, re-run full suite:

```bash
# Fix bugs in scripts/lick_2026b01_calculations.py
# Then verify all tests pass

python tests/test_data/run_all_tests.py > test_output.log

# Check for errors
grep -i "error" test_output.log

# Count successes
grep "Observable:" test_output.log | wc -l  # Should be 17
```

---

## Adding Tests to pytest

Future enhancement - convert to pytest:

```python
# tests/test_observability.py
import pytest
from scripts.lick_2026b01_calculations import analyze_targets

@pytest.mark.parametrize("test_case,date,expected", [
    ("test_aug_morning_only.csv", "2026-08-13", 10),
    ("test_aug_zero_observable.csv", "2026-08-13", 0),
])
def test_observability(test_case, date, expected):
    results_df, _, _ = analyze_targets(
        f"tests/test_data/{test_case}",
        date
    )
    n_obs = results_df['observable'].sum()
    assert n_obs == expected
```

Run with:
```bash
pytest tests/test_observability.py -v
```

---

## Summary

**Test suite provides:**
- Comprehensive edge case coverage (17 scenarios)
- Bug detection (found 3 critical bugs)
- Seasonal validation (Aug, Feb, Mar)
- Magnitude independence verification
- Pathological case handling checks

**Use cases:**
- Validate fixes after code changes
- Test new observatories/telescopes
- Verify seasonal calculations
- Demonstrate edge case behavior

**Files:**
- Generator: `tests/test_data/generate_test_frbs.py`
- Runner: `tests/test_data/run_all_tests.py`
- Results: `tests/test_data/results/`
- Summary: `tests/test_data/TEST_RESULTS_SUMMARY.md`
