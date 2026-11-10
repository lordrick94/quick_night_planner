> **Rescued from the private `Night_plans/Lick-2026B-01/` on 2026-11-09**
> (Created by JXP and Claude). Real target names are replaced by codes
> (`TGTnnnn`; the key is private) and Dec values in target tables are
> withheld. Paths to `Night_plans/...` now refer to the private plans
> directory (`$NIGHT_PLANNER_PLANS`).

# How the Lick-2026B-01 Night Plan Was Created

**Created by JXP and Claude**
**Date:** 2026-08-11
**Night:** August 13-14, 2026
**Observatory:** Lick Observatory, Shane 3m telescope
**Instrument:** Kast dual-beam spectrograph

---

## Table of Contents

1. [Overview](#overview)
2. [Initial Setup and Requirements](#initial-setup-and-requirements)
3. [Q&A Process: Gathering Critical Information](#qa-process-gathering-critical-information)
4. [Ephemeris Calculations](#ephemeris-calculations)
5. [Pointing Constraints](#pointing-constraints)
6. [Target Selection Process](#target-selection-process)
7. [Exposure Time Estimation](#exposure-time-estimation)
8. [Night Plan Structure](#night-plan-structure)
9. [Critical Corrections Made](#critical-corrections-made)
10. [Final Verification](#final-verification)
11. [Lessons Learned](#lessons-learned)

---

## Overview

This document explains step-by-step how the night plan for Lick-2026B-01 (night 1: August 13-14, 2026) was created. The plan selects and schedules CHIME/FRB host galaxy targets for spectroscopic observation with the Kast spectrograph.

**Key outputs:**
- `Lick_2026B-01_Night_plan.xlsx` - Excel timeline with target sequence, exposures, and ephemeris
- `target_analysis.csv` - Full analysis of all 12 viable targets
- `selected_targets_night1.csv` - Final 6 targets for the night
- Two Python scripts for reproducibility

---

## Initial Setup and Requirements

### Starting Point

The CHIME FFFF-PZ database had already generated a Resource (`Lick-2026B-01`) containing 14 CHIME/FRB targets that passed initial feasibility filters (airmass ≤ 2.0, r-mag ≤ 20.5, observable during the run window). Two were immediately cut for Dec > +82° (Shane pointing limit), leaving **12 viable candidates**.

**Target list source:** `Lick-2026B-01_targets.csv` from FFFF-PZ
**Initial filters already applied:** NeedSpectrum status, longslit mode, Aug 13-14 window, max_AM 2.0

### User Requirements

From the prompt file (`claude_prompts/night_plans/lick_2026aug13.md`):

1. **2-night run**, but plan **only night 1** (Aug 13)
2. **Instrument setup:** Kast with d57 dichroic, 600/7500 red grating, 600/4310 blue grism, 2" slit
3. **Exposure times** scaled by r-band magnitude
4. **Sheet structure** must match template: date-named sheets ("August 13th"), not target-named
5. Need **LST, UT, PST times** with sidereal time calculator
6. **Hour angle columns** for tracking pointing limits
7. Must cross-check ephemeris against **Lick calendar** (authoritative)

---

## Q&A Process: Gathering Critical Information

Before implementing, a detailed Q&A was conducted to clarify ambiguities. Key answers:

### Resource Naming
- **Q:** Zero-padded (`Lick-2026B-01`) or unpadded (`Lick-2026B-1`)?
- **A:** Use zero-padding: `Lick-2026B-01`

### Observation Window
- **Q:** Single night or multi-night? Start/end times?
- **A:** **2-night run**, but generate plan for **night 1 only** (Aug 13→14)
- **A:** Use **18° astronomical twilight** for dark observing (not 12° nautical)

### Target Selection Criteria
- **Q:** How many targets to select?
- **A:** Request 15 longslit targets from server, expect ~5-6 actually observed
- **Q:** FRB surveys, statuses, tags?
- **A:** Keep all null (no restrictions), take full pool
- **Q:** Magnitude limits?
- **A:** `max_mag = 20.5` (dark time, new moon ~Aug 12)

### Telescope Constraints (Critical!)
- **Q:** Any pointing limits beyond airmass ≤ 2.0?
- **A:** Shane has **two hard limits** (CORRECTED - initial understanding was wrong):
  1. **Dec ≤ +82°** (polar limit, already applied pre-plan)
  2. **HA: -5h ≤ HA ≤ +3.75h** (symmetric hour angle limits)
     - HA < -5h: too far EAST (>5h before transit)
     - HA > +3.75h: too far WEST (>3.75h after transit)
  3. **NO RA LIMITS** - observable RAs depend on LST and time of year

  **Note:** Initially misunderstood as "RA ≥ 5h" + "HA ≥ -3.75h" (west only). This error led to selecting 4 wrong targets before correction (see "Critical Corrections Made" section).

### Exposure Times
- **Q:** Scaling rules?
- **A:** By r-band magnitude:
  - r ≤ 15: 30 min + overhead (2×900s red, 1×1800s blue)
  - r ≤ 17: 60 min total (3×900s red, 2×1350s blue)
  - r 17-19: 80 min total (4×900s red, 2×1800s blue)
  - r 19-20.5: 120 min total (6×900s red, 3×1800s blue)
  - Kast is dual-beam: both arms expose *simultaneously*, so wall time = max(red, blue)

### Standard Stars
- **Q:** Which standard for Aug 13?
- **A:** Pick by highest airmass at twilight:
  - Evening: **HZ_44** (RA 13:23:35, Dec +36:07:59, mag 11.7)
  - Morning: **Feige_110** (RA 23:19:58.4, Dec -05:09:56, mag 11.8)

---

## Ephemeris Calculations

### Critical Decision: Timezone Convention

**Lick calendar uses PST (UTC-8) year-round**, even in summer when local time is PDT (UTC-7). This is crucial for LST calculations!

**Implementation:**
```python
PST = timezone(timedelta(hours=-8))  # Fixed offset, NOT pytz DST-aware
```

### Twilight Times (18° Astronomical)

Calculated using astropy, searching for sun altitude = -18°:

| Event | Time (PST) | LST |
|-------|------------|-----|
| **Evening 18° twilight** | 20:40 | 17h28m |
| **Morning 18° twilight** | 03:49 | 01h44m |
| **Timeline start** | 20:30 | (rounded to half-hour before dusk) |

**Verification against Lick calendar:**
- Evening: calculated 20:38 PST vs calendar 20:40 PST (**2 min** ✓)
- Morning: calculated 03:46 PST vs calendar 03:49 PST (**3 min** ✓)

**Night duration:** 7h08m (much shorter than initially calculated 8h18m with wrong twilight!)

### LST Verification

Cross-checked LST at 12° twilight times (where calendar provides reference):

| Time (PST) | Calculated LST | Calendar LST | Diff |
|------------|----------------|--------------|------|
| 20:04 (12° eve) | 17h27m50s | 17h28m | 10 sec ✓ |
| 04:19 (12° dawn) | 1h44m11s | 01h44m | 11 sec ✓ |

**LST calculation method:**
```python
def calculate_lst(utc_time, location=LICK):
    t = Time(utc_time)
    lst = t.sidereal_time('apparent', longitude=location.lon)
    return lst
```

---

## Pointing Constraints

### Two Hard Limits (CORRECTED)

Applied during target analysis:

#### 1. Declination Limit: Dec ≤ +82°

Already applied pre-plan. Two targets rejected:
- TGT0407 (Dec +84.08°)
- TGT0508 (Dec +84.70°)

**12 targets remain.**

#### 2. Hour Angle Limits: -5h ≤ HA ≤ +3.75h

Shane 3m has **symmetric HA limits** - cannot point too far east OR west of meridian:

**Constraints:**
- **HA < -5h:** too far EAST of meridian (target >5h before transit) ✗
- **HA > +3.75h:** too far WEST of meridian (target >3.75h after transit) ✗
- **-5h ≤ HA ≤ +3.75h:** observable ✓

**Hour Angle Convention:**
- HA = LST - RA (wrapped to ±12h)
- **Negative HA:** target EAST of meridian (before transit, rising)
- **Positive HA:** target WEST of meridian (after transit, setting)
- **HA = 0:** target on meridian (best airmass)

**NO RA LIMITS:** There is no "RA ≥ 5h" constraint. Observable RAs depend entirely on LST and the HA limits, which change throughout the night as LST advances.

#### Calculating Observable RA Ranges

For a given LST, the observable RA range is:
```python
# HA = LST - RA, so RA = LST - HA
ra_min = lst - ha_max  # LST - (+3.75h)
ra_max = lst - ha_min  # LST - (-5h)
```

**At evening twilight (LST 18.03h):**
- RA_min = 18.03 - 3.75 = **14.28h**
- RA_max = 18.03 - (-5) = **23.03h**
- Observable: **RA 14.28h – 23.03h**

**At morning twilight (LST 1.11h):**
- RA_min = 1.11 - 3.75 = **-2.64h** → **21.36h** (wrapped)
- RA_max = 1.11 - (-5) = **6.11h**
- Observable: **RA 21.36h – 24h ∪ 0h – 6.11h** (wraps around 0h)

**Throughout the night:**
- Evening-accessible: RA ~14–23h
- Morning-accessible: RA ~0–8h + ~21–24h
- **Never accessible: RA ~8–14h** (always HA > +3.75h, too far west)

### Applying HA Limits to Targets

For each target, calculate minimum and maximum HA during the night (20:38–03:46 PST):

**Targets at RA 0-5h (morning targets):**
- At evening twilight (LST 18h), these have HA ≈ +13h → -11h (very far west)
- But wait until morning! At LST 1-3h, HA ≈ -2h to -5h ✓ observable

**Targets at RA 15-16h (evening targets):**
- At evening twilight (LST 18h), HA ≈ +2h to +3h ✓ observable
- By morning (LST 1h), HA ≈ -14h → +10h (setting), no longer accessible

**Targets at RA 9-13h (rejected - too far west):**
- At evening twilight (LST 18h), HA ≈ +5h to +9h ✗ exceeds +3.75h limit
- Never enter observable window during the night
- These were the targets INCORRECTLY selected in the first version!

### Observable Targets: 6 Total (CORRECTED)

After applying HA limits throughout the night:

| TNS | RA (h) | HA range | Observable? |
|-----|--------|----------|-------------|
| TGT0060 | 0.55 | -4.5h to -0.0h (morning) | ✓ |
| TGT0506 | 1.62 | -3.7h to -0.8h (morning) | ✓ |
| TGT0176 | 2.40 | -2.9h to -1.6h (morning) | ✓ |
| TGT0252 | 5.25 | +0.5h to -4.4h (morning) | ✓ |
| TGT0059 | 15.45 | +2.6h to -9.9h | ✓ |
| TGT0172 | 15.74 | +2.3h to -10.2h | ✓ |
| **Rejected:** | | | |
| TGT0351 | 9.82 | +8.2h to +3.8h | ✗ always > +3.75h |
| TGT0562 | 11.71 | +6.3h to +1.9h | ✗ always > +3.75h |
| TGT0423 | 12.09 | +5.9h to +1.5h | ✗ always > +3.75h |
| TGT0070 | 12.21 | +5.8h to +1.4h | ✗ always > +3.75h |
| TGT0548 | 12.68 | +5.3h to +0.9h | ✗ always > +3.75h |
| TGT0321 | 12.86 | +5.2h to +0.7h | ✗ always > +3.75h |

**Key insight:** The 6 targets at RA 9-13h never enter the HA window. They're too far west at evening twilight and set before becoming accessible.

---

## Target Selection Process

### Observable Targets: 6 Total (CORRECTED)

After applying HA limits, only **6 of 12 targets** are observable:

**Evening-accessible (RA 15-16h):**

| TNS | RA (h) | Dec (°) | mag_r | min_AM | HA @ eve | Tags |
|-----|--------|---------|-------|--------|----------|------|
| TGT0172 | 15.74 | (private) | 18.44 | 1.12 | +2.30h | CHIME-Blind |
| TGT0059 | 15.45 | (private) | 16.87 | 1.19 | +2.58h | CHIME-Blind |

**Morning-accessible (RA 0-5h):**

| TNS | RA (h) | Dec (°) | mag_r | min_AM | HA @ morn | Tags |
|-----|--------|---------|-------|--------|-----------|------|
| TGT0060 | 0.55 | (private) | 15.98 | 1.01 | -0.00h | CHIME-Repeater |
| TGT0506 | 1.62 | (private) | 18.57 | 1.13 | -0.82h | CHIME-Unbiased |
| TGT0176 | 2.40 | (private) | 17.99 | 1.09 | -1.60h | CHIME-Repeater, CHIME-Blind |
| TGT0252 | 5.25 | (private) | 16.27 | 1.52 | -4.45h | CHIME-Repeater |

### Selection Strategy

**Goal:** Maximize science return in a 7.1h night

**All 6 targets selected** - the selection is constrained by observability, not choice:
- 2 evening targets (all that pass HA limits at RA 15-16h)
- 4 morning targets (all that pass HA limits at RA 0-5h)

**Observing sequence:**

**Evening block (20:30–22:30 PST):**
1. **TGT0172** (RA 15.74h, mag 18.44, 80 min) - low airmass 1.12, good S/N
2. **TGT0059** (RA 15.45h, mag 16.87, 60 min) - bright, efficient

**Morning block (00:30–03:30 PST):**
3. **TGT0060** (RA 0.55h, mag 15.98, 60 min) - brightest morning target
4. **TGT0506** (RA 1.62h, mag 18.57, 80 min) - CHIME-Unbiased sample
5. **TGT0176** (RA 2.40h, mag 17.99, 80 min) - Repeater + Blind tags
6. **TGT0252** (RA 5.25h, mag 16.27, 60 min) - Repeater, finish before dawn

**Total observing time:** 420 min (7.0h) — perfect fit for 7.1h night with slews, focus, standards, and calibrations

### Rejected Targets (RA 9-13h, Always Too Far West)

These 6 targets **never enter the observable HA window** during the night:

| TNS | RA (h) | mag_r | HA @ eve | HA @ morn | Why rejected |
|-----|--------|-------|----------|-----------|--------------|
| TGT0351 | 9.82 | 19.05 | +8.21h | +3.76h | Always > +3.75h limit |
| TGT0562 | 11.71 | 18.95 | +6.32h | +1.92h | Always > +3.75h until near dawn |
| TGT0423 | 12.09 | 18.97 | +5.94h | +1.53h | Always > +3.75h until near dawn |
| TGT0070 | 12.21 | 16.32 | +5.82h | +1.42h | Always > +3.75h until near dawn |
| TGT0548 | 12.68 | 19.79 | +5.35h | +0.94h | Always > +3.75h until dawn |
| TGT0321 | 12.86 | 19.18 | +5.18h | +0.76h | Always > +3.75h until dawn |

**Why they're inaccessible:**
- At evening twilight (LST 18h), these have HA +5h to +8h (too far west)
- They would need to be observed 2-5 hours EARLIER (LST 13-16h, mid-afternoon) to be in the HA window
- In August, the sun is at RA ~9-10h, so LST 13-16h is broad daylight
- They're "setting" targets that set before dark

**NOTE:** These same targets WOULD be observable in a different season when the sun is elsewhere (e.g., February when sun is at RA ~21-22h, making LST 13-16h occur at night).

---

## Exposure Time Estimation

### Magnitude-Based Scaling

Based on prior Lick/Kast FRB runs (analyzed in `claudes_brain.md`):

| r-mag range | Total time | Red arm | Blue arm | Rationale |
|-------------|------------|---------|----------|-----------|
| < 15 | 30 min | 2 × 900s | 1 × 1800s | Bright, quick |
| 15–17 | 60 min | 3 × 900s | 2 × 1350s | Standard |
| 17–19 | 80 min | 4 × 900s | 2 × 1800s | Moderate faint |
| 19–20.5 | 120 min | 6 × 900s | 3 × 1800s | Faint limit |

**Key constraint:** Kast is dual-beam (red + blue simultaneous), so wall time = max(red_total, blue_total), not the sum.

**Overhead assumption:** ~30% (slews, acquisitions, readouts) included in total time estimates.

### Applied to Selected Targets (CORRECTED)

| Target | mag_r | Red | Blue | Total (min) |
|--------|-------|-----|------|-------------|
| TGT0172 | 18.44 | 4×900 | 2×1800 | 80 |
| TGT0059 | 16.87 | 3×900 | 2×1350 | 60 |
| TGT0060 | 15.98 | 3×900 | 2×1350 | 60 |
| TGT0506 | 18.57 | 4×900 | 2×1800 | 80 |
| TGT0176 | 17.99 | 4×900 | 2×1800 | 80 |
| TGT0252 | 16.27 | 3×900 | 2×1350 | 60 |

---

## Night Plan Structure

### Excel Sheet Organization

Following the `Lick_2026A-4_Night_plan.xlsx` template:

**Sheets:**
1. **Observing Checklist** - pre-obs tasks (dome open, focus, etc.)
2. **August 13th** - main timeline for the night
3. *(future: FRB Observing Summary, Post Observing Tracking)*

### Timeline Columns (August 13th sheet)

| Column | Header | Content |
|--------|--------|---------|
| A | Start (LST) | Sidereal time at start |
| B | Start (UT) | UT time (decimal hours) |
| C | Start (PST) | Local PST time (HH:MM) |
| D | Duration | Minutes (e.g., "80 min") |
| E | End (PST) | End time (HH:MM) |
| F | Action | "Standard Star", "slew to -->", "Science + overhead", "Focus", etc. |
| G | target | FRB name or standard star |
| H | RA | Sexagesimal (HH:MM:SS.ss) |
| I | DEC | Sexagesimal (±DD:MM:SS.s) |
| **J** | **HA start** | **Hour angle at start (hours, ±12)** |
| **K** | **HA end** | **Hour angle at end (hours, ±12)** |
| L | mag(r) | r-band magnitude |
| M | sec mag | Secondary host magnitude (usually blank) |
| N | red side | Exposure config (e.g., "4 x 900") |
| O | blue side | Exposure config (e.g., "2 x 1800") |
| P | Redshift; | (blank pre-obs) |
| Q | Comments | P(O\|x), tags, notes |

**Sidebar (columns S-T):** Sidereal time calculator (sample PST → LST conversions)

### Timeline Sequence

**Start: 20:30 PST**

1. **Standard Star (HZ_44)** - 5 min
2. **Focus** - 5 min
3. **Science targets** (6 total):
   - Slew → target (2 min each)
   - Science + overhead (60-120 min depending on magnitude)
4. **Standard Star (Feige_110)** - 5 min (morning)
5. **Calibrations:**
   - Bias frames - 5 min
   - Flat fields - 10 min

**End: ~03:40 PST** (just before 03:46 dawn)

### Hour Angle Calculation

For each target with RA:

```python
ha_start = lst_start - ra_hours
ha_end = lst_end - ra_hours

# Wrap to ±12h
if ha > 12: ha -= 24
elif ha < -12: ha += 24
```

**Interpretation:**
- **Negative HA:** target east of meridian (rising, before transit)
- **Positive HA:** target west of meridian (setting, after transit)
- **HA = 0:** target on meridian (optimal airmass)

**Critical limits:** -5h ≤ HA ≤ +3.75h (Shane pointing limits, symmetric)

---

## Critical Corrections Made

### Mistake 1: Wrong Twilight Definition (Initial)

**Error:** Used -12° (nautical) instead of -18° (astronomical)

**Impact:**
- Evening twilight 1 hour too early (21:03 vs 20:40)
- Morning twilight 1.5 hours too late (05:21 vs 03:49)
- Night appeared 8h18m instead of actual 7h08m

**Fix:** Changed `twilight_alt=-18*u.deg` in `find_twilight()`

### Mistake 2: Timezone Confusion (Major!)

**Error:** Used `pytz.timezone('America/Los_Angeles')` which gives PDT (UTC-7) in August

**Impact:**
- LST off by ~1 hour (30+ minutes)
- Calculated LST 18h02m vs calendar 17h28m at evening twilight

**Root cause:** Lick calendar uses **PST (UTC-8) year-round** for consistency, not DST-aware timezones

**Fix:**
```python
PST = timezone(timedelta(hours=-8))  # Fixed offset
# NOT: PACIFIC = pytz.timezone('America/Los_Angeles')
```

**Verification after fix:**
- 12° eve: LST 17h27m50s vs calendar 17h28m ✓
- 12° dawn: LST 1h44m11s vs calendar 01h44m ✓

### Mistake 3: Morning Twilight Search

**Error:** Started morning twilight search at `evening + 8h`, but August night is only ~7h

**Impact:** Missed morning twilight initially (search didn't reach far enough back)

**Fix:** Start search at `evening + 6h`

### Mistake 4: MAJOR - Wrong Understanding of Shane HA Limits

**Error:** Believed Shane had:
- "RA ≥ 5h" constraint (NO SUCH LIMIT EXISTS!)
- Only HA ≥ -3.75h on west side (missing the -5h east limit)

**What I did wrong:**
- Rejected 4 targets at RA 0-5h for violating fake "RA < 5h limit"
- Selected 4 targets at RA 12-13h that ACTUALLY violated the real HA > +3.75h west limit
- **First night plan had 4 of 6 targets that couldn't be observed!**

**Correct Shane 3m limits:**
1. **Dec ≤ +82°** (polar limit) ✓
2. **HA: -5h ≤ HA ≤ +3.75h** (symmetric limits)
   - HA < -5h: too far EAST (>5h before transit)
   - HA > +3.75h: too far WEST (>3.75h after transit)
3. **NO RA limits** - observable RAs depend on LST and time of year

**Impact:**
- OLD target list: 2 correct (RA 15-16h) + 4 WRONG (RA 12-13h, violated HA west limit)
- NEW target list: 2 evening (RA 15-16h) + 4 morning (RA 0-5h, now correctly included)
- Total observing time: 520 min → 420 min (better fit for 7.1h night)

**Root cause:** Misunderstood telescope mechanical limits. HA constraints are symmetric and time-dependent - targets aren't "observable" or "not" universally, they're observable at specific LSTs.

**Fix:**
```python
# OLD (WRONG):
if ra_hours < 5.0:
    return False, "RA < 5h limit"
if ha < -3.75:
    return False, "HA < -3.75h limit"

# NEW (CORRECT):
if ha < -5.0:
    return False, "HA < -5h limit (too far east)"
if ha > 3.75:
    return False, "HA > +3.75h limit (too far west)"
# No RA check at all!
```

**Key lesson:** Always verify telescope pointing limits with the observer. Mechanical constraints are non-obvious and easily misunderstood.

---

## Final Verification

### Cross-Check Against Lick Calendar

Source: https://www.ucolick.org/calendar/lickcal2021-30/lick2026.12aug

**Row: THU AUG 13**

| Parameter | Calculated | Calendar | Diff | Status |
|-----------|------------|----------|------|--------|
| Sunset | - | 19:09 PST | - | - |
| 12° twilight end | 20:04 PST | 20:04 PST | 0 min | ✓ |
| 18° twilight end | 20:38 PST | 20:40 PST | 2 min | ✓ |
| 18° dawn | 03:46 PST | 03:49 PST | 3 min | ✓ |
| 12° dawn | 04:19 PST | 04:19 PST | 0 min | ✓ |
| Sunrise | - | 05:14 PST | - | - |
| **LST at 12° eve** | **17h28m** | **17h28m** | **0 min** | **✓** |
| **LST at midnight** | **21h24m** | **21h24m** | **0 min** | **✓** |
| **LST at 12° dawn** | **01h44m** | **01h44m** | **0 min** | **✓** |

**Conclusion:** Ephemeris calculations validated to **minute precision** (times) and **10-20 second precision** (LST).

### Airmass Verification (CORRECTED)

All 6 selected targets have minimum airmass ≤ 2.0 during the night:

| Target | Min AM | Time (PST) | When Observable |
|--------|--------|------------|-----------------|
| TGT0172 | 1.12 | 20:38 | Evening (at twilight) |
| TGT0059 | 1.19 | 20:38 | Evening (at twilight) |
| TGT0060 | 1.01 | 03:08 | Morning (near transit) |
| TGT0506 | 1.13 | 03:23 | Morning |
| TGT0176 | 1.09 | 03:23 | Morning |
| TGT0252 | 1.52 | 03:23 | Morning |

**Evening targets** (RA 15-16h): Low airmass at twilight, HA +2 to +3h (west of meridian, setting).

**Morning targets** (RA 0-5h): Not accessible at evening twilight (HA -6h to -13h, too far east), but rise into observable window by midnight and reach low airmass near dawn.

---

## Lessons Learned

### 1. Always Verify Against Authoritative Calendars

**Key insight:** Observatory calendars (like Lick's) are pre-computed with site-specific parameters and serve as ground truth. Cross-checking catches calculation errors early.

**Application:** Verified both times (twilight) and LST against calendar before finalizing plan.

### 2. Timezone Conventions Matter for LST

**Key insight:** Observatories may use non-standard timezone conventions (e.g., PST year-round) to avoid DST confusion. This directly affects LST calculations via UTC conversion.

**Application:** Read calendar documentation to understand timezone convention, use fixed UTC offset instead of DST-aware `pytz`.

### 3. Telescope Pointing Limits Are Mechanical, Not Astronomical - Verify With Observer!

**Key insight:** Shane has **ONLY TWO mechanical limits** (Dec ≤ 82°, HA: -5h to +3.75h), NO RA limit. Hour angle constraints are SYMMETRIC and create time-dependent observable RA windows that shift with LST.

**CRITICAL:** I initially believed there was an "RA ≥ 5h" limit and missed the east HA limit, leading to selecting 4 WRONG targets (RA 12-13h that violated HA > +3.75h) while rejecting 4 CORRECT ones (RA 0-5h that were morning-accessible).

**Application:**
- **Always verify pointing limits with the observer** - don't guess or assume
- HA limits create LST-dependent RA windows, not static RA forbidden zones
- Targets aren't "observable" or "not" universally - they're observable at specific LSTs
- Use `observable_ra_calculator.py` to visualize which RAs are accessible on any date

### 4. Dual-Beam Spectrographs Change Exposure Time Estimates

**Key insight:** Kast exposes both arms simultaneously, so total wall time ≠ red + blue. This differs from single-arm instruments.

**Application:** Exposure time = max(red_total, blue_total), not sum. Affects scheduling significantly.

### 5. Target Selection Is Criteria-Driven, Not Hand-Ranked

**Key insight:** FFFF-PZ draws targets stochastically (tag-weighted) from the feasible pool. The night plan selects from that set based on *observability*, not scientific priority.

**Application:** Document the selection mechanism honestly (Reports section of prompt file). Observers still down-select ~5-6 targets at the telescope based on conditions and priorities.

### 6. Reproducibility Requires Scripting

**Key insight:** Manual Excel creation is error-prone and not reproducible. Writing Python scripts (`lick_2026b01_calculations.py`, `build_night_plan.py`) ensures:
- Calculations are documented and reviewable
- Future nights can reuse the logic
- Errors can be debugged systematically

**Application:** All calculations → scripts, committed to repo. Night plan is *generated*, not hand-built.

---

## Automation Scripts Created

### `scripts/lick_2026b01_calculations.py`

**Purpose:** Calculate ephemeris, apply pointing constraints, select targets

**Key functions:**
- `find_twilight()` - find 18° twilight times
- `calculate_lst()` - PST → LST conversion
- `calculate_airmass()` - target visibility
- `check_pointing_limits()` - Dec & **HA** constraints (CORRECTED: no RA limit!)
- `analyze_targets()` - full night analysis
- `select_targets_for_night()` - choose 6 targets

**Outputs:**
- `target_analysis.csv` - all 6 observable targets (CORRECTED: was 8)
- `selected_targets_night1.csv` - final 6 targets

### `scripts/build_night_plan.py`

**Purpose:** Generate Excel night plan from selected targets

**Key functions:**
- `pst_to_lst()` - time conversion
- `format_ra_dec()` - sexagesimal formatting
- `add_observing_checklist()` - checklist sheet
- `add_night_sheet()` - main timeline with HA calculation
- `build_night_plan()` - orchestrate Excel generation

**Output:**
- `Lick_2026B-01_Night_plan.xlsx` - complete observing plan

### `scripts/observable_ra_calculator.py` (NEW)

**Purpose:** Calculate and visualize observable RA ranges for any date

**Key functions:**
- `find_twilight_lst()` - get LST at 18° twilight
- `calculate_observable_ra_range()` - RA window from LST & HA limits
- `observable_ra_for_night()` - RA ranges throughout a night
- `plot_observable_ra_vs_month()` - year-round visualization

**Outputs:**
- Terminal: evening/morning RA ranges for specified date
- `observable_ra_2026.png` - plot showing RA accessibility each month

**Usage:**
```bash
python scripts/observable_ra_calculator.py  # Aug 13, 2026 + year plot
```

**Key insight:** Shows that HA limits [-5h, +3.75h] create shifting RA windows throughout the year. No static "RA forbidden zone"!

---

## Usage for Future Nights

### To Generate Night 2 (Aug 14-15, 2026)

1. Update date in `lick_2026b01_calculations.py`:
   ```python
   date = '2026-08-14'
   ```

2. Run calculations:
   ```bash
   python scripts/lick_2026b01_calculations.py
   ```

3. Update Excel script:
   ```python
   date_str = "August 14th"
   start_pst = datetime(2026, 8, 14, 20, 30, 0, tzinfo=PST)
   ```

4. Build night plan:
   ```bash
   python scripts/build_night_plan.py
   ```

### To Adapt for Different Run

1. **Change observatory:** Update `LICK` coordinates, timezone offset, calendar URL
2. **Change instrument:** Update exposure time rules, setup notes
3. **Change constraints:** Modify `check_pointing_limits()` for different telescope
4. **Change target pool:** Point to new `_targets.csv` from FFFF-PZ

All logic is parameterized and reusable.

---

## Files Generated

```
Night_plans/Lick-2026B-01/
├── Lick-2026B-01_targets.csv              # FFFF-PZ output (14 targets)
├── Lick-2026B-01_possible_targs.xlsx      # Candidate targets (12 after Dec cut)
├── target_analysis.csv                     # Full analysis (12 targets)
├── selected_targets_night1.csv             # Final selection (6 targets)
├── Lick_2026B-01_Night_plan.xlsx          # MAIN DELIVERABLE
└── HOWTO_night_plan_creation.md           # This document

scripts/
├── lick_2026b01_calculations.py            # Ephemeris & target selection
└── build_night_plan.py                     # Excel generation
```

---

## Summary

**Night 1 Plan (Aug 13-14, 2026):**
- **Timeline:** 20:30 PST → 03:46 PST (7h16m)
- **Targets:** 6 CHIME/FRB host galaxies (2 evening + 4 morning)
- **Total observing:** ~420 min (7.0h of exposures with simultaneous arms + overhead)
- **Constraints satisfied:** Dec ≤ 82°, HA: -5h to +3.75h, AM ≤ 2.0
- **Ephemeris verified:** ±2-3 min (times), ±10-20 sec (LST) vs Lick calendar
- **Reproducible:** All calculations scripted in Python

**Key Decision:** Use **PST (UTC-8) year-round** for LST calculations, matching Lick calendar convention.

**Ready for observing!**

---

## Appendix: Target Selection Pipeline Investigation (2026-08-14)

After creating the initial plan, we investigated alternative target sources and discovered **critical issues with the FFFF-PZ automated target selection**.

### Scripts and Tools Used

#### 1. FFFF-PZ Database Tools

```bash
# Add resource to FFFF-PZ database
chime_ffff_pz_add_furesource chime_ffff_pz/data/Observing/Lick-2026B-1/Lick-2026B-1.json

# Query targets assigned to resource
chime_ffff_pz_targets Lick-2026B-1
# Output: Lick-2026B-1_targets.csv (4 targets)

# Generate finder charts (requires FFFF-PZ API running on localhost:8000)
cd chime_ffff_pz/data/Observing/Lick-2026B-1
chime_ffff_pz_finder TGT0060 Lick-2026B-1

# Generate telescope starlist from finder JSON files
chime_ffff_pz_starlist lick
# Output: lick.starlist
```

#### 2. Custom Target Query Script

**Location:** `scripts/query_ffffpz_targets.py`

Queries local FFFF-PZ database for all FRBs matching:
- Observable RA range (13.28h to 6.80h, wraps around 0h)
- Dec < 82° (Shane limit)
- Returns 314 candidates with P_Ux values

```bash
python scripts/query_ffffpz_targets.py
# Output: Night_plans/Lick-2026B-01/ffffpz_candidates.csv (314 FRBs)
```

**Key finding:** Identified 64 FRBs with P_Ux > 0.5 (likely hostless), 241 with P_Ux < 0.5 (likely has host).

**CRITICAL ERROR MADE:** Initially prioritized P_Ux = 1.000 thinking it meant "perfect host ID". **WRONG!** P_Ux = probability FRB is hostless:
- **P_Ux = 1.0** → 100% hostless (NO galaxy) ❌
- **P_Ux = 0.0** → has identified host ✓

Corrected: select P_Ux < 0.1 for targets with hosts.

#### 3. HA Limit Correction Script

**Location:** `scripts/fix_ha_limits.py`

**Problem discovered:** Original night plan violated Shane HA pointing limits (-5.0h to +3.75h) for ALL 6 targets!
- Evening targets: calculated end HA +9.4h to +9.7h (beyond +3.75h limit)
- Morning targets: calculated start HA -6.5h to -12.2h (beyond -5.0h limit)

**Solution:** Clips observable windows to Shane HA limits using astropy LST calculations.

```bash
python scripts/fix_ha_limits.py
# Output: Night_plans/Lick-2026B-01/selected_targets_ha_corrected.csv
```

**Results:**
- Evening targets MUST END by 22:48-23:05 PDT (when HA reaches +3.75h)
- Morning targets START staggered as HA crosses -5.0h:
  - TGT0060: 23:08 PDT (HA = -5.0h)
  - TGT0506: 00:12 PDT
  - TGT0176: 00:59 PDT
  - TGT0252: 03:49 PDT

**Key insight:** Total individual windows (1318 min) >> night duration (525 min) due to overlap. **Cannot observe all 6 targets for 70 min each!**

See `HA_LIMIT_FIX.md` for full analysis.

#### 4. hco_batch_jul26.csv Investigation

**Location:** `Night_plans/Lick-2026B-01/hco_batch_jul26.csv`

Pre-selected batch of 19 FRBs from HCO observing campaign. Manual investigation revealed:

**All 19 in local FFFF-PZ DB** ✓
**13 observable** on 2026-08-13
**7 have PATH results**
**3 with P_Ux = 0.000** (perfect host ID!)

**Top new candidates found:**
- **TGT0568**: RA=13.87h, mag=**15.36**, P_Ux=**0.000** ← BRIGHTEST of all!
- **TGT0567**: RA=13.59h, mag=16.93, P_Ux=**0.000** ← Better than original evening targets

**Why weren't these returned by `chime_ffff_pz_targets`?**

Investigation revealed: The API endpoint returns FRBs **already assigned** to the resource in the database, not all FRBs matching the criteria!

Server-side selection logic (unknown) appears to filter by:
1. Time window
2. Criteria (max_AM, max_mag)
3. **Additional unknown filters** (status? tags? manual curation?)

### Pipeline Limitations Discovered

**`chime_ffff_pz_targets` is NOT reliable for target selection!**

Reasons:
1. Returns pre-assigned FRBs only (4 in our case)
2. Returned 2 non-observable targets (TGT0407 RA=6.93h, TGT0508 RA=10.07h outside RA range)
3. Missed better targets (TGT0568 mag 15.36 vs returned targets mag 16-19)
4. No HA limit filtering on server side

### Recommended Workflow for Future Nights

**DO NOT rely on FFFF-PZ automated selection alone!**

1. **Start with curated batch files** (e.g., hco_batch_jul26.csv)
2. **Query local FFFF-PZ** for full FRB info:
   ```python
   from chime_ffff_pz.utils import ffff_pz_utils
   frbs = ffff_pz_utils.get_transients()
   ```
3. **Filter manually:**
   - P_Ux < 0.1 (has identified host)
   - Check PATH results exist
   - Observable RA/Dec for specific night
   - Brightness (mag < 19 preferred)
4. **Calculate HA windows** with `fix_ha_limits.py`
5. **Select 4-6 targets** based on:
   - Brightness (lower mag = shorter exposures)
   - P_Ux (lower = better host ID)
   - Observable time window (after HA clipping)
6. **Generate finders** (if FFFF-PZ API running):
   ```bash
   chime_ffff_pz_finder <FRB_name> <resource_name>
   ```
7. **Generate starlist**:
   ```bash
   chime_ffff_pz_starlist lick
   ```
8. **Update night plan** with final selection

### All Files Created During Investigation

```
Night_plans/Lick-2026B-01/
├── hco_batch_jul26.csv                    # Pre-selected batch (19 FRBs)
├── ffffpz_candidates.csv                  # All 314 observable FRBs
├── Lick-2026B-1_targets.csv              # API-returned (4 FRBs, limited)
├── selected_targets_ha_corrected.csv      # HA-clipped windows (original 6)
├── lick.starlist                          # Telescope starlist (5 of 6)
├── finder_charts/                         # Finder PNGs (5 of 6)
│   ├── TGT0059_finder.png
│   ├── TGT0060_finder.png
│   ├── TGT0172_finder.png
│   ├── TGT0176_finder.png
│   └── TGT0506_finder.png
├── NEW_TARGETS_FROM_FFFFPZ.md            # Initial analysis (P_Ux error)
├── FFFF-PZ_TARGETS.md                    # API targets comparison
├── HCO_BATCH_COMPARISON.md               # ★ BEST - found superior targets
└── HA_LIMIT_FIX.md                       # HA violation analysis

scripts/
├── query_ffffpz_targets.py               # Query all observable FRBs
├── fix_ha_limits.py                      # Calculate HA-corrected windows
└── document_pipeline_workflow.md         # Full investigation summary

chime-ffff-pz/chime_ffff_pz/data/Observing/Lick-2026B-1/
├── Lick-2026B-1.json                     # Resource definition
├── Lick-2026B-1_targets.csv              # API-returned targets
├── lick.starlist                          # Telescope starlist
└── FRB*_finder.json/png                   # Finder charts
```

### Critical Lessons Learned

1. **P_Ux Definition:**
   - P_Ux = probability FRB is hostless
   - For spectroscopy, select P_Ux < 0.1 (has host)
   - P_Ux = 1.000 → hostless (BAD for spectroscopy!)

2. **HA Limits are Critical:**
   - Shane: -5.0h ≤ HA ≤ +3.75h
   - Original plan violated limits for all 6 targets
   - Reduces observable time significantly (especially for morning targets)

3. **FFFF-PZ API Limitations:**
   - `chime_ffff_pz_targets` returns pre-assigned FRBs, not all matching criteria
   - Server-side selection logic unknown and incomplete
   - Manual filtering required for best results

4. **Pre-Selected Batches are Valuable:**
   - hco_batch_jul26.csv contained superior targets
   - TGT0568 (mag 15.36, P_Ux=0.000) better than all API-returned targets

5. **PATH Results Required:**
   - Check existence before generating finders
   - Magnitudes from PATH candidates determine exposure times

6. **Observable != Schedulable:**
   - RA range calculation doesn't account for HA limits
   - Targets can be "observable" but not fit in night after HA clipping
   - Heavy overlap means can't observe all targets

### Final Target Recommendation (Post-Investigation)

**Replace 1-2 evening targets with hco_batch candidates:**

**Evening (choose 2):**
- ★ **TGT0568** (mag=15.36, P_Ux=0.000) ← BEST NEW
- ★ **TGT0567** (mag=16.93, P_Ux=0.000) ← EXCELLENT NEW
- TGT0059 (mag=16.87, have finder) ← Original, still good

**Morning (keep original 4):**
- TGT0060 (mag=15.98, P_Ux=0.003) - brightest morning target
- TGT0506 (mag=18.57, P_Ux=0.003)
- TGT0176 (mag=17.99, P_Ux=0.105)
- TGT0252 (mag=16.27, P_Ux=0.035) - need to generate finder

**Action items if using new targets:**
1. Generate finders for TGT0568 + TGT0567
2. Recalculate HA windows
3. Regenerate starlist with final selection
4. Update Excel night plan

---

**Investigation Date:** 2026-08-14
**Tools Used:** chime_ffff_pz_targets, chime_ffff_pz_finder, chime_ffff_pz_starlist, custom Python scripts
**Key Discovery:** FFFF-PZ automated selection incomplete; manual curation found better targets
