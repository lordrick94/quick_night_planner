# Documentation Index

**night-planner** - Automated night plan generation for professional telescopes

Created by JXP and Claude

---

## Quick Links

### General Documentation

- **[Install Guide](../INSTALL.md)** - Conda environment, environment variables, first run, troubleshooting
- **[Shane Telescope Constraints](Shane_telescope_constraints.md)** - Shane 3m pointing limits, HA ranges, observable RA windows
- **[Target CSV Guide](target_csv_guide.md)** - How to build a target table that loads cleanly and makes a good night: columns, units, magnitudes, priorities
- **[Testing Guide](Testing_guide.md)** - How to use the test suite and edge case datasets
- **[Priority System](priority_system.md)** - What the planner does with a priority column: the float contract, tiered scheduling, what outranks priority, and what it never touches
- **[Priority: night-planner vs AstroScheduler](priority_comparison_astroscheduler.md)** - Comparison with the UCSC AstroScheduler priority-sequential Branch and Bound solver

### Run-Specific Documentation

- **[Lick-2026B-01 HOWTO](Lick-2026B-01_HOWTO_night_plan_creation.md)** - Complete step-by-step guide for Aug 13-14, 2026 night plan
- **[Lick-2026B-01 Corrections](Lick-2026B-01_CORRECTIONS_SUMMARY.md)** - Critical corrections to HA limit understanding

### Testing

- **[Test Results Summary](../tests/test_data/TEST_RESULTS_SUMMARY.md)** - Edge case testing results, bugs found, deadtime analysis
- **[Test Data README](../tests/README.md)** - How to generate and run test cases

### Internal Context

- **[Claude's Brain](../context/claudes_brain.md)** - Persistent knowledge about night planning, telescopes, and repository
- **[Claude's Context](../context/claudes_context.md)** - Detailed telescope/instrument/facility information

---

## Repository Structure

```
night-planner/
├── docs/                          # General documentation (this directory)
├── context/                       # Claude's persistent memory
├── Night_plans/                   # Run-specific observing plans
│   └── Lick-2026B-01/            # Example: Aug 13-14, 2026
├── scripts/                       # Reusable calculation scripts
├── tests/                         # Test suite and edge cases
│   └── test_data/                # 17 synthetic FRB target sets
├── night_planner/                 # Python package
├── claude_prompts/               # Initial setup prompts
└── Logs/                         # Daily narrative logs
```

---

## Workflow Overview

### Creating a New Night Plan

1. **Generate Resource in FFFF-PZ:**
   ```bash
   # Edit JSON
   vim chime-ffff-pz/data/Observing/<name>/<name>.json

   # Upload to server
   chime_ffff_pz_add_furesource <json>

   # Pull targets
   chime_ffff_pz_targets <name>
   ```

2. **Run Calculations:**
   ```bash
   # Edit date and paths in script
   python scripts/lick_2026b01_calculations.py

   # Generates:
   # - target_analysis.csv (all targets)
   # - selected_targets_night1.csv (final selection)
   ```

3. **Build Night Plan:**
   ```bash
   python scripts/build_night_plan.py

   # Generates:
   # - Lick_2026B-01_Night_plan.xlsx
   ```

4. **Verify:**
   - Cross-check twilight times against [Lick calendar](https://www.ucolick.org/calendar/)
   - Check LST calculations (should match within 10-20 sec)
   - Verify HA limits for all selected targets

---

## Key Concepts

### Hour Angle (HA)

```
HA = LST - RA (wrapped to ±12h)

Negative HA: target EAST of meridian (before transit, rising)
Positive HA: target WEST of meridian (after transit, setting)
HA = 0: target on meridian (best airmass)
```

### Shane 3m Pointing Limits

1. **Dec ≤ +82°** (polar limit)
2. **HA: -5h ≤ HA ≤ +3.75h** (symmetric)
   - HA < -5h: too far EAST (>5h before transit)
   - HA > +3.75h: too far WEST (>3.75h after transit)
3. **NO RA limits** - observable RAs depend on LST and time of year

See [Shane_telescope_constraints.md](Shane_telescope_constraints.md) for details.

### Observable RA Windows (Seasonal)

HA limits create **time-dependent** observable RA ranges:

| Month | LST Evening | LST Morning | Observable RAs |
|-------|-------------|-------------|----------------|
| Aug   | 18.03h      | 1.11h       | 14.3-23.0h, 23.7-8.4h |
| Feb   | 4.87h       | 15.11h      | ~0h-10h |
| May   | 13.5h       | 22.5h       | ~8.5-18.5h |
| Nov   | 0.5h        | 9.5h        | ~19.5-5.5h |

Window shifts ~2h/month as Earth orbits sun.

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `lick_2026b01_calculations.py` | Ephemeris, twilight, airmass, target selection |
| `build_night_plan.py` | Generate Excel night plan from selected targets |
| `observable_ra_calculator.py` | Calculate observable RAs for any date, generate year plot |
| `check_target_csv.py` | Validate a target table and report airmass, exposure and total hours |
| `generate_test_frbs.py` | Generate 17 synthetic test cases |
| `run_all_tests.py` | Run observability analysis on all test cases |

---

## Important Lessons

### 1. Always Verify Telescope Limits with Observer

Initial implementation had **wrong constraints** (RA ≥ 5h, HA ≥ -3.75h west only). This led to selecting 4 targets that violated the real limits!

**Correct Shane 3m constraints:**
- Dec ≤ 82°
- **Symmetric HA limits:** -5h ≤ HA ≤ +3.75h
- **NO RA limits**

### 2. Timezone Convention Matters

Lick calendar uses **PST (UTC-8) year-round**, even in summer when local time is PDT (UTC-7). This affects LST calculations.

```python
PST = timezone(timedelta(hours=-8))  # Fixed offset
# NOT: pytz.timezone('America/Los_Angeles')  # DST-aware
```

### 3. Cross-Check Against Authoritative Sources

Verify twilight times and LST against [Lick calendar](https://www.ucolick.org/calendar/lickcal2021-30/):
- Twilight times: within 2-3 min
- LST: within 10-20 sec

### 4. HA Constraints Create Time-Dependent RA Windows

Targets aren't "observable" or "not" universally - they're observable at **specific LSTs**. RA 0-5h targets are morning-only in August, but unobservable in February.

---

## Getting Help

- Building a target list? Start with the [Target CSV Guide](target_csv_guide.md)
- Read the [Lick-2026B-01 HOWTO](Lick-2026B-01_HOWTO_night_plan_creation.md) for a complete worked example
- Check [Testing Guide](Testing_guide.md) for edge case scenarios
- Review [Shane constraints](Shane_telescope_constraints.md) for telescope limits
- Consult `context/claudes_brain.md` for accumulated knowledge
