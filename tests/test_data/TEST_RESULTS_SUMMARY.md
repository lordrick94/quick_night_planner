### FRB Night Plan Edge Case Testing - Results Summary

**Created by JXP and Claude**
**Date:** 2026-08-12

---

## Executive Summary

**Question:** Does the Lick-2026B-01 night plan (Aug 13-14, 2026) have deadtime?

**Answer:** **NO DEADTIME**. The 6 selected targets flow continuously from 20:30 PST to ~03:50 PST:

- **Evening block** (20:30-23:04): TGT0172 (80 min) + TGT0059 (60 min)
- **Morning block** (23:06-03:50): TGT0060 (60 min) + TGT0506 (80 min) + TGT0176 (80 min) + TGT0252 (60 min)

First morning target (TGT0060, RA 0.55h) becomes observable at **22:08 PST**, before the evening block ends at 23:04. The schedule flows continuously with no gaps.

---

## Test Suite Overview

**17 synthetic FRB target sets** were generated to test edge cases:

| Category | Test Cases |
|----------|-----------|
| **Deadtime scenarios** | RA gaps, evening-only, morning-only |
| **RA clustering** | Sparse vs dense coverage |
| **HA limit edges** | Boundary conditions |
| **Declination extremes** | Southern limit to near-pole |
| **Seasonal variations** | August, February, March equinox |
| **Magnitude extremes** | All bright vs all faint |
| **Pathological cases** | Zero observable, one observable, all rejected |

### Files Generated

- **Test data:** `tests/test_data/test_*.csv` (17 files)
- **Generator script:** `tests/test_data/generate_test_frbs.py`
- **Test runner:** `tests/test_data/run_all_tests.py`
- **Results:** `tests/test_data/results/*_results.csv`

---

## Test Results

### ✅ Successful Tests (9/17)

| Test | Date | Targets | Observable | % | Notes |
|------|------|---------|------------|---|-------|
| **Aug - evening only** | 2026-08-13 | 10 | 9 | 90% | RA 14-17h, 1 too far west |
| **Aug - morning only** | 2026-08-13 | 10 | 10 | 100% | RA 0-4h, all observable |
| **Aug - clustered RA** | 2026-08-13 | 15 | 15 | 100% | Dense field RA 15.0-15.5h |
| **Aug - sparse coverage** | 2026-08-13 | 120 | 120 | 100% | RA 0-1.5h morning window |
| **Aug - extreme Decs** | 2026-08-13 | 8 | 7 | 88% | Dec -10° to +81°, 1 rejected |
| **Feb - good RAs** | 2026-02-15 | 9 | 9 | 100% | RA 3-11h winter window |
| **Aug - mixed mags** | 2026-08-13 | 10 | 9 | 90% | r=14.5-20.5 range |
| **Aug - all faint** | 2026-08-13 | 8 | 7 | 88% | r > 19.5 |
| **Aug - all bright** | 2026-08-13 | 8 | 7 | 88% | r < 17 |

**Key findings:**
- Morning-only targets (RA 0-4h) have 100% observability in August
- Clustered fields (15 targets in 0.5h RA) work fine - scheduler can handle dense fields
- Feb 15 LST window (~5h-15h) is completely different from August (~18h-1h)
- Extreme Decs up to +81° are observable (high airmass but within limits)

### ❌ Failed Tests (8/17) - Exposed Bugs

These tests **correctly exposed edge case bugs** in the calculation code:

| Test | Error | Root Cause |
|------|-------|------------|
| **Aug - RA 6-9h deadtime gap** | `NoneType < float` | Targets never enter observable window → min_am_time = None |
| **Aug - HA limit edges** | `NoneType < float` | Some targets at HA boundaries have None values |
| **Aug - all Dec > 82°** | `KeyError: 'RA_hours'` | All targets rejected before analysis → empty DataFrame |
| **Feb - wrong RAs** | `NoneType < float` | August RAs unobservable in February |
| **Mar - equinox** | `NoneType < float` | Similar to Feb wrong RAs |
| **Aug - zero observable** | `NoneType < float` | RA 8-13h never enters window in August |
| **Aug - one observable** | `NoneType < float` | 9/10 targets never observable |
| **Aug - circumpolar** | `KeyError: 'RA_hours'` | Dec +88° circumpolar targets issue |

**What these bugs reveal:**

1. **Code doesn't handle "never observable" gracefully:**
   - When a target never enters the HA window during the night, `min_am_time` is None
   - Sorting by None causes crashes
   - **Fix needed:** Check for None before comparisons, or set sentinel value (e.g., `inf`)

2. **Empty DataFrames after filtering:**
   - When ALL targets are rejected (e.g., all Dec > 82°), result is empty
   - Later code assumes columns exist
   - **Fix needed:** Early return when n_observable = 0, or add existence checks

3. **These are VALUABLE findings!**
   - Real-world scenarios can hit these cases (wrong season, bad coordinates)
   - Better to find bugs now than during observing

---

## Detailed Test Case Descriptions

### 1. **aug_deadtime_gap** ❌
- **RA:** 6-9h (all targets)
- **Expected:** Full-night gap - targets too far west at evening, too far east at morning
- **Result:** Code crash (never observable)
- **Interpretation:** In August (LST 18h-1h), RA 6-9h has HA:
  - Evening: HA = 18-6 = +12h (too far west, >+3.75h limit)
  - Morning: HA = 1-6 = -5h (just at east limit, but sets before entering window)

### 2. **aug_evening_only** ✅
- **RA:** 14-17h evenly spaced
- **Result:** 9/10 observable (90%)
- **Rejection:** 1 target at RA 14h has HA = +4.03h > +3.75h (just over limit)
- **Interpretation:** RA 14-17h is prime evening territory; only the westernmost edge fails

### 3. **aug_morning_only** ✅
- **RA:** 0-4h evenly spaced
- **Result:** 10/10 observable (100%)
- **Interpretation:** Perfect morning window - all targets enter HA limits before dawn

### 4. **aug_clustered_ra** ✅
- **RA:** 15.0-15.5h (15 targets in 0.5h range)
- **Result:** 15/15 observable (100%)
- **Interpretation:** Dense field scheduling works - targets don't need to be spread out

### 5. **aug_sparse_coverage** ✅
- **RA:** 0.03-1.47h (broad but within morning window)
- **Result:** 120/120 observable (100%)
- **Interpretation:** Can handle many targets if they're in the right RA range

### 6. **aug_ha_limits** ❌
- **RA:** Boundaries at HA = ±5h, ±3.75h for evening/morning
- **Expected:** Test edge conditions
- **Result:** Code crash
- **Interpretation:** Likely some targets exactly at boundaries or just outside - exposes rounding/comparison bugs

### 7. **aug_extreme_decs** ✅
- **Dec:** -25° to +81° (full range)
- **Result:** 7/8 observable (88%)
- **Interpretation:** Dec range mostly OK; only RA limit violations matter for Shane

### 8. **aug_over_dec_limit** ❌
- **Dec:** All 83-87° (above Shane +82° limit)
- **Result:** Code crash (KeyError)
- **Expected behavior:** Should gracefully return "0 observable targets"
- **Interpretation:** Edge case when NOTHING passes Dec filter - need early exit

### 9. **feb_observable** ✅
- **Date:** Feb 15, 2026
- **RA:** 3-11h (designed for winter LST window)
- **Result:** 9/9 observable (100%)
- **LST range:** Evening 4.87h, morning 15.11h (10.2h night!)
- **Interpretation:** Winter nights are longer; different RA window works perfectly

### 10. **feb_wrong_ras** ❌
- **Date:** Feb 15, 2026
- **RA:** 0-2h, 14-17h, 22-23h (August targets)
- **Expected:** Should fail - wrong season
- **Result:** Code crash (never observable)
- **Interpretation:** Confirms seasonal dependence - August RAs unobservable in Feb

### 11. **mar_equinox** ❌
- **Date:** Mar 20, 2026
- **RA:** 1-13h
- **Expected:** Test spring window (LST ~7.5h-16.5h)
- **Result:** Code crash
- **Interpretation:** Need to verify observable RAs for this date

### 12-14. **Magnitude tests** ✅
- **All passed:** Mixed (14.5-20.5), all faint (>19.5), all bright (<17)
- **Result:** Magnitude doesn't affect observability calculation (only exposure times)
- **Interpretation:** Code correctly separates magnitude from constraints

### 15. **aug_zero_observable** ❌
- **RA:** 8-13h (worst possible for August)
- **Expected:** 0 targets observable
- **Result:** Code crash
- **Interpretation:** This is the "RA gap" in August - always HA > +3.75h (too far west)

### 16. **aug_one_observable** ❌
- **RA:** 1 good (15.5h) + 9 bad (8-13h)
- **Expected:** 1/10 observable
- **Result:** Code crash
- **Interpretation:** Mix of good/bad targets exposes sorting bug

### 17. **aug_circumpolar** ❌
- **Dec:** +88° (circumpolar at Lick lat +37°)
- **RA:** Full range 0-23h
- **Expected:** All observable but high airmass (always above horizon)
- **Result:** Code crash
- **Interpretation:** Circumpolar targets may need special handling (never rise/set)

---

## Bugs Found and Recommended Fixes

### Bug 1: NoneType comparison when targets never observable

**Location:** `scripts/lick_2026b01_calculations.py`, line ~268

**Symptom:**
```
TypeError: '<' not supported between instances of 'NoneType' and 'float'
```

**Root cause:**
When a target never enters the observable HA window, the loop doesn't update `min_am_time`, leaving it as `None`. Later sorting/comparison crashes.

**Fix:**
```python
# In analyze_targets(), initialize:
min_am = 99.9
min_am_time = None
min_am_ha = None

# After sampling loop:
if min_am_time is None:
    # Target never observable
    min_am = 99.9
    min_am_time = twilight['evening_utc']  # Placeholder
    min_am_ha = 99.9  # Clearly invalid

# OR: filter out None before sorting
results_df = results_df[results_df['min_am_time'].notna()]
```

### Bug 2: Empty DataFrame after Dec filter

**Location:** `scripts/lick_2026b01_calculations.py`, line ~210

**Symptom:**
```
KeyError: 'RA_hours'
```

**Root cause:**
```python
df = df[df['Pri_Dec'] <= 82.0].copy()
```
If ALL targets have Dec > 82°, `df` is empty, but code continues.

**Fix:**
```python
# Filter by Dec limit
df = df[df['Pri_Dec'] <= 82.0].copy()

# Check for empty result
if len(df) == 0:
    print("\nWARNING: All targets rejected by Dec > 82° limit!")
    print(f"No observable targets for {date_str}")
    return pd.DataFrame(), twilight, start_pst  # Return empty DataFrame

# Continue with analysis...
```

### Bug 3: Circumpolar target handling

**Location:** Airmass calculation

**Issue:** Circumpolar targets (Dec > 90° - lat) never cross the horizon. Current code may not handle this correctly.

**Needs investigation:** Check astropy's AltAz behavior for circumpolar coordinates.

---

## Seasonal Observable RA Ranges (Reference)

From `scripts/observable_ra_calculator.py`:

| Month | LST Evening (18°) | LST Morning (18°) | Observable RAs | Night Length |
|-------|-------------------|-------------------|----------------|--------------|
| **Aug** (13th) | 18.03h | 1.11h | 14.3-23.0h, 23.7-8.4h | 7.1h |
| **Feb** (15th) | 4.87h | 15.11h | ~0h-10h | 10.2h |
| **Mar** (20th) | 7.59h | 16.53h | ~2.5-12.5h | 8.9h |
| **May** (15th) | 13.5h | 22.5h | ~8.5-18.5h | 9.0h |
| **Nov** (15th) | 0.5h | 9.5h | ~19.5-5.5h | 9.0h |

**Key insight:** Observable RA window shifts ~2h/month as Earth orbits sun. No single RA is "always observable" year-round from a given site.

---

## Recommendations

### 1. **Fix the bugs** (high priority)
- Handle None values in min_am_time
- Add early returns for zero-observable cases
- Test on failed edge cases to verify fixes

### 2. **Add validation checks** (medium priority)
- Warn if < 3 targets observable (night may be inefficient)
- Warn if all targets in one RA range (no evening/morning diversity)
- Check for large gaps in timeline

### 3. **Enhance test suite** (low priority)
- Add pytest unit tests using these edge cases
- Automate regression testing
- Test other observatories (different lat/lon)

### 4. **Documentation** (done)
- This summary documents edge case behavior
- `HOWTO_night_plan_creation.md` explains HA limits
- `observable_ra_calculator.py` visualizes seasonal windows

---

## Conclusion

**Original question answered:** Lick-2026B-01 has **NO deadtime**. The 6 targets flow continuously 20:30-03:50 PST.

**Bonus findings:** Testing revealed **3 edge-case bugs** that should be fixed before production use. All bugs relate to graceful handling of "nothing observable" scenarios - valuable to catch now!

**Test suite value:** The 17 synthetic target sets provide comprehensive regression testing for future code changes.

**Files to run:**
```bash
# Generate test data (already done)
python tests/test_data/generate_test_frbs.py

# Run full test suite (will show bugs)
python tests/test_data/run_all_tests.py

# After fixing bugs, re-run to verify all 17 cases pass
```

---

## Appendix: Test Data Format

Each `test_*.csv` file follows the FFFF-PZ target format:

| Column | Description |
|--------|-------------|
| `TNS` | FRB name (e.g., FRB20260113A) |
| `FRB_RA`, `FRB_Dec` | FRB position (degrees) |
| `FRB_DM` | Dispersion measure (pc/cm³) |
| `FRB_survey` | Survey name (CHIME) |
| `FRB_tags` | Tags (CHIME-Blind, etc.) |
| `Pri_RA`, `Pri_Dec` | Primary host position (degrees) |
| `Pri_POx` | P(O|x) association probability |
| `Pri_mag` | r-band magnitude |
| `Pri_filter` | Filter band |
| `mode` | Observing mode (longslit) |
| `Resource` | Resource name (Test-*) |

**Random elements:** Dec (unless specified), mag (unless specified), DM
**Fixed elements:** RA (per test case design), survey, tags, mode
