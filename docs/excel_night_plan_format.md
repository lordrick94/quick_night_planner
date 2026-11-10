# Excel night-plan format

Created by JXP and Claude, 2026-11-10.

This is the format of the observers' Excel night plan, documented from a
real past plan so that a **general builder** can produce the same file for
any plan (any instrument, telescope, date or number of nights).

**Builder:** `night_planner/excel_plan.py` (2026-11-10) implements §8 and
fixes every quirk in §7. It runs automatically after each generated plan,
and the GUI's Export rebuilds the workbook if the plan is newer. By hand:

```bash
night-planner excel --plan-dir $NIGHT_PLANNER_PLANS/RUN-N1 [--plan-dir .../RUN-N2] [--out X.xlsx]
python scripts/verify_excel_plan.py PLAN_DIR WORKBOOK.xlsx   # LibreOffice recalculation check
```

- **Reference file:** `pvt_templates/Lick_2026A-4_Night_plan.xlsx`
  (Shane/Kast, three nights in May). It is **private**: `pvt_templates/` is
  git-ignored, because the sheets hold real targets. This document gives the
  layout only, with placeholders (`<TARGET>`, `<RA>`) instead of real
  values.
- **How it was read:** `python scripts/inspect_excel_template.py
  pvt_templates/Lick_2026A-4_Night_plan.xlsx` writes a full cell-by-cell
  dump (value or formula, number format, font, fill, alignment, border,
  merges, widths, validations) to `pvt_templates/_inspect/`, which is
  private. Hyperlinks were listed separately.
- The file was made in Google Sheets and exported to `.xlsx`. Several quirks
  below come from that, e.g. checkboxes exported as plain `TRUE`/`FALSE`, and
  coordinates auto-converted to times.

---

## 1. Workbook: sheets in order

| # | Sheet | Visible | What it is |
|---|---|---|---|
| 1 | `dont use` | **hidden** | An older scratch timeline (see §6). Not reproduced. |
| 2 | `Observing Checklist` | yes | Pre- and post-observing to-do list with Done boxes (§3). |
| 3–5 | `May 15th`, `May 16th`, `May 17th` | yes | **One night sheet per night** (§2), all with the same layout. |
| 6 | `FRB Observing Summary` | yes | Empty results table, filled in after the run (§4). |
| 7 | `Post Observing Tracking` | yes | Per-target reduction tracker with drop-down lists (§5). |

**Night sheet names:** month name, a space, then the day with its ordinal
suffix (`May 15th`, `Oct 2nd`, `Sep 1st`, `Aug 23rd`). The date is the
evening the night starts.

**Defined names:** none. **Conditional formatting:** none on any sheet.
**Fonts:** Arial throughout, at the default size, except one comment in
size 12.

---

## 2. Night sheet (one per night)

### 2.1 Layout at a glance

```
      A          B          C         D          E        F            G         H     I     J        K        L         M         N           O
 1  Start(LST) Start(UT)  Start(PST) Duration   End(PST) Action       target    RA    DEC   mag (r)  sec mag  red side  blue side Redshift;   Comments
 2                                   "Only edit                     Open dome
                                      this column"
 3
 4  =C4+LST    =C4+UT     <typed>    <typed>    =C4+D4   ~12 deg start time
 5  =C5+LST    =C5+UT     =E4        0:05       =C5+D5   slew to -->  <STD>
 6  ...                   =E5        0:05       ...      standard     <STD>     <RA>  <DEC>
 7                        =E6        0:05                slew to -->  <TARGET>
 8                        =E7        1:00                Science + overhead <TARGET> <RA> <DEC> <mag> <mag2> 4 x 900 2 x 1800  (blank)  <comment>
 ...  (slew/science pairs repeat; rows 4-18 in the reference)
36  18 deg dawn  <hh:mm UT>          (typed note)
46  Standard Star Options | RA | DEC | FK5 | v        (reference table, rows 47-53)
57  Lick Weather Links
58  Forecast     link  -> hyperlink
59  Clear Sky clock link -> hyperlink

Side panel (columns Q-V, rows 2-9):
      Q             R      S      T        U                         V
 2  Calibrations   Red    Blue            sidereal time calculator
 3  Focus          [x]    [x]    <note>   12 deg local time         <hh:mm>
 4  Bias           [x]    [x]             12 deg LST                <hh:mm>
 5  Flats          [x]    [x]             Difference                =V4-V3
```

### 2.2 Timeline columns (row 1 headers)

| Col | Header (exact text) | Content | Number format | Formula (row *r*) |
|---|---|---|---|---|
| A | `Start (LST)` | Local sidereal time at the row start | `h:mm` | `=C{r} + TIME(14,30,0)` |
| B | `Start (Universal Time)` | UT at the row start | `h:mm` | `=C{r}+TIME(7,0,0)` |
| C | `Start (PST)` | Local clock time at the row start | `h:mm` | First row: a typed time. Every later row: `=E{r-1}` |
| D | `Duration \n(hh:min)` (line break in the header) | How long the row lasts, as an Excel time (`1:00` = 1 hour) | `h:mm` | **Typed.** The only input column. |
| E | `End (PST)` | Row end | `h:mm` | `=C{r}+D{r}` |
| F | `Action` | Row type (§2.3) | General | — |
| G | `target` | Target or standard name | General (standards: thin border all round) | — |
| H | `RA` | Right ascension, science and standard rows only | header `@`; values `h:mm:ss` | — |
| I | `DEC` | Declination, science and standard rows only | header `#:#:#.0`; values mixed (§7) | — |
| J | `mag (r)` | Primary (host) magnitude | General | — |
| K | `sec mag` | Secondary candidate magnitude | General | — |
| L | `red side` | Red-arm exposures, text `N x SEC` (e.g. `4 x 900`) | General, centred | — |
| M | `blue side` | Blue-arm exposures, text `N x SEC` (e.g. `2 x 1800`) | General, centred | — |
| N | `Redshift;` | Left blank; filled in at or after the telescope | — | — |
| O | `Comments` | Free text: priority (e.g. `Outcat 2 High Priority`), changes made during the night | General | — |

**How the formulas work.** Each row starts when the previous one ends
(`C = E` of the row above), and `E = C + D`. **Editing a duration in column D
re-times every later row**, which is why D2 says `Only edit this column` and
the whole of column D (header and values) has a light-blue fill. A and B are
the same instant in other time systems, each as a fixed offset added to C.

**Header style:** row 1 is bold, centred and wrapped, except `O1`
(`Comments`), which is plain. Data cells in A–E are centred.

### 2.3 Row types (column F, "Action")

| F text (exact, including the trailing space on `slew to --> `) | G | H–O | D (duration) in the reference |
|---|---|---|---|
| `Open dome` (row 2, a note, not timed) | — | — | — |
| `~12 deg start time` (first timed row) | — | — | 1:00 |
| `slew to --> ` | name of the *next* target or standard | empty | 0:05 – 0:15 |
| `standard` | standard name | RA, DEC | 0:05 |
| `Science + overhead` | target name | RA, DEC, mags, red/blue exposures, comments | 0:50 – 1:30 |

Every pointing is a pair of rows: a slew row, then a science or standard
row. In the reference each night has 15 timed rows (4–18): one start row,
one standard pair, and six target pairs.

### 2.4 Below the timeline

| Rows | Content |
|---|---|
| 19–35 | Empty (styled cells only). |
| 36 | `A36` = `18 deg dawn`, `B36` = a typed UT time (bold). A hand-typed note, not a formula. |
| 46 | Header of the **Standard Star Options** table: `Standard Star Options`, `RA`, `DEC`, `FK5`, `v`. Bold, thin borders, `FK5` cell filled light blue. |
| 47–53 | Seven public spectrophotometric standards (Feige 34, Feige 110, BD+28 4211, BD+33 2642, HZ 44, G191-B2B, BD+17 4708): name, RA, Dec, `2000.0`, V mag. Thin borders. Some cells highlighted bright green (`FF00FF00`), apparently marking the chosen standard. |
| 57 | `Lick Weather Links` |
| 58 | `Forecast` and a blue `link` cell, hyperlinked to `https://forecast.weather.gov/MapClick.php?lon=-121.62&lat=37.34` |
| 59 | `Clear Sky clock` and a blue `link` cell, hyperlinked to `https://server3.cleardarksky.com/c/MtHamCAkey.html?1` |

### 2.5 Side panel (columns Q–V)

| Cells | Content |
|---|---|
| `Q2:S2` | `Calibrations` (bold), `Red` (bold red `FFFF0000`), `Blue` (bold blue `FF4A86E8`) |
| `Q3:Q5` | `Focus`, `Bias`, `Flats` |
| `R3:S5` | `TRUE`/`FALSE` per arm, in green font (Google checkboxes; the export drops the checkbox itself) |
| `T3` | A free-text focus note |
| `U2` | `sidereal time calculator` |
| `U3`/`V3` | `12 deg local time`, a typed time |
| `U4`/`V4` | `12 deg LST`, a typed time |
| `U5`/`V5` | `Difference`, `=V4-V3` |

Only the first night sheet has the sidereal-time helper filled in. Its
result is not referenced by column A, which hard-codes `TIME(14,30,0)`.

### 2.6 Sheet geometry

| Column | A | B | D | E | F | G | H | I | J | K | L | M | N | O | U |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Width | 18.63 | 9.63 | 16.5 | 7.38 | 17.13 | 16.88 | 13.25 | 11.88 | 9.63 | 8.5 | 11.0 | 12.5 | 14.0 | 44.5 | 20.25 |

Columns C and P–T are at the default width. There are no merged cells and
no frozen panes. Styled empty cells run to row ~1012 and column AD, a Google
Sheets artefact.

---

## 3. `Observing Checklist`

Three columns: `Action` (width 41.75), `Done`, `Notes` (width 89.38,
wrapped). The header row is filled `FFD9EAD3` (light green). Done cells are
`TRUE`/`FALSE`, centred, in green font (exported checkboxes).

| Row | Action | Notes (if any) |
|---|---|---|
| 2 | **Pre Obs** (section, filled `FFFCE5CD`) | |
| 3 | Make Follow-up Resource | |
| 4 | Make Obs directory on chime_ffff_pz | Please start on a clean main branch |
| 5 | Uploaded FU Resource to git | |
| 6 | Add FU Resource to FFFF-PZ | |
| 7 | Make Observing folder on google Drive | |
| 8 | Make Target List | |
| 9 | Vet Target List for non-feasible Targets | 1. Note some of these targets for future automation (E.g Telescope Pointing Limits); Also look at airmass charts |
| 10 | Make Nightplan(s) | |
| 11 | Make pending List | |
| 12 | Add pending List to repo | |
| 13 | Ingest pending List to FFFF-PZ | |
| 14 | Add in relevant info to google Drive | |
| 15 | Make Finder Charts | |
| 16 | Make Starlist | |
| 17 | Proceed with  Obs (DO NOT GO ROGUE!!) | (no Done box) |
| 21 | **Post Obs** (section, filled `FFC9DAF8`) | |
| 22 | Download RAW files from Telescope servers | |
| 23 | Add RAW files to CANFAR (use script) | |
| 24 | Reduce Files | |
| 25 | Make Redshift Table | |
| 26 | Make obs log | Refine pending list if need be |
| 27 | Ingest Obs log to FFFF-PZ | |
| 28 | Ingest Redshifts to FFFF-PZ | |
| 29 | Clean up Reductions files | |
| 30 | Add Redshift Table and obs log to REPO | |
| 31 | Add Reduction and Science files too CANFAR | |
| 32 | Upload Redshift Screenshots to REPO | |
| 33 | Send Repo PR for merging | |

A new plan starts with every Done box set to `FALSE`.

---

## 4. `FRB Observing Summary`

Header row only: `Name` (width 18.38), `Observing Report` (29.38),
`Target Info` (40.5), `z`. Filled in after the run. A builder can pre-fill
`Name` with the scheduled targets.

---

## 5. `Post Observing Tracking`

Frozen at `A2`; every row 22.5 pt high; headers left-aligned,
vertically centred and wrapped.

| Col | Header | Width | Drop-down (rows 2–995) |
|---|---|---|---|
| A | `TNS` | 18.25 | — |
| B | `Reduction Status` | 26.75 | `Not started`, `In progress`, `Fluxed`, `Marz redshifts` |
| C | `Primary` | 23.13 | `Not Checked`, `No Continuum`, `Continuum No Redshift`, `z acquired` |
| D | `Secondary` | default | `Not Checked`, `Not needed`, `No Continuum`, `Continuum No Redshift`, `z acquired` |
| E | `Uploaded To F4PZ` | 25.75 | `Not Yet`, `Done` |
| F | `Uploaded To Repo` | 24.0 | `Not Yet`, `Done` |
| G | `Notes` | 23.88 | — |

A builder can pre-fill column A with the scheduled targets.

---

## 6. Hidden `dont use` sheet

An earlier, simpler timeline: `Start (LST)`, `Duration (hh:min)`, `end`, an
unlabelled action column (`slew to --> `, `standard`, `science`),
`target`, and `comments` merged across F:I on every row. It also has a
typed twilight table (`18 deg twilight`, `18 deg dawn`, `12 deg twilight`,
`12 deg dawn`, with `LST` labels). Frozen at `A2`. It is superseded by the
night sheets, and a builder should **not** reproduce it.

---

## 7. Quirks of the reference file (all fixed by the builder)

1. **Fixed time offsets.** `A = C + 14:30` (LST) and `B = C + 7:00` (UT) are
   typed constants. The LST offset changes by about 4 min per day and with
   site; the UT offset changes with site and daylight saving. A general
   builder should compute both for each night and put them in labelled
   cells (e.g. `V3` = UT offset, `V4` = LST offset). Columns A and B then
   reference those cells (`=C{r}+$V$3`), so the sheet stays editable.
2. **"PST" headers that are not PST.** `B = C + 7 h` means column C is
   really **PDT** (UTC−7) for these May nights. The header should come from
   the plan's time zone and date (`PDT`/`PST` at Lick, `HST` at Keck).
3. **Coordinates turned into times.** Google Sheets auto-converted typed
   sexagesimal: RA is stored as a time of day, and Dec as a time or a
   multi-day duration (`[h]:mm:ss`); a few are text. Some declinations are
   corrupted this way. **Write RA and Dec as text** (`@` format), e.g.
   `12:34:56.78`, `+12:34:56.7`.
4. **Hand-typed twilight.** The dawn note (row 36) and the 12° helper are
   typed by hand. Compute them from the plan's sun events instead.
5. **Checkboxes lost.** Done and calibration cells are bare `TRUE`/`FALSE`.
   Add a `TRUE,FALSE` list validation so they stay toggleable in Excel.
   Google Sheets can turn them back into checkboxes on import.
6. **Fixed length.** The reference has room for 15 timed rows. A builder
   should write as many rows as the plan needs and place the standard-star
   table and weather links below the last row, leaving a gap.
7. **Midnight.** `h:mm` shows times modulo 24 h, so `00:30` after `23:50` is
   correct on screen. Keep the cells as times (fractions of a day). Don't
   write strings, or the formulas break.

---

## 8. Mapping a `PlanResult` to a night sheet (as built)

**What the builder adds or changes compared with the reference:**

- Header times use the plan's zone abbreviation (`Start (PDT)`,
  `Start (HST)`); the magnitude header uses the plan's band (`mag (r)`).
- `V3` = UT − local and `V4` = LST − local (to the second), both computed
  for the night; `V5` = the instant `V4` is exact at (mid-night, in column C's
  day-fraction units). Formulas:
  `B = MOD(C+$V$3,1)` and `A = MOD(C+$V$4+(C-$V$5)*0.00273791,1)`. The last
  term is the sidereal gain (LST runs 0.27% fast), so A is exact all night
  (checked to < 0.1 min against astropy).
- A computed twilight table at `U7:X14`: sunset, 12°/18° dusk, 18°/12°
  dawn and sunrise, in local time, UT and LST. It replaces the typed dawn
  note and the hand-made sidereal helper.
- Calibrations panel rows: Focus, Bias, Flats **and Arcs**, × Red/Blue,
  with TRUE/FALSE drop-downs.
- Extra row types: `idle (nothing scheduled)`, `blocked: <reason>`, and a
  closing `End of night` row with zero duration (it shows the end time).
  The first row is `Start (~12 deg twilight)`, from 12° dusk to the plan's
  start.
- Standard-star options: the plan's own standards (highlighted green)
  followed by the 3 best by airmass at the start and at the end of the
  night, from the PypeIt library (`FFFF_PZ_REPO`). Without the library,
  names only. The `v` column is left blank (the library has no magnitudes).
- Weather links: the two Lick links for Kast; the Maunakea Weather Center
  (`http://mkwc.ifa.hawaii.edu/`) for LRIS.
- No hidden `dont use` sheet; styled cells stop at the last used row.

### Original spec

One `PlanResult` (`night_planner/plan_result.py`) gives one night sheet. A
run of several nights gives one workbook with one night sheet per plan,
between `Observing Checklist` and `FRB Observing Summary`.

**Time systems:** column C = local time in `plan.timezone`; the UT and LST
offsets are computed at `plan.night_start` from the telescope's location (§7.1).

**Rows, in time order**, merged from `plan.overheads` (`(start, end,
label)`: focus, standards, slews to standards), `plan.schedule`
(`ScheduledTarget`) and `plan.blocks` (`(start, end, reason)`):

| Source | Row(s) | C (start) | D (duration) | F | G | H–O |
|---|---|---|---|---|---|---|
| night start | start row | `plan.night_start` | until the first event | `~12 deg start time` | | |
| overhead labelled as a slew | 1 row | its start | end − start | `slew to --> ` | the standard | |
| overhead: standard | 1 row | its start | end − start | `standard` | standard name | RA, DEC (text) |
| overhead: focus/other | 1 row | its start | end − start | the label | | |
| `ScheduledTarget` | slew row | `start` | `slew_min` | `slew to --> ` | `name` | |
| | science row | `start + slew_min` | `end − (start + slew_min)` (acquisition + science, i.e. "Science + overhead") | `Science + overhead` | `name` | H, I = `ra_deg`, `dec_deg` as sexagesimal text; J = `mag`; K = secondary mag from the target table if present; L = `exposure_red`; M = `exposure_blue`; N blank; O = `notes` / `tags` |
| block | 1 row | block start | block length | `blocked: <reason>` | | |
| idle gap (`plan.idle_gaps()`) | 1 row | gap start | gap length | `idle` | | |

Only the first row's C is a typed time; every later C is `=E{r-1}`. So the
typed durations must add up exactly to the plan's timeline. Gaps and blocks
get their own rows for that reason.

**Single-arm instruments:** if a mode has only one exposure string, put
it in `red side` and leave `blue side` empty (or relabel the column).

**Side panel:** calibrations Focus/Bias/Flats × arms (`FALSE`). Fill the
sidereal-time helper from computed values. Add computed twilight rows:
sunset, 12° and 18° dusk, 18° and 12° dawn, sunrise, in local, UT and LST.

**Footer:** the standard-star table lists the standards the plan used
(from `night_planner/standards.py`) with text RA/Dec. The weather links
depend on the site: the two Lick links above for Shane; Mauna Kea
equivalents for Keck, to be supplied.

**Existing builders this would replace or absorb:**
`scripts/build_keck_night_plan.py` (LRIS, still tied to 2026-10-06),
`scripts/build_night_plan.py` (Lick 2026B-01 only), and
`night_planner/make_lick_night_plan.py` (one sheet *per target*, which
copies the checklist from a template workbook). None of them takes a
`PlanResult`, and none is called by the GUI export (see the 2026-11-10 log).
