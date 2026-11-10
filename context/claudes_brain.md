# Claude's Brain — night-planner

This file is Claude's persistent memory for the **night-planner** project. As I
learn about night planning, the telescope, the author's preferences, and how this
repository is organized, I record the durable, reusable knowledge here — the
things a fresh session would want to know. A dated **Version History** at the
bottom tracks every update.

## Project purpose

- Teach Claude to generate a **night plan for a modern, professional telescope**,
  learning from two professional astronomers (J. Xavier Prochaska, `jxp@ucsc.edu`,
  and a colleague).
- Longer-term goal: a **GitHub-hosted webpage dashboard** monitoring all of the
  author's Claude-assisted projects.

## Working conventions (from CLAUDE.md)

- **Git:** the author runs all git commands; I use only read-only git.
- **Calculations:** always write them as a Python script to disk (reproducible),
  never inline-only.
- **Logging:** same approach as the ClimateIntelligence repo — a daily narrative
  log I write at `Logs/YYYY/MM/YYYY-MM-DD.md`, plus `Logs/log_summary.csv` written
  automatically by the `Stop` hook (`.claude/hooks/log_usage.py`). CO2 ≈ 0.076 g
  per 1,000 tokens. See [`../Logs/logging.md`](../Logs/logging.md).
- **Coding:** Python; methods not classes; imports at top; docstrings with
  inputs/outputs; matplotlib/seaborn/Bokeh for plots; `"Created by JXP and Claude"`
  header on every file and docstring.
- **Target privacy (2026-11-09):** the repo is **public**; real targets are
  not. Plans go to `paths.plans_dir()` = `NIGHT_PLANNER_PLANS` or the
  git-ignored `<repo>/pvt_Nighplans/` (`Night_plans/` is git-ignored too).
  **Never write a real target name or position into a tracked file**: no logs,
  brain, docs, tests, prompts or scripts. Use `SIM*` objects or a placeholder.
  This includes *examples* in docstrings, logs and the brain: write
  "a position rounded to 1--2 decimals", never the numbers.
  Check with `scripts/scan_private_targets.py`. The scrub plan is in
  `claude_prompts/target_scrub.md`. The public, history-free copy is
  built by `scripts/build_public_snapshot.py` (2026-11-10: into
  `~/Projects/quick_night_planner`).

## Repository layout (as of 2026-07-11)

- `CLAUDE.md` — guidance for Claude (this project's rules).
- `claude_prompts/start_up.md` — ordered start-up prompts driving initial setup.
- `context/` — durable context; `claudes_brain.md` (this file).
- `Logs/` — daily narrative logs, `log_summary.csv`, `logging.md`.
- `.claude/` — `settings.json` (Stop hook wiring), `hooks/log_usage.py`,
  `skills/` (`grill-me`, `critical-partner`; copied from ClimateIntelligence).
- `setup.py` / `setup.cfg` / `pyproject.toml` — packaging. Author's convention
  (from `python/linetools` and `Projects/XAI`): metadata + deps in **setup.cfg**,
  `pyproject.toml` limited to `[build-system]`, `setup.py` a minimal `setup()` shim.
- `requirements.txt` — mirror of `setup.cfg` install_requires.
- `night_planner/` — the Python package (`__init__.py`, `__version__`).
- `tests/` — pytest suite (`test_import.py` smoke test passes).

## Author's Python-repo conventions (learned from linetools & XAI)

- Package layout: `<pkg>/` for source, `tests/` for `test_*.py`, metadata in
  `setup.cfg` under `[metadata]`/`[options]`, `pyproject.toml` build-system only.
- BSD-3 license; author `J. Xavier Prochaska`. Plotting via matplotlib.
- **Reference project:** `Projects/XAI` is the closest sibling — a Claude-driven
  *webpage dashboard to monitor all Claude-based projects* (matches night-planner's
  stated dashboard goal). Its `.claude/settings.json` (WebSearch/WebFetch allow +
  the `log_usage.py` Stop hook) is identical to ClimateIntelligence's and is the
  one to copy here (already in place from start-up prompt 1).
- Note: the prompt referenced `Oceanography/python`, which does not exist on disk;
  `papers/Oceanography/*` holds paper *analysis* dirs, not packaged repos. Used the
  author's actual Python repos (linetools, XAI, ClimateIntelligence) instead.

## Astronomy / night-planning knowledge

- _(To be filled in as I learn the telescope, instruments, targets, and the
  astronomers' night-planning workflow.)_
- **UCO/Lick observing calendars** (`ucolick.org/calendar/`, readme at
  `readme.html`; details in [`claudes_context.md`](claudes_context.md)):
  pre-computed nightly almanacs for **Lick (Mt. Hamilton, PST)** and **Keck
  (Maunakea, HST)**, one row per evening-date-plus-following-morning, in
  12° (nautical) and 18° (astronomical) twilight variants — sunset/sunrise,
  twilight/dawn times, moon rise/set, sidereal times (twilight/midnight/dawn),
  night & dark length, moon RA/Dec/distance at midnight. Authoritative
  site-specific reference for cross-checking our astroplan/thorsky-computed
  night events for any Lick/Keck night, 2011–2030 (adjacent decades also
  posted).
- **Instrument taxonomy & the facility instrument set** (full per-instrument
  summaries with URLs in [`claudes_context.md`](claudes_context.md), section
  "Instrument manuals"): the types that matter for planning are **imager /
  longslit / multi-object (MOS, slitmask) / echelle-echellette / IFU** — type
  drives the constraints (blue-UV coverage → dark time; NIR → moon-tolerant;
  MOS → masks fixed before the night; single slit → parallactic-angle/ADC
  choices; Nasmyth mounts → rotator/PA handling).

  | Instrument | Telescope (focus) | Type | Coverage | Planning hook |
  |---|---|---|---|---|
  | Kast | Shane 3m (Cass) | dual-arm longslit | blue+red via dichroic (4600/5700 Å splits) | slit PA; simultaneous arms |
  | HIRES | Keck I (Nasmyth) | echelle | 0.3–1.0 µm, R 25k–85k | HIRESb vs HIRESr fixed for the night; image rotator for PA/parallactic |
  | LRIS | Keck I (Cass) | imager+longslit+**MOS** | 3200–10,000 Å, R 300–5000 | masks milled on-site → pre-run lead time |
  | MOSFIRE | Keck I (Cass) | NIR **MOS**+imager | 0.97–2.41 µm (Y/J/H/K, one band), R≈3500 | CSU reconfigures in <5 min — no milled masks |
  | DEIMOS | Keck II (Nasmyth) | imager+longslit+**MOS** | optical, ≤5000 Å/exposure, R≤6000 | milled masks → pre-run lead time; 16.6′ slit length |
  | ESI | Keck II (Cass) | echellette+imager | 0.39–1.1 µm in one shot, R≤13k | fixed format, minimal setup choices |
  | KCWI | Keck II (Nasmyth) | **IFU** | blue 3500–5600 Å + red 5400–10,800 Å, R≈900–4500+ | slicer (8.4/16.5/33″×20.4″) sets R & FOV; dark time for blue |
  | NGPS | P200 (Cass) | 4-channel slit spectrograph | 3050–10,400 Å simultaneous, R>4000 | ships an ETC + Observation Timeline Modeler (prior art) |
  | GMOS | Gemini N & S | imager+longslit+**MOS**+IFU | 0.36–1.03 µm, R≤10k | queue/OB-based; masks + 3 mounted gratings decided in advance |

  Mask-lead-time (MOS) instruments: **LRIS, DEIMOS, GMOS** (physical milled
  masks) and **MOSFIRE** (software mask designs, but reconfigurable at night);
  single-slit/echelle: **Kast, HIRES, ESI, NGPS**; IFU: **KCWI** (and GMOS-IFU,
  NGPS slicer).
- **Kast FRB-host setup & exposure heuristic (2026B-01; from the authors'
  prior Lick/Kast plans):** standard setup is the **d57 dichroic** (split
  ~5700 Å), **600/7500** grating on the red arm, **600/4310** grism on the
  blue arm, **2" slit**. Kast is dual-beam — both arms expose
  *simultaneously*, so per-target wall clock = one arm's total, not the sum.
  Total integration T per arm scales with primary-host r-mag:
  <15.5 → 1800 s; 15.5–17.5 → 2400 s; 17.5–19.3 → 3600 s; ≥19.3 → 5400 s.
  Red splits into 600 s subframes (300 s if mag < 13); blue (less efficient)
  into 900 s (T ≤ 1800), 1200 s (T = 2400–3600), or 1800 s (T ≥ 5400)
  subframes, ≥2 per arm, keeping red_total ≈ blue_total. Cell strings are
  "N x 600" / "N x 1200"; Duration (hh:mm) = max arm total; slew rows stay
  at 5 min. Implemented in `night_planner/estimate_kast_exposures.py`.

### Skills & tools for telescope night planning (researched 2026-07-11)

**Installable agent/Claude skills**
- **Astropy Claude Code Skill** (mcpmarket) — coordinate transforms (ICRS/Galactic/
  **AltAz**), time-scale conversions (UTC/TAI/TDB), units, FITS I/O. The primitives
  for computing where/when a target is observable.
- **K-Dense-AI `claude-scientific-skills`** — 140+ agent skills (open Agent Skills
  standard, works in Claude Code). Includes an **Astropy** skill and a **SIMBAD**
  astronomical-database skill; astronomy DBs: NASA, SDSS, SIMBAD, Exoplanet Archive.

**Python packages (the computational core — wrap these, don't reinvent)**
- **astroplan** (Astropy-affiliated) — THE observation-planning package: `Observer`,
  `FixedTarget`, observability under constraints (`AirmassConstraint`,
  `AtNightConstraint`, `MoonSeparationConstraint`, `MoonIlluminationConstraint`),
  airmass/parallactic-angle plots, sky charts, and a **Scheduler** (priority /
  sequential). Already a project dependency (prompt 2). This is our engine.
- **Visplot** — web tool: hardware-aware visibility + heuristic scheduling
  (altitude & hour-angle limits, twilight, moon distance); good for ToO triggers.
- **AstroSA** — framework to benchmark/assess schedulers.

**Professional Phase-2 systems (the structure a "night plan" should emulate)**
- **ESO p2** — Observation Blocks (OBs), containers, README, finding charts, ObsPrep.
- **Gemini Observing Tool (OT)** — Phase-II observation definition; same sequences
  run at the telescope. Takeaway: a professional plan = ordered OBs + per-target
  constraints + finding charts + a run README, not just a target list.

**Best-practice knowledge to encode**
- Order targets by meridian transit / optimal airmass; plan around twilight windows,
  Moon phase & separation; check seeing/transparency forecasts (Clear Outside,
  Astrospheric). (Amateur equipment/thermal/night-vision tips are mostly N/A for a
  professional facility.)

**Recommendation:** build a project `night-plan` skill whose engine is **astroplan**,
optionally vendoring the **Astropy** skill for coord/time primitives, and whose
output structure mirrors ESO p2 / Gemini OT (ordered OBs + constraints + finding
charts + README). Awaiting the astronomers' specific telescope/site/instrument
before authoring. See references in Logs/2026/07/2026-07-11.md, Entry 4.

### The astronomers' real night-planning practice (/mnt/scratch/xavier/Observing, read 2026-07-12)

Full detail in [`claudes_context.md`](claudes_context.md), section "Observing
archive". The durable, reusable facts:

- **Run-folder template** (`Observing/<Instrument>/<Run>/`, Run = `2022Oct`,
  `2023A`, `2025A/Feb26`; per-night subfolders for multi-night runs): night-plan
  `.docx` + Keck starlist `.txt` + `inst_config.txt` (SIAS submission) +
  `Targets.docx`/target `.xlsx` + finder-chart docs + (MOS) mask files
  (`.lst`/`.obj`/`.reg`) + `Obs_logs*.xlsx` + backup-target docs + README/
  strategy notes. Instruments in the archive: DEIMOS, HIRES, KCWI, LRIS,
  MOSFIRE, NIRC2, ToO — Keck-centric.
- **Keck starlist format** (spec, verified across DEIMOS/HIRES/LRIS/KCWI
  starlists):
  `name  HH MM SS.ss  ±DD MM SS.s  equinox  [keyword=value …]  [# comment]`
  e.g. `J073802.33+274948.81  07 38 02.33 +27 49 48.81 2000.00 rotdest=128.30
  rotmode=PA vmag=22.0`. Observed keywords only: `rotdest=` (PA deg),
  `rotmode=PA|pa`, `raoffset=`/`decoffset=` (arcsec, star→target),
  `vmag=`, `pmra=`/`pmdec=`, `lgs=`, `pa=`. Conventions: offset stars as
  companion entries `<name>_OFF` / `_o` / `_S1..S3` sharing the target's
  `rotdest`; slitmasks listed by mask ID with mask PA in `rotdest`; imaging
  mosaic pointings `_p1..p4`; `#` comment lines as section headers
  (# Longslit / # FRBs / # Standards) and per-line notes (z, mag, "Beginning
  of night standard").
- **Night-plan doc skeleton** (recurring across DEIMOS 2022Oct, LRIS 2023A,
  HIRES 2026A, KCWI 2018Oct): (1) title + Useful-links (instrument page,
  ucolick ephemeris, weather, starlist, finders); (2) ranked science
  priorities; (3) per-program setup tables (grating/filter/λc, dichroic,
  slicer, decker/XDANGLE, binning, focus); (4) twilight block — open at
  sunset, focus, standard star, align first mask, and a second standard at
  morning twilight; (5) **LST-keyed timeline** bounded by the 18°-twilight
  LST range ("Night 1 (Oct 26: LST = 21:06-7:09 [18deg])"), blocks of
  target/mask + setup + exposures×repeats + contingency notes, mid-night
  MIRA (focus) for DEIMOS; (6) afternoon calibration checklist (biases,
  ThAr arcs, flats, 11× counts); (7) Backup Plans; (8) SA questions (+ phone
  number); (9) appended troubleshooting/lessons (living document); (10)
  pre-run TODO list. HIRES formats the timeline as a table
  (UTStart-End | Target | RA | Dec | Setup | Exp | # | z | mag | Comments).
- **Offset-star acquisition procedure** (DEIMOS 2022Oct README): center the
  `_OFF` star, TO applies the starlist raoffset/decoffset holding the PA →
  faint target in slit with star on-slit as reference; 600–900 s exposures
  with on-the-fly reduction deciding continue/abort/coadd.
- **inst_config.txt** = Keck SIAS form: PI, run_date, n_nights, mode
  checkboxes, and numbered slots for slitmasks/gratings/filters (LRIS also
  grisms/dichroics/blue+red filters, per night) + `slitmask_deadline` —
  hardware is locked weeks ahead; the plan must fit the declared slots.
- **ToO plan** (MOSFIRE FRB 190614D, 2020-12-07): single compact doc —
  trigger/date/instrument, paper, ephemeris, Goals, Setup, Targets(+offset
  star), acquisition rules (offset star J_AB 16–18.5 within 1′, relaxable to
  2′/J=19.5; avoid bright stars — persistence; rotate slit to catch both
  candidates). No LST timeline.
- **Pre-run target tracking table** (DEIMOS 2023Dec `target_info.xlsx`):
  Target | mag | Filter | Survey Image | Exp time per mask | Grating combo |
  Redshift | mask status (Submitted for milling / Milled) | tentative obs
  time (HST) | Comments.
- **Facilities breadth** (`Observations/`): AAO, ALMA, Gemini-N/S, HST, JWST,
  Keck, Lick_Kast, Magellan, MeerTRAP_HighDM, MMT, NOT, Pepsi, SOAR, VLT.
- **Starlist equinox is not always 2000.0**: the blackbody-standard grid
  `DEIMOS/2022July/starlist_blackbody_0hr.txt` uses **equinox 2016.0**
  (Gaia epoch) coordinates with `pmra=/pmdec=` on every line — a starlist
  writer must carry (epoch, pm) per target, not hard-code J2000.

### Lessons from FFFF_PZ, JSkyCalc/thorsky & astropy docs (2026-07-11)

Full survey in [`claudes_context.md`](claudes_context.md); durable takeaways:

- **Definitions to adopt (JSkyCalc/thorsky):** rise/set at sun/moon altitude
  **−0.833°** (zd 90°50′); astronomical twilight at sun alt **−18°**; hour angle
  = LST − RA wrapped to ±12 h; near the horizon use a *true airmass* (Snell &
  Heiser 1968 polynomial) rather than plain sec z; moonlight via the
  **Krisciunas & Schaefer (1991)** V mag/arcsec² sky-brightness model, not just
  a separation cut; report parallactic angle (slit orientation) and barycentric
  time/velocity corrections.
- **Two-layer design (thorsky `Observation` class):** separate *instantaneous
  circumstances* (LST/HA/alt/az/airmass/parallactic/moon/sun) from *per-night
  events* (sunset, −18° twilights, night center, moon rise/set). The single best
  ranking scalar is `hrs_up` — hours tonight above the critical altitude,
  clipped to the twilights.
- **Run/plan data model (FFFF_PZ `FRBFollowUpResource`):** an observing run =
  instrument + UT validity window + N targets per mode (imaging/longslit/mask)
  + selection criteria (survey, status, tags, P_Ox, mag limits) + **max_AM**.
  The plan is a flat pandas table (`TNS, Resource, mode`); the observing log
  returns as a table (`..., Conditions, texp, date, success`) and is ingested
  back to advance per-target statuses (NeedImage → NeedSpectrum → done).
- **Feasibility-filter idiom (FFFF_PZ `frb_targeting.calc_airmasses`):** build
  `Observer` from `EarthLocation.from_geodetic(lon, lat, elev)`; loop nights
  bounded by `twilight_evening/morning_astronomical` (use `which='previous'` to
  step nights safely); sample every 30 min; one vectorized `SkyCoord` array for
  all targets; keep targets whose *minimum airmass over the run* ≤ max_AM.
- **Core astropy recipe:** `target.transform_to(AltAz(obstime=times,
  location=loc))` → `.alt`/`.az`/`.secz`; `get_sun(t)` / `get_body('moon', t,
  loc)` for dark time and moon separation; `Time.sidereal_time('apparent',
  lon)`; `Time.light_travel_time(coord, kind='barycentric')` for BJD. Caveats:
  `.secz` is plane-parallel; AltAz refracts only if `pressure` is supplied.
- **The gap night-planner fills:** FFFF_PZ stops at *which* targets are
  observable in a run; JSkyCalc is a calculator, not a scheduler. Sequencing
  targets *within* the twilight-bounded night is our job (start from
  astroplan's Scheduler).

### FFFF-PZ Resource creation for CHIME FRB runs (HOWTO + chime-ffff-pz, 2026-08-13 prep)

Sources: `context/HOWTOs/FFFF-PZ-HOWTO.pdf` (pp. 6–8) and
`/home/xavier/Projects/FRBs/chime-ffff-pz` (docs/, scripts/, data/Observing/).

- **Naming:** `<Site>-<Semester>-<run#>` (e.g. `Lick-2025B-3`); one Resource
  per observing *run* (1–3 nights), run # unpadded by convention and
  incrementing within the semester. The name keys everything downstream
  (targets/obsplan/logobs/finder commands, git branch, CANFAR folder).
- **Workflow:** (1) hand-write JSON at
  `chime_ffff_pz/data/Observing/<name>/<name>.json`; (2)
  `chime_ffff_pz_add_furesource <json>` (PUT `add_frb_resource/`, HTTP 200;
  often prints a benign "error"); (3) confirm on the web dashboard; (4)
  `chime_ffff_pz_targets <name>` (PUT `targets_from_frb_followup_resource/`,
  HTTP 201) → `<name>_targets.csv` in the same folder (columns: TNS, FRB
  RA/Dec/DM/survey/tags, Pri_*/Sec_* host name/RA/Dec/POx/mag/filter, mode,
  Resource). Selection is stochastic — rerun if too few. Later:
  `<name>_pending.csv` + `chime_ffff_pz_obsplan`, finders, starlist
  (`chime_ffff_pz_starlist <observatory>`), `chime_ffff_pz_logobs`.
- **JSON fields** (Lick/Kast practice, from Lick-2025B-*/2026A-2):
  `instrument="KAST"`, UT `valid_start/valid_stop` (loose window OK — server
  clips to astronomical twilight and applies the min-airmass filter),
  `num_targ_img/mask = 0`, `num_targ_longslit` = 20–30 requested (only ~4–6
  observed per Kast night), `max_AM = 2.0`, `frb_surveys = "all"`,
  `frb_tags/frb_statuses = null` (server default → NeedSpectrum for
  longslit), `max_mag` 19.5–20.5 (PATH primary host r); **omit `min_POx`** —
  setting it overrides the status logic (HOWTO warning).
- **Auth:** `FFFF_PZ_USER/PASS/URL` (`https://frb.chimenet.ca/f4pz/`) from
  `chime-ffff-pz/automation/config/secrets.env`; run in the `astro` conda
  env. Git: branch named after the resource, JSON PR'd to main (author runs
  git). CANFAR registration (`fu_resources.csv` + `canfar_upload -f`) only
  matters for post-run data upload.
- **Keck/LRIS Resource convention (differs from Lick/Kast, added 2026-09-10
  per the author):** always request masked targets too —
  **`num_targ_mask > 0`**, not `0` — alongside `num_targ_longslit`, since
  LRIS (unlike Kast) has a real MOS mode for mag>21 targets. **Never trust
  FFFF-PZ's own `mode` column for the longslit/mask split** — it tags every
  target pulled via `num_targ_longslit` as `"longslit"` regardless of
  magnitude (verified empirically, Keck-2026B-01 Prompt 9: 5/5 mag>21
  targets tagged `"longslit"`). Apply your own mag>21 cut downstream
  instead (see `estimate_mos_exposure()` /
  `LRIS_LONGSLIT_MAG_LIMIT` in `night-planner/scripts/keck_2026oct06_calculations.py`).
- **FFFF-PZ sampling is stochastic per-pull, not just per-Resource:**
  re-running `chime_ffff_pz_targets` on an unchanged Resource, or one with
  only `num_targ_mask`/`num_targ_longslit` tweaked, can return a smaller or
  differently-composed set each time — always re-sync any local copy of a
  `<name>_targets.csv` before trusting downstream numbers.
- **Observing spreadsheet ("possible targs"):** each Lick/Kast run folder in
  obs_docs carries a `possible_targs.xlsx` (sheet `possible_targs`; columns
  TNS, RA_HMS, DEC_DMS, Epoch, Pri_mag, Sec_mag) — primary-host coords in
  sexagesimal, Epoch 2000.0, sorted by RA. Build it from the targets CSV with
  `night_planner/make_lick_possible_targs.py`, which also applies the
  **Shane pointing limit: no targets at Dec > +82°** (author, Q7.1 of the
  2026-08-13 plan). Note the server may return fewer targets than
  `num_targ_longslit` requests (e.g. 14 of 15 for Lick-2026B-01).
- **No conda env literally named `astro` on this machine (found 2026-09-14):**
  despite that name recurring in this project's own prompt files
  (`lick_2026aug13.md` etc.), `conda env list` here shows base, KRO, LRO,
  cigale, **frb_env**, git_page_env, pyar_env, pyp_env (plus micromamba
  `stenv`). The `chime_ffff_pz_*` CLI tools (`add_furesource`, `targets`, …)
  are installed in **`frb_env`**, and `FFFF_PZ_USER/PASS/URL` load correctly
  there from `~/.bashrc`. Use `conda run -n frb_env <chime_ffff_pz_cmd>` —
  check `conda env list` first if a prompt file says "astro" and it doesn't
  exist; don't assume the env name from old docs is still accurate.
- **HA-window-first scheduling pattern (2026-09-14, Lick-2026B-02):**
  the original Lick-2026B-01 night-plan pipeline picked a fixed observing
  order first and only checked/clipped Shane HA limits afterward
  (`fix_ha_limits.py`), which meant the first version of that plan
  violated the limits for all 6 targets. For Lick-2026B-02, compute each
  target's real HA-legal window *before* scheduling — entry/exit time
  where `-5.0h <= HA <= +3.75h`, clipped to the twilight-bounded night —
  then greedily schedule by **earliest window-close time first**
  (`target_window()` / `schedule_night()` in
  `scripts/lick_2026b02_calculations.py`): every scheduled block is
  HA-legal by construction, no after-the-fact patch needed. A target
  whose required exposure doesn't fit its own window, or whose window
  never opens at all, is logged with an explicit reason rather than
  silently dropped (same principle as the Keck scheduler's skip-reason
  logging, see "MOS-required targets" above). Reuse this pattern for
  future Lick/Kast single-night plans instead of scheduling first and
  checking HA second.
- **The legal RA/HA window shifts with the calendar date, and can flip
  which "half" of a target list is usable:** Lick-2026B-01 (Aug 13, LST
  18.0h→1.1h at twilight) could only use RA 15-16h (evening) + RA 0-5h
  (morning); Lick-2026B-02 (Sep 14, LST 19.2h→3.9h) could only use RA
  0-6h (morning) — the RA 8-15.4h band was unusable on *both* dates for
  different reasons relative to that night's LST, and several targets
  reappearing from the 2026B-01 pool (e.g. `TGT0321`) that were
  schedulable in August were *not* schedulable in September. Always
  recompute the HA window fresh per date; don't assume last run's
  observable/unobservable split still holds.
- **Twilight cross-check gotcha (ucolick.org calendar, 2026-09-14):** the
  Lick calendar page is a fixed-width text table; a naive WebFetch prompt
  asking it to "interpret" the row mis-aligned columns and returned the
  **12°-dawn** time under the 18°-twilight-dawn label (30 min off — looked
  plausible, was wrong). Fixed by re-asking WebFetch to quote the raw
  table row *and* header line verbatim, then hand-parsing columns against
  the header (`DAWN BEGINS` has both an `18` and `12` sub-column, in that
  order) rather than trusting a summarized interpretation. Verified
  18°-twilight to within 2 min this way, matching the aug13 precedent.
- **Created Lick-2026B-02 (2026-09-14, single night, run #2 of 2026B):**
  followed the same Resource workflow as Lick-2026B-01, reusing its
  parameters verbatim (max_AM=2.0, frb_surveys=all, tags/statuses=null,
  max_mag=20.5, num_targ_longslit=15). Clean `add_furesource` success (no
  benign-error string this time); `chime_ffff_pz_targets` returned exactly
  15/15 on the first pull. Dec ≤ +82° cut dropped 3 → 12 targets in
  `Night_plans/Lick-2026B-02/`. Two targets (`TGT0321`,
  `TGT0070`) reappeared from the Aug-13 pull with identical host
  coordinates — confirms the stochastic sampler is redrawing from the same
  underlying FFFF-PZ catalog, not a duplication bug. Full report in
  `claude_prompts/night_plans/lick_2026sep14.md`.

### Keck/LRIS Mode Summary (2026-09-09)

**LRIS Observing Modes:**
- **LONGSLIT:** mag ≤ 21 (practical limit for reasonable S/N in ~1h)
- **MOS (slitmask):** mag > 21 requires pre-milled masks (weeks lead time)
- **IMAGING:** Available for acquisition, photometry, or gap-filling

**LRIS Exposure Estimates (longslit):**
| mag_r | Red arm | Blue arm | Total |
|-------|---------|----------|-------|
| ≤14 | 2×180s | 2×180s | 11 min |
| 14-17 | 2×600s | 2×600s | 25 min |
| 17-19 | 3×600s | 3×600s | 35 min |
| 19-20.5 | 4×600s | 4×600s | 45 min |
| 20.5-21 | 5×600s | 5×600s | 55 min |

**Keck Pointing Limits:**
- Dec ≥ -37° (horizon limit)
- HA: -5.5h to +5.5h
- Zenith blind spot negligible

**Keck vs Lick Target Compatibility:**
- Lick (lat 37°) can observe Dec up to +82°
- Keck (lat 20°) struggles with Dec > 70° (high airmass)
- Targets at Dec > 82° excluded from Lick are observable from Keck at AM ~2.4
- For Keck runs, query FFFF-PZ with Dec < 60° for optimal coverage

### Keck Observatory coordinates (verified 2026-09-11)

`EarthLocation`: **lat 19.828333°N, lon -155.478333°W, height 4160 m**
(matches `astropy.coordinates.EarthLocation.of_site('keck')`, sourced from
the IRAF Observatory Database — the canonical reference, not a web search).
An earlier hardcoded value used lat 19.8263° (wrong by ~7 arcsec); fixed in
both Keck scripts. If a coordinate for Keck ever needs re-deriving, check
`EarthLocation.of_site('keck')` first rather than searching the web.

### Keck slew-time rule (all Keck instruments, per the author 2026-09-29)

- **Base slew = 10 min** between any two pointings (was 5 min on
  2026-09-29, raised to 10 by the author 2026-09-30).
- **Moving from Dec < +20° to Dec > +20° = 20 min.** Only the south-to-north
  crossing, as stated; north-to-south stays at the base 10 min.
- **MOS blocks get +5 min buffer per mask** (`MOS_MASK_BUFFER_MIN`) on top
  of the 60/90/120 min allocation (per the author 2026-09-30).
- **Late in the run, only schedule masks that exist or can still be milled**
  (`MOS_MASKS_AVAILABLE`); other mag>21 targets are rejected at a "2b. Mask"
  stage. The author said milling new masks close to the run is very hard, so
  when a re-pull brings in new MOS targets, check which masks are new.
- Applies to every Keck instrument (LRIS, DEIMOS, ...), so it lives in the
  shared `scripts/keck_overheads.py` (`keck_slew_minutes(from_dec, to_dec)`),
  not in an LRIS-specific file.
- Slew is charged by the scheduler per transition (it depends on the previous
  pointing), starting from the evening standard's Dec and including the slew to
  the morning standard. On-target time is `science_min`: for longslit that is
  the ETC exposure total (the old flat "+5 slew/acquisition" in `lris_etc`'s
  `total_min` is replaced by the slew); for MOS the 60/90/120 min block
  already includes mask-alignment overhead (per the author).
- Before this rule, slews were a flat 3 min in the xlsx while the scheduler
  budgeted 5 min, so the two scripts disagreed. Keep one source of truth.

### Keck-specific corrections to the Lick-derived scripts (2026-09-10)

The Keck scripts (`scripts/keck_2026oct06_calculations.py`,
`build_keck_night_plan.py`) started as adaptations of the Lick/Kast scripts
and initially carried over Lick-shaped assumptions. Two Keck-specific facts
now implemented:

- **Target-selection rule:** Keck's 10m aperture shouldn't re-observe what
  Lick's 3m already reaches. Rule: keep a target only if `mag_r > 19.0`,
  unless `Dec > 82°` (Lick/Shane's pointing limit — unreachable from Lick at
  any magnitude). `KECK_MAG_FAINT_LIMIT = 19.0`, `LICK_DEC_LIMIT = 82.0`,
  `passes_keck_target_selection()`.
- **Keck I Nasmyth-deck vignetting (real limits, not a generic alt floor):**
  source, Keck Telescope Pointing Limits
  (www2.keck.hawaii.edu/inst/common/TelLimits.html). Keck I's Nasmyth deck
  blocks the beam in a **fixed azimuth band, az 5.3°-146.2°** (N through E to
  SE) unless altitude ≥ 33.3°; elsewhere the floor is ~18°. This band is N/E
  for Keck I specifically — **Keck II is blocked S/W instead** (opposite
  side). LRIS is on Keck I, so a target **rising** through the NE/E sits in
  the blocked band at low altitude and must climb to 33.3° before it clears
  the deck ("wait for the target to rise"); a target **setting** in the W/SW
  clears at the normal 18° floor, so setting targets are the easier catch on
  Keck I. Implemented as `check_keck1_nasmyth_vignetting(az, alt)`, folded
  into `check_keck_limits()` (now takes `az` too).
- **Effect on the Keck/LRIS plan (date later corrected to Oct 6, see v0.35):** applying both to the (Lick-sourced)
  Lick-2026B-01 target pool dropped it from 6 targets/2.6h to **1 target/11
  min (2% utilization)** — most of the pool is either too bright (mag≤19,
  Dec≤82°) or fails the real Nasmyth check while rising. This exposed that
  the target *pool* itself needs a Keck-specific FFFF-PZ query (mag>19,
  Dec<60°), not just Keck-corrected scheduling logic. Full detail:
  `Night_plans/Keck-2026B-01/KECK_LRIS_2026OCT06_SUMMARY.md`, Prompt 5.

### Created a real Keck-2026B-01 FFFF-PZ Resource (2026-09-10, Prompt 6)

Followed the standard FFFF-PZ Resource workflow (see "FFFF-PZ Resource
creation" above) to replace the filtered-Lick-pool workaround with a genuine
Keck-native target list:
`chime-ffff-pz/chime_ffff_pz/data/Observing/Keck-2026B-01/Keck-2026B-01.json`
— `instrument="LRIS"`, `min_mag=19.0`/`max_mag=null` (the mag>19 rule
implemented server-side, matching the convention already used by
`Keck-2026A-8`/`Keck-2025B-2`), `num_targ_longslit=20`, `max_AM=2.0`. Ran
`chime_ffff_pz_add_furesource` then `chime_ffff_pz_targets Keck-2026B-01`
(both succeeded); copied the resulting `_targets.csv` (15 targets) into
`night-planner/Night_plans/Keck-2026B-01/` and repointed
`scripts/keck_2026oct06_calculations.py` at it.

- **Credentials note:** no `automation/config/secrets.env` exists on this
  machine (only the template + a `secrets_test.env`). `FFFF_PZ_USER/PASS/URL`
  are instead exported directly in `~/.bashrc`, pointing at a docker-hosted
  instance (`http://0.0.0.0:8000/`) — confirmed live and already holding real
  runs (e.g. `Lick-2026B-01`). `add_modify_resource.py`/`targets.py` read
  those env vars directly, no secrets file required. Asked the author before
  writing anything since it's a real write to a shared server; the author
  pointed at `.bashrc` as the credential source.
- **Bug found and fixed:** `select_targets_for_night()` was scheduling
  mag>21 (MOS-mask-required) targets into the night's timeline as 0-minute
  "observations" — masks take weeks to mill, so they can't be used this run.
  Now filtered out of the schedulable set (`lris_mode == 'MOS (mask
  required)'`); they still appear in the separate MOS-planning warning for
  tracking toward a future run.
- **Result:** of 15 Keck-native targets, 10 pass sky-observability
  (HA + Nasmyth-deck), but 6 of those are MOS-only (mag>21) — leaving 4
  real longslit targets, **3.3h science / 9.7h dark (35% utilization)**, up
  from 1 target/2% on the filtered Lick pool. Confirms: a dedicated
  Keck-specific FFFF-PZ Resource beats filtering another site's list. Full
  detail in `KECK_LRIS_2026OCT06_SUMMARY.md`, Prompt 6.
- **Gotcha:** `Keck-2026B-01_targets.csv` has 16 *lines* but only 15
  *targets* (1 header row) — easy to miscount by eye. The 15→4 funnel (5 fail
  sky-observability, 6 of the remaining 10 are MOS-only/mag>21) is spelled
  out as an explicit diagram at the top of the Target Analysis section in
  `KECK_LRIS_2026OCT06_SUMMARY.md` — point there first if this comes up again
  instead of recounting from the CSV.

### Real LRIS exposure-time calculator (2026-09-10, Prompt 7)

The `estimate_lris_exposure()` magnitude-bucket table (adapted from an
equally hand-wavy Kast heuristic via an arbitrary "LRIS is ~2x more efficient
than Kast" fudge factor) had no basis in throughput/sky/read-noise physics.
Replaced it with `scripts/lris_etc.py`, a client for the **real UCO/Lick web
S/N calculator** at etc.ucolick.org — the same engine behind the official
web LRIS/Kast/DEIMOS/ESI/HIRES ETCs, and callable directly as JSON
(`POST https://etc.ucolick.org/web_s2n/gen_inst_s2n`, no auth), not just
through the browser form.

- **Setup used:** grism 600/4000 (blue), grating 600/7500 centered ~7200 Å
  (red), dichroic D560, slit 1.0", binning 2x2 — the author's actual standard
  Keck/LRIS FRB-host config. Correcting a stale assumption: this repo
  previously documented 400/3400 blue / 400/8500 red, which the real ETC
  can't even model (see next point).
- **ETC coverage gotcha:** the ETC's blue-grism dropdown only *works* for
  B300 (300/5000) and B600 (600/4000) — B400 (400/3400) and B1200 return an
  **empty result with no error message** (`errormsg=""`, zero-length `s2n`
  array). Always check the array is non-empty, not just the error field,
  when validating this API. Red-grating options (600/7500, 600/10000,
  1200/9000, 400/8500, 831/8200) all work; only D560 dichroic is modeled.
- **Target S/N convention (per the author):** median S/N = 5 per pixel,
  continuum, measured in a blue window (4200-5200 Å) and a red window
  (6500-7500 Å) separately; the longer-required arm sets the simultaneous
  dual-beam wall-clock time (both arms expose together). Split into ≥2
  sub-exposures of ≤600s each for cosmic-ray rejection.
- **Method:** `required_exptime()` uses real ETC calls at each step (S/N≈√t
  only picks the *next exptime to try*, never assumed as the final answer),
  iterating to within 5% of the target S/N.
- **TLS note:** etc.ucolick.org's cert is genuinely CA-issued
  (InCommon/Sectigo) but the server doesn't send its intermediate — confirmed
  via `openssl s_client -showcerts` before reaching for `verify=False`.
  Fetched the one missing intermediate from the leaf cert's `Authority
  Information Access` CA-issuers URL and ship it alongside `certifi`'s bundle
  (`scripts/certs/ca_bundle_with_incommon.pem`) so verification still works
  properly.
- **Result:** at S/N=5, real LRIS exposures for mag 20-21 targets are ~1-3
  min of science time (7-11 min incl. overhead), not the 45-55 min the old
  heuristic gave — roughly a 15x overcorrection, consistent with Keck's 10m
  vs. Lick's 3m being ~11x the collecting area (the old heuristic's flat "2x"
  fudge factor was never close). Rerunning the Keck/LRIS plan (date later corrected to Oct 6, see v0.35) dropped total
  science time from 3.3h to 0.6h for the same 4 targets.
- **New implication:** with real (short) exposure times, utilization is now
  limited by *target count*, not exposure time — the plan uses only 6% of
  the night with just 4 targets in hand. Future Keck FFFF-PZ pulls should
  request many more targets (`num_targ_longslit` well above 20), since each
  one is now cheap in telescope time. Full detail in
  `KECK_LRIS_2026OCT06_SUMMARY.md`, Prompt 7.

### Correction: target S/N must be per single sub-exposure, not combined (2026-09-10, Prompt 8)

The author caught a real bug in the Prompt 7 model, not just a disagreement
of taste. `estimate_lris_exposure_real()` had searched for one *combined*
exposure time hitting `target_sn` (5), then divided that combined time across
sub-exposures — so each individual frame actually carried *less* than the
target S/N (e.g. "2×170s" each only reached S/N≈3, not 5). The author's own
recalled minimum for mag 21 ("≥15 min per exposure, ≥3 exposures") lines up
almost exactly with **S/N≈10 measured per single exposure** — confirmed
directly against the ETC's real S/N-vs-exptime curve (60s→1.3, 170s→3.0,
300s→4.5, 600s→7.0, 900s→8.9, 1200s→10.5 at mag 21, red arm).

**Fixed model:** `target_sn` (now default **10**) is the S/N required of one
single sub-exposure; the sub-exposure count is a separate fixed **minimum of
3** (cosmic-ray rejection — 2 frames can only flag a CR discrepancy, 3+ lets
you median-reject it; not derivable from S/N). Total time per target is now
`3 x (single-exposure time to hit S/N=10)`, not a combined time split three
ways.

**Result:** total science time for the Keck/LRIS plan's same 4 targets rose
from 0.6h (Prompt 7's under-delivering version) to **2.3h / 9.7h (23%
utilization)** — e.g. mag 21 (TGT0456): 3×1060s (58 min), vs. 2×170s
(10.7 min) under the buggy version and 45-55 min under the original
heuristic. 23% is the number that should stand. Full detail in
`KECK_LRIS_2026OCT06_SUMMARY.md`, Prompt 8.

**General lesson:** "combined S/N across N frames" and "S/N per single
frame, N times" are different targets — a real ETC call can still be wired
into the wrong quantity. When a domain expert's gut-check number disagrees
with a calculator's output by a large, consistent factor, reverse-engineer
what quantity their number is actually describing before assuming either
side is simply wrong — it pinned down the missing parameter here almost
exactly.

### MOS-required targets are scheduled directly, not just flagged (2026-09-11, Prompt 10)

Per the author: a mag>21 target isn't excluded from the night plan just
because it needs a mask -- it goes into the schedule with its real
allocated time (`estimate_mos_exposure()`, ~1-2h), on the working
assumption a mask can be milled before the run. `select_targets_for_night()`
in `scripts/keck_2026oct06_calculations.py` no longer drops
`lris_mode == 'MOS (mask required)'` rows before scheduling. MOS rows are
tagged `[MOS - MASK REQUIRED]` / `MASK REQUIRED` in the console timeline,
starlist, and Excel so it's unambiguous at the telescope which targets are
contingent on a mask actually existing by run night.

Added while doing this: skip-reason logging in the scheduler (it silently
`continue`d before). This immediately surfaced a real geometric constraint
that had been invisible: a target whose required exposure time exceeds what
fits in its own airmass<2.0 window gets correctly dropped, and now says why
(e.g. "needs 120 min but only 70 min left in its AM<2.0 window"). Lesson:
a silent `continue` in a scheduler hides genuine constraints, not just
uninteresting ones -- log the reason at every skip point.

## Version History

- **v0.1 — 2026-07-11:** Created during start-up prompt 1. Seeded project purpose,
  working conventions, and repository layout. Astronomy/night-planning knowledge
  section is a placeholder pending the astronomers' input.
- **v0.2 — 2026-07-11:** Start-up prompt 2 ("Basic start up"). Added Python
  packaging scaffolding (setup.py/setup.cfg/pyproject.toml, requirements.txt,
  `night_planner/` package, `tests/`) following the author's linetools/XAI
  convention. Recorded those conventions and the settings.json recommendation
  (copy XAI's — already in place). Chose astronomy deps: numpy, astropy,
  **astroplan** (observability/scheduling), matplotlib, pyyaml.
- **v0.3 — 2026-07-11:** Start-up prompt 3 (1st task under "Skills"). Copied the
  `grill-me` and `critical-partner` skills verbatim from ClimateIntelligence into
  `.claude/skills/` (both single-file SKILL.md, project-agnostic, no edits needed).
- **v0.4 — 2026-07-11:** Start-up prompt 4 (2nd task under "Skills"). Web-searched
  for skills/tools to help Claude learn telescope night planning; recorded findings
  in the "Skills & tools" subsection above (astroplan core; Astropy & SIMBAD agent
  skills; ESO p2 / Gemini OT as structural models). No skills installed yet —
  presented recommendations to the author for a decision.
- **v0.5 — 2026-07-11:** Executed context_prompts.md Code prompt 1 on the Fable 5
  model. Examined FFFF_PZ and JSkyCalc repos + astropy docs; wrote
  context/claudes_context.md and recorded new night-planning concepts here.
- **v0.6 — 2026-07-11:** Executed context_prompts.md Websites/Ephemeris prompt 1
  on the Fable 5 model. Documented the UCO/Lick & Keck calendar ephemeris sites
  in context/claudes_context.md.
- **v0.7 — 2026-07-11:** Executed context_prompts.md Websites/Instrument-manuals
  prompt 1 on the Fable 5 model. Summarized Lick/Keck/Palomar/Gemini instruments
  in context/claudes_context.md.
- **v0.8 — 2026-07-12:** Executed context_prompts.md Night-plans prompt 1 on the
  Fable 5 model. Summarized the /mnt/scratch/xavier/Observing archive (run-folder
  convention, Keck starlist format, night-plan doc anatomy) into
  context/claudes_context.md.
- **v0.9 — 2026-07-13:** Executed context_prompts.md Night-plans prompt 2 on the
  Fable 5 model — synthesized targets & observing strategies into the Responses
  subsection of claude_prompts/context_prompts.md, with pointers into the context
  and brain files. Added the Gaia-epoch (equinox 2016.0 + proper motions)
  starlist fact noted while re-verifying archive files.
- **v0.10 — 2026-08-13:** Lick 2026-08-13 plan prep (Fable 5). Read the
  FFFF-PZ HOWTO PDF and the chime-ffff-pz repo; added the "FFFF-PZ Resource
  creation" subsection (naming convention, JSON fields, add_furesource →
  targets workflow, auth, per-night Kast capacity). Posed Q&A in
  claude_prompts/night_plans/lick_2026aug13.md; no Resource generated yet.
- **v0.11 — 2026-08-10:** Generated the Lick-2026B-01 Resource (Fable 5):
  wrote/uploaded the JSON (clean success), pulled 14 targets, and built the
  observing spreadsheet via the new `night_planner/make_lick_possible_targs.py`
  (Dec ≤ +82° Shane cut dropped 2 targets → 12 in
  Night_plans/Lick-2026B-01/). Added the possible-targs spreadsheet
  convention and the Dec +82° pointing limit above.
- **v0.12 — 2026-08-10:** Built the Lick-2026B-01 Night plan (Fable 5) via the
  new `night_planner/make_lick_night_plan.py` →
  `Night_plans/Lick-2026B-01/Lick_2026B-01_Night_plan.xlsx`. Departure from
  the archive template (per the author's explicit prompt): science sheets are
  named per target TNS (12 sheets, RA order) instead of per night. Checklist
  copied from `Lick_2026A-4_Night_plan.xlsx` with Done flags reset; exposure
  times and Kast red/blue setup left blank (deferred to the observer); watch
  out that the archive template stores some sexagesimal DEC values as Excel
  time cells (negative decs silently lose their sign) — always write RA/DEC
  as text.
- **v0.13 — 2026-08-10:** Added Kast exposure estimates to the Lick-2026B-01
  Night plan (Fable 5) via the new `night_planner/estimate_kast_exposures.py`:
  d57 / red 600/7500 / blue 600/4310 / 2" slit, with the r-mag → total-
  integration heuristic calibrated to 9 prior Lick/Kast plans (recorded above
  under Astronomy knowledge). Filled red side / blue side / Duration on each
  target's "Science + overhead" row, set slew rows to 0:05, and stamped the
  Kast setup note in cell Q1 of every target sheet; Redshift left blank
  (unknown pre-obs).
- **v0.14 — 2026-08-10:** Wrote the Lick-2026B-01 target-selection report
  (Fable 5) into the prompt file's Reports section. Durable fact: CHIME FRB
  tag definitions (CHIME-Blind/-Repeater/-Unbiased/-Lowz/-GBO/-Bright/-KKO,
  etc.), including their stochastic-draw weights and per-sample cuts, live in
  `chime-ffff-pz` at `chime_ffff_pz/data/Criteria/*.json`.
- **v0.15 — 2026-08-11:** REGENERATED Lick-2026B-01 Night plan (Sonnet 4.5
  via lordrick). Corrected sheet structure: date-named sheets ("August 13th")
  not target-named, matching the Lick-2026A-4 template. ~~Added full Lick/Shane
  pointing constraints: **Dec ≤ +82°**, **RA ≥ 5h** (no targets west of 5h),
  **HA ≥ -3:45h** (cannot observe west of 3h45m HA).~~ **[WRONG - see v0.16]**
  Created automated calculation scripts: `scripts/lick_2026b01_calculations.py`
  (LST/twilight/airmass/target-selection) and `scripts/build_night_plan.py`
  (Excel generation from selected targets). For Aug 13, 2026: **18° astronomical
  twilight** 21:38 PDT / 20:38 PST (LST 18h02m) to 04:46 PDT / 03:46 PST
  (LST 1h11m), timeline starts 21:30 PDT. **Lick calendar timezone
  convention:** tables use "PST" label year-round (actual UTC-8), even in
  summer when local time is PDT (UTC-7); verified against
  ucolick.org/calendar (2-3 min agreement). ~~Of 12 viable targets (after Dec
  cut), 8 pass all pointing limits; selected 6 for night 1 (TGT0172,
  TGT0059, TGT0321, TGT0548, TGT0070, TGT0423)
  totaling ~520 min for 7.1h night.~~ **[4 of 6 targets WRONG - see v0.16]**
  Night plan → `Night_plans/Lick-2026B-01/Lick_2026B-01_Night_plan.xlsx`.
- **v0.16 — 2026-08-12:** CORRECTED Lick-2026B-01 Night plan (Sonnet 4.5
  via lordrick). **CRITICAL FIX:** v0.15 had wrong Shane pointing limits.
  **CORRECT constraints:** (1) **Dec ≤ +82°**, (2) **HA: -5h ≤ HA ≤ +3.75h**
  (symmetric - cannot point >5h east OR >3.75h west of meridian), (3) **NO
  RA limits** - observable RAs depend on LST and time of year. **Hour angle
  convention:** HA = LST - RA (±12h); negative HA = east of meridian (before
  transit), positive HA = west (after transit). Of 12 viable targets (after
  Dec cut), **only 6 pass HA limits during the night**: 2 evening (RA 15-16h:
  TGT0172, TGT0059), 4 morning (RA 0-5h: TGT0060, TGT0506,
  TGT0176, TGT0252), totaling **420 min** (7.0h). **Rejected:** 6
  targets at RA 9-13h (always HA > +3.75h, too far west). v0.15 incorrectly
  selected 4 of these rejected targets! Created
  `scripts/observable_ra_calculator.py` showing time-dependent RA windows.
  Full corrections in `Night_plans/Lick-2026B-01/CORRECTIONS_SUMMARY.md` and
  `HOWTO_night_plan_creation.md`. **KEY LESSON:** Always verify telescope
  mechanical limits with observer - HA constraints create LST-dependent RA
  windows, not static forbidden zones.
- **v0.17 — 2026-09-09:** Created Keck/LRIS night plan for Oct 2, 2026 (Opus 4.5
  via lordrick). New scripts: `scripts/keck_2026oct06_calculations.py` and
  `scripts/build_keck_night_plan.py`. Added LRIS mode summary (longslit mag ≤21,
  MOS for fainter, imaging available). Discovered Lick targets (high Dec) poorly
  suited for Keck (lat 20°) - only 6/14 observable. Added Lick-excluded target
  TGT0407 (Dec 84°, mag 13.3) observable from Keck at AM ~2.5. Output in
  `Night_plans/Keck-2026B-01/`. Recommendation: query FFFF-PZ with Dec < 60° for
  proper Keck coverage.
- **v0.18 — 2026-09-10:** Corrected Keck-specific params in
  `scripts/keck_2026oct06_calculations.py` (Sonnet 5). Added the
  mag>19-unless-Dec>82° target-selection rule and the real Keck I Nasmyth-deck
  vignetting check (researched at www2.keck.hawaii.edu/inst/common/TelLimits.html
  — az 5.3-146.2° needs alt≥33.3°, N/E for Keck I, opposite for Keck II),
  replacing the old generic alt<10° floor. Regenerated all outputs; result
  dropped from 6 targets/2.6h to 1 target/11 min (2% utilization), exposing
  that the Lick-2026B-01 pool itself is unsuited for Keck and a fresh
  Keck-specific FFFF-PZ query is the real fix. Full detail recorded above
  under "Keck-specific corrections to the Lick-derived scripts".
- **v0.19 — 2026-09-10:** Created a genuine `Keck-2026B-01` FFFF-PZ Resource
  (Sonnet 5) per the standard workflow — folder + JSON
  (`instrument=LRIS`, `min_mag=19.0`) in `chime-ffff-pz/.../Observing/`,
  `chime_ffff_pz_add_furesource` + `chime_ffff_pz_targets`, copied the
  15-target pull into night-planner and repointed
  `keck_2026oct06_calculations.py` at it. Also fixed a real scheduling bug
  (MOS-mask/mag>21 targets were being scheduled as 0-min "observations").
  Result: 4 real longslit targets, 3.3h/9.7h (35% utilization) — confirms a
  Keck-native pull beats filtering the Lick list. Full detail above under
  "Created a real Keck-2026B-01 FFFF-PZ Resource".
- **v0.20 — 2026-09-10:** Replaced the magnitude-bucket LRIS exposure
  heuristic with a real physical calculator (Sonnet 5). New
  `scripts/lris_etc.py` calls the real UCO/Lick web S/N calculator
  (etc.ucolick.org, JSON API) targeting S/N=5/pixel continuum per the
  author, using the author-confirmed real setup (grism 600/4000, grating
  600/7500 ~7200Å — corrected from a stale 400/3400/400/8500 assumption).
  Result: exposure times for mag 20-21 targets dropped from a 45-55 min
  heuristic to 7-11 min real (~15x), consistent with Keck's ~11x collecting
  area over Lick that the old flat "2x" fudge factor never captured. Total
  science time for the Oct 2, 2026 plan: 3.3h → 0.6h (same 4 targets) —
  utilization is now target-count-limited, not exposure-time-limited. Full
  detail above under "Real LRIS exposure-time calculator".
- **v0.21 — 2026-09-10:** Fixed a real bug the author caught in v0.20's
  model (Sonnet 5): target S/N was being hit *combined* across sub-exposures,
  so each individual frame under-delivered. Reverse-engineered the author's
  recalled "≥15 min/exposure, ≥3 exposures" at mag 21 against the ETC's real
  S/N-vs-exptime curve → confirmed S/N≈10 per *single* exposure was the
  actual intended target. Fixed `estimate_lris_exposure_real()`: target_sn=10
  per single sub-exposure, fixed minimum of 3 sub-exposures (CR-rejection,
  not S/N-derived). Science time for the same 4 targets: 0.6h → 2.3h (23%
  utilization) — the number that should stand. Full detail above under
  "Correction: target S/N must be per single sub-exposure, not combined".
- **v0.22 — 2026-09-10:** Added real MOS-mask handling and an explicit
  `info` column (Sonnet 5), per the author. New
  `estimate_mos_exposure()`: mag≤23→1h, 23-24→1.5h, ≥24→2h on-target time
  once a mask is milled (an operational bucket, not physics; 23-24 split
  point is this project's own interpolation of the author's "1.5-2h fainter"
  range). `target_analysis.csv` now carries an `info` column flagging every
  mag>21 target regardless of FFFF-PZ's own tag. Confirmed empirically that
  FFFF-PZ's `mode` column is untrustworthy for the longslit/mask split (see
  new "Keck/LRIS Resource convention" note above) — always request
  `num_targ_mask>0` going forward and apply our own mag cut regardless. Also
  synced a fresh, smaller (10-target) FFFF-PZ pull the author had made
  directly by editing the Resource JSON — re-ran the full pipeline: 2
  targets schedulable tonight (TGT0456, TGT0574), 1.4h/9.7h (14%
  utilization), 4 real MOS candidates with real time estimates attached.
  Full detail in `KECK_LRIS_2026OCT06_SUMMARY.md`, Prompt 9.
- **v0.23 — 2026-09-11:** Per the author, MOS-required targets now go
  *into* the actual schedule with their allocated time (Sonnet 5), not just
  a separate warning — v0.22 had computed real MOS timing but still excluded
  them from `select_targets_for_night()`'s output. Removed that exclusion
  (`estimate_lris_exposure()` already dispatches correctly); tagged MOS rows
  `[MOS - MASK REQUIRED]` / `MASK REQUIRED` in the console timeline,
  starlist, and Excel so it's unambiguous at the telescope which targets
  still need a milled mask. Also added skip-reason logging to the scheduler
  (previously silent), which immediately surfaced a real constraint:
  TGT0461 (mag 25.6, needs the full 2h MOS bucket) doesn't fit its own
  ~100-min airmass<2.0 window once other targets claim earlier time, so it's
  correctly excluded — not a bug, a genuine geometric conflict. Result: 5
  targets in the plan (2 longslit + 3 MOS), 4.4h/9.7h (45% utilization), up
  from 2 targets/14%. Full detail in `KECK_LRIS_2026OCT06_SUMMARY.md`,
  Prompt 10.
- **v0.24 — 2026-09-11:** Fixed a real Keck site-coordinate error (Sonnet
  5), per the author's question. `KECK = EarthLocation(...)` in both Keck
  scripts had latitude 19.8263°N; checked against
  `astropy.coordinates.EarthLocation.of_site('keck')` (IRAF Observatory
  Database, the canonical source) and found the correct value is
  19.828333°N — off by ~7 arcsec (~220 m). Longitude (-155.4783°) and
  elevation (4160 m) were already exactly right. Fixed both files with a
  comment citing the verification source. Impact on this run: negligible
  (same twilight times, same 5 targets, airmass shifted only in the
  4th-5th decimal) — fixed anyway since a hardcoded site constant should be
  correct regardless of whether current targets are sensitive to the error.
  Full detail in `KECK_LRIS_2026OCT06_SUMMARY.md`, Prompt 11.
- **v0.25 — 2026-09-14:** Created the `Lick-2026B-02` FFFF-PZ Resource
  (Sonnet 5) for the single night of 2026-09-14, run #2 of semester 2026B —
  reused all Lick-2026B-01 parameters per the author. Discovered no `astro`
  conda env exists on this machine; used `frb_env` instead (where the
  `chime_ffff_pz_*` CLI actually lives). Clean upload, 15/15 targets on the
  first pull, Dec ≤ +82° cut → 12 viable targets in
  `Night_plans/Lick-2026B-02/`. Recorded the env correction above so it
  isn't rediscovered next run. Full detail in
  `claude_prompts/night_plans/lick_2026sep14.md`.
- **v0.26 — 2026-09-14:** Built the Lick-2026B-02 Night plan (Sonnet 5),
  fixing the schedule-then-check-HA ordering bug from 2026B-01 by
  computing each target's HA-legal window before scheduling
  (`scripts/lick_2026b02_calculations.py`, earliest-window-close-first
  greedy scheduler) and generating the workbook from that schedule
  directly (`scripts/build_lick_2026b02_night_plan.py`). Verified 18°
  twilight against the live Lick calendar via WebFetch (within 2 min,
  after redoing a first fetch that mis-parsed the fixed-width columns).
  Result: 4 of 12 targets schedulable (250 min / 517 min night, 48%
  utilization), one real 137-min dead-time gap logged explicitly on the
  sheet. Recorded the reusable scheduling pattern and the date-dependent
  RA/HA window fact above. Full detail in
  `claude_prompts/night_plans/lick_2026sep14.md`.
- **v0.27 — 2026-09-14:** Author asked, for Lick-2026B-02, "why was each
  target rejected" and asked that a detailed per-target analysis always
  be produced, as a `.md` file. Wrote
  `scripts/target_rejection_analysis.py`, which walks every target from
  the *original* (pre-Dec-cut) pull through each filter stage in order
  (Dec cut -> HA window -> scheduling) and records the specific numeric
  reason at whichever stage it was dropped (or accepted), writing
  `Night_plans/<run>/target_rejection_analysis.md` (summary table +
  per-target detail section). **Going forward: produce this rejection
  analysis file for every night plan**, not just when asked — it's cheap
  (reuses `analyze_targets`/`schedule_night` from the run's calculations
  script) and turns "why isn't X in the plan" into a lookup instead of a
  fresh derivation each time.
- **v0.28 — 2026-09-15:** Two follow-ups on Lick-2026B-02 (Sonnet 5).
  (1) **HA-wrap display bug**: `target_rejection_analysis.py`'s
  `ha_never_legal_reason()` unwraps the morning-twilight HA past +12h
  (needed internally so it stays monotonically ≥ the evening HA for the
  "HA only increases through the night" check) but was reusing that same
  unwrapped value in the printed report text — displayed end-of-night HA
  could exceed ±12h. Fix: keep the unwrapped value for comparisons only;
  add a separate wrapped copy for display. **Lesson: whenever a value is
  deliberately unwrapped/denormalized for an internal comparison, keep a
  separately-named wrapped copy for anything user-facing — don't let the
  comparison variable leak into report strings.**
  (2) **Gap-fill "extras" from the full FFFF-PZ table**: added
  `scripts/lick_2026b02_extras.py`, pulling the *entire* FFFF-PZ table
  (`chime_ffff_pz_frbtable`/`get_table_from_ffffpz()` — no Resource
  binding, no stochastic sampling, unlike `chime_ffff_pz_targets`) and
  filtering to lower-priority FRBs (author-confirmed: status
  `AmbiguousHost`/`TooDusty` only — excludes `RunPublicPATH` "won't have
  hosts to look at" and the already-completed `GoodSpectrum`/`Redshift`;
  POx >= 0.6 floor, no ceiling since `min_POx` is never hard-coded in this
  repo) not already in the primary pull, then scheduling them into the
  primary schedule's idle intervals on a **separate** CSV/`.md`/Excel
  sheet (`Extras (Gap-Fill)`) so they're never confused with the primary
  science targets. **Scheduling gotcha caught before trusting the
  output**: the segments before the first primary target and after the
  last are *not* free — they're already consumed by the fixed
  focus/standard-star/bias/flat calibration blocks the Excel builder
  wraps around the science schedule — and a placed extra needs a slew
  buffer reserved on *both* sides, not just the side facing "now". Only
  gaps strictly between two primary targets, shrunk by
  `SLEW_MINUTES` on each end, are safe to fill. Full detail in
  `claude_prompts/night_plans/lick_2026sep14.md` (Prompts 3-4).
- **v0.29 — 2026-09-14:** Author asked to force-schedule a previously-skipped,
  too-short-window target (`TGT0604`) as the very first thing of the
  night anyway, accepting a partial exposure, and estimated this would push
  the rest of the schedule ~45-50 min later. Added `forced_first` support to
  `schedule_night()` (`FORCED_FIRST_TNS` constant) and computed the *actual*
  shift: ~30 min, not 45-50. **Lesson: a target's HA-legal window closes at
  a fixed clock time (the Shane HA_MAX mechanical limit), not a fixed
  duration after it starts** — starting a forced target earlier only
  captures more of a window whose end is already set; it doesn't buy back
  time elsewhere. And if much of that window overlapped time that was
  already idle (e.g. waiting for the *next* target's own `HA_MIN` rising
  limit to open), the real knock-on delay is smaller than a naive
  "duration consumed" estimate suggests — worth computing explicitly
  rather than trusting a round-number guess, even the author's own.
  Second lesson: **this pipeline's Focus/Standard-star overhead is only
  modeled at the Excel-building layer, not in `schedule_night()`'s own
  `current_time`** — fine as long as that overhead always lands inside
  pre-existing slack (true for every normal night so far), but the moment
  it doesn't (a forced-first target with no slack before the next
  target), the CSV and the Excel sheet silently disagree and produce a
  real overlap. Fixed by adding `FOCUS_MINUTES`/`STD_STAR_MINUTES` to the
  calculations script itself for this specific override, but worth
  remembering this gap exists generally. Full detail in
  `claude_prompts/night_plans/lick_2026sep14.md` (Prompt 5).
- **v0.30 — 2026-09-14:** Generated real finder charts and starlists for
  Lick-2026B-02 via `chime-ffff-pz`'s own tools (`chime_ffff_pz_finder`,
  `chime_ffff_pz_starlist` — see that repo's `observing-prep` skill),
  replacing the earlier placeholder `make_lick_2026b02_starlist.py` (which
  its own docstring admitted just reused PATH primary-host coordinates,
  no offset star, no slit centering/PA, because no finder-chart step had
  been run yet). **Key mechanic: `chime_ffff_pz_finder <TNS> <fu_resource>`
  isn't gated by Resource membership** — it fetches the FRB's PATH
  candidates directly (`grab_frb`) and only uses the Resource name to
  look up the instrument, so it works fine for the extras (which were
  never part of the `Lick-2026B-02` FFFF-PZ Resource's own target pull).
  **Second mechanic: `chime_ffff_pz_starlist` globs `*finder.json` in the
  current directory with no group filter** — to keep the main and extras
  starlists separate (this run's running theme), stage each group's JSONs
  into its own directory and run the tool once per directory, then
  reorder the output rows into actual schedule order (the tool emits them
  in filesystem-glob order, not observing order) before appending
  anything that isn't an FRB (e.g. the standard star, which has no
  FFFF-PZ entry). Noted a cosmetic upstream bug in passing (positive Dec
  printed unsigned in the Lick starlist format) without touching the
  `chime-ffff-pz` repo — not this project's to fix, and it didn't affect
  this run (all targets are Dec-positive by the Shane limit anyway).
- **v0.31 — 2026-09-16 (UTC; PST 2026-09-15):** Built Lick-2026B-02 night
  2 (2026-09-15/16). Per the author, TGT0602 and TGT0583 got
  redshifts night 1 and are done; everything else observed night 1
  (3 primary + 3 gap-fill extras, 6 targets total) is repeated tonight,
  pooled into one FRB-priority list — **the former primary/extras tier
  split doesn't carry over to a repeat night once the author says "FRBs
  are the main priority"; re-derive priority from the author's current
  framing, not from a stale internal category.** New
  `scripts/lick_2026b02_night2_calculations.py` reused
  `target_window()`/the earliest-window-close-first pattern unchanged;
  TGT0604 hit the same tight (~42 min) forced-first window as night
  1, confirming that's a recurring property of that target/date pairing,
  not a one-off. Result: 6/6 FRB repeats scheduled, 402 min science.
  Author also supplied 6 non-FRB spare/filler targets with RA/Dec/mag
  given directly (mixed filters C/V/g/r/L, used as an r-mag proxy for the
  Kast exposure heuristic — flagged as an approximation since there's no
  real host photometry for these). Slotted into the FRB schedule's idle
  gaps the same way as night 1's extras; 2 of 6 fit.
  **Verified a specific author claim against the real Shane HA mount
  limit rather than trusting it outright**: the author said TGT0003
  ("rising right now") could "definitely" be caught in twilight. Direct
  calculation showed TGT0003 is circumpolar from Lick (Dec 53.51° >
  90°−lat 52.66°) but the Shane's -5.0h≤HA≤+3.75h range is a **mount**
  limit, independent of the physical horizon — its window this specific
  night doesn't open until 06:03 PST, 13 min *after* sunrise (05:50 PST).
  Not forced into the schedule (unlike TGT0604, this isn't a
  legal-but-short window needing truncation — the mount genuinely cannot
  point there yet when the window would need to open). Added
  `never_legal_diagnostic()` to report the exact clock time any
  never-HA-legal target's window *would* open relative to real
  sunset/sunrise, rather than just labeling it unobservable — this
  incidentally showed a second never-legal spare (TGT0004) actually opens
  at 04:38 PST, comfortably before sunrise, so it's a genuine dawn-twilight
  candidate the author could choose to push past the formal 18° cutoff for,
  unlike TGT0003. **Lesson: when a domain expert's specific claim about a
  target's visibility conflicts with what a hard mechanical limit implies,
  compute the real numbers and report them plainly rather than either
  silently overriding the limit to match the claim or silently dropping
  the target without explanation** — this is a sharper case than the
  earlier "S/N per exposure" lesson (v0.21 above) because here the
  calculator is right for a structural reason (a real, fixed mount range)
  rather than a modeling ambiguity, so the resolution isn't a compromise.
  Added the "September 15th" and "Spare Targets (Sep 15)" sheets to the
  *existing* `Lick_2026B-02_Night_plan.xlsx` (new
  `scripts/build_lick_2026b02_night2_plan.py`) rather than a new workbook,
  continuing the per-date-sheet convention. New
  `scripts/make_lick_2026b02_night2_starlist.py` reuses night 1's
  target/_S/_C 3-line starlist blocks verbatim for every repeat (same sky
  coordinates — no need to re-run the finder-chart pipeline for a repeat
  target) and adds plain single-coordinate rows for the two scheduled
  spare targets, in tonight's actual observing order
  (`lick_night2.starlist`).
- **v0.32 — 2026-09-16 (UTC; PST 2026-09-15):** Author revised the
  already-built night-2 spare schedule twice in one prompt: swap
  `TGT0005` for a new DLA sightline (`TGT0007`, RA RA_REDACTED,
  Dec DEC_REDACTED, `exptime=3600` given directly -- no magnitude), and add
  `TGT0003` "at the end of the night" despite v0.31's finding that its
  Shane window doesn't open until 06:03 PST (after both 18-deg twilight
  and sunrise). **A target given a fixed exptime instead of a magnitude
  can't go through `estimate_kast_exposures.estimate_exposure()`** -- a
  `FIXED_EXPTIME_S` dict + a `schedule_greedy_fixed()` variant in the new
  `scripts/lick_2026b02_sep15_revision.py` handled the one-target
  exception without touching the general scheduler. **When the author
  says "replace one of the extras" without naming which, don't force the
  replacement into the old slot -- drop the named target from the pool
  and let the greedy scheduler re-place the new one on its own merits**,
  since the two targets can have very different durations/HA windows;
  here `TGT0007` (60 min fixed) landed in a *different* idle gap
  (03:11-04:11, after `TGT0574`) than `TGT0005` (00:44-01:24) ever
  occupied -- re-running the real scheduler caught this, hand-editing the
  CSV would have missed it.
  **v0.31's mount-limit finding didn't change -- it's an explicit author
  override, not new physics.** When an author instruction directly
  contradicts an earlier, still-valid calculation, the older result isn't
  wrong and doesn't get erased: schedule the override transparently
  (TGT0003 as a forced-last row at 06:03 PST, its earliest
  physically-legal moment) with the full diagnostic reasoning attached as
  the schedule's own comment, so the plan makes clear *why* this one row
  breaks the night's normal dark-sky/twilight framing instead of looking
  like a routine target. Reused the FRB-repeat schedule's own CSV as a
  fixed input rather than recomputing it -- neither change touches the
  main-priority repeats.
- **v0.33 — 2026-09-16 (UTC; PST 2026-09-15):** Non-FRB spare/filler
  targets (TGT0004, TGT0003, TGT0002, TGT0005, TGT0006, TGT0001,
  `TGT0007`) had no finder chart -- `chime_ffff_pz_finder` only
  works through the FFFF-PZ database, and these are author-supplied
  RA/Dec transients with no FFFF-PZ entry. **Before writing any code,
  delegated pure research (read `chime_ffff_pz/scripts/finder_chart.py`
  and `starlist.py` in full) to an Explore subagent, then re-verified its
  report against the actual source myself** before driving real
  network/API calls off of it -- worth doing whenever a subagent's
  findings are about to become the basis for code that touches something
  live (image cutouts, star catalogs), not just when the stakes are
  obviously high. Confirmed the DB-independent code path is exactly
  `finder_chart.py`'s `set_coords()` single-target
  (`len(gal_coords)==1`) branch: no instrument/slit/secondary needed
  since these are single-coordinate transients, not FRB
  primary+secondary-host pairs.
  New `scripts/lick_2026b02_nonfrb_finders.py` drives the same core
  machinery directly (`coord_utils.radec_to_coord`,
  `catalogs.query_catalog` for the Pan-STARRS offset star,
  `plotting.grab_image_wcs` for the cutout, `finder.generate()` for the
  plot) and writes the identical JSON schema
  (`TNS`/`primary_ra`/`primary_dec`/`slitcen_ra`/`slitcen_dec`/
  `offset_star_*`/`offset_ra`/`offset_dec`) an FFFF-PZ-backed finder
  would, so downstream tooling can't tell the difference. Must run in
  the `frb_env` conda environment. TGT0003's cutout came back almost
  entirely saturated-black -- turned out its coordinates sit right on
  M101's disk (mag 12.1 checks out for a bright nearby-galaxy field);
  **a wildly different-looking finder chart isn't automatically a
  rendering bug -- check what's actually at those coordinates before
  assuming the pipeline broke.**
  **Caught a real correctness bug in the upstream chime_ffff_pz package
  before trusting its output**: `chime_ffff_pz.scripts.starlist.
  add_coord_to_row()` formats Dec arcmin/arcsec straight from
  `coord.dec.dms` without `abs()`, so a southern-Dec target gets a
  doubly-signed row (TGT0001, Dec DEC_REDACTED, came out `-2 -51 -55.6`
  instead of `DEC_REDACTED`) -- invisible until now because every prior
  FRB target here happened to be Dec-positive. **A bug that never
  triggers on the data seen so far isn't fixed -- it's just untested;
  don't assume upstream code is correct merely because nothing broke
  yet.** Per the established "don't patch someone else's repo for a
  cosmetic issue" precedent (v0.30's unsigned-positive-Dec note), didn't
  touch chime-ffff-pz -- reused this project's own already-correct
  `starlist_row()` convention (`abs()` on minutes/seconds, signed
  zero-padded degrees, from `make_lick_2026b02_night2_starlist.py`)
  instead in the new `scripts/make_lick_2026b02_nonfrb_starlist.py`.
  Also fixed a latent bug of my own in `blocks_by_tns()` (used by
  `make_lick_2026b02_night2_starlist.py` to group a starlist file's lines
  into per-target blocks): it found a block's TNS by splitting on the
  first underscore, silently assuming no target name contains one --
  `TGT0007` breaks that assumption (would merge under key
  `"DLA"`). Fixed by stripping a trailing `_S`/`_C` suffix instead.
  **Lesson: a parsing heuristic that works for every name seen so far can
  still be wrong in general -- check whether it depends on an unstated
  assumption about the input space, especially right after that
  assumption gets violated by a new kind of name (here, one with an
  underscore in it).**
- **v0.34 — 2026-09-16 (UTC; PST/PDT 2026-09-15):** Author suspected
  night-2 LST times were off by >1h vs. the real Lick ephemeris.
  Delegated the investigation (not the fix) to a subagent with a
  specific, falsifiable hypothesis (PST/PDT mixup, since 2026-09-15 is
  deep in US DST) rather than a vague "check this" -- got back a
  concrete, testable answer instead of a vague one, and re-verified the
  key claims myself (re-read the actual code, reran `find_twilight()`)
  before trusting them, since this was about to justify changing a
  shared calculation module. **Finding: the LST/UTC math was already
  correct — `find_twilight()`'s forward-search loop derives the real UTC
  instant via `.astimezone()` regardless of what the fixed offset is
  labeled, confirmed against both a fresh DST-aware recomputation and a
  live fetch of ucolick.org/calendar's actual page for that date (~1-2
  min agreement).** The apparent "1-hour error" was a **label** mismatch:
  Lick's own published almanac deliberately labels every night "PST"
  year-round (verified live, not a past misreading -- see v0.15 above and
  the HOWTO's "Mistake 2" from Lick-2026B-01, where DST-aware time was tried *first*
  and deliberately replaced with fixed PST specifically to match Lick's
  calendar convention), so the code's "19:43 PST" was the right instant,
  just a real hour behind an actual wall clock at Lick in September
  (PDT, UTC-7). **Lesson: "the numbers don't match the real-world
  reference" and "the calculation is wrong" are different claims -- check
  whether a labeling/convention choice, not the arithmetic, is the actual
  source of a discrepancy before changing calculation code.**
  This is the *opposite* correction direction from Lick-2026B-01's
  "Mistake 2" (that HOWTO went DST-aware -> fixed-PST; this one goes
  fixed-PST -> DST-aware) -- not a contradiction, just two different
  authors/requests wanting different things from the same underlying
  ambiguity (match Lick's own almanac label vs. match a real wall clock
  at the telescope). **When a past decision and a new request point
  opposite directions on the same axis, that's a sign the axis itself is
  genuinely a judgment call, not that either past-Claude or present-Claude
  got the physics wrong — worth asking the author to confirm intent
  explicitly (did here, via AskUserQuestion) rather than silently
  re-deciding it.**
  Implementation: `lick_2026b02_calculations.py`'s `PST` constant is now
  `zoneinfo.ZoneInfo('America/Los_Angeles')` (checked first that nothing
  else imports the `PST` name directly, so the change stayed contained);
  all persisted "PST"-labeled output (Excel headers, the forced-TGT0003
  comment text, console diagnostics) switched to print the real `.tzname()`
  dynamically instead of a hardcoded string. **Caught a subtler bug while
  doing this**: a datetime parsed back from a CSV's `"...-07:00"` string
  carries a generic fixed-offset tzinfo, not the named zone, so
  `.tzname()` on it prints `"UTC-07:00"` instead of `"PDT"` even though the
  instant is identical to one computed fresh from `ZoneInfo(...)` --
  `pd.Series.dt.tz_convert('America/Los_Angeles')` right after parsing
  fixes the *label* without changing the *instant*. **Lesson: a value's
  numeric correctness and its display identity (which named zone
  `.tzname()`/`%Z` reports) can silently diverge across a
  serialize/deserialize round-trip -- don't assume `.tzname()` is stable
  just because the underlying UTC instant is.**
  Re-ran the full night-2 pipeline (calculations -> revision -> Excel ->
  starlist) and confirmed the same targets got scheduled in the same
  relative order as before the fix -- only the printed clock labels
  shifted by a constant +1h, exactly as expected for a pure relabeling,
  confirming this really was cosmetic and not a scheduling-logic change.
  Deliberately left night 1's (2026-09-14, already-observed) own
  `main()`/console labels untouched -- out of scope for a "second night"
  request and nothing there feeds a persisted night-2 artifact.
- **v0.35 — 2026-09-17:** Author caught a wrong run date: the Keck/LRIS plan
  had been built for Oct 2, 2026 throughout v0.17-v0.24, but the real night
  is **Oct 6, 2026** (Sonnet 5). Since twilight/LST/airmass/HA/vignetting
  all depend on `date_str`, treated this as a full pipeline rerun, not a
  text find/replace: renamed `scripts/keck_2026oct02_calculations.py` ->
  `scripts/keck_2026oct06_calculations.py` (content's `date_str` default
  and output filenames updated too), updated `build_keck_night_plan.py`'s
  date default/checklist title/sheet name/start-time constant, reran both,
  and renamed the dated output files (`Keck_LRIS_2026Oct02_Night_plan.xlsx`,
  `keck_lris_oct02.starlist`, `KECK_LRIS_2026OCT02_SUMMARY.md` -> `...Oct06...`).
  **Result: same 5 targets, same 45% utilization** — evening/morning
  twilight shifted by ~1-3 min (19:22->19:19 HST / 05:01->05:02 HST), and
  one rejected target's *reason* changed (TGT0573: Nasmyth-deck
  vignetting on Oct 2 -> below-horizon-all-night on Oct 6) without changing
  its exclusion. **Deliberately not touched:** the live FFFF-PZ
  `Keck-2026B-01` Resource JSON
  (`chime-ffff-pz/chime_ffff_pz/data/Observing/Keck-2026B-01/Keck-2026B-01.json`)
  still has its `valid_start`/`valid_stop` set to the Oct 2/3 UTC window —
  updating a live Resource on a shared server is a follow-up for the
  author, not a local file edit. Also left the Session Log narrative in
  `KECK_LRIS_2026OCT06_SUMMARY.md` (Prompts 1-11) and the git branch name
  (`keck-2026oct02`) alone, since those are an accurate record of what was
  actually said/run at the time — only the doc's current-state sections
  (Ephemeris, target tables, timeline, output files) were regenerated.
  Full detail in `KECK_LRIS_2026OCT06_SUMMARY.md`, Prompt 12. **Lesson:** a
  wrong observing date is a whole-pipeline error, not a cosmetic one —
  always rerun the ephemeris/scheduling code for the corrected date rather
  than editing date strings by hand, since even a small date shift can flip
  an individual target's rejection reason (though not always the outcome).
- **v0.36 — 2026-09-30 (UTC; HST 2026-09-29):** Author asked how Keck slew
  times were computed and to check the Oct 6 ephemeris against the UCO Keck
  calendar (ucolick.org/calendar/keckcal2021-30/keck2026.18oct; the Oct 6
  row matches the script to within 1 min: twilight 19:19, dawn 05:01 vs
  05:02 from the 1-min step, LST 20:01/05:44). Slews had been flat
  constants (3 min in the xlsx, 5 min in the scheduler). Author set the Keck
  rule: 5 min base, 20 min when moving from Dec < +20 to Dec > +20, for all
  Keck instruments; MOS blocks already include mask overhead. Added
  `scripts/keck_overheads.py`, made the scheduler charge per-transition
  slews, and reran the Oct 6 plan: same 5 targets, 40 min of slews, one
  20-min crossing (TGT0536 +13.9 -> TGT0574 +39.4) that lands in
  the existing mid-night gap. Also added
  `scripts/keck_2026oct06_rejection_analysis.py` and its
  `target_rejection_analysis.md`. See "Keck slew-time rule" above.
- **v0.37 — 2026-09-30 (UTC):** FFFF-PZ global server is
  `https://frb.chimenet.ca/f4pz/` (`set_ffff_pz_global` alias in `~/.bashrc`;
  local docker is `http://0.0.0.0:8000/`). A Resource added to the local
  docker instance does not exist on global. `add_frb_resource` is
  add-or-modify, so check that a name is free first (a target pull on a
  missing name returns 402 "Could not find resource"). The Keck-2026B-01
  name is taken on global per the author, so the Oct 6 Keck/LRIS Resource
  on global is **Keck-2026B-02** (10 mask + 20 longslit, window
  2026-10-07T05:00:01Z-15:45:38Z; 20 targets returned). The
  05:00:01Z-15:45:38Z bounds (19:00-05:45 HST) are the standing Keck
  Resource convention. The greedy scheduler has no priority input, so a
  bigger pool can bump high-value targets (e.g. the CHIME repeater
  TGT0456) out of crowded early-evening windows.
- **v0.38 — 2026-09-30 (UTC):** Rebuilt the Oct 6 Keck/LRIS plan from the
  global Keck-2026B-02 pull into `Night_plans/Keck-2026B-02/` (B-01 outputs
  kept as the earlier record). Base Keck slew is now 10 min (20 min for the
  Dec<+20 -> Dec>+20 crossing is unchanged), with +5 min buffer per MOS
  block. Masks are restricted to the 5 B-01 MOS candidates plus
  TGT0593, the one new mask the author will try to get, because it
  fills the mid-night gap. Result: 9 targets (4 MOS, 5 longslit), 6.1 h on
  target plus 100 min of slews, 63% of dark time. Only 10 min are idle
  (01:59-02:09), and the night ends at 03:59. The CHIME repeater
  TGT0456 is still bumped (7 min left in its window) by the greedy
  earliest-window order; the scheduler still has no priority input.
- **v0.39 — 2026-09-30 (UTC):** Brought every doc up to date with the
  Keck-2026B-02 plan. The B-01 SUMMARY now has a superseded banner, Prompts
  15-19, and relabeled snapshot sections. The B-01 rejection report is
  marked as a snapshot. README gained a Keck/LRIS quick start and scripts.
  claudes_context gained an FFFF-PZ servers section and the reason every
  target comes back `longslit` (FFFF-PZ mask mode isn't implemented).
  `claude_prompts/night_plans/keck_2026oct02.md` got Sessions 4-5, and the
  overview deck's slide 3 was changed to Keck-2026B-02, 9 targets, 6.1 h
  (63%). For docs, keep the old run folder as a marked record rather than
  rewriting its history, and point to the new run folder.
- **v0.40 — 2026-09-30 (UTC):** Filler search for idle time
  (`scripts/keck_2026oct06_filler_search.py`). Lessons:
  (1) **Local FFFF-PZ pulls go stale.** Most mag>18 targets from other runs'
  pulls are no longer NeedSpectrum (Redshift, TooDusty, GoodSpectrum,
  NeedImage). Always check the current status with the read-only `chk_frb`
  endpoint before scheduling a target from an old pull. `frb_status` is
  the write endpoint; don't call it.
  (2) Per the author: **never force a target above AM 2 into a Keck
  schedule**, including Lick-excluded high-Dec targets. From Keck
  (lat 19.8) anything above Dec ~84 never reaches AM 2 (e.g. TGT0584
  2.52, TGT0508 2.68). Note: the existing code still allows AM < 2.5
  for mag < 17 in `find_observable_window()`/`analyze_targets()`.
  (3) Mag 18-19 targets are OK as *fillers* for idle Keck time (author).
  (4) Fixed `analyze_targets()` crashing with `min_am_ha=None` for targets
  that never rise.
- **v0.41 — 2026-10-01 (UTC):** TGT0593 (mag 22.6) moved to longslit
  because no new mask will be milled (author). S/N=10 per exposure is
  unreachable for mag > 22 in longslit (the ETC tops out at 3 x 7200 s), so
  it keeps its 1 h block as 3 x 1200 s (`LONGSLIT_FORCED`): S/N per exposure
  is 5.7 blue / 2.8 red. When a faint target is forced into longslit,
  report its S/N and let the author decide; don't silently schedule hours.
  Finders and the target list were made with `chime_ffff_pz_finder <TNS>
  Keck-2026B-02` and `chime_ffff_pz_starlist keck --skip-missing`, run in the
  Observing/Keck-2026B-02 dir. Notes:
  (1) **Fresh shells may have `FFFF_PZ_URL` set to local docker
  (0.0.0.0:8000) from `~/.bashrc`.** Export the global URL explicitly before
  each FFFF-PZ call; the first finder run failed with connection refused.
  (2) The starlist's "Skipped N FRBs (missing candidates files)" warning
  only affects the magnitude printout; the rows are still written.
  (3) Starlist output is in glob order, unsigned for positive Dec, and has
  no standards. `scripts/make_keck_2026oct06_targetlist.py` reorders it to
  schedule order, adds '+' and standards, annotates rows, and writes
  `Keck-2026B-02.starlist`, a target-list .md and `finders/` copies.
  (4) For MOS targets, the finder's `rotdest` is a longslit default; the
  mask PA wins.

- **v0.42 — 2026-10-13 (UTC):** Forcing a rejected target in only ever worked
  for a *rising* one. Both schedulers appended forced targets after the whole
  night, so a fast-setting host -- the main reason to force anything, since
  the scheduler drops it precisely because its full exposure won't fit the
  window sliver left -- could never be placed: its window shut hours before
  the schedule ended. Durable points:
  (1) **Lick (`kast_calculations.reserve_forced()`):** forced targets are
  placed *before* the greedy pass, inside their own HA window, and the slot
  (padded one `SLEW_MINUTES` either side) is passed to `schedule_greedy()` as
  a block, so the night schedules around them. Both pads are needed at Lick:
  the greedy loop models slew as a cursor advance, not a row, so neither the
  incoming nor the outgoing slew is otherwise accounted for across a block.
  (2) **Placement rule: as late inside the target's own window as the
  requested time allows.** One rule, both cases -- a setting target lands at
  the top of the night because that is all it has, a rising one lands at the
  end where it was going anyway -- and it reserves the least of everyone
  else's time.
  (3) **Keck tries append first, reservation second.** Appending disturbs
  nothing, and the delivered 2026-10-06 plan depends on it: reserving
  TGT0461's slot (even padded by only the 10-min base slew) lands five
  minutes earlier than the append did and costs TGT0272. So
  `select_targets_for_night()` appends, and recurses *once* with
  `reserved`/`reservations` only for the targets append couldn't place,
  clearing `skip_log` because pass 1 described a night that no longer
  exists. Keck-2026B-02 reproduces timestamp for timestamp.
  (4) The old Keck append deliberately let a forced target overrun its AM<2.0
  window and morning twilight "per the explicit request"; the reservation
  path truncates at window close instead. Keep that difference in mind when
  comparing an appended plan with a re-run one.
  (5) **A forced target that cannot be placed must surface as a decision.**
  `adapters.lick_kast()` was ignoring `out['forced_failures']`, so the
  scheduler printed "window closed" to stdout and the browser saw an
  unchanged plan -- which reads as "it worked". Both adapters now emit a
  `4. Forced` rejection.
- **v0.43 — 2026-10-13 (UTC):** Finder charts now draw the PATH **secondary**
  candidate, read from the plan's own target table (`Sec_RA`/`Sec_Dec`/...)
  by `finder.load_secondaries()`. Durable points:
  (1) **Colours follow `chime_ffff_pz/finder.py`:** red primary, orange
  secondary, cyan offset star. Keep that, so our charts and the FFFF-PZ ones
  read the same at the telescope.
  (2) **Never size a candidate marker in points.** A PATH primary and its
  runner-up are routinely 3" apart (TGT0606 2.8", TGT0602 2.9"),
  which is ~7 px at a 4' field -- a 260-pt circle swallows both exactly where
  the chart has to tell them apart. Use `SphericalCircle` at a fixed sky
  radius (2" for candidates, 4" for the offset star).
  (3) **Under ~12" separation, even that fails**, so the chart gets a
  `Cutout2D` zoom inset (box = 6x the separation). Inside the inset, label
  offsets must be vertical: the main chart's radial offsets are in points,
  and the inset is small in figure units, so they land on its frame.
  (4) **P(O|x) needs `:.3g`, not `:.3f`** -- these run to 1e-279.
  (5) `backend.app._plan_targets_csv()` recovers the table a saved plan was
  built from, via `request.argv` (`--targets-csv`, or `targets_csv` inside a
  `--config` JSON). Any later feature needing the original table should use
  it rather than guessing from the plan directory.
- **v0.44 — 2026-10-13 (UTC):** Finder slit angle is now a choice, and the
  parallactic angle's exposure dependence is documented. Durable points:
  (1) **`slit_mode`** on `finder.generate_for_plan()` and
  `/api/finders/generate`: `'parallactic'` (default) or `'candidates'`, the
  latter setting the slit to `primary.position_angle(secondary)` so both PATH
  candidates land in one exposure. Read from the plan's own target table --
  no FFFF-PZ needed. The older `use_ffffpz` path still exists and differs in
  using FFFF-PZ's candidate list.
  (2) **Never let that choice be silent.** Candidates mode prints its
  dispersion cost on the chart (subtitle + caption) and records `slit_mode`,
  `parallactic_pa`, `pa_vs_parallactic` in the sidecar; a target with no
  secondary falls back to parallactic and the browser names it. The cost is
  wildly per-target: 0.4 deg for TGT0606, 43.6 for TGT0176, 59.5
  for TGT0602.
  (3) **The parallactic angle is a function of the exposure, not the
  target.** `average_parallactic()` integrates over `science_start`..`end`,
  5-min samples, tan(z)-weighted. For TGT0176 from 00:10 the angle runs
  59.8 deg (20 min) -> 51.9 (60) -> 45.2 (90) -> 38.1 (120), weighted
  misalignment 2.3 -> 7.2 -> 11.9 -> 17.6 deg. **Past ~90 min near transit a
  single slit setting stops being defensible; split the block.** And because
  the angle is tied to the scheduled duration, changing an exposure means
  regenerating the finders.
  (4) `scripts/analyze_slit_pa.py` reports, per target, the chosen angle, the
  swing, the weighted offset, and whether the secondary falls in the slit
  (perpendicular distance vs half the slit width).
- **v0.45 — 2026-10-14 (UTC):** Checked our slit angles against Lick's own
  tools in `helpful_scripts/` (Burrous 1990 `pa.c`, `calcint.c`). Durable
  points:
  (1) **Our parallactic angle is exact.** 441 HA/Dec points, 0.000000 deg
  disagreement with `pa.c`. We use four-quadrant `atan2(sin HA, tan lat cos
  dec - sin dec cos HA)`; pa.c uses `asin` plus a quadrant patch
  (`acos(tan lat / tan dec)` for Dec > lat). Don't "fix" ours toward theirs.
  (2) **pa.c quotes the angle at the exposure midpoint**, we quote a
  tan(z)-weighted average. Difference on real targets: 0.1-0.6 deg. Expect an
  observer cross-checking with pa.c to see the midpoint number.
  (3) **THE SHANE DOES NOT TAKE A SKY PA.** It takes a Cassegrain tub Nixie
  readout, `readout = 0.87 x PA + 0.05` (table in `calcint.c`, ported to
  `night_planner/lick_tub.py`). PA 108.92 -> tub **94.81**. Dialling the PA
  puts the slit ~16 deg off. Lick finders, sidecars and starlist rows now
  carry `#TUB = x or y`; always quote **both** settings, 180 deg apart, since
  which is reachable depends on where the tub already sits.
  (4) The calcint table runs 20..380 and its last 20 deg deliberately repeat
  the first 20 -- never normalise with a plain `% 360`, or 380 reads 17.45
  instead of 330.64.
  (5) Keck/LRIS is unaffected: it takes `rotdest=` in sky PA. The `rotator`
  key on the SITES entry is what distinguishes them.
- **v0.46 — 2026-10-14 (UTC):** Synthetic target tables in `test_targs/`,
  built by `scripts/make_test_target_tables.py` (seeded, regenerable).
  Durable points:
  (1) **Everything is `SIM`-prefixed and drawn from a seed.** Never put
  realistic-looking fake targets in this repo without an unmistakable marker
  -- a table that escapes its directory could get observed.
  (2) **Three tables exist to be refused** (`bad_ambiguous_ra_units`,
  `bad_burst_position_only`, `bad_odd_headers`). If a change makes them load,
  the change is wrong: reading an RA as hours instead of degrees moves the
  telescope by 15x. `tests/test_test_targs.py` asserts the refusals.
  (3) Seasonal tables cluster on the RA transiting at local midnight: Oct 1h,
  Jan 7h, Apr 13h, Jul 19h. Run one against the wrong date and nearly
  everything should reject -- that is a test, not a bug.
  (4) **Lick applies no airmass cut.** `target_window()` is pure hour-angle
  against the mount limits, so a Dec -30 target (culminates at alt 22.7 deg,
  airmass 2.6 from Lick) schedules happily where Keck would drop it at AM 2.0.
  Worth raising with the author before a run with southern fillers.
  (5) Fixed on the way: `load_targets()` now accepts a `Path` (it tested only
  `isinstance(source, str)`), and `adapters.lick_kast()` no longer discards
  `limit_reason` -- "Dec +86 > +82, above the Shane mechanical limit" reads
  very differently from "never HA-legal tonight".
- **v0.47 — 2026-10-14 (UTC):** Diagnosed an observer's PA discrepancy on
  Keck-2026B-02/TGT0574 (requested 170.8, set 195.2 by eye, both traces
  recovered). Durable points:
  (1) **Beware the tub coincidence.** tub(195.2) = 169.87, within 0.94 of
  170.8 -- a near-perfect false match. But this was **Keck/LRIS, which has no
  Cassegrain tub**. Always establish which telescope a number came from
  before reaching for the 0.87 scaling.
  (2) Our angle was correct: recomputing the PATH candidate-to-candidate axis
  from the targets CSV gives 170.82 vs the requested 170.81.
  (3) **The slit-tolerance formula settles these arguments:** both objects
  are in the slit only while `sep * sin(delta) <= width/2`. For a pair 21.8"
  apart that is **+/-1.3 deg at 1" slit width**. At 24.4 deg off, the
  secondary is 9.0" off the centreline. So a reported angle differing by tens
  of degrees *while both spectra came out* cannot be a sky PA -- it is an
  instrument/rotator angle. Nobody's intuition gets this tolerance right.
  (4) Open question for the observer: which field read 195.2? If it is
  ROTPOSN, the LRIS rotator-to-sky offset (~24.4 deg here) belongs in the
  SITES registry beside `rotator: 'cass_tub'`, and Keck charts should quote
  it the way Lick charts now quote the tub.
  (5) `scripts/diagnose_pa_discrepancy.py` reruns the whole analysis for any
  plan/target/pair of angles.
- **v0.48 — 2026-10-14 (UTC):** Corrects v0.47, which named the wrong
  telescope. TGT0574 was observed at **Lick**, not Keck -- it has
  finders in both `Keck-2026B-02/finders/` and
  `Lick-2026B-02/finder_charts/`. **A value matching in one plan is not
  identification** when a target appears in several. Durable points:
  (1) **The Shane tub zero point is probably NOT zero.** The slit that put
  both candidates on it was sky PA 170.81 (catalogue-verified); the reported
  readout was 195.2, i.e. **+24.4 deg**. If that is the zero point, every
  `night_planner.lick_tub` number is low by a constant **21.22 Nixie**. Not
  applied -- one data point. Get a second readout from a Lick night.
  (2) **The coincidence that nearly fooled me twice:** tub(195.2) = 169.87,
  within 0.94 of 170.81, which looks like a clean PA/tub swap. A +24.4 deg
  offset and the 13% shrink cancel near PA 164 and diverge elsewhere (10 deg
  apart at PA 240). Check a coincidence at a second angle before believing it.
  (3) **Kast's 2" slit holds a 21.8" pair only within +/-2.63 deg.** Since
  both traces were recovered, the by-eye alignment was right and the number
  was in another frame. The slit-tolerance formula is the fastest way to tell
  a units problem from a pointing problem.
  (4) The Lick finder centres the slit *between* the two candidates
  (`center_lick_kast_slits`), so its "Target" J-name differs from the
  primary's. That is not an error.
- **v0.49 — 2026-10-14 (UTC):** **Fixed a real scheduling bug in
  `target_window()` (scripts/lick_2026b02_calculations.py).** It unwrapped the
  morning HA to be >= the evening HA, then tested the overlap against only
  the k=0 copy of [HA_MIN, HA_MAX]. A target 10.5h past the meridian at dusk
  is the same target rising back into HA -5 before dawn, so **every late
  riser was reported "never inside the Shane HA window"**. Now tests
  k = -1, 0, +1; at most one can overlap, since the night is shorter than 24h
  minus the window. Regression on Lick-2026B-03: the eight scheduled targets
  keep identical slots and TGT0572 is added at 04:29-05:34. The planner
  had been discarding an hour at the end of such nights.
- **v0.50 — 2026-10-14 (UTC):** Finder slit modes reworked, and a serious
  twilight bug fixed. Durable points:
  (1) **An existence check must consider the mode.** `generate_for_plan()`
  skipped any target whose PNG existed, so switching parallactic ->
  candidates silently kept the old chart while the starlist quoted the new
  angle. Decide the effective mode first (candidates only where a secondary
  exists), then treat a differing sidecar `slit_mode` as stale.
  (2) **FFFF-PZ is no longer a separate option.** Candidates mode *is* the
  FFFF-PZ path, reading Sec_RA/Sec_Dec from the plan's own target table --
  nothing fetched, no live Resource. `_ffffpz_finders()` (the
  `chime_ffff_pz_finder` shell-out) is deleted; recover from git if ever
  wanted. Targets with no secondary fall back to parallactic, are named in
  the browser and carry `fallback_reason`.
  (3) `finder.slit_report()` + `finders/slit_report.txt` record what angle
  every chart was drawn at. Keep writing it -- the question resurfaces days
  later when a spectrum looks wrong.
  (4) **`find_twilight()` could not handle summer.** It stepped 1 min with a
  600-iteration cap from local noon, reaching only 22:00, so **every Lick
  night from late May to early August raised "Could not find evening
  twilight"** -- no summer plan was possible. Now one vectorised 24 h scan.
  21 June reads 22:25-03:53; already-planned dates are unchanged.
  (5) When a generate re-renders the page, the form must be restored from
  remembered state or it lies about what was asked for.
- **v0.51 — 2026-10-14 (UTC):** PATH candidates are an FFFF-PZ property,
  recognised by format. Durable points:
  (1) **`targets_io.detect_format()`** returns 'ffff-pz' vs 'generic' from
  the combination only FFFF-PZ produces: burst position + DM
  (FRB_RA/FRB_Dec/FRB_DM) *alongside* ranked candidates with probabilities
  (Pri_POx/Sec_POx). Surfaced by `/api/targets/inspect` and shown in the
  Inspect panel. `load_secondaries()` returns {} for a generic table even
  when it has Sec_RA.
  (2) **Do not use a per-row name/DM heuristic for this.** The real
  Lick-2026B-03 pull carries a DM for only 15 of 19 rows (baseband-merged
  ones have none), so a DM test rejects four genuine FRBs.
  (3) **The root cause was fabricated test data.** `write_ffffpz()` gave
  Sec_* to supernovae and DLAs, so the planner fitted slits through
  candidates those objects cannot have. It now asserts FRB-only, which
  immediately caught a second bad table. `allsky_mixed.csv` is generic;
  `allsky_frb_ffffpz.csv` is the FFFF-PZ all-sky table.
  (4) When writing synthetic data, give each format only the rows that
  format can legitimately describe -- otherwise the fake table teaches the
  code a false rule and the bug looks like a code bug.
- **v0.52 — 2026-10-14 (UTC):** **Shane HA limits are -05:40 east, +03:45
  west** (author's decision, adopting the published values; east was -5.0
  until now). Durable points:
  (1) Written as `-(5 + 40/60)` / `3 + 45/60` in
  `scripts/lick_2026b02_calculations.py` so the published figures are legible
  in the source, and pinned by a test -- a silent revert costs 40 min of
  window on every rising target and nothing else would complain.
  (2) Worth, on the Lick-2026B-03 table: 11 of 19 targets gain window, ten
  the full 39.9 min, one newly observable, **387 min total**. A target
  already up at dusk gains nothing -- the east limit never clipped it.
  `scripts/compare_ha_limits.py` recomputes this for any table and date.
  (3) The constant was duplicated in five scripts. Live ones updated;
  `build_lick_2026b02_night_plan.py` and `lick_2026b02_sep15_revision.py`
  keep their -5.0 *text* because they record delivered nights, so their
  printed limits now differ from their imported behaviour.
- **v0.53 — 2026-10-15 (UTC):** Swept every synthetic table across the year
  (`scripts/sweep_test_plans.py`) and found four bugs. Durable points:
  (1) **`datetime + timedelta` on a DST-aware datetime is wall-clock
  arithmetic.** Across the spring-forward gap 01:30 + 90 min lands on 03:00,
  30 minutes later in real time -- time runs *backwards*. Use
  `night_planner.sky.advance()` (to UTC, add, back) for every scheduling
  addition. Lick only: Pacific/Honolulu has no DST, so Keck was never
  exposed. Always assert schedule invariants in UTC; local labels
  legitimately jump an hour.
  (2) A frame built from per-row dicts can be missing columns entirely when
  no row took the branch that sets them -- "nothing observable tonight"
  crashed on `sort_values('start_pst')`. Guarantee the schema after
  building, not at each use.
  (3) **Duplicate target names are scheduled twice.** `load_targets()` now
  refuses them. Merged tables (the baseband merge into Lick-2026B-03) are
  where this arises. All 15 existing Night_plans tables pass.
  (4) `--start` after morning twilight produced a negative-length night and
  a silent empty plan; now refused.
  (5) The sweep's value is the invariant checker, not the runs: overlaps,
  blocks outside the night, exposures outside their own HA window, targets
  scheduled twice or missing from decisions. Keep DST dates and the
  manual-start/block variants in `DATES`.
- **v0.54 — 2026-10-16 (UTC):** **The Shane tub zero point is confirmed
  correct — v0.48's suspected 24.4 deg offset was wrong.** Lick-2025B-3 frame
  `r2046.fits` (TGT0415, 2025-10-24) records TUB 194.80 together with HA
  -2:23:23 and Dec +78:14:43. Inverting calcint.c gives slit axis 43.85 deg;
  the parallactic angle at that instant is 42.54 deg. **Agreement to 1.3
  deg.** `night_planner/lick_tub.py` needs no offset, and the note is now in
  its docstring with the frame cited. Durable points:
  (1) **A Kast header carries TUB, HA, DEC, AIRMASS, SLIT_N and the
  gratings** -- enough to reconstruct exactly how any past frame was
  observed. `scripts/tub_from_header.py` and `scripts/finder_from_frame.py`
  do this; reach for them before trusting an anecdote about an angle.
  (2) **Observed drift, measured not modelled:** on this target the tub was
  set once per block and left. It matched parallactic to ~1 deg at the start
  of the first block; by the end of the second, at Dec +78 near transit,
  parallactic had moved to 8.6 deg while the tub still implied 44.3 -- **35.7
  deg off**. High-Dec targets near transit rotate fastest; that is where
  splitting a block actually pays.
  (3) Both tub settings 180 deg apart are legitimate and observers do use the
  far one: here they used 194.8, the "or" value our starlist prints, not 38.2.
- **v0.55 — 2026-10-16 (UTC):** Drew a finder on a **burst** position by
  mistake and the author spotted it by eye. Durable points:
  (1) **The archived Lick-2026B-01/02 candidate files
  (`ffffpz_candidates.csv`, `unassigned_targets_ra1-4h.csv`,
  `candidates_ra1-4h_with_path.csv`, `extras_schedule.csv`) give the FRB
  position in generically named `dec`/`Dec_deg` columns**, beside DM and
  P_Ux. For TGT0415 that is 5.9" from the host. Never read these with a
  hand-rolled `pd.read_csv`; `targets_io.load_targets()` exists precisely to
  refuse a burst position standing in for a host.
  (2) **Verify a coordinate is on light before drawing a slit around it.**
  `scripts/check_target_on_source.py` does it. DAOStarFinder is the wrong
  tool -- it filters on roundness and rejects extended hosts; use smoothed
  local maxima instead.
  (3) The telescope pointing recorded in a Kast header is good evidence of
  where the host is: here it was 0.34" from a 13-sigma source while the
  catalogue row was 5.56" away. `finder_from_frame.py` now warns when a
  supplied position differs from the pointing by more than the slit width.
  (4) A geometry check and a position check are different questions. The
  slit was centred on its given coordinate to 0.0000" the whole time.
- **v0.56 — 2026-10-16 (UTC):** Audited and documented how target priority is
  set (`docs/priority_system.md`, prompt `claude_prompts/development/priorities.md`).
  Durable points:
  (1) **There is no priority field in this pipeline.** `targets_io.ALIASES`
  recognises `name/ra/dec/mag` + `pox/tags/dm` and nothing else;
  `make_test_target_tables.py` emits a `priority` A/B column
  (`test_targs/spring_ra_hours.csv`) that `load_targets()` silently drops.
  Claim that column name first when building a real system.
  (2) Apparent priority decomposes into four layers: the FFFF-PZ tag-weighted
  stochastic draw (the only numerical encoding of science value — and it acts
  on *membership in the pool*, not on rank inside it); hard feasibility gates
  (HA/Dec/mag, which reject but never rank); the greedy
  earliest-window-close-first scheduler (pure urgency, value-blind); and hand
  overrides (`--force`/`reserve_forced`, `FORCED_FIRST_TNS`, separate pools,
  author statements in prose).
  (3) **`setting_priority` is not a science rank** — it is a binary
  evening/morning class on the superseded Lick-2026B-01 path, consumed by
  `fix_ha_limits.py` only to pick the HA sign convention. Do not extend it.
  (4) The clearest real two-tier priority in the repo is expressed as
  *architecture, not data*: `lick_2026b02_extras.py` builds a separate
  lower-priority pool (`AmbiguousHost`/`TooDusty`, POx>=0.6) via a different
  FFFF-PZ call and writes it to its own `Extras (Gap-Fill)` sheet.
  (5) P(O|x), tags and magnitude are all non-inputs to ordering: POx and tags
  reach the plan as a Comments string, magnitude sets exposure time only.
- **v0.57 — 2026-10-16 (UTC):** Read and compared the UCSC AstroScheduler
  (`/home/lordrick/Projects/fun_side_projects/ryan_scheduler/AstroScheduler`,
  UCSC-Transients) against our priority handling →
  `docs/priority_comparison_astroscheduler.md`. Durable points:
  (1) **It schedules the same telescope with the same HA limits**
  (-5.6667/+3.75), so it is directly comparable. But its `ShaneTelescope` sets
  `dec_min=-35.0, dec_max=72.0` against our `DEC_LIMIT = 82.0` with no southern
  limit, and its slew is a flat 7 min against our `SLEW_MINUTES = 5`. **Both
  Dec conventions cannot be right — ask the author.**
  (2) **The design worth copying is the tier loop**, not the solver:
  `_solve_internal()` partitions targets by float priority (1 = highest,
  `0.0` = standard-star sentinel), solves tiers best-first, and re-enters
  already-placed targets as *mandatory* (`S_active`) in every later tier. A
  low-priority target can then never displace a high one, yet a high one can
  still be *re-positioned* to let a lower one fit — which a one-pass greedy
  cannot do, and which is exactly our TGT0456 failure mode (v0.37/v0.38).
  This wraps `schedule_greedy` rather than replacing it.
  (3) Inside a tier: Branch and Bound minimising
  `median_airmass + 1000*twilight_dist`, with `100000` per dropped target.
  That penalty is ~5 orders above airmass, so the objective is
  **lexicographic in practice** (count first, then quality) — and **priority
  is not in the cost function at all**, only in the tier loop. Greedy warm
  start, suffix-min pruning, 1-min chunks, hard 20000-iteration cap → good,
  **not provably optimal**.
  (4) Three channels outrank priority there: `manual_start_time` (pre-reserved
  before tier 1), `schedule_before` precedence via topo sort, and
  `previous_start_chunks` tried first so a mid-night re-solve does not churn —
  the last has no night-planner equivalent and we re-run plans constantly.
  (5) Priority there is **hand-authored** (`priority = X` in the target file,
  default 3.0 in the JS parser / 1.0 in the API) with no catalog behind it, and
  their rejections are a bare `conflicts` list with no reason. **The two repos
  are missing opposite halves of the same system: they have a consumer with no
  principled source, we have a source with no consumer.**
- **v0.58 — 2026-10-19 (UTC):** Built the priority system the v0.56/v0.57 docs
  said was missing: `priority` is now a real float column (lower = better,
  `DEFAULT_PRIORITY = 1.0`), recognised by `targets_io.ALIASES`, carried by
  `analyze_targets` into every schedule frame, and consumed by a tier loop.
  Durable points:
  (1) **The comparison doc was right about *what* to build and wrong about
  *how*.** I had written that we should copy AstroScheduler's
  "already-placed-is-mandatory" trick by passing tier-1 slots to a second
  `schedule_greedy` pass as blocks. That cannot work here: `fit_around_blocks`
  can only ever push a target *later* (`candidate_start` is monotonically
  non-decreasing) and `schedule_greedy`'s cursor never rewinds, so one more
  full-night pass sails past every gap it already crossed. The working form is
  **per-gap** — compute gaps, call `schedule_greedy` once inside each,
  restarting the cursor — which the repo already did at
  `lick_2026b02_night2_calculations.py:366-386`. **Lesson: read the primitives
  before trusting a design note, even one you wrote three days ago.**
  (2) `schedule_by_priority()` short-circuits to a single `schedule_greedy`
  call when there is one tier, so an un-prioritised table schedules *exactly*
  as before. `tests/test_priority_tiers.py` asserts it. Keep that guarantee.
  (3) `--max-targets` used to trim by `nsmallest(n, 'start_pst')` — by time —
  which would silently drop a top-priority late target for an early filler.
  Now sorts by `(priority, start_pst)`.
  (4) `TargetDecision.priority` **must stay defaulted**: `from_dict` splats a
  saved row into the constructor, so any new field without a default breaks
  every `plan_result.json` already on disk.
  (5) Priorities travel to the scheduler **as a column in a derived
  `targets_with_priority.csv` written into the plan directory**, not as a
  request field. That is what makes a GUI plan reproducible — verified by
  re-running the CLI on that file and getting an identical schedule.
  (6) `frontend/app.js` has **no persistence of any kind** and `useTemplate()`
  clones a fresh template on every route change, so anything a pre-plan page
  needs must be stashed in the module-level `state`. A reload still loses it
  and there is no `dir=` to re-fetch from, so the priorities page says so
  instead of rendering empty.
- **v0.59 — 2026-10-19 (UTC):** Made the repo run on any machine —
  41 hardcoded paths across 25 files, now `night_planner/paths.py`. Durable
  points:
  (1) **Hardcoded paths split into two kinds wanting opposite treatment.**
  Inside the repo (root, `Night_plans/`, `scripts/`) they should be *derived*
  from `Path(__file__)`, never configured — a setting is one more thing to get
  wrong, and a computed path cannot be. Only genuinely external locations get
  environment variables: `FFFF_PZ_REPO` (guesses a sibling checkout first),
  `NIGHT_PLANNER_PLANS`, `LICK_NIGHT_PLAN_TEMPLATE` (deliberately no default —
  guessing a read-only file's path turns "set this variable" into a confusing
  missing-file trace).
  (2) **This had been silently broken for months.** `make_lick_night_plan.py`
  carried a `/home/xavier/Projects/...` default that worked for nobody on this
  machine. That is the whole failure mode: fine for whoever wrote it, invisible
  to them, broken for everyone else.
  (3) `tests/test_paths.py` greps every source file for machine-specific
  absolute paths. **Plant a violation to confirm a guard test like this
  actually fails** — I did; a guard that passes vacuously is worse than none.
  (4) Importing every script to smoke-test them **runs work**: several scripts
  have no `if __name__ == '__main__'` guard (`check_deadtime_lick_2026b01.py`
  prints an entire analysis). Expect side effects from an import sweep.
  (5) **Establish causation before "repairing" unexpected git changes.** A
  modified plan directory looked like my import sweep had clobbered it and I
  nearly `git checkout`-ed it back; it was the author's own GUI session
  (a `uvicorn backend.app` on port 8020) testing the new feature. A confident
  repair of someone else's work is worse than the mess it tidies.
- **v0.60 — 2026-10-19 (UTC):** `backfill_partials()` fills leftover idle time
  with truncated exposures of targets dropped for want of time, marked
  `PARTIAL` in `skip_reason` → `notes`. Durable points:
  (1) **The `notes`-prefix convention is the repo's labelling mechanism.**
  `FORCED` already drove `targetClass()`, a pill and the rescue list; adding
  `PARTIAL` needed only a new CSS token, a legend row and a pill. Reuse it for
  any future category rather than inventing a field.
  (2) Two invariants a truncating scheduler must hold, both tested: a partial
  **never moves anything already scheduled**, and **never leaves the target's
  own HA window** just because the exposure is short.
  (3) **Idle time has two different causes and only one is fixable this way.**
  On `Lick-2026A-07_host_wg` (211 min idle) truncation changed *nothing*: both
  rejected targets' HA windows did not overlap any gap — TGT0600's
  16-minute window closes before science even starts, since focus + evening
  standard eat the first 20 min. That is an **exhausted pool**, not
  all-or-nothing rejection. Where the pool really is oversubscribed
  (`autumn_ffffpz`) it went 85% → 88% of night used. Diagnose which cause is in
  play before promising a fix.
  (4) **Known cosmetic bug:** the kast adapter passes no `overheads=`, so the
  focus/standard block at the head of the night counts as *idle*, making
  `idle_min` read ~15 min high on every Lick plan.
  (5) On a night where nothing is observable `schedule_greedy` returns a frame
  with **no columns at all** — `run()`'s schema-guarantee loop exists for that.
  Any new pass inserted before it must guard for a missing `'scheduled'`
  column.
- **v0.61 — 2026-10-21 (UTC):** Rewrote `docs/priority_system.md` around *"you
  have a targets table with priority values — what happens?"*, replacing the
  2026-10-16 version whose first line was "there is no priority field anywhere
  in this pipeline". Durable points:
  (1) **Docs in this repo describing an absence go stale the fastest.** v0.56
  and v0.57 both documented the missing priority system; v0.58 built it two
  days later and neither doc was touched. When a doc's thesis is "X does not
  exist", it has a shelf life — check `git log` before editing one.
  (2) The useful framing for priority is **precedence, not layers**: feasible →
  blocks → forced → tier → urgency within tier → table order. `reserve_forced`
  runs *before* `schedule_by_priority` and hands its slot back as a block, so
  forcing is strictly stronger than any tier value.
  (3) Priority values are **tier labels, not weights** — only the sort order of
  the distinct values is used, so `1,2,3` and `1,10,100` give identical
  schedules. Worth stating explicitly in any user-facing doc.
  (4) `free_gaps` lives in `scripts/kast_calculations.py:241`, *not* in
  `scripts/schedule_overrides.py` (which has `fit_around_blocks` and
  `push_past_blocks`); and `schedule_overrides.py` is under `scripts/`, not
  `night_planner/`.
  (5) The Keck/LRIS path (`scripts/keck_2026oct06_calculations.py:921`) is
  still `sort_values('window_end')` — tiering exists only in the Kast entry
  point. Any claim that "the planner schedules by priority" needs that caveat.
- **v0.62 — 2026-10-21 (UTC):** Shipping pass for other users: hardcoded-path
  audit, `environment.yml`, `INSTALL.md`
  (`claude_prompts/shipping.md`). Durable points:
  (1) **`night_planner/paths.py` is the only place machine-specific paths may
  live.** Repo-internal paths derive from `__file__`; external ones read
  `FFFF_PZ_REPO`, `NIGHT_PLANNER_PLANS`, `LICK_NIGHT_PLAN_TEMPLATE`. New code
  that needs a plan directory calls `plans_dir()` / `plan_dir(name)` — never
  `REPO_ROOT / 'Night_plans'`, which is how `backend/app.py` had drifted into
  writing somewhere different from the CLI.
  (2) **A default argument relative to the CWD is a hardcoded path in
  disguise.** `estimate_kast_exposures.py` defaulted to
  `Night_plans/Lick-2026B-01/...`, which worked only from the repo root and
  ignored `NIGHT_PLANNER_PLANS`. `tests/test_paths.py` never caught it because
  the literal has no leading slash.
  (3) `tests/test_paths.py` only scans `.py`/`.js`/`.html` *string literals*,
  so a `cd /home/someone/...` inside a markdown fence slips past it — and those
  get copy-pasted. `scripts/check_portability.py` covers code + config + docs,
  exits 1 on a finding, and is now called from `test_paths.py`. It skips
  `Logs/`, `Night_plans/`, `context/`, `claude_prompts/`: those are records of
  one machine on one night, not code. It also has to skip *itself* in that
  test, since it spells out the patterns it hunts.
  (4) **The declared dependencies were five; the code imports eleven.** pandas
  (51 files) and openpyxl (13) were both undeclared. `setup.cfg` now carries
  them plus pytz/requests/certifi, with `[gui]`, `[finders]`, `[dev]`, `[full]`
  extras. `astroplan` is declared and imported *nowhere* — left in place,
  flagged for JXP.
  (5) `environment.yml` pins python 3.12 and solves clean on conda-forge
  (verified with `conda env create --dry-run`). Verify an env file by solving
  it, not by reading it.
  (6) The CLI has **`calc`, `build`, `serve`** — no `generate` — and uses
  dashed flags (`--targets-csv`, `--output-dir`). `build` is wired for
  `lris` only; `kast` has no Excel builder yet (`INSTRUMENTS` in
  `night_planner/cli.py`).
- **v0.63 — 2026-11-07 (UTC):** Sorted the 2026-11 user-testing feedback (7
  users) into tiered goals in `claude_prompts/development/users_comments.md`.
  Durable points:
  (1) **Gaps users noticed that the code confirms:** no detector readout
  model; acquisition is folded into slew; the LRIS ETC uses each target's
  *minimum* airmass, not the scheduled one; seeing is hard-coded at 0.8″;
  Kast has no ETC (empirical magnitude rule); table headers carry no units.
  (2) The "20 min hit" users report is the Keck Dec +20° S→N slew rule.
  Explain it in the interface, don't remove it.
  (3) **Pending conflict:** X (likely JXP) now asks for a 5 min WMKO slew
  baseline and a separate acquisition term; Lordrick asks for 5 min longslit /
  10 min mask. This may reverse the 2026-09-30 "base slew 10 min" rule. Don't
  change `keck_overheads.py` until Q1 in that file is answered.
  (4) The most requested feature is a **live night mode** (mark progress,
  replan from now, planned-vs-actual, as-realized log). It needs the plan to
  become stateful per entry. Design that in `plan_store.py`/`plan_result.py`
  before writing any UI.
- **v0.64 — 2026-11-07 (UTC):** Decisions on the user-feedback goals
  (`claude_prompts/development/users_comments.md`, Decisions table).
  Durable points:
  (1) **X in user comments = JXP; his comments take precedence** over other
  testers'.
  (2) **New Keck overhead model (decided, not yet coded):** slew base 5 min
  (was 10), Dec < +20° → > +20° crossing 14 min (was 20), plus a separate
  acquisition: longslit 5 min, mask 10 min. Supersedes the 2026-09-30 rule
  above once `scripts/keck_overheads.py` is updated. Open: whether the 10 min
  mask acquisition replaces `MOS_MASK_BUFFER_MIN` (Q7), and whether Lick gets
  an acquisition term (Q8).
  (3) **Priorities stay fractional.** Sunil's integer-ranks request was
  declined so existing ranks need no renumbering. Priority is strict tiering,
  never probabilistic; only the value order matters.
  (4) **ETC airmass rule:** default to the worst airmass in the scheduled
  block (conservative), user-adjustable (worst / mid / best).
  (5) **Seeing is a manual input**; no forecast pulling for now.
  (6) **Calibrations (arcs, flats, biases) are not scheduled.** Remove the
  Keck arc/flat blocks (`adapters.py:176`); standards and focus stay. A
  calibrations checklist page replaces them: Lick biases + flats + arcs per
  configuration; LRIS flats + arcs per configuration *and per mask*.
  (7) `t_target` gets a companion per-row `required` flag. Required targets
  get full time or are rejected, never backfilled as partials.
- **v0.65 — 2026-11-07 (UTC):** Wrote
  `claude_prompts/development/user_comments_implementation.md` (renamed by
  the author from implementation.md; 10 milestones for goals
  T1–T4; calibrations checklist first). Code facts found while planning,
  true as of this date:
  (1) `select_targets_for_night` reserves a flat 30 min "for calibrations"
  (`keck_2026oct06_calculations.py:939`), separate from the arc/flat
  overhead blocks in `adapters._keck_overheads`. Both must go together.
  (2) `adapters.lick_kast` emits **no overhead blocks**, so Kast's 20 min of
  focus + evening standard (`FOCUS_MINUTES`, `STD_STAR_MINUTES`) shows as
  idle in the viewer.
  (3) `FinderRequest.targets` already supports rendering a subset of
  finders; only the frontend lacks the button.
  (4) The LRIS path has no partial backfill; `backfill_partials` is
  Kast-only.
  (5) `query_lris_etc` takes `ffilter` (default `sdss_r.dat`), so the
  magnitude band is a pass-through.
  (6) Planned home for instrument numbers other than Keck slew/acq:
  `night_planner/instrument_params.py` (not yet created).
- **v0.66 — 2026-11-07 (UTC):** Added goal T4.2 / Milestone 11: an
  observer's log page (`observing_log.json` per plan) that generates
  `observing_report_<date>.md`. Durable points:
  (1) `scripts/make_observing_report.py` already writes the **FFFF-PZ
  observing-log CSV** (`TNS, FRB_Survey, Resource, mode, date, texp,
  Conditions, success`) from a saved plan + flags. The new log must feed it
  through one shared row builder, not a parallel one. The committed
  `Night_plans/Keck-2026B-02/Keck-2026B-02_report.csv` is the regression
  fixture.
  (2) Design rule: the log is the single as-realized record. Tier 5
  automation (start/finish buttons, data watcher) writes into it with
  `source: auto`, and never into a second file.
  (3) The web interface palette is light (`--bg: #f6f8fb`); there is no
  night mode yet.
- **v0.67 — 2026-11-07 (UTC):** The observer's log and the calibrations
  checklist are **one page** ("Observing log", spec in Milestone 1b of
  `claude_prompts/development/user_comments_implementation.md`), per
  Lordrick. Durable design points:
  (1) A single `observing_log.json` per night holds `night`, `calibrations`,
  `night_checklist`, `conditions`, `targets` and `unplanned`. One
  `merge_log` handles plan regeneration: user-touched rows and ticked
  calibrations are kept as `not_in_plan`, never dropped.
  (2) Calibration items carry UT and frame numbers, not just a tick, because
  reduction (PypeIt) needs the calibration file ranges.
  (3) With multiple scenarios (M10) there is still one log per night.
  Calibrations are the union across scenarios.
  This supersedes the separate `calibrations.json` / `/api/calibrations`
  design in v0.64–v0.66.
- **v0.68 — 2026-11-07 (UTC):** Lordrick answered three plan questions.
  (1) **Lick overheads:** about 3 min slew + 3 min acquisition per target
  (6 min total, replacing the all-inclusive 5 min). This is planned as
  `LICK_SLEW_MIN` / `LICK_ACQ_MIN` in `night_planner/instrument_params.py`.
  Caution: the current 5 min lives in three run-specific scripts
  (`lick_2026b02_calculations.py`, `_extras.py`, `_night2_calculations.py`)
  that the general Kast path imports from. `adapters._attribute_kast_slews`
  only recognises a gap of exactly `SLEW_MINUTES`, so it must change in step
  with the scheduler.
  (2) **Kast target S/N = 10** per sub-exposure (≥ 3 subs); first 5, raised
  to 10 on 2026-11-08 UTC (Lordrick). It is a flag (`--target-sn`). LRIS is 10.
  (3) **ETC plug-in:** function shape, not a class (overrides Sunil's "ETC
  class" for now).
  Q7 (MOS buffer) is still open; the default is to drop it.
- **v0.69 — 2026-11-07 (UTC):** Corrections to v0.68, from Lordrick.
  (1) **Lick overheads are 2 min slew + 3 min acquisition = 5 min per
  target**, not 3 + 3. The total equals the old all-inclusive 5 min, so Kast
  schedule timing is unchanged; only the labels split.
  (2) **Q7: keep the +5 min per-mask buffer (`MOS_MASK_BUFFER_MIN`)** on top
  of the planned 10 min mask acquisition. It is deliberate, not a double
  count, so don't remove it. LRIS mask cost = slew + 10 acq + 60/90/120
  block + 5 buffer.
  All plan questions (Q1–Q8) are now answered.
- **v0.70 — 2026-11-07 (UTC):** Instrument numbers fetched from the web
  (full tables with links: "Data needed" in
  `claude_prompts/development/user_comments_implementation.md`).
  (1) **LRIS readout**
  ([win_bin](https://www2.keck.hawaii.edu/inst/lris/win_bin.html)), elapsed
  time per frame including erase:
  - Red Mark IV, 2 amps (spectroscopy): 1x1 97 s, 2x2 39 s.
  - Blue: 1x1 54 s, 1x2 36 s. **Blue 2x2 is not published.**

  (2) **Kast readout**
  ([hw_detectors](https://mthamilton.ucolick.org/techdocs/instruments/kast/hw_detectors.html)),
  blue/red:
  - Slow, full frame: 43/34 s.
  - Slow, sub-region: 7/20 s.
  - Fast, sub-region: 2/14 s.

  (3) **UCO ETC Kast form:** `inst=kast`.
  - Grisms: G2 = 600/4310, G3 = 830/3460.
  - Grating: 600/7500 only.
  - Dichroics: **d55, d46 only (no d57)**.
  - Slits: 1.0, 1.5, 2.0.
  - Same filters as LRIS: `sdss_{ugriz}.dat`, `Buser_{B,V}.dat`,
    `Cousins_{R,I}.dat`.
  - Output grid: 3150–8000 Å.

  (4) **UCO ETC LRIS form:** dichroics D560, D460, D500, D680.
  (5) **Getting through the ETC's certificate problem:** the server omits its
  intermediate. Use `--cacert scripts/certs/ca_bundle_with_incommon.pem`
  (curl) or `verify=CA_BUNDLE` (requests). Never `-k`.
  (6) **Limits:**
  - Keck I zenith limit is 88.9° elevation, with no stable guiding for
    transits above ~85° ([TelLimits](https://www2.keck.hawaii.edu/inst/common/TelLimits.html)).
  - LRIS rotator physical PA: −239 < x < 189
    ([rotpposn](https://www2.keck.hawaii.edu/inst/lris/procs/rotpposn.html)).
  - Shane HA is −5:40/+3:45 (the page source has a stale commented-out
    +5:40; trust +3:45), and Dec runs −35 to +72 nominal, +82 absolute.

  (7) Verify WebFetch-summarised numbers against the raw HTML. It mis-read
  the Shane west limit.
- **v0.71 — 2026-11-07 (UTC):** Lordrick's answers after the web fetch.
  (1) **LRIS readout in practice: ~80 s blue, ~40 s red** (default 2x2).
  This overrides the web blue numbers (54 s at 1x1). Per-frame cost is
  80 s, the slower arm.
  (2) **Kast: always slow readout.** We use full frame, 43 s blue / 34 s red
  → 43 s per frame (sub-region unconfirmed).
  (3) **Kast ETC dichroic: d55** (d57 isn't offered).
  (4) **LRIS rotator:** starlists send the finder `slit_pa` as
  `rotdest=… rotmode=pa` (sky PA, as in chime-ffff-pz). That has been
  accurate, and Keck converts it to the physical angle. The physical range
  is 428° wide, so no LRIS rotator check is needed.
  (5) **Shane tub reference: `helpful_scripts/calcint.c`.** It covers every
  PA (20–380 → readout 17.45–330.64), so no tub reject rule is needed.
  M9 is now Keck elevation checks only.
- **v0.72 — 2026-11-07 (UTC):** **Kast readout is 20 s per frame**
  (Lordrick: "normally 20 s on the blue side"). This replaces the 43 s full
  frame in v0.71. The Lick page lists 20 s for the *red* slow sub-region and
  7 s for blue; the per-frame cost is 20 s either way.
- **v0.73 — 2026-11-07 (UTC): Milestone 1 implemented.**
  (1) **Calibrations are not scheduled.**
  - No arc/flat overheads.
  - The LRIS end-of-night reserve is
    `keck_2026oct06_calculations.MORNING_RESERVE_MIN` (closing slew to
    Feige 110 + 5 min standard).
  - Calibrations live on the **Observing log** page (`#/log?dir=`).

  (2) **Observing log storage.**
  - `observing_log.json` sits in the plan directory, managed by
    `night_planner/observing_log.py`: `open_log` = load + `merge_log` +
    save; `set_field` validates every edit and records provenance in
    `edits`.
  - Routes: `GET/PATCH /api/log`, `POST /api/log/report`. CLI:
    `night-planner report --plan-dir`.
  - Rows and items with user input survive plan regeneration as
    `not_in_plan`.

  (3) **The report.** `night_planner/observing_report.py` writes
  `observing_report_<date>.md` and the FFFF-PZ CSV.
  `scripts/make_observing_report.py` goes through `build_ffffpz_rows`
  (verified byte-identical on Keck-2026B-02).
  (4) **Rules and checklists.** `night_planner/instrument_params.py` now
  exists (`DEFAULT_CONFIG`, `config_label`, `CALIBRATION_RULES`,
  `NIGHT_CHECKLIST`, `is_mask_mode`); later milestones extend it.
  (5) **Gotcha: `plan.output_dir` is where a plan was generated, not
  necessarily where it is being viewed.** Anything that writes beside a
  plan must use the requested directory: `backend._plan_here` pins it;
  the frontend uses `state.outputDir`.
  (6) **Gotcha: never `pkill -f` a pattern that appears in the same
  command line.** Stop servers by PID.
- **v0.74 — 2026-11-07 (UTC): Milestones 2-10 implemented** (details in
  `claude_prompts/development/user_comments_implementation.md` Logs).
  Durable points:
  (1) **Block anatomy:** start → slew → acquisition → science_start →
  exposures → readout → end. `end - science_start = on_target_min +
  readout_min`. The totals reconcile: on target + slew + acq + readout +
  overheads + blocked + idle = night (`tests/test_overheads.py`).
  (2) **One owner per number:**
  - Keck slew/acq: `scripts/keck_overheads.py`.
  - Everything else: `night_planner/instrument_params.py` (Lick 2+3 min,
    `READOUT_S`, `ETC_OPTIONS`/`ETC_FILTERS`/stand-ins,
    `KECK_ELEVATION_LIMITS`, `CALIBRATION_RULES`).
  (3) **ETC:** `night_planner/etc.py`. Function signature `etc(mag, band,
  airmass, seeing, config, target_sn, n_sub_min)`; registry lris / kast /
  empirical; `load_etc('pkg.mod:func')`; cached. **The Kast default is
  `empirical`, pending Lordrick/JXP**: at S/N 5 the ETC is 0.07× the rule
  at mag 16-17 and 2.4× at mag 21.
  (4) **Tests are offline by construction:** `tests/conftest.py` blocks
  sockets and fakes `query_uco_etc` *session-wide*, because a
  module-scoped fixture would otherwise run first. Real-ETC tests carry
  `@pytest.mark.network` and need `--run-network`.
  (5) **LRIS single-tier schedule pinned** by
  `tests/snapshots/lris_single_tier.json`. Re-record it only on purpose
  (`tests/snapshots/make_lris_snapshot.py`).
  (6) **Keck zenith:** never cut a window at the keyhole. It's a per-target
  block (`zenith_keyhole`); `check_keck_limits(..., ignore_zenith=True)`
  in the window search and the best-airmass check.
  (7) **Scenarios:** `<base>/<slug>/` plan dirs plus
  `<base>/scenarios.json`. One `observing_log.json` at the base;
  `backend._log_context` resolves it.
  (8) **Palette:** check with `scripts/check_palette.py` (CIEDE2000 ≥ 12
  under protan/deutan), never by eye.
  (9) **FFFF-PZ `Pri_filter`** is the band of `Pri_mag`, in the form
  'Survey:Instrument-band'; `targets_io.normalize_band` keeps the band.
- **v0.75 — 2026-11-07 (UTC): user tutorial ("night-planner Handbook"
  artifact, https://claude.ai/artifact/DbC4mVutCjmFyQMh6CxR5Y).**
  (1) **Example tables live in `examples/tutorial/`, not `test_targs/`.**
  `tests/test_test_targs.py` globs `test_targs/*.csv`, so a new table
  there joins every table test. `scripts/make_tutorial_examples.py`
  rebuilds the tables from `test_targs/autumn_ffffpz.csv` (all SIM
  objects). It also writes the two worked Kast plans (2026-10-20, own
  table and FFFF-PZ) as JSON, so the tutorial's numbers can be refreshed
  after the time model changes.
  (2) **`PlanResult.idle_gaps` is a method**, returning [(start, end)].
  (3) The tutorial has a mode switch: "Your own table" vs FFFF-PZ
  (Resource → `chime_ffff_pz_add_furesource` → `chime_ffff_pz_targets` →
  plan → candidates slit → log/FFFF-PZ CSV → `make_pending_targets.py`).
  If pages or flags change, update the artifact by republishing from the
  same template (the scratchpad template does not persist; rebuild from
  the published page).
- **v0.76 — 2026-11-08 (UTC): Kast target S/N 5 → 10.** `TARGET_SN['kast']`
  in `night_planner/etc.py` is now 10 (Lordrick). It matters only with
  `--etc kast`; the empirical rule (still the Kast default) has no S/N term.
  At S/N 10 the UCO ETC wants 3 min at r = 16, 158 min at r = 20 and caps
  at 3 × 7200 s from r = 20.5 (r = 21 reaches only S/N ≈ 7):
  `Night_plans/kast_exposure_model_comparison_sn10.csv`. The full test suite
  fails offline with astropy IERS errors in the sandbox; run it with
  `iers.conf.auto_max_age = None` (or with network) — 144 pass.
- **v0.77 — 2026-11-09 (UTC): target privacy / scrub.** Real targets have
  leaked into 235 tracked files and 239 history paths: `Night_plans/`,
  `Keck-2026B-02_test1000/`, `claude_prompts/night_plans/`, run scripts, Logs,
  this brain, README, docs and some tests. `scripts/scan_private_targets.py`
  catalogues names and positions from the private dir, scans HEAD and every
  commit, and writes `git filter-repo --replace-text` rules
  (names → `TGTnnnn`, positions → `RA/DEC_REDACTED`) into
  `pvt_Nighplans/_scrub/`. `plans_dir()` now defaults to `pvt_Nighplans`; the
  `frb_env` conda env sets `NIGHT_PLANNER_PLANS`. Gotchas: starlists spell
  standards in lower case (`bd284211`); `cand_gal_names` cells are
  Python-list strings; `tests/test_data` synthetic names collide with 2 real
  TNS names, with fake positions. History rewrite pending JXP (see D1–D4 in the
  prompt file).
- **v0.78 — 2026-11-10 (UTC): scrub decisions applied.** Lordrick's answers:
  scrub names and positions (D1), move the run scripts (D2), rescue the docs
  (D3), delete and re-create the GitHub repo (D4). **Engine vs one-off:**
  `keck_2026oct06_calculations.py`, `lick_2026b02_calculations.py`,
  `lick_2026b02_night2_calculations.py` and `lick_2026b01_calculations.py`
  are imported by the CLI, adapters and tests: they are the engine despite
  their run names, so they stay public. The other 13 run scripts now live in
  `pvt_Nighplans/<run>/scripts/`. The removal list is
  `claude_prompts/target_scrub_paths.txt`, shared by `filter-repo` and the
  scan script. **Lesson:** exact-string scans miss rounded positions
  (RA/Dec to 1--2 decimals, or RA in hours). Always run `scan_private_targets.py
  --coarse`, and `--verify` before any rewrite. Rescued docs:
  `docs/Lick-2026B-01_{HOWTO_night_plan_creation,CORRECTIONS_SUMMARY}.md`,
  `docs/data/kast_exposure_model_comparison*.csv`. Claude Code's safety
  check blocks `rm` in a `bash -c` script; leave deletions to the user.
- **v0.79 (2026-11-10)** — Fresh-repo route chosen over `filter-repo`. New
  `scripts/build_public_snapshot.py` copies the kept tracked files, applies
  `replace_text.txt`, and audits the copy (`--update` refreshes it,
  `--audit-only` only checks it). Built `~/Projects/quick_night_planner`: 218
  files, 0 names, 0 exact positions; 144 tests pass there (run with
  `PYTHONPATH` set to it, because `frb_env` has night-planner installed in
  editable mode from the old repo). **Lessons:** (1) real positions written as RA in
  hours to 2 dp are up to 0.075 deg off, and truncation to 1 dp up to 0.1 deg,
  so the rounded-position check now uses 0.1 deg (0.2 deg for hours).
  (2) I had written a real rounded position as an *example* in my own
  notes and in a docstring. (3) Tests that run on real private data must
  not name a real target; `test_observing_log` now reads its `--extra` from
  the private `Keck-2026B-02/report_extra.txt`.
