# Implementation plan — user-feedback goals T1–T4

## Before we start
Read and follow all Claude rules in this repo (`CLAUDE.md`, `Logs/logging.md`,
`context/claudes_brain.md`). Goal IDs (T1.1 …) refer to
[`users_comments.md`](users_comments.md); the "done when" tests live there and
are not repeated here.

**Scope:** Tiers 1–4, approved 2026-11-07. Tiers 5–6 (live night mode,
research) are out of scope. The **observing log page, with the calibrations
checklist built in** (T3.7 + T4.2), is pulled forward to **Milestone 1**, to
try first.

## Ground rules for every milestone
- **One source of truth per number.** Keck slew and acquisition stay in
  `scripts/keck_overheads.py`. Everything else instrument-specific (readout,
  default configuration, ETC-supported options, calibration rules, rotator
  limits) goes in one new module, `night_planner/instrument_params.py`.
  It holds plain dicts and functions, no classes.
- **Never invent an instrument number.** A value that isn't in hand stays
  `None`. The plan then shows it as **NOT SET** in the assumptions panel
  (T2.8) rather than silently using 0. Every value carries a source comment.
  See [Data needed](#data-needed-before-or-during-the-work).
- **Old plans must still load.** Every new `ScheduledTarget` / `PlanResult`
  field gets a default, so a `plan_result.json` written before the change
  still loads (`tests/test_plan_result.py` already guards this for
  `priority`; extend it per field).
- **Both instruments, or say why not.** Each step names what it does on the
  LRIS path (`scripts/keck_2026oct06_calculations.py` → `adapters.keck_lris`)
  and the Kast path (`scripts/kast_calculations.py` → `adapters.lick_kast`).
  The two schedulers are different code. A change to one is not a change to
  both.
- **Tests never hit the network.** ETC calls are monkeypatched with a
  deterministic stand-in (S/N ∝ √t, degraded with airmass and seeing). One
  marked `@pytest.mark.network` test may call the real ETC.
- **New flags go everywhere they're needed.** Each one is added to the
  instrument's `parse_args`, `INSTRUMENTS[...]['supports']`
  (`night_planner/cli.py`), `GenerateRequest` and its argv builder
  (`backend/app.py`), and `NightPlanConfig` (`scripts/night_plan_io.py`).
- The LRIS scheduler lives in `keck_2026oct06_calculations.py`, named for one
  run but wired in as *the* LRIS calc module. Edits there change every LRIS
  plan. Record each change in that module's docstring.
- After each milestone: run `pytest`, update `context/claudes_brain.md`
  (version entry) and the daily log. JXP commits.

---

## Milestone 1 — calibrations out of the timeline; observing log page with the calibrations checklist (T1.5, T3.7, T4.2)

### 1a. Remove scheduled calibrations (T1.5)
| File | Change |
|---|---|
| `night_planner/adapters.py:176` `_keck_overheads` | Drop `('Arc lamps', 10)` and `('Internal flats', 10)`. Keep the evening standard, focus, slew to Feige 110, and morning standard. Update the docstring. |
| `scripts/keck_2026oct06_calculations.py:939` | `available_time = dark_hours*60 - 30  # Reserve 30 min for calibrations` → reserve only the closing slew + morning standard. That is `keck_slew_minutes(…, MORNING_STANDARD_DEC) + 5`, i.e. 10 min after M2: the slew to Feige 110 (Dec −5°) is never a S→N crossing. Name the constant. |
| `scripts/keck_2026oct06_calculations.py:1202` `print_night_plan` | Replace the "Calibrations (arcs, flats) – 20 min" line with "Calibrations: see the observing log". |
| `scripts/build_keck_night_plan.py:74-75, 307-309` | Remove the arc/flat rows from the Excel plan; add a one-line pointer to the observing log. |
| `night_planner/plan_result.py` (`idle_gaps`, `overruns` docstrings) | Stop saying calibrations are part of the plan. |
| Kast path | Nothing to remove: `lick_kast` emits no calibration blocks. Check `make_lick_night_plan.py` (Excel) for calibration rows and remove them for consistency. |

**Test:** extend `tests/test_backend.py` / `test_plan_result.py`. A generated
LRIS plan has no overhead labelled arc/flat/bias. Its usable science time is
20 min longer than before (net of the 30 → 10 reserve change, so ≈40 min
more budget).

### 1b. Observing log page, with the calibrations checklist built in (T3.7 + T4.2)

One page, **Observing log** (`#/log?dir=`), replaces the separate
calibrations page and observer's log (merged per Lordrick, 2026-11-07). It
has one storage file and one merge rule, and the `.md` observing report is
generated from it. It needs only a saved plan, so it lands with 1a. Later
milestones add columns to the plan (acq, readout, S/N), and the log picks
them up without changes.

#### What the page holds, top to bottom

**1. Night header** (pre-filled where the plan knows the value):

| Field | Pre-fill | Notes |
|---|---|---|
| Telescope, instrument, date, configuration | from `PlanResult` (+ `assumptions` once M7 lands) | read-only |
| Observers, support astronomer / telescope operator | — | free text |
| Dome open / close (local + UT) | planned night start/end | editable; feeds the time accounting |
| Time lost: weather, technical, other (min + reason) | 0 | several rows allowed |
| Night summary conditions | — | sky (clear / thin cirrus / patchy / thick / closed), seeing range ″, humidity/wind notes |
| General notes | — | free text |

**2. Calibrations checklist** (T3.7). Generated from
`instrument_params.CALIBRATION_RULES` and the plan:
- **Lick/Kast:** biases, flats and arcs **per configuration** (usually one).
- **Keck/LRIS:** flats and arcs **per configuration and per slitmask**.
  Masks = scheduled targets whose `mode` starts with `MOS`; the mask name is
  the target name (as in `MOS_MASKS_AVAILABLE`).
- Each item: ☐ taken · UT taken · **frame numbers** (suggested: PypeIt needs
  the calibration file ranges as much as the science ones) · note. Items are
  grouped by configuration, then by mask.

**3. Night checklist** (suggested; short, fixed, per instrument in
`instrument_params.NIGHT_CHECKLIST`):
- Start of night: focus, evening standard.
- End of night: morning standard, data copied off the instrument machine,
  log reviewed, report generated.
- Calibrations are *not* repeated here; section 2 covers them. A one-line
  status ("4 / 6 calibrations taken") sits beside this checklist.

**4. Conditions log** (suggested): timestamped rows of
`UT time · sky · seeing ″ · note`, with a "now" button that stamps the
current UT. Conditions change through the night, so one per-night value
loses information and one per target duplicates it. A target row shows the
entry in force when it started, and can override it.

**5. Target table.** One row per scheduled target, in plan order, plus one
row each for the evening and morning standards:

| Column | Pre-fill | Input |
|---|---|---|
| Target, mode, planned start–end, planned exposure | plan | read-only |
| **Status** | `pending` | `observed` · `partial` · `not observed` · `skipped`; needed for the report |
| Reason (when not observed / skipped / partial) | — | dropdown: weather, ran out of time, technical, target not acquired, lower priority / bumped, other; + text |
| Actual start (UT) | — | time field with a "now" button |
| Exposures taken, per arm | planned recipe | `n × s`, editable; total integration computed |
| Frame numbers / file range | — | e.g. `r251006_0045–0047` |
| Airmass at start | computed from the actual start (`calculate_airmass`) | read-only |
| Slit PA used | planned PA (finder/parallactic) | editable |
| Conditions (sky, seeing ″) | the conditions-log entry in force | overridable |
| Quick checks | — | ☐ acquired ☐ on slit / mask aligned ☐ exposures complete ☐ quick-look OK |
| Data quality | — | good / usable / poor |
| Redshift / success | blank | FFFF-PZ `success` (yes / no / unknown), and an optional z |
| Comments | — | free text |

- **Unplanned targets** (suggested): an "add target" row that picks from the
  plan's rejected targets (coordinates and magnitude come along) or takes a
  free name. The FFFF-PZ CSV needs these too (the script's `--extra` today).
- **Time accounting strip** above the table: planned on-target vs
  integrated, and time lost by cause. These are computed, never typed.

**6. Generate report** button: writes the `.md` report and the FFFF-PZ CSV,
then shows any warnings and links to both files.

#### Configuration and rules (`night_planner/instrument_params.py`, new)
Seeded here and grown in later milestones:
- `DEFAULT_CONFIG = {'lris': {...}, 'kast': {...}}`. LRIS values come from
  `scripts/lris_etc.py` (`B600`, `600/7500`, `D560`, 1.0″, `2x2`). Kast
  values come from `estimate_kast_exposures.py` (d57, 600/7500, 600/4310,
  2″).
- `config_label(instrument, config) -> str`, e.g.
  `"B600 / R600/7500 / D560 / 1.0″ / 2x2"`.
- `CALIBRATION_RULES = {'kast': {'per_config': ['bias', 'flat', 'arc'], 'per_mask': []}, 'lris': {'per_config': ['flat', 'arc'], 'per_mask': ['flat', 'arc']}}`
  (per Lordrick, 2026-11-07). Editing this dict is the only change needed to
  add e.g. LRIS biases later.
- `NIGHT_CHECKLIST = {'lris': [...], 'kast': [...]}`.

#### Storage and merge (`night_planner/observing_log.py`, new; functions only)
- **One file:** `observing_log.json` in the plan directory, with keys
  `night`, `calibrations`, `night_checklist`, `conditions`, `targets`,
  `unplanned`. The `/api/export` zip picks it up with no change.
- `calibration_items(plan, configs) -> list[dict]`: one item per
  (calibration × config) and per (calibration × mask). The stable id is
  `f"{kind}:{scope}:{scope_name}"`. `configs` = `[DEFAULT_CONFIG[instrument]]`
  until M4 makes the configuration an input. It already takes a list, so
  multi-config nights need no change later.
- `new_log(plan, configs) -> dict`, `load_log(output_dir)`,
  `save_log(output_dir, log)`.
- `merge_log(log, plan, configs)`: **one** merge rule for target rows and
  calibration items, keyed by target name / item id, for a plan regenerated
  mid-run.
  - Anything with user input is kept. A target or mask that left the plan is
    marked `not_in_plan: True` (a calibration already taken is never lost).
  - New targets / masks get fresh `pending` / unticked entries.
- Every edited value records `updated_ut` and `source` (`manual` | `auto`)
  from day one. That way T5.1's start/finish buttons and T5.6's frame watcher
  can write into this same file later, without a second log.
- Times are stored in UT and shown in UT and local, matching the rest of the
  interface.

#### Backend and frontend
- **API** (`backend/app.py`):
  - `GET /api/log?output_dir=` returns the log, created and merged on demand.
  - `PATCH /api/log` with `{output_dir, path, value}` sets one field, e.g.
    `targets.TGT0590.status` or `calibrations.arc:mask:TGT0461.done`.
    Small writes, safe to autosave on blur.
  - `POST /api/log/report` returns `{markdown_path, csv_path, warnings}`.
  - Use `_safe_dir` / `_require_plan` like the other routes.
- **Frontend:**
  - `tpl-log` template and `renderLog()`, a nav entry "Observing log", route
    `#/log?dir=`.
  - Sections 1–6 as above. Sections 2–4 are collapsible, so the target
    table is reachable during the night.
  - Rows are coloured by status; pending rows are highlighted near the end
    of the night.
  - Usable on a laptop at the telescope: large inputs, no hover-only
    controls. Suggested follow-up: a dim night mode for the whole app (the
    current palette is light, `--bg: #f6f8fb`).

#### The Markdown report (`night_planner/observing_report.py`, new)
`render_markdown(plan, log) -> str`, written to
`<plan>/observing_report_<YYYY-MM-DD>.md`. Sections:

1. **Header:** telescope · instrument · date (local night of / UT), observers,
   configuration, plan directory.
2. **Summary:** targets observed / partial / not observed (counts), total
   integration vs planned, time lost by cause, night conditions.
3. **Conditions log:** the timestamped table.
4. **Observed targets:** target, mode, UT start, exposures, total s, airmass,
   PA, sky/seeing, quality, frames, success/z.
5. **Not observed / partial:** target, status, reason, comment.
6. **Unplanned targets.**
7. **Standards and calibrations:** standards rows; calibrations per config
   and per mask (taken or not taken, UT, frames).
8. **Night checklist** and **notes**.
9. **Footer:** generated-by line, and the plan/log file names, so the report
   can be traced back.

- **Warnings, not silent gaps:** list any `pending` rows, observed rows with
  no exposures or frame numbers, and untaken calibrations, at the top of the
  report and in the API response. The report is still generated.
- **FFFF-PZ CSV from the same data:** refactor
  `scripts/make_observing_report.py`. Move the row logic into
  `observing_report.build_ffffpz_rows(plan, log, survey, resource)`, and
  `exposure_seconds` with it, preferring the log's actual exposures over the
  plan's. The script's `--conditions/--drop/--failed/--extra` flags become a
  minimal log passed through the same function, so CLI and page share one
  path.
- **CLI:** `night-planner report --plan-dir …` writes both files from a saved
  log; add it to `night_planner/cli.py`.

#### Tests (`tests/test_observing_log.py`)
- **Calibrations:**
  - LRIS, one config + two MOS targets → 6 calibration items (2 config +
    2×2 mask).
  - Kast, one config → 3 items.
- `new_log` gives one `pending` row per scheduled target + 2 standards.
- A field set via `PATCH` (target and calibration) survives `load_log`.
- `merge_log` after a regenerate that drops a MOS target keeps its filled row
  *and* its ticked calibration items as `not_in_plan`, and adds new ones.
- `render_markdown` on a fixture log with one observed, one partial and one
  not-observed row:
  - puts each in the right section
  - lists calibrations taken / not taken
  - warns about a pending row
  - is deterministic (no timestamps except the stored ones)
- The export zip contains `observing_log.json`.
- **Regression:** the refactored CLI reproduces
  `Night_plans/Keck-2026B-02/Keck-2026B-02_report.csv` byte-for-byte from the
  committed `plan_result.json` and the flags used for it.


---

## Milestone 2 — Keck overhead model and units (T1.2, T1.4)

### 2a. Slew and acquisition (T1.2)
- **`scripts/keck_overheads.py`:**
  - `KECK_SLEW_BASE_MIN = 5` (was 10) and `KECK_SLEW_DEC_CROSS_MIN = 14`
    (was 20).
  - New `KECK_ACQ_MIN = {'longslit': 5, 'mask': 10}` and
    `keck_acquisition_minutes(mode)`. Any `mode` starting with `MOS` counts as
    a mask.
  - Add a dated history note to the docstring (decided 2026-11-07, Q1).
- **`select_targets_for_night`:**
  - Block length becomes `slew_min + acq_min + on_target_min`.
  - `science_start = obs_start + slew + acq`.
  - Store `acq_min` in the row dict.
  - The skip-reason strings name all three terms.
- **Q7 (answered 2026-11-07, Lordrick: "don't drop the extra 5 min for
  masks"):** `MOS_MASK_BUFFER_MIN` stays at 5 and `estimate_mos_exposure` is
  unchanged. A mask target therefore costs slew + 10 min acquisition + the
  60/90/120 min block + 5 min buffer. Say so in the `keck_overheads.py`
  docstring, the assumptions panel (T2.8) and the brain file, so the
  buffer isn't later mistaken for a double count and removed.
- **Schema:** `ScheduledTarget.acq_min: float = 0.0`. `PlanResult.summary()`
  gains `acq_min`.
- **Lick slew and acquisition (Q8, answered 2026-11-07 by Lordrick; revised
  the same day to "slew time 2 min and acquisition 3 for a total of 5"):**
  - `instrument_params.py`: `LICK_SLEW_MIN = 2`, `LICK_ACQ_MIN = 3`, each
    with that source comment. **The total stays 5 min**, so Kast schedules
    don't move. Only the labelling changes: 5 min of "slew" becomes 2 min
    slew + 3 min acq.
  - The 5 min value is defined three times today
    (`lick_2026b02_calculations.py:70`, `lick_2026b02_extras.py:53`,
    `lick_2026b02_night2_calculations.py:56`). The run-specific scripts keep
    their constant. The general path takes its value from
    `instrument_params.py`, so the number has one owner from now on:
    - `kast_calculations.py` (imports `SLEW_MINUTES` at line 29, uses it in
      `forced` reservations and `free_gaps`) uses
      `LICK_SLEW_MIN + LICK_ACQ_MIN` as the gap between targets.
    - `schedule_greedy` (night-2 module, lines 213 and 248) hard-codes the
      module's own `SLEW_MINUTES`. It gains a `slew_min=SLEW_MINUTES`
      keyword, and `kast_calculations` passes the sum. The value is
      unchanged today, but the keyword stops the two from drifting apart.
    - `adapters._attribute_kast_slews` imports `SLEW_MINUTES` from the
      night-2 module and only recognises a gap of exactly that length. It
      must read the same sum, then split the gap into `slew_min = 2` and
      `acq_min = 3`. If the sum and the gap ever differ, every Kast slew
      turns back into idle time.
  - Test: a two-target Kast plan has a 5 min gap, with 2 min slew and 3 min
    acq, and its totals reconcile.
- **Kast totals:** `lick_kast` emits no overheads, so Kast's 20 min of focus
  + evening standard (`FOCUS_MINUTES`, `STD_STAR_MINUTES` in
  `kast_calculations.py`) shows as **idle** today. Emit them as overhead
  blocks in `lick_kast` so the T1.2 totals check
  (on target + slew + acq + readout + overheads + idle = night) holds on both
  paths.
- **Timeline (`frontend/app.js` ~531–540):** draw an `acq` segment between
  slew and science; add the legend entry; add a `--acq` colour in
  `style.css` (picked in M7, T2.1).
- **Tests:**
  - `keck_slew_minutes(10, 30) == 14`, `keck_slew_minutes(30, 10) == 5`.
  - `keck_acquisition_minutes('MOS (mask required)') == 10`.
  - A two-target LRIS plan reconciles to the minute.
  - Update `scripts/check_test_tables.py` / `tests/test_data` expectations
    that hard-code the old 10/20 values (grep for them).

### 2b. Units and the Dec-crossing explanation (T1.4)
- **Plan table header** (`frontend/app.js:645`): `slew [min]`, `acq [min]`,
  `on target [min]`, `exposure [n × s]`. Check every other numeric field
  (`targetDetail`, summary tiles, rejections table, night chart hover) for
  missing units.
- **Hover text:** where `slew_min > KECK_SLEW_BASE_MIN`, the tooltip reads
  "Dec +20° crossing (S→N): 14 min". The backend sets
  `ScheduledTarget.slew_reason` so the frontend never duplicates the rule.

---

## Milestone 3 — readout time (T1.1)

- **`instrument_params.py`:** `READOUT_S`, per frame, in seconds:
  - LRIS, our default 2x2: `{'blue': 80, 'red': 40}`. Source: Lordrick,
    2026-11-07, observer experience. The Keck web table (Data needed) stays
    as a comment, for the other binnings and for comparison. Keck's 2x2 red
    value is 39 s; blue 2x2 isn't published.
  - LRIS, other binnings: `None` (NOT SET) until someone needs them; don't
    scale from 2x2.
  - Kast, slow mode (always used): **20 s per frame** (Lordrick,
    2026-11-07: "normally on Kast read out is 20s on the blue side").
    Kast's web page gives 20 s for the *red* side's slow sub-region and
    7 s for blue (full frame 43/34 s). Either way the per-frame cost is
    20 s. Store `{'blue': 20, 'red': 20}` with both sources.
- `readout_seconds(instrument, config) -> float | None` returns the slower
  arm, since the arms read out in parallel: **LRIS 80 s, Kast 20 s.** If
  either arm is `None` it returns `None` (NOT SET), not the known arm.
- **LRIS:** in `select_targets_for_night`,
  `on_target_min = science_min + n_sub × readout / 60`. Parse `n_sub` from the
  exposure dict (`estimate_lris_exposure_real` already knows it; return
  `n_sub` and `sub_len_s` as numbers instead of making callers parse
  `"3 x 600"`).
- **MOS:** the 60/90/120 min block is an operational allocation, not exposure
  arithmetic. Leave readout out of it unless JXP says otherwise, and note
  this in the assumptions panel.
- **Kast:** add readout per sub-frame in `schedule_greedy`
  (`scripts/lick_2026b02_night2_calculations.py:187, 217`), using
  `estimate_exposure`'s frame counts.
- **Schema:** `ScheduledTarget.readout_min: float = 0.0`, a summary total, and
  a plan-table column.
- **Missing values:** `readout_seconds` returns `None` → charge 0 and add
  `readout: NOT SET` to `plan.assumptions` (M7). Never fall back silently.
- **Tests:** with a monkeypatched `READOUT_S`, a 3×600 s target costs
  `30 + 3×readout/60` min; with `None`, the plan's assumptions flag it.

---

## Milestone 4 — configuration, seeing and band as inputs (T3.1, T3.2, T3.5)

These three are the inputs the ETC and the observing log's calibrations read, so
they land together.

- **`instrument_params.py`:**
  - `ETC_OPTIONS`: what the ETC can model. LRIS blue grism ∈ {B300, B600}
    only (others return empty arrays; brain file, 2026-09-10). Red grating ∈
    {600/7500, 600/10000, 1200/9000, 400/8500, 831/8200}. Dichroic ∈
    {D560, D460, D500, D680} (the form, 2026-11-07). Slit ∈ {0.7, 1.0, 1.5}.
    Kast: grism ∈ {G2, G3}, grating ∈ {600/7500}, dichroic ∈ {d55, d46},
    slit ∈ {1.0, 1.5, 2.0}. The form also lists B400 and B1200, but the
    brain file (2026-09-10) says they return empty arrays. Keep them out
    until re-tested.
  - `validate_config(instrument, config)` raises a readable error for a
    combination the ETC can't model.
- **Flags** (both instruments): `--grism`, `--grating`, `--dichroic`,
  `--slit`, `--binning`, `--seeing` (default 0.8), `--mag-band` (default `r`).
  Each run's `out` dict returns the resolved `config`, `seeing`, `mag_band`.
- **LRIS ETC plumbing:**
  - `estimate_lris_exposure(_real)` takes `config`, `seeing` and `band`
    instead of the module defaults.
  - `query_lris_etc` already has `ffilter` (default `sdss_r.dat`). Map band →
    ETC filter file in `instrument_params.ETC_FILTERS` (from the form,
    2026-11-07): `u/g/r/i/z → sdss_*.dat`, `B/V → Buser_*.dat`,
    `R/I → Cousins_*.dat` (uppercase R/I are Cousins, lowercase are SDSS).
- **Per-target band:** add an optional `mag_band` column in
  `night_planner/targets_io.py` (`OPTIONAL_FIELDS`, aliases such as `band`,
  `filter`). The row value beats the plan-wide `--mag-band`.
- **Kast:** the empirical rule has no seeing or band dependence. Kast accepts
  the flags, reports them as "not used by the Kast exposure model" in the
  assumptions, and starts using them once it has a real ETC (M5).
- **Frontend:** a new "Configuration" card at the top of Targets and
  constraints. It has dropdowns limited to `ETC_OPTIONS` (served by a new
  `GET /api/instruments/{name}/options`), a seeing field, a band dropdown,
  and (from M5) the airmass rule. It defaults to `DEFAULT_CONFIG`. The
  regenerate path (`/api/regenerate`) carries these through `plan.request`.
- **Calibrations:** `observing_log.calibration_items` now receives the real config.
- **Tests:** an unsupported grism → 400 with a readable message. Seeing 1.2″
  gives a longer monkeypatched exposure than 0.6″. A table with
  `mag_band=g` on one row passes `sdss_g…` to the ETC stub for that row only.

---

## Milestone 5 — ETC at the scheduled airmass, S/N diagnostics, pluggable ETC (T1.3, T3.4)

### 5a. ETC interface (T3.4b) — first, since 5b and Kast build on it
- **New `night_planner/etc.py`.** The signature, for every ETC:
  `etc(mag, band, airmass, seeing, config, target_sn, n_sub_min) -> {'sub_len_s', 'n_sub', 'sn_sub': {'blue', 'red'}, 'wave', 's2n'}`.
  - `lris_etc` wraps `scripts/lris_etc.py`.
  - `ETC_REGISTRY = {'lris': lris_etc}`.
  - `load_etc(spec)` loads a user function from `"package.module:function"`.
  - New flag `--etc` (default: the registry entry).
  - Sunil asked for an "ETC class". **Decided 2026-11-07 (Lordrick): use the
    function shape for now.** A class can wrap it later without changing
    callers.
- **Cache:** `functools.lru_cache` keyed on
  `(mag, band, round(airmass, 2), seeing, frozen config, target_sn)`. 5b
  calls the ETC per placement iteration, and each call is a network round
  trip.

### 5b. Airmass rule (T1.3)
- **`--airmass-rule {worst, mid, best}`**, default `worst` (Q4).
- **New helper** `block_airmass(ra, dec, t0, t1, rule, location, step_min=5)`
  in `night_planner/sky.py`. It samples `calculate_airmass` over
  `[science_start, end]`.
- **LRIS loop** (`select_targets_for_night`): after `fit_around_blocks`
  places a target:
  1. Compute the rule airmass over its science span.
  2. Re-call the ETC.
  3. If `science_min` grew by more than 0.5 min, re-place it and repeat (at
     most 3 rounds; worst-case airmass only grows with block length, so this
     converges).
  4. If it no longer fits its window, skip it with a reason naming both
     airmasses.
- **Schema:** `ScheduledTarget.airmass` becomes the rule airmass actually used
  (today it is `min_airmass`). Add `airmass_min` and `airmass_rule`.
- **Kast:** needs 5c first; until then the assumptions say "Kast: airmass not
  used".

### 5c. Kast real ETC
- **Spike: done 2026-11-07.** The field names and options are in the ETC
  table under [Data needed](#data-needed-before-or-during-the-work), and one
  probe returned LRIS-shaped JSON. `kast_etc` sends `inst=kast`,
  `grism=G2`, `grating=600/7500`, `slitwidth=2.0`.
  - **Dichroic: d55** (decided 2026-11-07, Lordrick). Our d57 isn't offered;
    the assumptions panel says "ETC run with d55 (setup: d57)".
  - Pick continuum S/N windows inside 3150–8000 Å, the ETC's Kast grid.
  - Then add `kast_etc` to the registry and switch `kast_calculations` from
    `estimate_exposure` to the registry.
- **Kast S/N target: S/N = 5 for now** (decided 2026-11-07, Lordrick, "we
  can change later"). It is per sub-exposure, with ≥ 3 sub-exposures, the same
  convention as LRIS. It lives in `instrument_params.py` as
  `TARGET_SN = {'lris': 10, 'kast': 5}`, and a `--target-sn` flag overrides it
  per plan. The assumptions panel (T2.8) shows the value used.
- The empirical rule was calibrated on past nights, so switching to the
  ETC changes every Kast plan. Before switching the default, put
  before/after exposure numbers (`scripts/compare_exposure_models.py`-style)
  in the log so the change is visible. Keep `--etc empirical` as a way back.

### 5d. S/N diagnostics (T3.4a)
- Per target, store `sn_sub` (blue/red) and `sn_combined = √n_sub × sn_sub`.
  This is exact for n identical independent frames, read noise included per
  frame.
- Write the S/N(λ) arrays, downsampled to ~200 points, to
  `<plan>/etc/<target>.json`.
- `GET /api/etc?output_dir=&target=` serves them.
- The target detail panel shows a small Plotly S/N(λ) plot with the
  `target_sn` line and the two continuum windows shaded.

- **Tests:**
  - With a stub ETC whose time grows with airmass, a target placed late
    (higher airmass) gets a longer exposure than with `--airmass-rule best`.
  - `load_etc("tests.fake_etc:etc")` is used when passed.
  - The `sn_combined` arithmetic is checked.

---

## Milestone 6 — `t_target` and `required` (T3.3)

- **`targets_io.py`:** add optional fields `t_target` (minutes; aliases
  `t_target`, `t_obs`, `exptime_min`) and `required` (bool; accepts
  true/false/yes/no/1/0, defaults to false). Report bad values the same way
  `priority_coercions` does.
- **LRIS:** if `t_target` is set, `exp = {'science_min': t_target, …}` with
  `time_source = 'user'`. Still call the ETC, so `etc_min` can be shown
  beside it. That call is skippable with `--no-etc-for-user-times` if
  latency matters.
- **Kast:** in `schedule_greedy`, use `t_target` when set.
  `backfill_partials` (`kast_calculations.py:288`) skips rows with
  `required = True`. A required row that doesn't fit is rejected with
  "required: needs N min, no gap that long".
- **LRIS partials:** the LRIS path has no partial backfill today, so
  `required` changes nothing there yet. Say so in the docs rather than add
  partials to LRIS in this milestone.
- **Schema / interface:** `ScheduledTarget.time_source` ('ETC' | 'user'),
  `etc_min`, and `required`; plan-table columns; document both columns in
  `docs/target_csv_guide.md`. Add `test_targs/t_target_required.csv` as a
  fixture.
- **Tests:**
  - `t_target` rows get exactly that time.
  - A required Kast row that can only fit partially is rejected, not
    truncated.
  - The table round-trips through `/api/targets/inspect`.

---

## Milestone 7 — quick interface fixes (T2.1–T2.8)

These are independent and can be done any time after M2. T2.1 needs the
acquisition segment to exist, and T2.8 is most useful once M3–M6 have
filled in the assumptions.

| Goal | Change |
|---|---|
| T2.1 | `style.css` tokens. `--overhead` → orange (Okabe–Ito `#E69F00` is the candidate). `--idle` moves off amber, to hatched neutral grey. Pick `--acq` to be distinct from science blue and the partial pink. Check the palette with a script (`scripts/check_palette.py`: pairwise ΔE under deuteranopia/protanopia simulation), not by eye. Cover dark mode if the CSS has it. |
| T2.2 | Plan header (`#plan-head`, `renderPlan`) and every plan sub-page: `{instrument} · {telescope} · {date}`. The data is already in `PlanResult`. |
| T2.3 | Add `lst_start_h` / `lst_end_h` to `PlanResult.to_dict()`, computed with astropy at `night_start`/`night_end` from the site in `SITES`. Draw a second tick row under the timeline by reusing `nightTicks` / `lstLabel` (`app.js:1197-1240`). |
| T2.4 | `index.html` setup form: mark the target table and output directory required, since the backend already rejects runs without them (`app.py`, `generate`). Mark start, max targets and blocks "optional". Under the upload, list the required CSV columns from `REQUIRED_FIELDS` (`name, ra, dec, mag`) and the optional ones from `OPTIONAL_FIELDS`, served by `/api/targets/inspect` so the list never drifts. |
| T2.5 | `/api/targets/inspect` preview (`app.py:230`) adds `tags`, `dm`. Priorities page shows them, with a toggle. Add `ScheduledTarget.tags` / `dm` (defaulted) and a toggleable plan-table column. |
| T2.6 | Hint text on the upload card and the priorities page (copy in the goals file). |
| T2.7 | **Backend done already:** `FinderRequest.targets` (`app.py:581`) takes a list; empty means all. Add a per-card "generate" / "re-render" button in `renderFinders` that posts `{targets: [name], overwrite: true}`. |
| T2.8 | `PlanResult.assumptions: dict` (defaulted), filled by each run's `out`: config, seeing, band, ETC name, S/N target, n_sub, airmass rule, slew/acq/readout values, and NOT SET flags. Shown as a collapsible panel on the plan page and written into the export. |

**Tests:** `tests/test_backend.py` checks `assumptions`, `lst_*`, `tags`/`dm`
in the API output. The frontend is checked by hand in the running app (the
`run` skill); there is no JS test harness.

---

## Milestone 8 — priority tiers on the LRIS path (T1.6)

- **Refactor** the body of `select_targets_for_night`'s loop into
  `_greedy_pass(observable, start, end, blocks, prev_dec, budget, skip)`.
  Behaviour stays identical for a single tier. Lock that down first with a
  snapshot test on a fixed `test_targs/` table and date.
- **Tiers:** mirror `schedule_by_priority` (`kast_calculations.py:396`).
  Tier 1 runs over the whole night. Each lower tier runs inside the gaps the
  placed targets leave, with every placed target immovable.
- **The LRIS-specific complication is slew.** Unlike Kast's flat 5 min, a
  Keck slew depends on the previous Dec, so inserting X between A and B can
  turn B's slew into the 14 min crossing. The fit test for X must be exact:
  `slew(A→X) + acq(X) + X + slew(X→B) + acq(B)` must end by
  `B.science_start`. If it does, recompute B's slew. Don't shrink gaps by a
  worst-case margin; that throws time away.
- **Forced targets:** `reserve_forced_targets` / `append_forced_targets`
  already sit before scheduling. Keep the precedence documented in
  `docs/priority_system.md` (forced beats any tier). Update that doc: it
  currently says the LRIS path ignores priority.
- **Tests:** port `tests/test_priority_tiers.py` cases to LRIS. Two tiers,
  where tier 2 would have won the slot under `window_end` order → tier 1
  wins. One tier → identical to the snapshot.

---

## Milestone 9 — rotator and zenith limits (T3.6)

- **Limits fetched 2026-11-07** (table under
  [Data needed](#data-needed-before-or-during-the-work)).
- **Keck checks to build:**
  - Elevation above 85° during the block → warn ("stable guiding not
    guaranteed").
  - Above 88.9° → reject for that time.
  - Below 33.3° for az 5.3–146.2° (Nasmyth deck) → reject for that time.
- **LRIS rotator: no separate check** (Lordrick, 2026-11-07). Starlists
  already send the finder's `slit_pa` as `rotdest=… rotmode=pa`
  (`night_planner/starlist.py:50`, same as `chime-ffff-pz`'s `starlist.py`),
  and that has been accurate. Keck's software converts sky PA to the
  physical angle. Its legal range (−239 < x < 189) spans 428°, more than a
  full turn, so every `rotdest` has a legal physical angle. The rotator
  only gets into trouble tracking near zenith, which the 85° warning
  already flags.
- **Shane tub: reference is `helpful_scripts/calcint.c`** (ported as
  `night_planner/lick_tub.py`, checked 0.000 deg against `pa.c`, brain
  v0.45). Its table covers PA 20–380°, tub readout 17.45–330.64, so every
  slit PA has a tub setting. Starlists already quote both settings, 180°
  apart. No reject rule is needed. Build two things only:
  - A test that `tub_settings` stays inside [17.45, 330.64] for PA 0–360°.
  - The tub readout shown in the observing-log target row (M1b), next to
    PA.
- Shane HA/Dec limits are already enforced; nothing to add.
- **`instrument_params.KECK_ELEVATION_LIMITS`** (`zenith_max=88.9`,
  `guide_warn=85.0`, `nasmyth_floor=33.3`, `nasmyth_az=(5.3, 146.2)`), with
  the TelLimits URL. The check runs in `analyze_targets` (window) and after
  placement (track); reasons go to the rejections page.
- **Tests:** a synthetic target transiting within the zenith limit during its
  block is flagged; one that doesn't isn't.

---

## Milestone 10 — several plans per night, as tabs (T4.1)

- **Request:** `GenerateRequest.scenarios: [{name, seeing, start, blocks}]`
  (optional). The backend runs `generate_plan` once per scenario into
  `<output_dir>/<scenario_slug>/` and writes `<output_dir>/scenarios.json`
  (names, sub-dirs, summary numbers). Each scenario is an ordinary plan
  directory, so finders, starlist and export all work unchanged per tab.
- **Frontend:** a "Scenarios" section on the setup page, with presets (good
  0.6″ / median 0.8″ / poor 1.2″, "lost first half" = block from
  `night_start` to midnight) and free rows. The plan page shows tabs when
  `scenarios.json` exists, plus a comparison table: targets scheduled,
  on-target h, idle min, and targets unique to each scenario.
- **Observing log:** only one scenario is actually observed, so there is
  **one log per night**, at `<output_dir>/observing_log.json`, not one per
  tab. The observer marks a scenario "in use". Switching scenarios runs
  `merge_log`, so filled rows are kept. Calibration items are the union of
  configs and masks across all scenarios: a mask needs its arcs and flats if
  any scenario might use it.
- **Depends on:** M4 (seeing input) and M5 (airmass-aware ETC). Without them,
  the tabs differ only in blocks and start time.
- **Tests:** three seeing scenarios → three plan dirs; the poor-seeing plan
  has ≥ the on-target minutes per target of the good one; `scenarios.json`
  lists all three.

---

## Milestone 11 — merged into Milestone 1b

The observer's log and the calibrations checklist are one page (2026-11-07); see [1b](#1b-observing-log-page-with-the-calibrations-checklist-built-in-t37--t42).

---

## Data needed before or during the work

**Answered 2026-11-07 (Lordrick), after the web fetch:**

| Item | Answer | Applied in |
|---|---|---|
| LRIS readout | "Read out is more on blue than red, so ~80 s for blue and ~40 for red". This is observer experience at our default 2x2 and **overrides the web table**. Red agrees with Keck's 39 s; blue is well above the page's 54 s (1x1). Slower arm = **80 s per frame** | M3 |
| Kast read mode | "I always use slow readout" → slow mode. Then "normally on Kast read out is 20s on the blue side" → **20 s per frame**. This matches the web's slow sub-region value for the red side (20 s); the web gives the blue side 7 s | M3 |
| Kast ETC dichroic | **d55** (our d57 isn't offered) | M5c |
| LRIS sky → physical rotator angle | "Our chime-ffff-pz finder script calculates rotdest which appears to be accurate" → no conversion of our own; see M9 | M9 |
| Shane tub range | Use the Shane script (`helpful_scripts/calcint.c`) as the reference | M9 |

**Fetched from the web 2026-11-07** (raw ETC forms saved in the session
scratchpad; every value gets its URL as the source comment in
`instrument_params.py`):

*Readout (M3).* LRIS times are elapsed for a 0–1 s exposure, including
erase and readout, which is what we want per frame.

| Detector | Mode | Time | Source |
|---|---|---|---|
| LRIS red (Mark IV, May 2021) | 2 amps (spectroscopy), 1x1 | 97 s | [win_bin](https://www2.keck.hawaii.edu/inst/lris/win_bin.html) |
| | 2 amps, 2x2 | **39 s** | same |
| | 2 amps, 1x2 / 2x1 | 55 s / 65 s | same |
| | 4 amps (imaging), 1x1 / 2x2 | 54 s / 24 s | same |
| LRIS blue | full frame, 1x1 | 54 s | same |
| | full frame, 1x2 | 36 s | same |
| | half frame, 1x2 | 23 s | same |
| | (no binning stated) | 42 s | [detectors](https://www2.keck.hawaii.edu/inst/lris/detectors.html) |
| Kast blue (Fairchild 2k×2k) | slow, full frame (2110×2048) | 43 s | [Kast detectors](https://mthamilton.ucolick.org/techdocs/instruments/kast/hw_detectors.html) |
| | slow / fast, typical sub-region | 7 s / 2 s | same |
| Kast red (Hamamatsu 1024×4096) | slow, full frame | 34 s | same |
| | slow / fast, typical sub-region | 20 s / 14 s | same |

LRIS spectroscopy reads the red CCD with 2 amps
([redccdmanual](https://www2.keck.hawaii.edu/inst/lris/redccdmanual.html)).
Its "typical sub-region" windows are blue `330 2048 995 0` and red
`2725 525 675 409` (nr nc sr sc).

*ETC forms (M4, M5c).* Both are at `https://etc.ucolick.org/web_s2n/{lris,kast}`
and post to `gen_inst_s2n`. The server omits its intermediate certificate;
use `scripts/certs/ca_bundle_with_incommon.pem`, as `lris_etc.py` does.

| Field | LRIS options | Kast options |
|---|---|---|
| `inst` | `lris` | `kast` |
| `dichroic` | D560, D460, D500, D680 | d55, d46 |
| `grism` (blue) | B300 (300/5000), B600 (600/4000), B400 (400/3400), B1200 (1200/3400) | G2 (600/4310), G3 (830/3460) |
| `grating` (red) | 600/7500, 600/10000, 1200/9000, 400/8500, 831/8200 | 600/7500 |
| `slitwidth` | 0.7, 1.0, 1.5 | 1.0, 1.5, 2.0 |
| `binning` | 1x1, 2x1, 2x2, 3x1 | same |
| `ffilter` | `sdss_{u,g,r,i,z}.dat`, `Buser_{B,V}.dat`, `Cousins_{R,I}.dat` | same |
| `mtype` | 2 = AB, 1 = Vega | same |
| others | `exptime`, `mag`, `seeing`, `airmass`, `redshift`, `template` (blank = flat) | same |

One Kast probe (G2, d55, 600/7500, 2.0″, 1x1, r = 19 AB, 900 s, seeing
1.5″, airmass 1.1) returned the same JSON keys as LRIS (`wave`, `s2n`,
`errormsg`, ...), on a 10 Å grid from 3150 to 8000 Å. The Kast red side is
modelled only to 8000 Å.

*Limits (M9).*

| Limit | Value | Source |
|---|---|---|
| Keck I max elevation (zenith limit) | 88.9° | [TelLimits](https://www2.keck.hawaii.edu/inst/common/TelLimits.html) |
| Keck guiding | "Stable guiding cannot be guaranteed" for transits above ~85° | same |
| Keck I accessible elevation | 33.3–88.9° for az 5.3–146.2° (Nasmyth deck); 18–88.9° elsewhere | same |
| LRIS rotator physical PA | −239° < x < 189° (wraps by ±360) | [rotpposn](https://www2.keck.hawaii.edu/inst/lris/procs/rotpposn.html) |
| Shane HA | −5:40 to +3:45 | [Shane pointing](https://mthamilton.ucolick.org/techdocs/telescopes/Shane/pointing/) |
| Shane Dec | −35.0° to +72.0° nominal; +82.0° absolute (Feb 2025, needs approval) | same |
| Shane software limit | 80° zenith distance; obstructions cost ~5 min each | same |

The repo already uses the Shane HA limits and the 82° absolute Dec limit
(`lick_2026b02_calculations.py:66-68`). The page source still holds a
commented-out "+05:40:00" west limit; the live value is +3:45.

**Answered 2026-11-07 (Lordrick):**

| Item | Answer | Applied in |
|---|---|---|
| Kast S/N convention | "Make this S/N 5 for now but we can change later" → `TARGET_SN['kast'] = 5`, per sub-exposure, ≥ 3 sub-exposures, `--target-sn` overrides | M5c |
| Q8: Lick acquisition term | First "about 3 min to slew and about 3 min to acquire"; revised to "slew time 2 min and acquisition 3 for a total of 5" → `LICK_SLEW_MIN = 2`, `LICK_ACQ_MIN = 3` (5 min per target, unchanged total) | M2a |
| Q7: drop the +5 min mask buffer? | "Don't drop the extra 5 min for masks" → `MOS_MASK_BUFFER_MIN` stays 5, on top of the 10 min mask acquisition | M2a |
| Sunil: function-shaped ETC plug-in | "Just do this for now" → function shape | M5a |

## Order and dependencies

```
M1 calibrations out + observing log/checklist + .md report ─┐
M2 overheads ────┼─> M7 UI (T2.1 needs M2's acq segment)
M3 readout ──────┤
M4 config/seeing/band ─> M5 airmass + ETC ─> M10 scenarios
M6 t_target/required (after M5: needs etc_min)
M8 LRIS priority tiers (after M2: exact slew+acq fit test)
M9 Keck elevation checks + tub in log (independent; data in hand)
```

M1 and M2 need no outside data and are the right first session. M1 makes
the observing log usable at the telescope before the time-model work lands.
M3's numbers are in hand (LRIS 80 s, Kast 20 s per frame); only binnings
other than LRIS 2x2 stay NOT SET.

## Prompt
1. T1 to T4 should be fine; the calibration checklist should be good to try.
   Make an implementation.md.
2. Add a page for an automated observer's log: a checklist and columns
   (conditions, comments), a table of the plan's targets that can mark a
   target as not observed, other suggestions, and an observing report as a
   .md file at the end.
3. Combine the observer's log with the calibration checklist page.
4. Answers written into the "Data needed" table: Kast S/N, Q8, Sunil.
5. Make slew time 2 min and acquisition 3 for a total of 5 for Lick, and
   don't drop the extra 5 min for masks.
6. Get the web numbers first.
7. LRIS readout ~80 s blue, ~40 s red; Kast always slow readout; use d55;
   the chime-ffff-pz finder's rotdest is accurate; use the Shane script for
   the tub.
8. Normally on Kast read out is 20s on the blue side; what were the web
   values for LRIS readout?
9. We can use 80 for now. If we have everything, go ahead.
10. Continue through all the milestones, and return to old ones when they
    need updating.

## Logs
- **2026-11-07 (UTC), Claude (Opus 5.5):** Wrote this plan after reading the
  code paths each goal touches:
  - `adapters.py` (`keck_lris`, `_keck_overheads`, `lick_kast`)
  - `plan_result.py`
  - `cli.py` (`INSTRUMENTS`, `generate_plan`)
  - `backend/app.py` (`GenerateRequest`, `/api/generate`, `FinderRequest`)
  - `keck_2026oct06_calculations.py` (`select_targets_for_night`,
    `estimate_*_exposure`, `run`, `parse_args`)
  - `kast_calculations.py` (`run`, `schedule_by_priority`,
    `backfill_partials`)
  - `lris_etc.py`

  Findings that shaped the plan:
  - The finder endpoint already accepts a target list, so T2.7 is frontend
    only.
  - The LRIS scheduler holds back a flat 30 min "for calibrations" (line 939),
    which T1.5 must also remove.
  - The Kast plan shows its 20 min of focus + evening standard as idle,
    which would break the T1.2 totals check.
  - LRIS has no partial backfill, so `required` only acts on Kast for now.
  - The ETC already takes a filter argument, so band support is plumbing.
  - Keck's Dec-dependent slew makes LRIS priority gap-filling need an exact
    insertion test.

  The calibrations checklist is Milestone 1, as asked. No code was changed.
- **2026-11-07 (UTC), Claude (Opus 5.5), prompt 2:** Added Milestone 11
  (observer's log page + Markdown observing report, goal T4.2), per
  Lordrick.
  - **Builds on, not replaces,** the existing
    `scripts/make_observing_report.py` (FFFF-PZ CSV). Its row logic moves
    into a shared function, with a byte-for-byte regression test against
    the committed Keck-2026B-02 report.
  - **Suggestions added beyond the request:** a timestamped conditions log,
    frame numbers per target, quick-check boxes, unplanned-target rows,
    a computed time-accounting strip, and a short night checklist that
    links to (rather than copies) the M1 calibrations checklist. Also
    report warnings for pending/incomplete rows, and a `source` field per
    value so Tier 5 automation can write into the same log later.
  - Placed directly after M1 in the order.
- **2026-11-07 (UTC), Claude (Opus 5.5), prompt 3:** Merged the observer's
  log and the calibrations checklist into one page, per Lordrick: M1b now
  specifies the combined "Observing log", and M11 is a pointer to it.
  - One storage file (`observing_log.json`), one merge rule and one
    `PATCH` endpoint. The separate `calibrations.json`, `calibrations.py`
    and `/api/calibrations` are gone.
  - Calibration items gained UT and frame-number fields, because PypeIt
    needs the calibration file ranges.
  - The night checklist no longer repeats calibrations.
  - For M10 scenarios: one log per night (not per tab), with calibrations
    taken as the union across scenarios.
- **2026-11-07 (UTC), Claude (Opus 5.5), prompt 4:** Folded Lordrick's
  answers from the Data-needed table into the plan.
  - **Q8 → M2a:** `LICK_SLEW_MIN = 3`, `LICK_ACQ_MIN = 3`.
  - **Kast S/N = 5 → M5c:** `TARGET_SN` dict plus a `--target-sn` flag.
  - **Function-shaped ETC → M5a.**

  Checking where Lick's 5 min comes from turned up three copies of
  `SLEW_MINUTES = 5` in the run-specific `lick_2026b02_*` scripts. The
  general Kast path borrows them, and so do `schedule_greedy` and
  `_attribute_kast_slews`. The attribution only recognises a gap of exactly
  `SLEW_MINUTES`, so changing the gap without changing it would turn every
  Kast slew back into idle time. M2a now spells out all four places, and
  keeps the old scripts at 5 so the 2026B-02 nights still reproduce. I read
  "S/N 5" as per sub-exposure (≥ 3 subs), matching LRIS.

  Still open: Q7, readout times, ETC filter names, Kast ETC fields,
  rotator and zenith limits. No code changed.
- **2026-11-07 (UTC), Claude (Opus 5.5), prompt 5:** Lick revised to 2 min
  slew + 3 min acq (5 min total, same as today), and Q7 answered: keep the
  +5 min mask buffer. Because the Lick total is unchanged, the M2a Lick work
  shrinks to a relabelling plus moving the constant to one owner. Kast
  schedules don't shift. M2a's Q7 bullet now keeps
  `MOS_MASK_BUFFER_MIN = 5` and documents the full mask cost, so nobody
  later "fixes" it as a double count. Every Q-question is now answered. The
  remaining open items are data only: readout, filter names, Kast ETC
  fields, rotator and zenith limits. No code changed.
- **2026-11-07 (UTC), Claude (Opus 5.5), prompt 6:** Fetched the
  instrument numbers from the Keck, Lick and UCO ETC pages, and put them
  with links in "Data needed".
  - Readout feeds M3, the ETC forms feed M4 and M5c, the limits feed M9.
  - The ETC server's missing intermediate certificate stopped plain curl;
    I used the repo's own CA bundle, with verification still on.
  - One Kast ETC probe confirmed the request fields and the response shape.
  - Cross-checking the Shane page caught a summariser error (+5:40 west
    HA). The raw HTML showed that line is commented out; the live value is
    +3:45, which matches the repo.

  Four items the web doesn't answer stay open:
  - LRIS blue readout at 2x2.
  - Which Kast read mode we use.
  - d57 vs the ETC's d55/d46.
  - Shane tub travel.

  Plus the LRIS sky-to-physical rotator offset needed for M9. No code
  changed.
- **2026-11-07 (UTC), Claude (Opus 5.5), prompt 7:** Applied Lordrick's
  answers.
  - **LRIS readout:** 80 s blue / 40 s red at 2x2 (experience beats the web
    table's blue numbers), so 80 s per frame.
  - **Kast readout:** slow mode, so 43 s. I picked full frame; it was
    unspecified, so I flagged it.
  - **Kast ETC:** d55.
  - **M9 shrank.** I checked `night_planner/starlist.py` and
    `chime-ffff-pz/.../starlist.py`: both send `rotdest=slit_pa
    rotmode=pa`. With a 428° physical range, LRIS needs no rotator check.
    `calcint.c` covers every PA, so Shane needs no tub check. M9 is now
    Keck elevation checks only (85° warn, 88.9° zenith, 33.3° Nasmyth),
    plus showing the tub readout in the observing log.

  No outside data remains outstanding. No code changed.
- **2026-11-07 (UTC), Claude (Opus 5.5), prompt 8:** Kast readout set to
  20 s per frame (Lordrick), replacing my full-frame 43 s guess. The web's
  20 s is the red side's slow sub-region time; blue is listed as 7 s.
  Either way the cost is 20 s, since the arms read out in parallel. I
  re-quoted the LRIS web values on request. No code changed.
- **2026-11-07 (UTC), Claude (Opus 5.5), prompt 9: Milestone 1 built.**
  - **1a.**
    - `_keck_overheads` no longer emits arcs/flats.
    - The LRIS 30 min reserve became `MORNING_RESERVE_MIN` (closing slew +
      standard, 15 min today, 10 after M2).
    - The printout and the Excel plan point to the Observing log.
  - **1b.**
    - New modules: `night_planner/instrument_params.py`,
      `observing_log.py` and `observing_report.py`.
    - Routes `GET/PATCH /api/log` and `POST /api/log/report`.
    - A `night-planner report` CLI command.
    - An "Observing log" page (`#/log`).
    - `make_observing_report.py` now goes through `build_ffffpz_rows` and
      reproduces `Keck-2026B-02_report.csv` byte for byte.
    - Tests: 14 new in `tests/test_observing_log.py`; 93 pass.
  - **Deviations from the spec:**
    - Standards rows come from overheads whose label contains "standard",
      so Kast gets none until M2 emits its standards.
    - Planned PA is pre-filled from the finder sidecar
      (`finders/<name>_finder.json`) when one exists.
    - Exposures default to blank (the plan's recipe shows as a placeholder
      and is used in the report, with a warning), so "no exposures
      recorded" can still be detected.
  - **Bug caught in the browser check:**
    - The page took its directory from `plan.output_dir`, which is where
      the plan was generated, not the directory being viewed. A copied
      plan therefore wrote its log into the original directory.
    - Fixed on both sides: the page uses the opened directory, and the API
      pins `plan.output_dir` to the resolved request directory.
  - The saved `Night_plans/*/plan_result.json` files still carry the old
    arc/flat overheads until each plan is regenerated.
- **2026-11-07 (UTC), Claude (Opus 5.5), prompt 10: Milestones 2-10
  built.** 144 tests pass (+1 real-ETC test behind `--run-network`).
  - **M2 (slew/acq):** `keck_overheads` (5/14 min slew, acquisition 5/10,
    `keck_slew_reason`); Lick 2+3 min from `instrument_params`
    (`schedule_greedy` takes `slew_min`, `_attribute_kast_slews` splits the
    gap). Kast focus + evening standard are now overhead blocks, and the
    first Kast target gets its slew/acq. Timeline acq segment; units.
  - **M3 (readout):** `READOUT_S`, `readout_minutes` (per-arm wall clock).
    LRIS 80 s/frame, Kast 20 s/frame. MOS blocks, forced/partial
    allocations and user `t_target` get none. `ScheduledTarget.readout_min`.
  - **M4 (config/seeing/band):**
    - Flags via `add_config_args` / `resolve_options`.
    - `ETC_OPTIONS`, `validate_config` (400 with the allowed list).
    - `etc_filter`; d57 → d55 stand-in.
    - `mag_band` column, including FFFF-PZ `Pri_filter` (`Blanco:DECam-r`
      → `r`).
    - `/api/instruments/{name}/options` and the Configuration card.
  - **M5 (ETC):**
    - `night_planner/etc.py`: function interface, registry, `load_etc`,
      `lru_cache`.
    - `sky.block_airmass`; LRIS and Kast both re-size at the scheduled
      airmass and always re-fit the block.
    - S/N per sub/combined; `<plan>/etc/<target>.json`, `/api/etc`, S/N
      plot on the airmass page.
    - **Kast default stays `empirical`.** At S/N 5 the ETC is 0.07× the
      rule at mag 16-17 and 2.4× at mag 21
      (`scripts/compare_kast_exposure_models.py`,
      `Night_plans/kast_exposure_model_comparison.csv`). Switching is
      Lordrick/JXP's call; `--etc kast` turns it on.
  - **M6 (t_target/required):** both columns, coercion reporting, Kast
    backfill skips required rows (`required: needs N min, no gap that
    long`), `time_source` / `etc_min`, fixture
    `test_targs/t_target_required.csv`, guide section.
  - **M7 (UI):**
    - Okabe-Ito palette checked by `scripts/check_palette.py` (CIEDE2000 ≥
      12 under protan/deutan; the old palette had science vs MOS at 0.6
      under deutan).
    - Instrument in the header; LST axis.
    - Required/optional marks and the column list
      (`/api/targets/columns`).
    - Tags/DM toggles; priority hints; per-card finder button;
      Assumptions panel.
  - **M8 (LRIS tiers):** `_greedy_pass` refactor, pinned by
    `tests/snapshots/lris_single_tier.json` (recorded before the
    refactor); `_insert_tier` with the exact slew fit.
  - **M9 (limits):** `KECK_ELEVATION_LIMITS`; 88.9° zenith limit as a
    per-target keyhole block (`zenith_keyhole`), guiding warning above 85°.
  - **M10 (scenarios):** `night_planner/scenarios.py`,
    `GenerateRequest.scenarios`, `/api/scenarios`, tabs + comparison. One
    log per night at the base, with calibrations as the union.
  - **Back to M1:**
    - The log's calibrations follow `PlanResult.config` (M4).
    - Union across scenarios (M10).
    - Overrun notice no longer mentions calibrations.
  - **Bugs caught on the way:**
    - The zenith check first cut near-zenith targets' windows at transit
      (the snapshot test caught it); now a keyhole.
    - Re-sized exposures within the 0.5 min tolerance weren't re-fitted
      (Kast totals were 1.5 min over).
    - Empty `mag_band` cells reached the ETC as 'nan'.
    - A module-scoped test fixture reached the real ETC before the
      function-scoped network block. It is now session-scoped.
