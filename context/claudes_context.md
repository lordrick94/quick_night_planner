# Claude's Context — night-planner

Product context for the **night-planner** project: a survey of two external code
bases relevant to telescope night planning, plus the astropy primitives they (and
we) build on. Written 2026-07-11 by executing `claude_prompts/context_prompts.md`
(Code section, prompt 1). Everything below was read directly from the repos/docs
cited; where I did not verify a detail I say so.

---

## 1. FFFF_PZ — FRB follow-up target & observation management

**Repo:** <https://github.com/FRBs/FFFF_PZ> — a fork of **YSE_PZ** (Coulter et
al. 2023, arXiv:2303.02154), the Young Supernova Experiment's Django-based
transient survey management platform, adapted for **FRB follow-up by "F4"**
(the FRB follow-up collaboration). It is a full web application (Django + MySQL,
Docker-deployed) whose job is *human-in-the-loop* target management: ingest
transient alerts, associate host galaxies, and drive follow-up decisions.

### Architecture (night-planning-relevant slice)

All application code lives in the Django app `YSE_App/`. FRB-specific logic is
in top-level `YSE_App/frb_*.py` modules; the ORM data model is in
`YSE_App/models/`.

**Facility data model** (a chain of Django models):

- `models/observatory_models.py` — `Observatory`: name, `utc_offset`,
  `tz_name`, plus daylight-savings fields (`DLS_utc_offset`, `DLS_start/end`).
- `models/telescope_models.py` — `Telescope`: FK to Observatory + `latitude`,
  `longitude`, `elevation` (the geodetic inputs for airmass computations).
- `models/instrument_models.py` — `Instrument` (FK to Telescope) →
  `InstrumentConfig` → `ConfigElement` (many-to-many): instrument setups as
  composable named elements.
- `models/telescope_resource_models.py` — `TelescopeResource` (telescope + PI +
  groups + `begin_date_valid`/`end_date_valid`, i.e. a semester allocation) with
  subclasses **`ToOResource`** (awarded/used ToO hours *and* triggers),
  **`QueuedResource`** (awarded/used hours), **`ClassicalResource`** with
  `ClassicalObservingDate` (specific scheduled nights, each with a
  `ClassicalNightType`). This captures the three professional observing modes:
  classical / queue / ToO.

**FFFF-PZ servers** (credentials and URL in `~/.bashrc`; the CLI reads
`FFFF_PZ_URL`/`FFFF_PZ_USER`/`FFFF_PZ_PASS`):

- Global: `https://frb.chimenet.ca/f4pz/` (alias `set_ffff_pz_global`).
- Local docker: `http://0.0.0.0:8000/` (alias `set_ffff_pz_local`).
- Resources are per server, so one added locally does not exist on global.
  `chime_ffff_pz_add_furesource` (`add_frb_resource/`) **adds or modifies**
  by name. Check that a name is free first: a target pull on a missing name
  returns 402 "Could not find resource".

**The observing-run model** — `models/frbfollowup_models.py`:

- `FRBFollowUpResource` ≈ *one observing run*: `name`, `instrument` (FK),
  `valid_start`/`valid_stop` (UT datetimes), **per-mode target counts**
  (`num_targ_img`, `num_targ_longslit`, `num_targ_mask`), **`max_AM`** (maximum
  acceptable airmass), and target-selection criteria: `frb_surveys`,
  `frb_tags`, `frb_statuses`, `min_POx` (minimum PATH host-association
  probability P(O|x)), `min_mag`/`max_mag` host-magnitude cuts. Optional
  `obs_type` (Classical/ToO/Queue), `PI`, `Program`, `Period` (e.g. "2024A").
- Key methods: `get_frbs_by_mode()` (filter candidates, apply the airmass
  feasibility cut, split by mode) and `generate_target_table()` → a **pandas
  DataFrame** of observable targets for the run.

### Target selection & the airmass filter — `YSE_App/frb_targeting.py`

- `calc_airmasses(frb_fu, gd_frbs)` — the core visibility computation, built
  directly on **astroplan + astropy**:
  1. `EarthLocation.from_geodetic(telescope.longitude*u.deg, telescope.latitude*u.deg, telescope.elevation*u.m)`
     → `astroplan.Observer(location=..., timezone="UTC")`.
  2. Loop over the nights between `valid_start` and `valid_stop`, bounding each
     night with `Observer.twilight_evening_astronomical()` /
     `twilight_morning_astronomical()` (note the `which='previous'` idiom to
     step night-by-night without an infinite loop).
  3. Sample every **30 minutes**; `altaz = tel.altaz(time, frb_coords)`
     (vectorized over all targets at once via a single `SkyCoord` array);
     airmass computed as plain **sec z** = `1/cos(zenith)`, set to 1e9 below
     the horizon.
  4. Return the **minimum airmass each target reaches during the run**; the
     caller keeps targets with `min_AM <= resource.max_AM`.
- `targetfrbs_for_fu(frb_fu)` — Django QuerySet filtering by survey, transient
  status (default: `NeedImage` / `NeedSpectrum` / `NeedSecondary`), and tags.
- `grab_targets_by_mode(...)` — mode logic: **imaging** targets are those with
  status `NeedImage` (no host identified yet); **longslit** targets need status
  `NeedSpectrum` plus host `P_Ox > min_POx` and magnitude cuts; **mask** not
  implemented. This is why every pulled target comes back tagged `longslit`
  even when `num_targ_mask > 0`. The night-planner re-derives MOS from
  magnitude (mag > 21).
- `select_with_priority(...)` / `assign_probs(...)` — when more targets pass
  than requested (`num_targ_*`), draw probabilistically (uniform random vs
  tag-derived priority probabilities, looping until N selected). Selection is
  stochastic, not an optimizer.
- `target_table_from_frbs(frbs, mode)` — builds the target table rows: TNS
  name, FRB RA/Dec, DM, survey, tags, and the **top-two host candidates by
  PATH P(O|x)** (name, RA/Dec, P_Ox, magnitude+filter), plus `mode`.

### Plan/log round-trip — `YSE_App/frb_observing.py`

- `ingest_obsplan(obsplan: pandas.DataFrame, user, iresource)` — a *night plan*
  is a simple table with columns `TNS`, `Resource`, `mode`. Ingest scrubs
  previous pending requests for the resource, validates each target's status
  against its mode, creates `FRBFollowUpRequest` rows, and updates statuses.
  Returns `(int, str)` HTTP-like status codes.
- `ingest_obslog(obslog: pandas.DataFrame, ...)` — the *observing log* comes
  back as a table with columns `TNS, Resource, mode, Conditions, texp, date,
  success`, creating `FRBFollowUpObservation` rows and advancing each
  transient's status (lifecycle logic in `YSE_App/frb_status.py`:
  NeedImage → NeedSpectrum → ... driven by what data exist).

### What FFFF_PZ teaches night-planner

- The **shape of a plan**: run (instrument + UT validity window + N targets per
  mode + selection criteria + max airmass) → filtered target table → priority
  down-select → flat table handed to the observer → log table ingested back.
- The **min-airmass-over-run feasibility filter** (twilight-bounded, 30-min
  sampling, vectorized SkyCoord) is a compact, proven astroplan pattern we can
  reuse almost verbatim.
- Facility config as Observatory → Telescope(lat/lon/elev) → Instrument →
  Config hierarchy; observing time as Classical/Queue/ToO resources.
- Highly relevant socially: same FRB community (fork "for FRB follow-up by
  F4"), PATH P(O|x) host association — the author's own science workflow.
- Caveat: FFFF_PZ selects *which* targets are observable in a run; it does
  **not** sequence targets within a night (no per-night ordering/scheduling).
  That gap is exactly what night-planner should fill.

---

## 2. JSkyCalc — Thorstensen's "time and the sky" calculator

**Repo:** <https://github.com/jrthorstensen/JSkyCalc> — John Thorstensen's
(Dartmouth) classic interactive observing-planning tool, the Java GUI
descendant of his C `skycalc`. The GitHub repo ships **only `JSkyCalc.jar` and
a README** ("The source is not included; message me if you would like it").

To examine actual code I read the author's Python port,
**<https://github.com/jrthorstensen/thorsky>** ("Python time-and-the-sky
programs built mostly on astropy", successor to deprecated `pyskycalc`), which
implements the same computations: modules `thorskyutil.py` (~1600 lines of
functions), `thorskyclasses3.py` (site/observation classes), and
`pyskycalc3.py` (a Tkinter GUI "generally similar to the java program
JSkyCalc"). Statements below cite those files.

### Core data structures (`thorskyclasses3.py`)

- `obs_site` — observatory: name, `EarthLocation` (geocentric xyz), local
  timezone; defaults to MDM/Kitt Peak; `get_sites()` reads a site file.
- `Observation` — bundles `celest` (a `SkyCoord`), `t` (an astropy `Time`), and
  a site. Methods: `computesky()`, `computesunmoon()`, `computeplanets()`,
  `computebary()` / `computequickbary()`, `setnightevents()`,
  `compute_hours_up()`, `printnow()`, `printnight()`.

### Instantaneous circumstances (`Observation.computesky` + `printnow`)

For one (site, time, target), JSkyCalc computes and displays:

- **LST** — `lpsidereal(time, location)` (fast low-precision sidereal time).
- Current-equinox coordinates (precession matrices, `currentFK5frame` /
  `currentgeocentframe`) and constellation.
- **Hour angle** = LST − RA, wrapped to ±12 h (`wrap_at(12.*u.hour)`).
- **Alt, Az, parallactic angle** — `altazparang(dec, ha, lat)` (spherical
  trig, no refraction); the parallactic angle (and its ±180° alternative) is
  printed for slit-orientation decisions.
- **True airmass** — `true_airmass(alt)`: a 4th-order polynomial fit to the
  Snell & Heiser (1968, PASP 80, 336) KPNO airmass tables in (sec z − 1),
  i.e. *better than plain sec z at large zenith distance*; valid to airmass
  ~12, returns sec z − 1.5 beyond.
- **Moon**: position (`lpmoon` fast / `accumoon` accurate), altitude/azimuth,
  **illuminated fraction**, human phase description (`phase_descr`, via
  `flmoon` Meeus-style phase JDs), **moon–object angular separation**, and
  **lunar sky brightness in V mag/arcsec²** — `lunskybright(...)` implementing
  **Krisciunas & Schaefer (1991, PASP 103, 1033)** (dark sky ≈ 21.5).
- **Sun**: position (`lpsun`), alt/az; twilight state, with `ztwilight(alt)`
  giving how many mag brighter than dark sky the twilit sky is.
- **Barycentric corrections**: time and velocity — the slow path uses astropy's
  `SkyCoord.radial_velocity_correction()` and
  `Time.light_travel_time(coord, kind='barycentric')`; prints "add X sec and
  Y km/s to observed" plus barycentric JD.
- Planetary positions (`computeplanets`), and a bright-star sky display done
  with cached rotation matrices (`precessmatrix`, `cel2localmatrix`,
  `icrs2topoxyz`) for speed.

### Per-night almanac (`setnightevents` / `printnight`; `nightevents()` in thorskyutil)

The "night events" block — the skeleton every night plan hangs on:

- **Sunset/sunrise** at altitude **−0.833°** (zenith distance 90° 50′,
  refraction + solar semi-diameter).
- **Evening/morning astronomical twilight** at sun altitude **−18°**.
- **Center of night** (midpoint), **moonrise/moonset** (same −0.833°).
- Algorithm: analytic first guess from hour angles (`ha_alt(dec, lat, alt)` =
  the HA at which a dec reaches a given altitude), then iterative refinement
  (`jd_sun_alt`, `jd_moon_alt`). All reported in local time (or UT).

### Observability helpers (`thorskyutil.py`)

- `min_max_alt(lat, dec)` — min/max altitude a declination ever reaches.
- `ha_alt(dec, lat, alt)` — hour angle at which the target crosses altitude
  `alt` (rise/set/critical-airmass HA).
- `hrs_up(timeup, timedown, evening, morning)` — **hours a target is above a
  critical altitude within the observing night** (clipped to twilights);
  exposed per-object as `Observation.compute_hours_up()`. This "hours up
  tonight at airmass < X" number is the single most useful observability
  scalar for ranking targets.

### What JSkyCalc teaches night-planner

- The **canonical quantity checklist** for any per-target, per-time display:
  LST, HA, alt/az, airmass, parallactic angle, moon alt/illumination/
  separation/sky-brightness, sun alt/twilight state, barycentric corrections.
- The **night-event definitions to adopt**: rise/set at −0.833°, astronomical
  twilight at −18°, night center; moon events likewise.
- Two clean layers: *instantaneous circumstances* vs *per-night events* —
  a good module split for our code.
- Physics upgrades over naive formulas worth carrying: true-airmass polynomial
  (Snell & Heiser) instead of sec z near the horizon; Krisciunas & Schaefer
  moon sky-brightness model rather than a bare moon-separation cut.
- astroplan reproduces most of this (Observer.twilight_*, moon_illumination,
  parallactic_angle, target rise/set), so we get JSkyCalc's outputs through
  our existing dependency — thorsky is the reference for *definitions* and for
  anything astroplan lacks (e.g., `lunskybright`, `hrs_up`).

---

## 3. astropy — the primitives underneath everything

(Skimmed at docs.astropy.org, stable: the `astropy.coordinates` and
`astropy.time` docs, plus the example-gallery page "Determining and plotting
the altitude/azimuth of a celestial object" — an end-to-end observation-
planning walkthrough.)

### The three pillars

- **`astropy.units`** (`u.deg`, `u.hourangle`, `u.m`, ...) — every angle,
  length, and time interval is a `Quantity`; both repos above pass units
  explicitly (e.g. `telescope.longitude*units.deg`).
- **`astropy.time.Time`** — time scales `utc, ut1, tt, tai, tdb, tcg, tcb,
  local`; formats `jd, mjd, iso, isot, datetime, ...`; arithmetic via
  `TimeDelta` (used by FFFF_PZ for 30-min/1-day stepping:
  `TimeDelta(1800, format='sec')`). Sidereal time:
  `t.sidereal_time('apparent'|'mean', longitude)` (needs a longitude or a
  `location` on the Time). Barycentric/heliocentric light-travel time:
  `t.light_travel_time(skycoord, kind='barycentric', location=...)` → add to
  `t` for BJD (exactly what thorsky's `computebary` does).
- **`astropy.coordinates`** —
  - `SkyCoord(ra=..., dec=..., unit='deg')`, accepts arrays (vectorize over
    targets); `SkyCoord.from_name('M33')` resolves names via Simbad/Sesame.
  - `EarthLocation.from_geodetic(lon, lat, height)` or
    `EarthLocation.of_site('keck')` (named-observatory database).
  - `AltAz` frame: the whole observability computation is one line —
    `target.transform_to(AltAz(obstime=times, location=loc))` → `.alt`, `.az`,
    and **`.secz`** for airmass. Passing an *array* of times gives the
    altitude/airmass track for a night in a single vectorized call.
  - `get_sun(time)` and `get_body('moon', time, location)` for solar/lunar
    positions → sun altitude < −18° defines dark time; moon–target separation
    via `SkyCoord.separation()`.

### How they combine (the canonical recipe)

```
loc    = EarthLocation.of_site(...)               # or from_geodetic
times  = midnight + delta_hours                    # Time + np.array*u.hour
frame  = AltAz(obstime=times, location=loc)
altaz  = target.transform_to(frame)                # .alt, .az, .secz
sunalt = get_sun(times).transform_to(frame).alt    # twilight/dark windows
moon   = get_body('moon', times, loc)              # separation, altitude
```

### Caveats noted

- `.secz` is the plane-parallel approximation — fine to Z ≈ 70–75°, degrades
  near the horizon (hence JSkyCalc's Snell & Heiser polynomial).
- The `AltAz` transform includes atmospheric refraction only if you supply
  `pressure` (and optionally temperature/humidity/obswl); by default it is
  unrefracted.
- Moon positions should be requested with a `location` for topocentric
  accuracy; sun/moon coordinates come back in GCRS, so transform both target
  and body into the same `AltAz` frame before taking separations near the
  horizon.

### The astroplan connection

**astroplan** (already in our `setup.cfg`/`requirements.txt`) is a thin,
Astropy-affiliated layer over exactly these primitives: `Observer` wraps
`EarthLocation` + timezone (adding `altaz()`, `twilight_evening_astronomical()`,
`twilight_morning_astronomical()`, moon/sun conveniences, `parallactic_angle()`),
`FixedTarget` wraps `SkyCoord`, and its constraints/schedulers operate on grids
of the same `AltAz` transforms. FFFF_PZ's `calc_airmasses` is a working example
of driving astroplan this way; thorsky shows the same computations done from
raw astropy (plus faster low-precision shortcuts). night-planner should follow
FFFF_PZ's pattern (astroplan on top) and use thorsky/JSkyCalc as the reference
for definitions and output content.

---

## Synthesis for night-planner

1. **Plan structure** (from FFFF_PZ): an observing run = instrument + UT window
   + per-mode target counts + selection criteria + max airmass; the deliverable
   is a flat target table; the return product is an observing log table.
2. **Night skeleton** (from JSkyCalc): sunset/−18° twilight/night center/
   −18° twilight/sunrise + moon rise/set/illumination — compute these first,
   then place targets.
3. **Per-target metrics** (both): HA, alt/az, airmass (true airmass if pushing
   high Z), parallactic angle, moon separation + lunar sky brightness,
   hours-up-tonight below the airmass limit.
4. **Engine**: astropy `SkyCoord`/`Time`/`AltAz` via astroplan `Observer`;
   vectorize targets in one `SkyCoord` array and times in one `Time` array.
5. **Gap we fill**: neither tool *sequences* a night (FFFF_PZ stops at target
   selection; JSkyCalc is a calculator, not a scheduler) — ordering targets by
   transit/airmass windows within the twilight-bounded night is night-planner's
   core job (astroplan's Scheduler is the starting point).

---

## Ephemeris websites (UCO/Lick & Keck calendars)

(Added 2026-07-11, executing `claude_prompts/context_prompts.md`, Websites >
Ephemeris, prompt 1. All pages below were fetched and verified.)

The University of California Observatories hosts pre-computed observing
calendars (compiled by Dr. Arnold Klemola; contact `webeditor@ucolick.org`) —
an authoritative, site-specific nightly almanac for the two facilities we care
most about.

**Read this first — the explanatory readme:**

- <https://ucolick.org/calendar/readme.html> — describes what the calendars
  tabulate: sunrise/sunset, moonrise/moonset, sidereal times (at twilight,
  midnight, and dawn), and length of night (whole night, dark hours, % dark).
  Each calendar comes in **two twilight variants**: nautical (sun −12°) and
  astronomical (sun −18°).

**Lick Observatory (Mt. Hamilton, altitude 1283.0 m; times in PST):**

- <https://ucolick.org/calendar/lickcal2011-20/index.html> — years 2011–2020.
- <https://ucolick.org/calendar/lickcal2021-30/index.html> — years 2021–2030.

**Keck Observatory (Maunakea; computed for altitude 4160.0 m; times in HST):**

- <https://ucolick.org/calendar/keckcal2011-20/index.html> — years 2011–2020.
- <https://ucolick.org/calendar/keckcal2021-30/index.html> — years 2021–2030.

**Structure (verified by fetching the pages):** the four index URLs are pure
navigation pages — for each year they link 12 monthly calendar files per
twilight variant (e.g. `keck2021.18jan` = Keck, January 2021, 18° twilight;
`lick2021.12jan` = Lick, January 2021, 12° twilight). Adjacent-decade indexes
(1998–2010, 2031–2040, 2041–2050) are linked from the same pages.

**Per-month table contents (verified on `lick2021.18jan` and
`keck2021.18jan`):** one row per night — "ONE LINE REFERS TO EVENING DATE AND
FOLLOWING MORNING" — with columns for DATE (local zone), SUN SET, TWILIGHT
ENDS (12° and 18°), MOON RISE / MOON SET, DAWN BEGINS (18° and 12°), SUN RISE,
SIDEREAL TIMES (at twilight end, midnight, and dawn), NIGHT LENGTH / DARK
LENGTH, and the Moon at midnight (RA, Dec, distance). All dates/times are in
the site's local standard zone (PST for Lick, HST for Keck) *except* the
sidereal times; footers also list the month's moon-phase dates (new/quarters/
full).

**Use for night-planner:** these tables are an independent, observatory-
blessed reference for exactly the night-skeleton quantities we compute with
astroplan/thorsky (sunset/sunrise, 12°/18° twilights, moon rise/set, LST,
night/dark length) — ideal for **cross-checking our computed values** for any
Lick or Keck night in 2011–2030, and as a quick human-readable lookup when no
code is at hand.

---

## Instrument manuals (Lick, Keck, Palomar, Gemini)

(Added 2026-07-11, executing `claude_prompts/context_prompts.md`, Websites >
Instrument manuals, prompt 1. Summaries below come from fetching each manual/
homepage; where a page was a hub or blocked I say so and note which facts came
from linked/secondary Keck-Gemini documentation. Unverified numbers are
omitted or flagged approximate.)

These are the instruments night-planner must eventually be able to plan for.
**Instrument choice drives the plan's constraints:** wavelength coverage sets
moon/twilight tolerance (blue/UV wants dark time; NIR tolerates moon); MOS
instruments need slitmasks designed (and, except MOSFIRE, physically milled)
*days-to-weeks before* the night; single-slit instruments raise
parallactic-angle/ADC and slit-PA decisions at plan time; mount (Cassegrain vs
Nasmyth) affects rotator/PA behavior.

### Lick Observatory — Shane 3 m

- **Kast** — dual-channel (blue + red) **longslit spectrograph** with direct
  imaging; **Shane 3 m, Cassegrain focus**.
  <https://mthamilton.ucolick.org/techdocs/instruments/kast/>
  The two arms observe **simultaneously via a dichroic beamsplitter**
  (post-2016 dichroics split at **4600 Å and 5700 Å**); separate gratings
  (red) / grisms (blue) per side give a range of dispersions (details on
  sub-pages; the top page is a hub linking Blue Side / Red Side / Position
  Angle / Arc & Flat lamps / Exposure Time Calculator pages). A
  spectropolarimeter module exists. Night-planning notes: Cassegrain mount →
  slit **position angle** is set by the rotator (dedicated PA sub-page);
  calibration (arc/flat) lamp sets are part of the standard setup; **new users
  must be checked out by a resident astronomer** on their first night.

### Keck Observatory — Keck I & II (10 m)

- **HIRES** — grating cross-dispersed **echelle spectrograph** (high
  resolution); **Keck I, right Nasmyth (f/15)**, permanently mounted.
  <https://www2.keck.hawaii.edu/inst/hires/>
  Coverage **0.3–1.0 µm** (complete in one setting shortward of ~6200 Å;
  redward needs two echelle settings); **R ≈ 25,000–85,000** set by slit
  (decker) plates; fixed slit plates only — **no multi-object mode** (order
  separation 6–43″ limits slit length). Two cross-disperser configs,
  **HIRESb** (blue) vs **HIRESr** (red), **cannot be swapped during the
  night** — a hard planning constraint. Nasmyth mount → field rotation during
  exposure; an **image rotator** holds either a fixed slit PA or the
  **parallactic angle**. Extras: exposure meter, iodine cell (precision RVs).
- **LRIS** — **imager + longslit + multi-object (slitmask) spectrograph**;
  **Keck I, Cassegrain**.
  <https://www2.keck.hawaii.edu/inst/lris/lrishome.html>
  Blue and red cameras observe **simultaneously via dichroics**, total
  coverage **3200–10,000 Å**; blue arm uses grisms, red arm gratings, both
  **R ≈ 300–5000**; FOV **6′ × 7.8′** (imaging and spectroscopy), pixel scale
  0.135″/pix; UBVGRI + narrowband filters; optional spectropolarimeter; peak
  system efficiency ~50%. **Slitmasks are milled on-site at Keck** — MOS masks
  must be designed and submitted well before the run (days–weeks lead time),
  so MOS targets must be locked in at proposal/pre-run stage, not on the night.
- **MOSFIRE** — near-IR **multi-object spectrograph + imager**; **Keck I,
  Cassegrain** (since 2012).
  <https://www2.keck.hawaii.edu/inst/mosfire/home.html>
  Top page is a hub (Pre-/Observing/Post-Observing links); band/resolution
  numbers below are from the MOSFIRE instrument paper & UCLA IR Lab pages:
  coverage **0.97–2.41 µm, one band (Y, J, H, or K) at a time**, **R ≈ 3500**
  for a 0.7″ slit; FOV **6.1′ × 6.1′**; H2RG 2K×2K detector. Its
  **cryogenic Configurable Slit Unit (CSU)** — 46 slit pairs — is
  **reconfigured electronically in < 5 minutes**: no physical mask milling, so
  mask designs (made in software) can be changed between targets during the
  night, unlike LRIS/DEIMOS/GMOS. NIR instrument → far more moon-tolerant;
  plan around OH-sky variability and AB nod patterns instead.
- **DEIMOS** — visible-wavelength **multi-slit imaging spectrograph** (MOS +
  longslit + imaging); **Keck II, Nasmyth** (since 2002).
  <https://www2.keck.hawaii.edu/inst/deimos/>
  Up to **~5000 Å of coverage per exposure**, resolution up to **R ≈ 6000**;
  **16.6′ slit length** on sky (~2× LRIS); typically **100+ slits per mask**
  (1000+ point sources with narrowband filters); 8K×8K CCD mosaic;
  closed-loop **flexure compensation** (±0.25 px over 360° rotation). Like
  LRIS, masks are physically milled — **design/submission lead time before
  the run is mandatory** for MOS work.
- **ESI** — **echellette spectrograph and imager**; **Keck II, Cassegrain**.
  <https://www2.keck.hawaii.edu/inst/esi/>
  Cross-dispersed echellette mode: **complete 0.39–1.1 µm coverage in a
  single exposure** at up to **R ≈ 13,000** with a **20″ slit**; low-dispersion
  prism mode **R ≈ 1000–6000** with an **8′ long slit**; direct imaging over
  **2′ × 8′**. Open-loop flexure compensation (±0.25 px over full rotation).
  Fixed-format echellette → minimal nightly configuration choices (good
  "one-setup" workhorse for faint-object full-optical spectra).
- **KCWI** — bench-mounted **integral field (IFU) spectrograph**; **Keck II,
  right Nasmyth**.
  <https://www2.keck.hawaii.edu/inst/kcwi/>
  Two channels split by a **dichroic at 5600 Å**: blue **3500–5600 Å**
  (gratings BL R≈900, BM R≈2000, BH1–3 R≈4500) and red **5400–10,800 Å**
  (RL R>500, RM1–2 R>1400, RH1–4 R>3250). Three selectable image slicers
  share a 20.4″ axis: **Small 8.4″ × 20.4″ (0.35″ sampling), Medium
  16.5″ × 20.4″ (0.69″), Large 33″ × 20.4″ (1.35″)**; resolution scales with
  slicer (Small ≈ 4× the Large-slicer R). **Nod-and-shuffle** offered on the
  blue channel (not red, as of 2023B); the Large slicer is best for extended
  emission / sky-subtraction-limited work. Blue/UV IFU science strongly
  prefers **dark time** — moon phase is a first-order scheduling constraint.

### Palomar — Hale 200-inch (P200)

- **NGPS** — Next Generation Palomar Spectrograph, the **4-channel UV–NIR
  medium-resolution slit spectrograph** replacing the 1970s Double
  Spectrograph (DBSP); **P200, Cassegrain (f/13.6)**.
  <https://caltechopticalobservatories.github.io/NGPS/> (hub; specs at
  `technical-specifications.html`, plus a Users Manual and Science pages)
  Four channels observed **simultaneously**: **U 3050–4430 Å, G 4250–5960 Å,
  R 5620–7950 Å, I 7530–10,400 Å** (total 3050–10,400 Å in one shot);
  **R > 4000 at the narrowest slit** (~4100–4500 at 0.4″); a **3-slice
  adjustable-width slicer/IFU** (slices 50″ long, each 0.36–10″ wide)
  recovers slit losses. Acquisition/guiding: offset guider FOV
  **4.44′ × 4.15′** plus two slice-viewing cameras (21″ × 50″). Planning
  tools shipped with the instrument: **exposure-time calculator and an
  "Observation Timeline Modeler"** (target-list/timeline planning) — worth
  studying as prior art for night-planner.

### Gemini — 8 m (North & South)

- **GMOS** — Gemini Multi-Object Spectrograph: **imager + longslit + MOS
  (slitmask) + IFU**, one copy on **each** of Gemini North and South.
  <https://www.gemini.edu/instrumentation/gmos>
  (The gemini.edu page returned HTTP 403 to our fetcher — facts below are from
  Gemini's own documentation/summary text retrieved via search and the
  GMOS performance paper, Hook et al. 2004, PASP 116, 425.)
  Coverage **0.36–1.03 µm**; imaging/spectroscopy over a **~5.5′ × 5.5′
  field**; four modes: imaging, longslit, MOS, IFU. MOS masks typically hold
  **30–60 slits** (several hundred with narrowband filters) and are cut from
  mask designs prepared in advance (usually from GMOS pre-imaging) — another
  **daytime mask lead-time** instrument. IFU covers **~35 arcsec² at 0.2″
  sampling**. Resolving power up to **R ≈ 10,000** with 0.25″ slits; a suite
  of gratings (e.g. B1200, R600) of which **only three are mounted at a
  time** — configuration must be declared before the night. Gemini runs
  queue-based observing (Phase II via the Observing Tool; see the OT notes in
  `claudes_brain.md`), so "planning" here means OB construction rather than
  a classical night sequence.

---

## Observing archive: how the astronomers plan a night (/mnt/scratch/xavier/Observing)

(Added 2026-07-12, executing `claude_prompts/context_prompts.md`, Night plans,
prompt 1. This is the author's REAL archive of past observing runs — read
directly from disk. Everything below cites actual files; the archive holds
~4400 files, so I sampled the human-readable planning material rather than
reading everything. Where I infer, I say so.)

The archive has two trees: **`Observing/`** — the planning material (the gold),
and **`Observations/`** — reduced data/results by facility.

### 1. Directory convention — the run-folder template

`Observing/<Instrument>/<Run>/…` with Instrument ∈ {DEIMOS, HIRES, KCWI, LRIS,
MOSFIRE, NIRC2, ToO} and Run a semester/month tag (`2022Oct`, `2023A`,
`KCWI_2021A`, `2025A/Feb26`; multi-night runs get per-night subfolders like
`2021May/May10`, `May11`). A mature run folder (e.g. `DEIMOS/2022Oct/`,
`LRIS/2023A/`, `DEIMOS/2023Dec/`) contains:

- **Night plan doc** — `DEIMOS_ 2022 Oct Night plan.docx`, `LRIS_2023_Apr.docx`,
  `Keck_HIRES May 2026.docx`, `KCWI/2018Oct/Nightly Plans.docx` (one doc can
  cover several nights, or one doc per night: `Nov4_plan.docx`, `Nov5_plan.docx`).
- **Keck starlist** — `deimos_starlist.txt`, `starlist.txt`,
  `starlist_2020oct12.txt`, `masterStarlist.txt`,
  `Keck_DEIMOS_2023-12-14_stlist_kyle.txt`.
- **Instrument configuration** — `inst_config.txt` (Keck SIAS form dump) and/or
  a `Config.docx`.
- **Target descriptions** — `Targets.docx`, per-program docs (KCWI runs carry
  one docx per science program: `FRB180924.docx`, `UDGs.docx`, `Type-II
  QSOs_.docx`, …), and target spreadsheets (`target_info.xlsx`,
  `targets.xlsx`).
- **Finder charts** — `Finder charts.docx`, `Finders/` folders (one docx per
  target incl. `Standard stars.docx` in `LRIS/2023A/Finders/`).
- **Slitmask designs** (MOS runs) — `mask_design_folders/` or `Masks/` with per-
  mask `*.lst` (mask center + PA + selected objects), `*.obj` (object catalog:
  name, RA, Dec, equinox, mag, band, priority), and DS9 `*.reg` files
  (slit boxes on sky, e.g. `frb230718.reg`: `box(128.163497d, -40.453903d,
  42.2", 1.0", 59d)`).
- **Observing logs** — `Obs_logs*.xlsx` (also per-night: `Obs_logs_Nov4.xlsx`),
  sometimes Keck-generated HTML logs (`18-10-07_KCWI_U074.html`).
- **README / strategy docs** — `README_observing_strategy.docx` (DEIMOS
  2022Oct), `README.docx` (LRIS 2020Jan), plus instrument-tips docs
  (`KCWI/Mar2018/Observing_Tips.docx`, `NIRC2/2023Aug/Extra Keck Notes
  (Michele).docx`).
- **Backups** — `LRIS/2023A/Backups/` holds backup-program docs
  (`sGRB_Backup_LRIS_Apr.docx`, `Tang Backup Targets.docx`).
- Sometimes post-run **PypeIt reduction trees** (`DEIMOS/2023Dec/2023dec/redux/
  keck_deimos_*/*.pypeit`, `*.par`, `Science/spec1d_*.txt`, `QA/*.html`) and
  even logistics (`Flights.docx`, `Food.docx`).

This folder layout is itself the template a night-planner deliverable should
emulate: plan + starlist + config + targets + finders + masks + log skeleton.

### 2. The Keck starlist format (verified across DEIMOS/HIRES/LRIS/KCWI)

Fixed leading columns, then free-form `keyword=value` options and `#` comments:

```
name(<~16 char)  HH MM SS.ss  ±DD MM SS.s  equinox  [keyword=value ...]  [# comment]
```

Real examples read from the archive:

- `DEIMOS/2022Oct/deimos_starlist.txt` — science target + offset star pairing:
  ```
  J073802.33+274948.81      07 38 02.33 +27 49 48.81 2000.00 rotdest=128.30 rotmode=PA vmag=22.0
  J073802.33+274948.81_OFF  07 38 02.03 +27 49 51.89 2000.00 rotdest=128.30 rotmode=PA vmag=17.5 raoffset=3.89 decoffset=-3.08
  ```
- `LRIS/2020Oct12/starlist_2020oct12.txt` — sections separated by comments
  (`# Longslit`, `# FRBs`, `# DLA`, `# Standards`, `#Slitmask name …`), e.g.
  `FRB180301_o  06 12 53.70 +04 40 13.3 2000.0 raoffset=12.7 decoffset=-2.2 rotmode=pa rotdest=356.2`
- `HIRES/2026A/starlist.txt` adds `lgs=0 pa=0.00`; the HIRES plan doc embeds a
  standard-star line with proper motion: `bd29d2091  10 47 23.163 +28 23 55.92
  2000.0 vmag=10.1 pmra=0.0118 pmdec=-0.8247 # 10994 F5 D`.
- `KCWI/2018Oct/masterStarlist.txt` — grouped by program with blank lines,
  `#` comments carrying redshift/mag/reference, and explicit beginning/end-of-
  night standards (`G93-48 … # Beginning of night standard`).

Keywords actually observed (do not invent others): **`rotdest=`** (rotator
destination angle in deg = slit/mask PA), **`rotmode=PA`** (also lowercase
`pa`), **`raoffset=` / `decoffset=`** (arcsec offsets from an offset star to
the target), **`vmag=`**, **`pmra=` / `pmdec=`**, **`lgs=`**, **`pa=`**.
Conventions: an offset/alignment star gets its own entry named
`<target>_OFF`, `<target>_o`, `<target>_S1..S3`, or `offset_S`, carrying the
*same* `rotdest` as the target plus the ra/dec offsets to slew from star to
target; slitmask entries are named by mask ID (`200906_1`,
`F190608_`) with the mask PA in `rotdest`; imaging mosaic pointings appear as
`<target>_p1..p4` (`LRIS/2023A/starlist_hhmmss.txt`). Coordinates are almost
always space-separated sexagesimal + `2000.0`, though colon-separated also
appears (KCWI master list) — presumably both accepted by Keck.

The offset-star procedure is spelled out in
`DEIMOS/2022Oct/README_observing_strategy.docx`: slew/center on the `_OFF`
star, have the telescope operator apply the starlist ra/dec offsets while
holding the PA, so the (faint, r~22) target lands in the slit with the star
also on the slit as a position reference; then expose 600–900 s with on-the-fly
reduction deciding whether to continue, abort, or coadd.

### 3. Anatomy of a Night plan document

Recurring structure across `DEIMOS_ 2022 Oct Night plan.docx`,
`LRIS_2023A/LRIS_2023_Apr.docx`, `HIRES/2026A/Keck_HIRES May 2026.docx`,
`KCWI/2018Oct/Nightly Plans.docx`:

1. **Header & links** — run title ("Keck/HIRES May 2026", "LRIS 2023 April"),
   then a "Useful links" list: instrument website/config form, **ephemeris**
   (the ucolick.org Keck calendar), weather, starlist, finder-chart docs/Drive
   folders, exposure/echelle simulators.
2. **Science priorities** — ranked list of programs/targets with the why
   ("20220717: Highest priority mask… need host redshift; up to 5 masks for
   220610, ~45 min per mask").
3. **Setup / configurations** — instrument settings per program: DEIMOS
   grating+filter+λc ("600ZD GG455-7000", "830G+OG550-8500"); LRIS
   dichroic/grism/grating/filters/binning and even focus values; KCWI a
   config table (Name | Slicer | Grating | Central Wave | Calibrated? |
   Comments); HIRES decker/ECH/XDANGLE/binning with cross-checks ("confirm
   bluest order is 108 or 109").
4. **Twilight block** — open at sunset (time given in HST), focus, standard
   star, align first mask; a *second* standard at morning twilight (KCWI:
   "Twilight (12 deg): G93-48 (standard)" … end of night "G191B2B").
5. **The timeline — the core**: a time-ordered sequence keyed to **LST** (or
   UT/HST), with the night's LST range and 18°-twilight bounds stated up
   front — e.g. "Night 1 (Oct 26: LST = 21:06-7:09 [18deg]): 21:06-22:06:
   2207_1 (600ZD GG455-7000); … 23:45-00:00: MIRA; 00:00-02:30:
   Tier2022-Mask1 …". Each block: target/mask ID, setup, exposure×repeats,
   inline contingency notes ("This is close to vignetting", "may need to
   start ~10 min earlier", "Remaining?"). HIRES 2026 formats this as a table
   (UTStart-End | Target | RA | Dec | Setup | Exp | # | z | r_mag | Comments)
   and marks the 12°/18° twilight times as rows.
6. **Calibrations** — afternoon checklist: biases, arcs (ThAr with specified
   lamps/filters/exptimes), dome/trace flats, counts (11 exposures), MIRA
   (telescope focus) scheduled mid-night for DEIMOS.
7. **Backup plans** — explicit "Backup Plans" section (LRIS 2023A) plus
   backup-target docs in the run folder; also alternate-half-night plans
   ("2nd Half Night… Revised Plan").
8. **Questions for / answers from the Support Astronomer** — "SA questions
   (Percy: +1 808 …)", handover time, shutter vignetting; KCWI plans contain
   an inline Q&A dialogue between the two astronomers (X and collaborators)
   resolving strategy (offsets between exposures, sky-PA tricks, binning).
9. **Troubleshooting/lessons appended in place** — DEIMOS FCS-failure
   procedure and the "Jul 25: Ran into FCS issues again…" diary; HIRES plan
   ends with a frame-by-frame log of calibration attempts. Plans are living
   documents that accrete the night's reality.
10. **To-do list pre-run** — "Things TODO: offset finder charts, submit night
    2 configuration…, generate a starlist in WMKO format" (LRIS 2023A).

Per-target detail level (LRIS 2023A example): time window in LST, target +
coords, mode (mask/longslit/imaging), full setup incl. focus values, exposure
sequence per camera ("4x1100s blue, 8x500s red"), dithers/PAs for imaging
mosaics, and decision rules ("Do 10 min exposures. Check for emission
features… If you got them, move to the next mask.").

### 4. Supporting artifacts

- **`inst_config.txt`** (read for DEIMOS/2023Dec, LRIS/2023A,
  LRIS/2024A-B/LRIS_June): the Keck SIAS instrument-configuration submission —
  `pi_name`/`pi_email` (Prochaska, xavier@ucolick.org), `run_date`,
  `n_nights`, mode checkboxes (`cb_Longslit`, `cb_Multislit`, `cb_Imaging`),
  then numbered hardware slots: DEIMOS SLITMASK1..11 (mask names like
  `2211_1`, `Long1.0B`, `GOH_X`) + GRATING (600ZD, 830G, Mirror) + FILTER
  (OG550, GG455, R); LRIS additionally GRISM/DICHROIC/RED_FILT/BLUEFILT per
  night; plus `slitmask_deadline`. I.e. the whole instrument state is locked
  in weeks ahead — the plan must work within these declared slots.
- **Mask-design files**: `.lst` = mask center line (`8:32:28.81 -40:25:18.0
  2000.0 PA=-31.00`), guider center, then selected objects; `.obj` = full
  object list (name RA Dec equinox mag band priority); `.reg` = DS9 slit
  boxes generated "from frb230718.fits by dsim2regions.py".
- **Target spreadsheets**: `DEIMOS/2023Dec/target_info.xlsx` columns —
  Target | mag | Filter | Survey Image | Exp time (s) per mask | Gratting
  combo | Redshift | mask status ("Submitted for milling"/"Milled") | obs
  time (tentative) HST | Comments — i.e. a pre-run tracking table from which
  the night plan is assembled.
- **MOSFIRE offset files**: `20190520B_target_offset_+1.5.txt` /
  `_-1.5.txt` (nod positions).
- **Observing tips** (KCWI, `Observing_Tips.docx`): 4×15 min exposures with
  interleaved pairs of objects at offset redshifts (each serves as the
  other's sky), dither but don't rotate, check targets for bright stars/
  Galactic extinction, bias between slews.

### 5. ToO runs

`ToO/2020/2020-12-07 MOSFIRE (FRB 190614D).docx` is the only ToO file — a
single compact doc, not a run folder. Structure: title (date, instrument,
trigger source), reference paper, ephemeris link, **Goals** ("Redshifts
baby"), Setup (longslit tailored to seeing, grating, dither pattern),
Targets (2 host candidates + offset star with coords and mags), and
**Acquisition guidelines** — offset star J_AB 16–18.5 within 1′ (relaxable to
2′ / J=19.5), avoid bright stars (detector persistence), rotate to catch both
candidates in one slit, finding charts optional. A ToO plan is thus a
stripped-down single-target(+offset-star) recipe: trigger → goal → setup →
acquisition, with no LST timeline.

### 6. Observations/ — facilities breadth

`Observations/` (results, skimmed only) is organized by facility: **AAO,
ALMA, Gemini-N, Gemini-S, HST, JWST, Keck (DEIMOS/KCWI/LRIS/MOSFIRE/…),
Lick_Kast, Magellan, MeerTRAP_HighDM, MMT, NOT, Pepsi, SOAR, VLT**, plus
cross-facility planning spreadsheets at top level (`Observing.xlsx`,
`2021_observing.xlsx`, `FRB_Field_observations.xlsx`, `GMOS-MOS programs
summary.xlsx`, `MUSE programs summary.xlsx`) and PypeIt workflow docs. The
astronomers observe on essentially every major O/IR facility plus ALMA, but
the *night-planning* archive is Keck-centric.

### 7. What night-planner should reproduce

1. **The deliverable set, not just a plan**: per-run folder = night-plan doc +
   WMKO-format starlist + instrument config + target table + finders + (MOS)
   mask files + an observing-log skeleton + backup targets.
2. **A starlist writer** emitting the exact Keck format above, including
   `_OFF`/`_S1` offset-star companion entries with `raoffset/decoffset` and
   shared `rotdest`, section comment headers, and standards.
3. **An LST-keyed timeline** bounded by the 18°-twilight LST range, with
   per-block target/setup/exposures, a twilight standard at each end,
   mid-night MIRA/focus where relevant, and inline contingencies.
4. **Setup tables per program** (grating/filter/λc/dichroic/slicer/decker…)
   constrained to what the submitted `inst_config` declares.
5. **Priorities + backups + SA-questions sections** — the human scaffolding
   the astronomers demonstrably rely on.
6. **ToO mode**: the compact trigger→goal→setup→acquisition single-target
   recipe with offset-star selection rules (J 16–18.5 within 1′).
