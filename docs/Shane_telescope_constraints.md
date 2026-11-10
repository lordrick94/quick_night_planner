# Shane 3m Telescope Constraints

**Observatory:** Lick Observatory, Mount Hamilton, CA
**Telescope:** Shane 3-meter
**Coordinates:** Lat +37.3414°, Lon -121.6429°, Elevation 1283m

Created by JXP and Claude

---

## Pointing Limits

### 1. Declination Limit

**Dec ≤ +82°** (polar limit)

Targets with Dec > +82° cannot be observed due to mechanical limits near the north celestial pole.

**Example rejections:**
- TGT0407 (Dec +84.08°) ✗
- TGT0508 (Dec +84.70°) ✗

---

### 2. Hour Angle Limits (CRITICAL)

**-5h ≤ HA ≤ +3.75h** (symmetric limits)

The Shane telescope has **asymmetric** hour angle limits:

| Limit | Value | Meaning | Direction |
|-------|-------|---------|-----------|
| **East limit** | HA < -5h | Cannot point >5h before meridian transit | Too far EAST |
| **West limit** | HA > +3.75h | Cannot point >3.75h after meridian transit | Too far WEST |

#### Hour Angle Convention

```
HA = LST - RA (wrapped to ±12h)

Examples:
  LST = 18h, RA = 15h → HA = +3h (target west of meridian, setting)
  LST = 18h, RA = 21h → HA = -3h (target east of meridian, rising)
  LST = 1h, RA = 23h → HA = +2h (after midnight, target setting)
```

**Sign convention:**
- **Negative HA:** Target EAST of meridian (before transit, rising)
- **Positive HA:** Target WEST of meridian (after transit, setting)
- **HA = 0:** Target exactly on meridian (optimal airmass)

---

### 3. NO RA Limits

**IMPORTANT:** There are **NO static RA constraints**.

The observable RA range depends on:
1. Local Sidereal Time (LST)
2. Hour Angle limits
3. Time of year (which determines LST at twilight)

**Common misconception:**
- ❌ "Shane cannot observe RA < 5h"
- ✅ "Shane cannot observe targets with HA < -5h or HA > +3.75h at a given LST"

RA 0-5h targets are **perfectly observable** in August mornings when LST is in the right range.

---

## Observable RA Calculation

For a given LST, the observable RA window is:

```python
# HA = LST - RA
# Rearrange: RA = LST - HA

# For HA in [-5h, +3.75h]:
ra_min = LST - HA_MAX = LST - 3.75
ra_max = LST - HA_MIN = LST - (-5) = LST + 5

# Wrap to [0, 24h) range
ra_min = ra_min % 24
ra_max = ra_max % 24
```

### Examples

#### August 13, 2026 (Night Start)

**Evening twilight:** LST = 18.03h

```
ra_min = 18.03 - 3.75 = 14.28h
ra_max = 18.03 + 5 = 23.03h

Observable RAs: 14.28h – 23.03h
```

**Morning twilight:** LST = 1.11h

```
ra_min = 1.11 - 3.75 = -2.64h → 21.36h (wrapped)
ra_max = 1.11 + 5 = 6.11h

Observable RAs: 21.36h – 24h ∪ 0h – 6.11h (wraps around 0h)
```

**Combined night coverage:**
- Evening-accessible: RA ~14–23h
- Morning-accessible: RA ~0–8h + ~21–24h
- **Gap: RA ~8–14h** (always HA > +3.75h, too far west all night)

---

## Seasonal Observable RA Ranges

The observable RA window shifts **~2h per month** as Earth orbits the sun:

| Date | LST Eve | LST Morn | Observable RAs | Gap (unobservable) |
|------|---------|----------|----------------|--------------------|
| **Aug 13** | 18.03h | 1.11h | 14.3-23.0h, 23.7-8.4h | RA ~8-14h |
| **Sep 13** | 20.03h | 3.11h | 16.3-1.0h, 1.7-10.4h | RA ~10-16h |
| **Oct 13** | 22.03h | 5.11h | 18.3-3.0h, 3.7-12.4h | RA ~12-18h |
| **Nov 13** | 0.03h | 7.11h | 20.3-5.0h, 5.7-14.4h | RA ~14-20h |
| **Dec 13** | 2.03h | 9.11h | 22.3-7.0h, 7.7-16.4h | RA ~16-22h |
| **Jan 13** | 4.03h | 11.11h | 0.3-9.0h, 9.7-18.4h | RA ~18-24/0h |
| **Feb 13** | 6.03h | 13.11h | 2.3-11.0h, 11.7-20.4h | RA ~20-2h |
| **Mar 13** | 8.03h | 15.11h | 4.3-13.0h, 13.7-22.4h | RA ~22-4h |

**Key insight:** No single RA is observable year-round. August targets (RA 14-23h) are **unobservable** in February. February targets (RA 2-11h) are **unobservable** in August.

---

## Target Observability Determination

### Step 1: Calculate Hour Angle at Evening and Morning Twilight

For each target:

```python
# At evening twilight
ha_eve = lst_eve - ra_target
if ha_eve > 12: ha_eve -= 24
elif ha_eve < -12: ha_eve += 24

# At morning twilight
ha_morn = lst_morn - ra_target
if ha_morn > 12: ha_morn -= 24
elif ha_morn < -12: ha_morn += 24
```

### Step 2: Check Limits

Target is observable if **HA is in range at ANY point during the night**:

```python
# Sample every 15 minutes throughout night
for time in np.arange(eve_twilight, morn_twilight, 15*minutes):
    ha = lst(time) - ra
    if -5.0 <= ha <= 3.75:
        target_is_observable = True
        break
```

### Step 3: Reject Violations

**Rejected if:**
- Dec > +82°
- HA never enters [-5h, +3.75h] window during the night

**Example rejections (Aug 13, 2026):**

| Target | RA (h) | HA @ Eve | HA @ Morn | Reason |
|--------|--------|----------|-----------|--------|
| TGT0351 | 9.82 | +8.21h | +3.76h | Always > +3.75h (too far west) |
| TGT0423 | 12.09 | +5.94h | +1.53h | HA > +3.75h at evening, enters window too late |
| TGT0548 | 12.68 | +5.35h | +0.94h | HA > +3.75h at evening |

All RA 9-13h targets are rejected in August - they're "setting" targets that set before dark.

---

## When Targets Become Observable

A target at RA `r` becomes observable when:

```
HA = -5h (east limit)
LST = RA - 5

If LST < 0: LST += 24
```

**August 13, 2026 examples:**

| Target | RA | Observable from | LST |
|--------|----|----|-----|
| TGT0060 | 0.55h | 22:08 PST | 19.55h |
| TGT0506 | 1.62h | 23:12 PST | 20.62h |
| TGT0176 | 2.40h | 23:59 PST | 21.40h |
| TGT0252 | 5.25h | 02:50 PST | 0.25h |

All four become observable **during the night** as LST advances and they rise into the HA window.

---

## Common Mistakes (from Lick-2026B-01 Corrections)

### Mistake 1: Assuming "RA ≥ 5h" Limit

**WRONG:**
```python
if ra < 5.0:
    return False, "RA < 5h limit"
```

**CORRECT:**
There is NO RA limit. Targets at RA 0-5h are observable in the morning when LST is appropriate.

### Mistake 2: Only Checking West HA Limit

**WRONG:**
```python
if ha < -3.75:  # Only checking west side
    return False, "HA too far west"
```

**CORRECT:**
```python
if ha < -5.0:
    return False, "HA < -5h (too far east)"
if ha > 3.75:
    return False, "HA > +3.75h (too far west)"
```

Limits are **symmetric** - must check both east AND west.

### Mistake 3: Confusing HA Sign Convention

**WRONG:** "Negative HA means west of meridian"

**CORRECT:** Negative HA means **EAST** of meridian (before transit, rising)

```
HA = LST - RA

If target hasn't transited yet (still rising):
  RA > LST → HA < 0 → EAST of meridian

If target has transited (setting):
  RA < LST → HA > 0 → WEST of meridian
```

---

## Verification Tools

### 1. Lick Observatory Calendar

**URL:** https://www.ucolick.org/calendar/lickcal2021-30/

Provides authoritative twilight times and LST values for cross-checking calculations.

**Expected accuracy:**
- Twilight times: ±2-3 minutes
- LST: ±10-20 seconds

### 2. Observable RA Calculator

```bash
python scripts/observable_ra_calculator.py
```

Outputs:
- Observable RA ranges for a given date
- Year-round plot showing seasonal shifts

### 3. Deadtime Checker

```bash
python $NIGHT_PLANNER_PLANS/Lick-2026B-01/scripts/check_deadtime_lick_2026b01.py  # private
```

Analyzes timeline to identify gaps when no targets are observable.

---

## Implementation Reference

From `scripts/lick_2026b01_calculations.py`:

```python
def check_pointing_limits(ra, dec, ha):
    """
    Check if target violates Shane 3m pointing limits.

    Constraints:
    - Dec ≤ 82° (polar limit)
    - HA limits: -5h ≤ HA ≤ +3.75h

    Note: NO RA limits.
    """
    if dec > 82:
        return False, f"Dec {dec:.1f}° > 82° limit"

    if ha < -5.0:
        return False, f"HA {ha:.2f}h < -5h limit (too far east)"

    if ha > 3.75:
        return False, f"HA {ha:.2f}h > +3.75h limit (too far west)"

    return True, ""
```

---

## Summary

**Shane 3m has exactly TWO mechanical constraints:**

1. **Dec ≤ +82°** (polar limit)
2. **HA: -5h ≤ HA ≤ +3.75h** (symmetric limits)

**No RA limits exist.** Observable RAs shift ~2h/month with seasons.

**Always verify:**
- HA at both evening and morning twilight
- Check if target enters HA window at ANY point during night
- Cross-check against Lick calendar

**Key lesson:** Telescope mechanical limits are non-obvious. Always verify with observer and authoritative sources before assuming constraints.
