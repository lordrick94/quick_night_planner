# User feedback → actionable goals

## Before we start
Read and follow all Claude rules in this repo (`CLAUDE.md`, `Logs/logging.md`,
`context/claudes_brain.md`).

## Where this came from
Feedback from seven users of the web interface (Kyle, Sunil, X, Alexa,
Lordrick, Michele, Alice), collected in the 2026-11 testing round. The verbatim
comments are kept in the **Appendix** at the bottom. Each goal below cites who
asked for it, so nothing gets lost in the regrouping.

**X is JXP. Where comments conflict, JXP's take precedence.**
The decisions that settled the open questions are recorded in
[Decisions](#decisions-answered-2026-11-07). Goals below already reflect them.

Goals are sorted into **tiers by order of work**, not by how many people asked:

1. **Tier 1 — the plan's time accounting.** Fix first: every number the plan
   shows depends on it.
2. **Tier 2 — quick interface fixes.** Small, independent, low risk.
3. **Tier 3 — inputs and configuration** (including the calibrations
   checklist).
4. **Tier 4 — several plans per night.**
5. **Tier 5 — live night mode.** The plan follows the night as it happens.
   Most requested feature overall (Kyle, Michele, Alice). Large.
6. **Tier 6 — research / long term.**

Each goal lists its current state in the code, so the work starts from what
exists. "Done when" is the acceptance test.

---

## Quick answers to the questions users asked

These describe the code **today**. Goal **T2.8** puts the answers on the
interface. Where a goal will change the answer, the goal is named.

| Question (who) | Answer from the code today |
|---|---|
| "What is the 20 min hit?" (bug list) | The Keck slew rule: a move from Dec < +20° to Dec > +20° costs **20 min**; every other slew costs 10 min (`scripts/keck_overheads.py`). The interface never explains it, so it looks like a bug. **Becomes 14 min (T1.2).** |
| "What units are slew and on target in?" (Alexa, Sunil) | **Minutes.** Exposure strings are in **seconds**. The table headers show no units (`frontend/app.js:645`). Fixed by T1.4. |
| "Are readout times included?" (Alexa, Sunil, X, Lordrick) | **No.** Detector readout is not modelled anywhere. On-target time is the sum of exposure times only. Fixed by T1.1. |
| "Are acquisition times assumed?" (Alexa) | Folded into the slew (Keck: 10 min flat; Lick: 5 min). There is no separate acquisition term. Fixed by T1.2. |
| "Is instrument config switching included?" (Alexa) | No. The planner assumes one fixed setup for the whole night. |
| "What configuration is the ETC using?" (Alexa) | LRIS: B600/4000 grism, R600/7500 grating, D560 dichroic, 1.0″ slit, 2×2 binning, 0.8″ seeing, S/N = 10 per pixel per sub-exposure, ≥ 3 sub-exposures (`scripts/lris_etc.py`). Kast: no ETC. It uses an empirical magnitude-to-time rule calibrated on past Lick plans (`night_planner/estimate_kast_exposures.py`). |
| "Is airmass in the exptime calculation?" (Sunil) | LRIS: **yes, but only the target's best (minimum) airmass of the night**, not the airmass at its scheduled time (`scripts/keck_2026oct06_calculations.py:956`). Kast: **no.** Fixed by T1.3. |
| "What seeing is assumed?" (Lordrick) | 0.8″, hard-coded (`DEFAULT_SEEING` in `scripts/lris_etc.py`). Kast: not used. Made an input by T3.2. |
| "Can we set priorities in a column?" (X) | **Yes, already.** A `priority` column in the target CSV is read (`night_planner/targets_io.py:34`) and pre-fills the priorities page. Nothing in the interface says so (T2.6). |
| "Is priority weighted / probabilistic?" (Lordrick, 2026-11-07) | **No.** Priorities are strict tiers: only their *order* matters (`1,2,3` ≡ `1,10,100`). Within a tier, urgency (earliest-closing window) then table order. The Keck/LRIS path ignores priority altogether (`keck_2026oct06_calculations.py:921`, see T1.6). |
| "Does it export to CSV?" (Michele) | It exports a `.zip` of the whole plan directory (`/api/export`). There is no single editable plan CSV (T5.5). |
| "Do I block out time and rerun as the night goes on?" (Michele) | Today, yes: blocked windows plus regenerate is the only workaround. Tier 5 replaces it. |

---

## Tier 1 — time accounting

### T1.1 Model detector readout time
- **Asked by:** Sunil, Alexa, X, Lordrick ("very different for Keck IR vs Lick
  optical with long exposures").
- **Now:** absent. On-target time = Σ exposure times.
- **Do:** add a per-instrument readout time (seconds per frame, per arm, per
  binning mode where it matters) to the instrument definition. Charge
  `n_frames × readout` inside each target's block. For dual-beam instruments,
  charge the slower arm (the arms read out in parallel).
- **Needs:** real readout values for LRIS (blue, red), Kast (blue, red) and any
  IR instrument we add. **Do not guess them.** Take them from the observers or
  the instrument web pages, and cite the source in code.
- **Done when:** each target's on-target time in the plan table equals
  exposures + readouts, and the summary reports total readout time.

### T1.2 Keck: 5 min slew, 14 min Dec crossing, separate acquisition
- **Asked by:** X/JXP ("5 min slew baseline for WMKO", "separate overhead for
  acquisition"), Lordrick ("5 min going into longslit, 10 min going into
  mask"), Alexa. **Decided** (Q1).
- **Now:** Keck slew = 10 min base, 20 min for the S→N Dec +20° crossing
  (`scripts/keck_overheads.py`). No acquisition term.
- **New model (Keck, all instruments):**

  | Term | Value |
  |---|---|
  | Slew, base | **5 min** (`KECK_SLEW_BASE_MIN`, was 10) |
  | Slew, Dec < +20° → Dec > +20° | **14 min** (`KECK_SLEW_DEC_CROSS_MIN`, was 20) |
  | Acquisition, longslit | **5 min** (new) |
  | Acquisition, mask | **10 min** (new) |

- **Do:** keep `scripts/keck_overheads.py` as the single source of truth and
  add `keck_acquisition_minutes(mode)` there. Show acquisition on the
  timeline as its own segment with its own colour, and as its own table
  column. Update the `keck_overheads.py` docstring history and the brain file
  (this reverses the 2026-09-30 rule).
- **Avoid double counting:** the MOS block (60/90/120 min) used to include
  mask alignment, plus a +5 min per-mask buffer (`MOS_MASK_BUFFER_MIN`). With a
  10 min mask acquisition charged explicitly, **all three stay (Q7,
  answered)**: the block, the +5 min buffer and the 10 min acquisition.
- **Lick (Q8, answered):** 2 min slew + 3 min acquisition, 5 min per target
  (same total as the old all-inclusive 5 min). Shown as separate slew and acq segments too.
- **Done when:** the timeline shows slew and acquisition as distinct segments;
  a S→N Dec +20° crossing shows 14 min; and the totals add up: on target +
  slew + acquisition + readout + overheads + idle = night length.

### T1.3 Exposure time at the scheduled airmass (conservative by default)
- **Asked by:** Sunil. **Decided** (Q4).
- **Now:** the LRIS ETC is called once, at the target's minimum airmass,
  before scheduling. A target observed at airmass 1.8 gets the exposure time
  it would need at 1.1.
- **Do:** after scheduling, recompute the exposure time at the **worst
  (highest) airmass within the target's scheduled block**. Iterate if the
  block grows: a longer block can reach a higher airmass. The airmass rule is
  a setting with three choices: `worst` (default), `mid-exposure`, `best`.
  Users can change it in the configuration step (T3.1) and when regenerating
  a plan.
- Kast needs a real ETC first (T3.4).
- **Done when:** for every target, the ETC airmass equals the worst airmass
  of its scheduled block (or the chosen rule), and the assumptions panel
  (T2.8) names the rule used.

### T1.4 Put units everywhere, and explain the Dec-crossing slew
- **Asked by:** Sunil, Alexa, bug list.
- **Do:** header units (`slew [min]`, `acq [min]`, `on target [min]`,
  `exptime [s]`); hover text on any slew above the base that names the rule
  ("Dec +20° crossing, 14 min").
- **Done when:** no number on any page is unitless.

### T1.5 Stop scheduling and showing calibration times
- **Asked by:** Lordrick (additional comment).
- **Now:** after the last Keck target, the plan adds `Arc lamps` (10 min) and
  `Internal flats` (10 min) as overhead blocks (`night_planner/adapters.py:176`).
  These count against the night and are drawn on the timeline.
- **Do:** remove the arc and flat blocks from the Keck plan and from any Lick
  equivalent. The observer decides when to take calibrations. The calibrations
  checklist (T3.7) covers them instead. **Keep** the evening/morning flux
  standards, the focus check and the slew to the morning standard: those are
  on-sky time.
- **Done when:** no arc, flat or bias block appears on the timeline or in the
  time budget, and the freed 20 min is available to science.

### T1.6 Priority on the Keck/LRIS path
- **Found while answering** the weighting question. Not a user request, but
  every priority goal depends on it.
- **Now:** priority tiers (`schedule_by_priority`,
  `scripts/kast_calculations.py:396`) exist only on the Kast path. The
  Keck/LRIS scheduler sorts by `window_end` and ignores the priorities page.
- **Do:** route the LRIS scheduler through the same tiering.
- **Done when:** the same targets with two priority tiers give a different,
  tier-respecting LRIS schedule; with one tier the schedule is unchanged.

---

## Tier 2 — quick interface fixes

| ID | Goal | Asked by | Now | Done when |
|---|---|---|---|---|
| T2.1 | **Orange for overhead** on the timeline | X/JXP | Overhead is teal (`--overhead: #0d9488`); idle is already amber (`--idle: #f59e0b`) | Overhead (now standards + focus only, per T1.5) is orange. Idle and the new acquisition segment (T1.2) get colours that can't be confused with it. Palette checked colourblind-safe |
| T2.2 | **Instrument name in the plan viewer** | X/JXP | Header shows date/context only on some pages | Instrument + telescope shown on every plan page |
| T2.3 | **LST axis under the plan timeline** | X/JXP | LST exists on the Night chart page only | Plan timeline has a local + LST axis (reuse `nightTicks`) |
| T2.4 | **Mark required vs optional fields** on Targets and constraints | Alexa | No marking | Required inputs flagged (e.g. `*`), optional ones say "optional"; the CSV column requirements are shown too (`docs/target_csv_guide.md`) |
| T2.5 | **Show FFFF-PZ tags and DM** on the priorities page and plan table | Michele | `tags` and `dm` are read (`targets_io.py`) but not shown | Optional columns, toggleable, so the user can see which targets are e.g. high-DM while setting priority |
| T2.6 | **Explain priority in the interface** | X/JXP, Sunil | A `priority` column is read but the interface doesn't say so | Hint on the upload card and the priorities page: a `priority` column is read; lower = first; only the order of values matters; fractions are allowed |
| T2.7 | **Generate a single finder chart** | X/JXP | Finders page renders all targets | Per-target "generate" button (and re-render) |
| T2.8 | **"Assumptions" panel** on the plan page | Alexa, Sunil, Lordrick | Assumptions live only in code/docs | Panel lists ETC config, seeing, S/N target, airmass rule, and the slew/acq/readout values used for *this* plan; saved with the plan |

**Dropped:** integer-only priority ranks (Sunil). Fractions stay, so existing
priority values don't need renumbering (Q2). T2.6 explains the existing
behaviour instead.

---

## Tier 3 — inputs and configuration

### T3.1 Set the instrument configuration at the start
- **Asked by:** Lordrick, Alexa.
- **Do:** a configuration step (grating/grism, dichroic, slit, binning)
  before targets, defaulting to the current standard setup. Plan-wide
  settings live here too: seeing (T3.2) and the ETC airmass rule (T1.3). It
  feeds the ETC, the readout model and the calibrations checklist (T3.7), and
  is stored in the plan.
- **Later:** per-target config and config-switch overhead (Alexa); only if
  someone actually needs mixed setups in one night.

### T3.2 Seeing as a manual input
- **Asked by:** Lordrick, Alexa. **Decided** (Q5): manual input only for now.
- **Do:** a seeing field (default 0.8″) in the configuration step, fed to the
  ETC and editable on regenerate.
- **Not planned:** pulling a seeing forecast (MKWC, Lick).
- **Feeds:** T4.1 (plans per weather condition).

### T3.3 Per-target `t_target` and a `required` flag
- **Asked by:** X/JXP ("optional/required column of t_target which would set
  the value"; "if it provides the estimated exposure time, include").
  **Decided** (Q3): a per-row flag.
- **Do:** two optional target-table columns:
  - `t_target` (minutes on target). If present, it sets the time, and the ETC
    is not used for that row.
  - `required` (true/false, default false). A required target gets its full
    time or is rejected with a reason. It is never truncated into a partial by
    the backfill pass (`backfill_partials()`). A non-required target can be
    truncated into a partial, as now.
- **Show in the plan table,** for every row: the time used, its source
  ("user" or "ETC"), and the ETC estimate next to it even when `t_target`
  overrides it.
- **Done when:** a CSV with `t_target` on some rows schedules exactly those
  times; a `required` row that can't fit is rejected rather than made a
  partial; and `docs/target_csv_guide.md` documents both columns.

### T3.4 ETC: S/N diagnostics and a pluggable interface
- **Asked by:** Sunil.
- **Do:** (a) for each target, show the predicted S/N per sub-exposure and
  combined, at the scheduled airmass (T1.3) and seeing (T3.2). Include a small
  S/N(λ) plot from the ETC response we already get. (b) Define an ETC
  interface as a plain function signature, e.g.
  `etc(mag, band, airmass, seeing, config, target_sn) -> {exptime_s, n_sub, sn}`,
  and let the user point the config at their own function. Follow the repo
  convention: methods, not classes. Sunil said "ETC class"; **decided
  (Lordrick, 2026-11-07): the function shape for now.**
- Kast gets a real ETC through the same interface (etc.ucolick.org serves Kast
  too). **Kast target S/N = 10** per sub-exposure (Lordrick,
  2026-11-07; first set to 5 the same day), adjustable per plan.

### T3.5 Magnitude band choice
- **Asked by:** Michele.
- **Now:** one `mag` column (r assumed; aliases in `targets_io.py:55`).
- **Do:** a band field (column or per-table setting), passed to the ETC.
- **Done when:** a g- or i-band table gives different, correct ETC times.

### T3.6 Rotator and zenith limits
- **Asked by:** Sunil.
- **Now:** pointing limits (Dec, HA, Keck I Nasmyth vignetting) are modelled.
  Rotator range and the zenith keyhole (fast azimuth near zenith on alt-az
  Keck) are not.
- **Do:** per-telescope rotator range + zenith-angle minimum. Reject or flag
  targets whose slit PA / track crosses them. Limits must come from the
  observatory pages (cite them).

### T3.7 Calibrations checklist (a section of the Observing log, T4.2)
- **Asked by:** Lordrick (additional comment). Replaces the calibration
  blocks removed in T1.5.
- **Do:** a calibrations section **on the Observing log page (T4.2)**, not a
  page of its own (merged 2026-11-07). It lists the calibrations the night
  needs, as checkboxes saved with the log:
  - **Lick/Kast:** biases, flats and arcs **for each configuration** (usually
    just one).
  - **Keck/LRIS:** flats and arcs **for each configuration and for each
    slitmask** in the plan.
  - The list is generated from the configuration (T3.1) and the scheduled MOS
    masks. Each row shows what it is for ("config: B600/R600/D560/1.0″" or
    "mask: <name>").
- **Done when:** a plan with one longslit config and two masks lists three
  LRIS flat+arc sets; ticking items persists across reloads; and the checklist
  is included in the export.
- **Feeds:** T5.4 (calibrations taken become part of the as-realized log).

---

## Tier 4 — several plans per night

### T4.1 Plans for different conditions, shown as tabs
- **Asked by:** X/JXP ("generate multiple plans into tabs"), Alexa ("multiple
  night plans for different weather conditions"), Lordrick.
- **Do:** generate N plans from the same targets, each with its own
  manually entered conditions (seeing, start time, blocked windows; e.g.
  0.6″ / 0.8″ / 1.2″, or "lost first half"). Show them as tabs, with a
  comparison row (targets observed, on-target hours, idle).
- **Depends on:** T3.2 (seeing input) and T1.3 (airmass-aware ETC), otherwise
  the plans differ only in name.

### T4.2 Observer's log page and Markdown observing report
- **Asked by:** Lordrick (2026-11-07). Overlaps Michele's "plan of what I
  actually did" and Kyle's as-realized log.
- **Now:** `scripts/make_observing_report.py` writes the FFFF-PZ
  observing-log CSV from a plan, from the command line only. You pass the
  night's conditions and the dropped/failed targets as flags. There is no
  page and no per-target notes.
- **Do:** a log page with one editable row per target in the selected plan.
  It has a status (observed / partial / not observed + reason), conditions,
  the exposures actually taken, frame numbers and comments. Above the table
  sit night-level fields and a short start/end-of-night checklist. A button
  generates `observing_report_<date>.md`, and the FFFF-PZ CSV from the same
  data. The calibrations checklist (T3.7) is a section of this page.
  Full spec: Milestone 1b in
  [`user_comments_implementation.md`](user_comments_implementation.md).
- **This is the manual first step of Tier 5.** T5.1's start/finish buttons
  and T5.6's data watcher will later write into the same log file, instead of
  a second one.
- **Done when:** a plan's log can be filled in, survives reloads and a plan
  regenerate, and produces a Markdown report listing every planned target
  as observed, partial or not observed (with reasons). The FFFF-PZ CSV from
  the page matches what `make_observing_report.py` gives for the same inputs.

---

## Tier 5 — live night mode

Seven separate requests describe one feature. Build it in this order. Each
step is useful on its own.

| ID | Goal | Asked by |
|---|---|---|
| T5.1 | **Start / activate a plan**: a "now" line on the timeline; per-target buttons *started*, *finished*, *skipped*, *partial (N min)*; timestamps recorded | Alice, Kyle, Michele |
| T5.2 | **Planned vs actual timeline**: the actual track drawn above the planned one, with an ahead/behind-schedule indicator | Alice |
| T5.3 | **Replan the rest of the night** from "now", with completed targets removed and partial time credited towards the target. `required` targets (T3.3) keep their full-time rule | Michele, Kyle |
| T5.4 | **As-realized log export** at the end of the night: plan, actual, notes, calibrations checklist (T3.7) and data-quality fields in one file. Mostly delivered by T4.2. What remains is filling the timestamps automatically from T5.1 | Kyle, Michele |
| T5.5 | **Editable plan CSV**: one plan CSV with stable target IDs and a notes column, for Google Sheets. Re-imports must not clobber notes on regenerate | Michele |
| T5.6 | **Watch for new data**: a background watcher on the data directory reads FITS headers (object, RA/Dec, exptime) and offers to assign each frame to a plan entry | Kyle |

- **State model:** T5.1–T5.3 need the plan to become a stateful object with
  status per entry, not a regenerated output. Design this once (in
  `night_planner/plan_store.py` / `plan_result.py`) before building UI.
- **Done when (T5.1–T5.4):** a dry-run night, replayed from a script with
  fake timestamps, produces a correct planned-vs-actual chart and a log file.

---

## Tier 6 — research / long term

- **T6.1 Quick-look reduction and real-time S/N** (Kyle): as frames land
  (T5.6), run a fast extraction and compare the measured S/N with the ETC
  prediction. The `lris-longslit-redux` PypeIt workflow is the natural base,
  but full PypeIt is too slow for real time. Start by measuring the S/N of a
  single raw frame.
- **T6.2 Learn from plan vs log** (Kyle): the as-realized logs (T5.4) become
  training data, e.g. calibrating real overheads per instrument against the
  modelled ones. Needs several nights of logs first.
- **T6.3 What would the guider camera see** (Lordrick): a finder-style
  preview at guider scale and field of view, with expected guide stars. Needs
  each guider's FOV, pixel scale and depth.

---

## Decisions (answered 2026-11-07)

| Q | Question | Answer | Goal |
|---|---|---|---|
| Q1 | Keck slew and acquisition numbers | Slew 5 min base; Dec-crossing **reduced from 20 to 14 min**; acquisition longslit 5 / mask 10 min. "Follow other suggestions." | T1.2 |
| Q2 | Integer-only priorities? | **Leave as is** (fractions allowed), so existing ranks don't need changing | T2.6; integer ranks dropped |
| Q3 | `t_target` optional/required? | **A per-row flag** | T3.3 |
| Q4 | Which airmass for the ETC? | **Conservative (worst in block)**, adjustable in the configuration and on regenerate | T1.3 |
| Q5 | Seeing forecast source? | **Manual input for now** | T3.2 |
| Q6 | Who is X? | **X is JXP; his comments take precedence** | all |
| Q7 | MOS double count? | **Keep the +5 min mask buffer** on top of the 10 min mask acquisition (Lordrick) | T1.2 |
| Q8 | Lick acquisition term? | **Yes: 2 min slew + 3 min acquisition, 5 min total** (Lordrick; first given as 3 + 3) | T1.2 |
| — | Kast S/N target? | **S/N = 10** (was 5), changeable (Lordrick) | T3.4 |
| — | ETC plug-in shape (Sunil) | **Function shape for now** (Lordrick) | T3.4 |
| — | Additional | Don't show calibration times; add a calibrations checklist page (Lick: biases, flats, arcs per config; LRIS: flats, arcs per config and per mask) | T1.5, T3.7 |

## Open questions — still to answer

None. Q1–Q8 are all answered (see Decisions above).

---

## Prompt
1. Read and understand comments, ask questions where necessary, sort and
   rewrite this file into an actionable set of goals.
2. Read answers and recalibrate goals.

## Logs
- **2026-11-07 (UTC), Claude (Opus 5.5), prompt 1:** Read all seven users'
  comments and checked each against the code (`frontend/`, `backend/app.py`,
  `scripts/keck_overheads.py`, `scripts/lris_etc.py`,
  `night_planner/targets_io.py`, `night_planner/estimate_kast_exposures.py`).
  Rewrote the file into six work tiers with goal IDs, current state and
  acceptance tests. Answered the users' direct questions from the code: the
  "20 min hit" is the Keck Dec +20° slew rule; readout is not modelled; the
  ETC uses best-of-night airmass. Six open questions were listed for
  JXP/Lordrick. The verbatim comments are kept below.
- **2026-11-07 (UTC), Claude (Opus 5.5), prompt 2:** Folded in the answers to
  Q1–Q6 and the calibrations comment.
  - Rewrote T1.2 with the new Keck numbers (5 / 14 / acq 5 / acq 10) and
    T1.3 with worst-in-block airmass as a configurable default.
  - T3.3 now pairs `t_target` with a `required` flag that blocks partials.
  - Seeing is manual only; the forecast was dropped.
  - Integer priorities were dropped in favour of explaining the current
    behaviour (T2.6).
  - Added T1.5 (remove arc/flat blocks, `adapters.py:176`; standards and
    focus stay) and T3.7 (calibrations checklist).
  - Added T1.6 after the weighting question surfaced that the LRIS path
    ignores priority.
  - Two follow-ups remain (Q7 MOS double count, Q8 Lick acquisition), each
    with a stated default.
- **2026-11-07 (UTC), Claude (Opus 5.5), follow-up:** Added T4.2
  (observer's log page + Markdown observing report), per Lordrick. It builds
  on the existing `scripts/make_observing_report.py` (FFFF-PZ CSV) rather
  than replacing it. The implementation is Milestone 11 in
  `user_comments_implementation.md`.
- **2026-11-07 (UTC), Claude (Opus 5.5), follow-up:** Merged T3.7 into
  T4.2: the calibrations checklist is a section of the Observing log page,
  stored in the same `observing_log.json`. Spec moved to Milestone 1b.
- **2026-11-07 (UTC), Claude (Opus 5.5), follow-up:** Applied Lordrick's
  answers from the implementation plan's data table:
  - Q8: Lick gets 3 min slew + 3 min acquisition (T1.2).
  - Kast target S/N is 5 for now (T3.4). Raised to 10 later that day.
  - The ETC plug-in is a function, not a class (T3.4).

  These are now in the Decisions table. Q7 is still open, with its default.
- **2026-11-07 (UTC), Claude (Opus 5.5), follow-up:** Lick revised to 2 min
  slew + 3 min acquisition (5 min total). Q7 answered: keep the +5 min mask
  buffer. No open questions remain.
- **2026-11-07 (UTC), Claude (Opus 5.5), follow-up:** Fetched readout
  times, ETC form fields and telescope/rotator limits from the web for T1.1,
  T3.1/T3.4 and T3.6. They're in the implementation plan's "Data needed"
  section, with links.
- **2026-11-07 (UTC), Claude (Opus 5.5), follow-up:** Lordrick's answers:
  - LRIS readout ~80 s blue / ~40 s red, so 80 s per frame (T1.1).
  - Kast slow readout, 43 s full frame (T1.1).
  - Kast ETC uses the d55 dichroic (T3.4).
  - The finder's `rotdest` is trusted, so LRIS gets no rotator check, and
    `calcint.c` is the tub reference (T3.6).

- **2026-11-07 (UTC), Claude (Opus 5.5), follow-up:** Tiers 1-4 implemented
  (T1.1-T1.6, T2.1-T2.8, T3.1-T3.7, T4.1, T4.2); see the implementation
  plan's Logs. Open decision: the Kast default stays on the empirical rule,
  because the ETC at S/N 5 differs from it by 0.07-2.4×.
- **2026-11-08 (UTC), Claude (Opus 5.5):** Kast target S/N raised from 5 to
  10 per sub-exposure (Lordrick: "Let's increase the S/N to 10 for Lick").
  It only affects `--etc kast`; the empirical default ignores S/N. At S/N 10
  the ETC/empirical ratio is 0.07× at r = 16, 1.75× at r = 20, and r ≥ 20.5
  hits the 3 × 7200 s cap (`Night_plans/kast_exposure_model_comparison_sn10.csv`).
---

## Appendix — original comments (verbatim)

### Comments from a number of user
Night Planner Feedback
Kyle’s comments
Make the interface more dynamic, as that is more realistic
Can the plan interface allow you to input progress as data is actually obtained, the idea being that the plan can adjust in "real-time" as the night proceeds
You could potentially have something running in the background that can automatically detect the presence of new data that you can assign to specific parts of the plan
At the end of the night, the complete as-realized plan could then be exported to a log file.  (The plan vs. log files could potentially be used to train the planning algorithm.)
It would be nice to connect a quick reduction process that could also provide real-time assessments of the data quality to ensure that you're reaching, e.g., the desired S/N
Sunil’s comments
Maybe restrict priorities to be ranks, i.e., integer values.
Consider rotation limits and maybe zenith angle limits.
Please use units for time. I see exptime in s, but “on target” is in minutes, I think.
Readout overheads not included in the “on target” time.
Suggested exptimes should be backed up by S/N diagnostics from the internal ETC.
As an aside, maybe expose the ETC format to the user so that they may plug in their own ETC class, for instance.
Is airmass going into the exptime calculation?
X’s comments
Can we set priorities in a column?
Can we use Orange for overhead?
Use 5min slew baseline for WMKO
Separate overhead for acquisition?
Add Instrument name to viewer
Add LST at bottom of time series
Include read out time
Include an optional/required column of t_target which would set the value
If it provides the estimate exposure time, include
Can we generate multiple plans into tabs?
Can we generate only a single Finder chart?
Alexa’s comments/questions
In Targets and Constraints page, denote which fields are truly required and which are optional
What configuration is the ETC using?
Are readout times and instrument config switching incorporated?
What units are slew and on target in?
Are any assumptions made on time for acquisition?
Multiple night plans for different weather conditions


Lordrick’s comments/questions
Slew times, just 5min for going into Longslit and 10min going into mask, rethink write
Read out time not considered - very different for Keck IR obs vs Lick optical with long exposures
Set configuration at beginning of night plan
What seeing is being assumed, maybe have an option of plans using forecast best we can
What could you see at a guider Camera

Michele’s comments
As the night goes on, how do I specify that this target was observed for X minutes so now readjust the rest of the plan? Do I just block out that time and rerun?
Does this export to a csv file that I can then edit in google sheets to leave notes and such? This might get messy if we keep regenerating the plan here
Have some kind of plan that this is what I actually did
Add option for different magnitude bands
Can the FFFF-PZ tag be optionally included in a table so I can remember which target is which?
So when I set priority, for example, I can see which targets are high-DM
Alice’s comments
Is it possible to “activate” or “start running” the plan as you begin observing? And you can track when targets begin being observed, finish etc. and show the “actual” timeline progressing above the “planned” timeline? I suppose a visual aid to help see if you’re on schedule or not


Bugs?
What is the 20min hit?
