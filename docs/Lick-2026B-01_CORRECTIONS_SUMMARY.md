> **Rescued from the private `Night_plans/Lick-2026B-01/` on 2026-11-09**
> (Created by JXP and Claude). Real target names are replaced by codes
> (`TGTnnnn`; the key is private) and Dec values in target tables are
> withheld. Paths to `Night_plans/...` now refer to the private plans
> directory (`$NIGHT_PLANNER_PLANS`).

# Critical Corrections to Lick-2026B-01 Night Plan

**Date:** 2026-08-11 (late session)
**Issue:** Misunderstood Shane 3m telescope pointing limits

---

## Original (INCORRECT) Understanding

**Constraints believed:**
1. Dec ≤ +82° ✓ (correct)
2. **RA ≥ 5h** ✗ (WRONG - no such limit exists!)
3. **HA ≥ -3:45h** ✗ (WRONG - this is the WEST limit, not east)

**Impact:**
- Rejected 4 targets at RA 0-5h thinking they violated "RA < 5h limit"
- Selected 6 targets at RA 12-16h, which actually violate the HA limits!

---

## Corrected Understanding

**Shane 3m Actual Constraints:**
1. **Dec ≤ +82°** (polar limit)
2. **HA limits: -5h ≤ HA ≤ +3.75h**
   - HA < -5h: too far EAST (cannot point >5h before meridian transit)
   - HA > +3.75h: too far WEST (cannot point >3.75h after meridian transit)
3. **NO RA limits** - observable RAs depend only on time of year and sun position

**Hour Angle Convention:**
- HA = LST - RA (wrapped to ±12h)
- **Negative HA:** target EAST of meridian (before transit, rising)
- **Positive HA:** target WEST of meridian (after transit, setting)

---

## Observable RA Ranges (Aug 13, 2026)

From `scripts/observable_ra_calculator.py`:

**Evening twilight (LST 18.03h):**
- Observable RAs: **14.28h – 23.03h**
- Targets at RA 12-14h have HA > +3.75h (too far west) ✗
- Targets at RA 0-8h have HA < -5h (too far east) ✗

**Morning twilight (LST 1.11h):**
- Observable RAs: **23.67h – 8.42h** (wraps around 0h)
- Targets at RA 0-8h NOW observable (HA in range) ✓

**Night coverage:**
- Evening: RA ~14-23h accessible
- Morning: RA ~0-8h + 23-24h accessible
- Gap: RA ~8-14h NOT observable (too far west throughout night)

---

## Target List Changes

### OLD Selection (INCORRECT)

6 targets at RA 12-16h:
1. TGT0172 (RA 15.74h) ✓ still valid
2. TGT0059 (RA 15.45h) ✓ still valid
3. TGT0321 (RA 12.86h) ✗ HA +5.18h > +3.75h limit
4. TGT0548 (RA 12.68h) ✗ HA +5.35h > +3.75h limit
5. TGT0423 (RA 12.09h) ✗ HA +5.94h > +3.75h limit
6. TGT0070 (RA 12.21h) ✗ HA +5.82h > +3.75h limit

**4 of 6 targets violated HA west limit!**

### NEW Selection (CORRECT)

6 targets, split between evening and morning:

**Evening targets (RA 15-16h):**
1. **TGT0172** (RA 15.74h, mag 18.44, 80 min) - HA +2.30h ✓
2. **TGT0059** (RA 15.45h, mag 16.87, 60 min) - HA +2.58h ✓

**Morning targets (RA 0-5h):**
3. **TGT0060** (RA 0.55h, mag 15.98, 60 min) - HA -0.00h at minimum ✓
4. **TGT0506** (RA 1.62h, mag 18.57, 80 min) - HA -0.82h at minimum ✓
5. **TGT0176** (RA 2.40h, mag 17.99, 80 min) - HA -1.60h at minimum ✓
6. **TGT0252** (RA 5.25h, mag 16.27, 60 min) - HA -4.45h at minimum ✓

**Total:** 420 min (7.0h) - perfect fit for 7.1h night

---

## Rejected Targets (Why?)

**RA 9-13h targets (6 total) - TOO FAR WEST:**
- TGT0351 (RA 9.82h): HA +8.21h at evening twilight
- TGT0562 (RA 11.71h): HA +6.32h
- TGT0423 (RA 12.09h): HA +5.94h
- TGT0070 (RA 12.21h): HA +5.82h
- TGT0548 (RA 12.68h): HA +5.35h
- TGT0321 (RA 12.86h): HA +5.18h

All have HA > +3.75h (west limit) at evening twilight and never enter observable window during the night.

---

## Files Updated

### Scripts
- ✓ `scripts/lick_2026b01_calculations.py` - corrected HA limits
- ✓ `scripts/observable_ra_calculator.py` - NEW, shows RA ranges vs time of year
- ✓ `scripts/build_night_plan.py` - regenerated with new targets

### Data
- ✓ `target_analysis.csv` - 6 observable (was 8 wrong)
- ✓ `selected_targets_night1.csv` - NEW 6 targets
- ✓ `Lick_2026B-01_Night_plan.xlsx` - regenerated timeline

### Documentation
- ⚠️ `HOWTO_night_plan_creation.md` - NEEDS MAJOR REWRITE (sections 5-7)
- ⚠️ `context/claudes_brain.md` - NEEDS UPDATE (v0.15 has wrong limits)
- ⚠️ `Logs/2026/08/2026-08-11.md` - ADD correction entry

---

## Key Lessons

1. **Always verify telescope limits with observer** - mechanical limits are non-obvious
2. **HA ≠ RA** - hour angle depends on LST, changes throughout night
3. **East vs West confusion** - negative HA is EAST (rising), positive is WEST (setting)
4. **Time-dependent observability** - targets at RA 0-5h are morning-only, not forbidden
5. **Double-check rejection reasons** - "RA < 5h" should have been suspicious (why that specific value?)

---

## Observable RA Plot

See `observable_ra_2026.png` - shows which RAs are accessible each month with HA limits [-5h, +3.75h].

**Key insight:** Accessible RA window shifts ~2h/month as Earth orbits sun. August window: RA ~14h-8h (wrapping through 0h).

---

## Next Steps

1. ✓ Regenerate night plan with correct targets
2. ✓ Create observable RA calculator script
3. ⚠️ Rewrite HOWTO sections 5-7 (Pointing Constraints, Target Selection, Rejected Targets)
4. ⚠️ Update brain.md v0.15 with correct limits
5. ⚠️ Add correction entry to session log

**Status:** Night plan is now CORRECT. Documentation needs updates.
