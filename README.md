# night-planner

Automated night plan generation for professional telescope observations.

Created by J. Xavier Prochaska and Claude

---

## Overview

**night-planner** generates optimized observing schedules for CHIME/FRB host galaxy spectroscopy at Lick Observatory (Shane 3m + Kast spectrograph) and Keck (Keck I + LRIS: longslit, MOS, imaging). The system handles:

- **Ephemeris calculations** (twilight times, LST, airmass)
- **Telescope constraints** (Dec limits, hour angle limits)
- **Target selection** (observable window, magnitude-based priorities)
- **Timeline generation** (Excel night plans with slews, exposures, calibrations)
- **Seasonal RA windows** (time-dependent observability)

---

## Quick Start

### Generate a Night Plan

```bash
# 1. Create FFFF-PZ Resource and pull targets
chime_ffff_pz_add_furesource Night_plans/Lick-2026B-01/Lick-2026B-01.json
chime_ffff_pz_targets Lick-2026B-01

# 2. Calculate observability
python scripts/lick_2026b01_calculations.py

# 3. Build Excel night plan
python scripts/build_night_plan.py
```

Output: `Night_plans/Lick-2026B-01/Lick_2026B-01_Night_plan.xlsx`

### Keck/LRIS (example: Oct 6, 2026)

```bash
# 1. Point at global FFFF-PZ, create the Resource, pull targets
set_ffff_pz_global
chime_ffff_pz_add_furesource Keck-2026B-02.json   # adds OR modifies by name
chime_ffff_pz_targets Keck-2026B-02

# 2. Schedule (ETC exposures, Keck slews, masks), then build outputs
python scripts/keck_2026oct06_calculations.py
python scripts/build_keck_night_plan.py
```

Output: the run's directory under the private plans dir
(`$NIGHT_PLANNER_PLANS/Keck-2026B-02/`: xlsx, starlist). The per-run
rejection report script is kept privately with that run's plan. Keck rules: 5 min base slew, 14 min from Dec < +20 to Dec > +20, then acquisition (5 min longslit, 10 min mask)
(`scripts/keck_overheads.py`); MOS blocks 1-2 h + 5 min buffer, only for
masks in `MOS_MASKS_AVAILABLE`.

### Planning options (2026-11-07)

Both instruments (`night-planner calc --instrument lris|kast ...`, or the
Configuration card on the setup page) take:

| Flag | Default | What it does |
|---|---|---|
| `--grism --grating --dichroic --slit --binning` | the standard setup | instrument configuration; only values the UCO/Lick ETC can model are accepted |
| `--seeing` | LRIS 0.8", Kast 1.5" | FWHM fed to the ETC |
| `--mag-band` | `r` | band of the `mag` column (a per-row `mag_band` / FFFF-PZ `Pri_filter` wins) |
| `--etc` | LRIS `lris` (UCO ETC), Kast `empirical` | exposure model: `lris`, `kast`, `empirical`, or your own `package.module:function` |
| `--target-sn` | LRIS 10, Kast 10 | median continuum S/N per sub-exposure (>= 3 sub-exposures) |
| `--airmass-rule` | `worst` | airmass the ETC runs at over each target's scheduled block (`worst`, `mid`, `best`) |

What every plan now includes:
- **Time accounting.** Slew, acquisition, readout and on-target time are
  separate terms, and on target + slew + acquisition + readout + overheads +
  blocked + idle = the night. Keck: 5 min base slew, 14 min for a S→N Dec
  +20° crossing, acquisition 5 min longslit / 10 min mask, readout 80 s per
  frame at 2x2. Lick: 2 min slew + 3 min acquisition, readout 20 s per
  frame. The plan page's **Assumptions** panel lists the values used.
- **Target table columns.** `priority` (tiers, on both instruments),
  `t_target` (your own minutes on target) and `required` (full time or
  nothing). See [`docs/target_csv_guide.md`](docs/target_csv_guide.md).
- **Telescope limits.** Keck I can't track above 88.9° elevation (a short
  keyhole each target's block avoids), and blocks passing above 85° carry a
  guiding warning.
- **Scenarios.** Several plans for one night (e.g. seeing 0.6/0.8/1.2",
  "lost first half"), shown as tabs with a comparison table.
- **Observing log page.** Calibrations checklist, night checklist,
  conditions log and per-target outcomes, then a Markdown night report plus
  the FFFF-PZ CSV (`night-planner report --plan-dir ...`).

Calibrations are no longer scheduled. They are ticked off on the Observing
log page.

### Run Tests

```bash
# Unit/integration tests (offline: the UCO ETC is faked, sockets blocked)
conda run -n frb_env python -m pytest -q
# ...plus the one test that calls the real ETC
conda run -n frb_env python -m pytest -q --run-network

# Generate 17 edge case test datasets
python tests/test_data/generate_test_frbs.py

# Run full test suite
python tests/test_data/run_all_tests.py

# View results
cat tests/test_data/TEST_RESULTS_SUMMARY.md
```

---

## Documentation

### 📖 Getting Started

- **[Install Guide](INSTALL.md)** - Clone to generated night plan in five minutes
- **[Documentation Index](docs/README.md)** - Complete documentation overview
- **[Shane Telescope Constraints](docs/Shane_telescope_constraints.md)** - HA limits, observable RA windows
- **[Testing Guide](docs/Testing_guide.md)** - Edge case validation, bug reports

### 📝 Examples

- **[Lick-2026B-01 HOWTO](docs/Lick-2026B-01_HOWTO_night_plan_creation.md)** - Complete worked example (Aug 13-14, 2026; target names replaced by codes)
- **[Corrections Summary](docs/Lick-2026B-01_CORRECTIONS_SUMMARY.md)** - Critical HA limit corrections

### 🧪 Testing

- **[Test Results Summary](tests/test_data/TEST_RESULTS_SUMMARY.md)** - 17 edge cases, bugs found, deadtime analysis
- **[Test Suite README](tests/README.md)** - How to run tests

---

## Key Features

### ✅ Accurate Ephemeris

- 18° astronomical twilight calculations
- LST verified to 10-20 sec precision against Lick calendar
- PST (UTC-8) year-round convention
- Airmass tracking throughout night

### ✅ Shane 3m Constraints

**Correctly implements:**
1. **Dec ≤ +82°** (polar limit)
2. **HA: -5h ≤ HA ≤ +3.75h** (symmetric limits)
3. **NO RA limits** (observable RAs depend on LST and season)

**Key insight:** Observable RA window shifts ~2h/month as Earth orbits sun.

### ✅ Deadtime Analysis

Detects gaps when no targets are observable (the run-specific script is
kept privately in `$NIGHT_PLANNER_PLANS/Lick-2026B-01/scripts/`):
```bash
python $NIGHT_PLANNER_PLANS/Lick-2026B-01/scripts/check_deadtime_lick_2026b01.py
```

**Lick-2026B-01 result:** NO deadtime - targets flow continuously 20:30→04:12 PST.

### ✅ Comprehensive Testing

17 synthetic test cases covering:
- Seasonal variations (Aug, Feb, Mar)
- HA limit boundaries
- Zero/one observable targets
- Dense vs sparse fields
- Extreme declinations

**Status:** 9/17 passing, 8/17 exposing known bugs (documented for fixing)

---

## Repository Structure

```
night-planner/
├── docs/                          # 📖 Documentation
│   ├── README.md                 # Documentation index
│   ├── Shane_telescope_constraints.md
│   └── Testing_guide.md
├── pvt_Nighplans/                 # 🔒 Observing plans: PRIVATE, git-ignored
│                                  #    ($NIGHT_PLANNER_PLANS; real targets)
├── scripts/                       # 🔧 Calculation scripts
│   ├── lick_2026b01_calculations.py    # Ephemeris & target selection
│   ├── build_night_plan.py             # Excel generation
│   ├── observable_ra_calculator.py     # RA windows by date
│   ├── keck_2026oct06_calculations.py  # Keck/LRIS ephemeris & scheduling
│   ├── build_keck_night_plan.py        # Keck Excel generation
│   ├── keck_overheads.py               # Keck slew rule (all instruments)
│   └── lris_etc.py                     # Real LRIS ETC client
├── tests/                         # 🧪 Test suite
│   ├── README.md
│   └── test_data/
│       ├── generate_test_frbs.py       # Generate 17 test cases
│       ├── run_all_tests.py            # Run all tests
│       ├── TEST_RESULTS_SUMMARY.md     # Results analysis
│       ├── test_*.csv                  # 17 synthetic datasets
│       └── results/                    # Test outputs
├── context/                       # 🧠 Claude's memory
│   ├── claudes_brain.md          # Persistent knowledge
│   └── claudes_context.md        # Detailed reference
├── Logs/                          # 📔 Session logs
├── night_planner/                 # 📦 Python package
├── claude_prompts/               # Initial setup
└── README.md                      # This file
```

---

## Scripts

| Script | Purpose |
|--------|---------|
| `lick_2026b01_calculations.py` | Calculate ephemeris, apply constraints, select targets |
| `build_night_plan.py` | Generate Excel night plan with timeline |
| `observable_ra_calculator.py` | Show observable RAs for any date + year plot |
| `keck_2026oct06_calculations.py` | Keck/LRIS ephemeris, Nasmyth-deck limits, ETC exposures, scheduling |
| `build_keck_night_plan.py` | Keck Excel night plan |
| `keck_overheads.py` | Keck slew and acquisition times (5 min base slew, 14 min Dec<+20 -> Dec>+20; acquisition 5 min longslit, 10 min mask) |
| `lris_etc.py` | LRIS exposure times from the UCO/Lick ETC |
| `generate_test_frbs.py` | Create 17 synthetic edge case datasets |
| `run_all_tests.py` | Run observability on all test cases |

---

## Known Issues

### Bugs Found by Testing (8 edge cases)

**Status:** Documented, awaiting fixes

1. **NoneType comparison** when targets never observable (6 tests)
   - Targets never enter HA window → `min_am_time = None` → sorting crashes
   - **Fix:** Set sentinel value or filter None before sorting

2. **Empty DataFrame** when all targets rejected (2 tests)
   - All Dec > 82° → empty result → code continues → KeyError
   - **Fix:** Early return when zero targets pass filters

See [`tests/test_data/TEST_RESULTS_SUMMARY.md`](tests/test_data/TEST_RESULTS_SUMMARY.md) for details.

---

## Important Lessons

### 1. Always Verify Telescope Limits

Initial implementation had **wrong constraints** (RA ≥ 5h, HA ≥ -3.75h west only). This led to selecting 4 targets that violated real limits!

**Correct Shane limits:**
- Dec ≤ 82°
- **Symmetric HA:** -5h ≤ HA ≤ +3.75h
- **NO RA limits**

### 2. Timezone Matters

Lick calendar uses **PST (UTC-8) year-round**, not DST-aware PDT. This affects LST calculations.

```python
PST = timezone(timedelta(hours=-8))  # Fixed offset ✓
# NOT: pytz.timezone('America/Los_Angeles')  # DST-aware ✗
```

### 3. Cross-Check Authoritative Sources

Verify against [Lick calendar](https://www.ucolick.org/calendar/lickcal2021-30/):
- Twilight times: ±2-3 min
- LST: ±10-20 sec

---

## Example: Lick-2026B-01 (Aug 13-14, 2026)

**Night:** Aug 13-14, 2026 (7.1h dark)
**Targets:** 6 CHIME/FRB hosts (2 evening RA 15-16h, 4 morning RA 0-5h)
**Timeline:** 20:30→04:12 PST (NO deadtime)
**Total observing:** 420 min (7.0h science + 0.7h overhead)

### Selected Targets

| Target | RA (h) | r-mag | Exposure | Window |
|--------|--------|-------|----------|--------|
| TGT0172 | 15.74 | 18.44 | 80 min | Evening |
| TGT0059 | 15.45 | 16.87 | 60 min | Evening |
| TGT0060 | 0.55 | 15.98 | 60 min | Morning |
| TGT0506 | 1.62 | 18.57 | 80 min | Morning |
| TGT0176 | 2.40 | 17.99 | 80 min | Morning |
| TGT0252 | 5.25 | 16.27 | 60 min | Morning |

**Rejected:** 6 targets at RA 9-13h (always HA > +3.75h, too far west)

See [`docs/Lick-2026B-01_HOWTO_night_plan_creation.md`](docs/Lick-2026B-01_HOWTO_night_plan_creation.md) for complete step-by-step guide.

---

## Installation

Full walkthrough, including troubleshooting:
**[INSTALL.md](INSTALL.md)**.

```bash
git clone https://github.com/profxj/night-planner.git
cd night-planner

# Conda (recommended -- the astro stack builds cleanly here)
conda env create -f environment.yml
conda activate night-planner
pip install -e .

# Or pip only
pip install -e ".[gui,dev]"
```

Check the install on a machine that has never seen this repo:

```bash
pytest
python scripts/check_portability.py   # no machine-specific paths
night-planner --help
```

**Dependencies:** numpy, pandas, astropy, astroplan, matplotlib, openpyxl,
pyyaml, pytz, requests, certifi. Extras: `[gui]` for the viewer (FastAPI,
uvicorn), `[finders]` for finder charts (astroquery, photutils), `[dev]` for
pytest/black/flake8.

### Environment variables

Nothing inside the repo needs configuring: the repo root and
`scripts/` are all worked out from the code's own location, so a fresh clone
runs wherever you put it. Only paths *outside* the checkout need telling.

| Variable | Needed for | Default |
|----------|-----------|---------|
| `FFFF_PZ_REPO` | The `chime-ffff-pz` checkout: standard-star library, finder charts, Observing data | A sibling directory next to this repo |
| `NIGHT_PLANNER_PLANS` | The private plans directory — real targets, never committed | `<repo>/pvt_Nighplans` (git-ignored) |
| `LICK_NIGHT_PLAN_TEMPLATE` | `make_lick_night_plan.py` only — the template .xlsx it copies its checklist sheet from | None; the builder asks for it |
| `FFFF_PZ_URL` / `FFFF_PZ_USER` / `FFFF_PZ_PASS` | Talking to the FFFF-PZ server | None |

If you keep the two repos side by side, nothing above needs setting:

```
Projects/
├── night-planner/
└── chime-ffff-pz/
```

Otherwise:

```bash
export FFFF_PZ_REPO=/path/to/chime-ffff-pz
```

Every one of these fails with a message naming the variable to set, rather
than a missing-file error from somewhere deep in a data read. See
[`night_planner/paths.py`](night_planner/paths.py).

---

## Development

### Adding a New Observatory

1. Update coordinates in calculation script
2. Update HA limits (telescope-specific)
3. Verify timezone convention
4. Cross-check against observatory calendar
5. Generate test cases for new site

### Adding a New Instrument

1. Update exposure time scaling rules
2. Add instrument setup notes
3. Update Excel template structure
4. Document in HOWTO

---

## References

- **Lick Observatory Calendar:** https://www.ucolick.org/calendar/
- **CHIME/FRB FFFF-PZ:** https://frb.chimenet.ca/f4pz/
- **Astropy Documentation:** https://docs.astropy.org/

---

## License

BSD-3-Clause

## Authors

- J. Xavier Prochaska (jxp@ucsc.edu)
- Claude (Anthropic)

---

## Getting Help

1. Read [`docs/README.md`](docs/README.md) for documentation index
2. Check [`docs/Lick-2026B-01_HOWTO_night_plan_creation.md`](docs/Lick-2026B-01_HOWTO_night_plan_creation.md) for worked example
3. Review [`tests/test_data/TEST_RESULTS_SUMMARY.md`](tests/test_data/TEST_RESULTS_SUMMARY.md) for edge cases
4. Consult [`context/claudes_brain.md`](context/claudes_brain.md) for accumulated knowledge
