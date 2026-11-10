# How to Make a Good Target CSV

Created by JXP and Claude

> **Who this is for:** anyone preparing a target list for a night-planner run —
> collaborators, students, or the observer themselves — whether the list comes
> out of FFFF-PZ or out of a spreadsheet.
>
> **See also:** [`priority_system.md`](priority_system.md) for what the planner
> does with priority once it has it, and
> [`Shane_telescope_constraints.md`](Shane_telescope_constraints.md) for the
> pointing limits quoted here.

---

## The short version

A target table needs four things: **a name, a position, and a magnitude.**
This is a complete, valid file:

```csv
name,ra_deg,dec_deg,mag
TGT0534,145.2341,37.8812,19.4
FRB20260104C,201.9983,12.0417,17.2
FRB20260118B,312.4408,55.6130,21.8
```

Check it before you plan with it:

```bash
python scripts/check_target_csv.py my_targets.csv
```

That prints which column it read for each field, what units it inferred, the
best airmass each target can reach, the exposure each magnitude implies, and
the total hours of science the list represents. It exits non-zero if the table
cannot be read at all. The viewer's **"Read targets & set priorities"** button
does the same checks in the browser.

The rest of this document is about the difference between a file that *loads*
and a file that makes a *good night*.

---

## 1. The columns

Column names are matched case-insensitively, ignoring punctuation and spaces,
so `Dec_deg`, `DEC DEG` and `decdeg` are all the same column. For each field
the planner takes the **first** spelling it finds, in the order listed:

| Field | Required | Accepted spellings (in priority order) | Units |
|-------|----------|----------------------------------------|-------|
| name | **yes** | `TNS`, `name`, `target`, `target_name`, `objname`, `object`, `id` | text |
| RA | **yes** | `Pri_RA`, `ra_deg`, `radeg`, `ra_hours`, `ra`, `rightascension`, `right_ascension`, `ra_j2000` | see §2 |
| Dec | **yes** | `Pri_Dec`, `dec_deg`, `decdeg`, `dec`, `de`, `declination`, `dec_j2000` | always degrees |
| mag | **yes** | `Pri_mag`, `mag_r`, `rmag`, `r_mag`, `mag`, `magnitude` | r-band, AB |
| P(O\|x) | no | `Pri_POx`, `pox`, `p_ox` | 0–1 |
| tags | no | `FRB_tags`, `tags`, `tag` | text |
| DM | no | `FRB_DM`, `dm` | pc cm⁻³ |
| priority | no | `priority`, `prio`, `rank` | float, **lower = more important** |
| mag_band | no | `mag_band`, `band`, `mag_filter`, `Pri_filter` | band of `mag`: `u g r i z` (SDSS), `B V` (Buser), `R I` (Cousins). FFFF-PZ's `Blanco:DECam-r` reads as `r` |
| t_target | no | `t_target`, `t_obs`, `exptime_min` | minutes on target; **sets the time for that row** |
| required | no | `required` | true/false (also yes/no, 1/0); default false |

**Every other column is carried through untouched.** Add `Notes`, `programme`,
`z_phot`, whatever you like — nothing is lost, and the extra columns appear in
the output CSVs beside the schedule. Use that freely rather than cramming
information into the target name.

Ordering of columns does not matter. Ordering of *rows* does not matter either —
the scheduler sorts by its own criteria.

---

## 2. Units: the one thing the planner refuses to guess

Getting RA units wrong moves the telescope by a factor of 15 and produces an
output that looks completely normal. So the planner will not guess. It decides
like this:

1. **The column name settles it.** `ra_hours` → hours. `ra_deg`, `radeg`,
   `Pri_RA` → degrees.
2. **Sexagesimal settles it.** If the values contain `:` or spaces
   (`RA_REDACTED`, `DEC_REDACTED`), RA is read as **hours** and Dec as
   **degrees** — the usual convention.
3. **Otherwise, if every value is ≤ 24, the table is refused.** A bare column
   called `ra` holding `18.57` is genuinely ambiguous.

```
'ra' is numeric and every value is <= 24, so it could be hours or degrees
```

**The fix is to rename the column** to `ra_deg` or `ra_hours`. That is better
than answering the question in the GUI each time, because the file then says
what it means and the next person to open it does not have to ask.

Dec is always degrees. There is no ambiguity to resolve and no `dec_hours`.

---

## 3. The four ways a table gets refused

The planner refuses rather than guesses in exactly these cases. Each refusal
names the problem; here is what to do about it.

### "no column found for 'ra'" on an FFFF-PZ-looking table

You have `FRB_RA` / `FRB_Dec` but no `Pri_RA` / `Pri_Dec`. Those are **not
interchangeable**. `FRB_RA` is the *burst* position — where the radio emission
came from, with its localisation uncertainty. `Pri_RA` is the **host galaxy**
PATH associated with it, and that is what the telescope points at and what the
slit goes on.

They are deliberately not aliased to each other, because silently observing an
arcsecond-scale offset from the actual host is a failure that produces a
perfectly ordinary-looking spectrum of nothing.

**Fix:** get the host position. If you genuinely mean to point at the burst
position — a blind search, say — rename the column to `ra_deg` yourself, so the
decision is recorded in the file.

### "N row(s) have unreadable coordinates: ..."

A blank cell, a stray `--`, a `nan`, or a sexagesimal string the parser could
not take. The message names up to five offenders. Fix or delete those rows.

### "N target name(s) appear more than once"

Almost always a merge gone wrong. The scheduler has no way to notice, so it
books the same object twice and spends part of the night re-observing it. Each
target gets exactly one row.

If you really want two different observations of one object (two
configurations, two epochs), give them distinct names: `TGT0534_blue`
and `TGT0534_red`.

### "no column found for 'name'" and friends

The header is spelled something not in the table above. Rename it, or add an
alias to `ALIASES` in [`night_planner/targets_io.py`](../night_planner/targets_io.py)
if it is a spelling you will keep using.

---

## 4. Magnitude is not optional, and it is not decoration

**The magnitude sets the exposure time**, which sets how many targets fit in
the night. It is the single most consequential number in the file after the
position. For Lick/Kast the mapping is a deterministic heuristic calibrated
against nine previous night plans:

| r-band magnitude | Total integration per arm | Wall clock |
|------------------|---------------------------|------------|
| < 15.5 | 1800 s | 30 min |
| 15.5 – 17.5 | 2400 s | 40 min |
| 17.5 – 19.3 | 3600 s | 60 min |
| ≥ 19.3 | 5400 s | 90 min |

Consequences worth knowing before you build the list:

- **A guessed magnitude is a guessed night.** Putting `20` in because you do not
  know is not neutral — it books 90 minutes. If a target's magnitude is
  genuinely unknown, say so in a `Notes` column and expect to revisit it.
- **It should be the *host* r-band magnitude**, not the FRB, not a different
  filter. `Pri_mag` from FFFF-PZ is already this.
- **The boundaries bite.** 19.2 and 19.4 differ by 30 minutes of telescope time.
  If a magnitude is near a boundary and uncertain, that uncertainty is worth
  half an hour of your night.
- Kast is dual-beam: red and blue expose *simultaneously*, so the wall-clock
  cost is one arm's total, not the sum.

---

## 5. Priority

Add a `priority` column when some targets matter more than others:

```csv
name,ra_deg,dec_deg,mag,priority
TGT0534,145.2341,37.8812,19.4,1
FRB20260104C,201.9983,12.0417,17.2,1
FRB20260118B,312.4408,55.6130,21.8,2
FRB20260122D,45.1100,8.2210,18.0,3
```

The convention, shared with the UCSC AstroScheduler so the two stay comparable:

- **A number. Lower is more important.** 1 beats 2 beats 3.
- **Default is 1.** A table with no priority column puts every target in one
  tier, which schedules exactly as it did before priorities existed.
- **Fractions are fine** (`1.5`) when you want to slot something between tiers
  without renumbering everything.
- **Letters are not.** `A`/`B`/`high`/`low` are not numbers; they silently fall
  back to 1. The checker and the GUI both report this as a count of coerced
  values — do not ignore that line, because it means your ranking was thrown
  away.

### What the tiers actually do

Tier 1 is scheduled first across the whole night. Tier 2 is then fitted into
whatever gaps tier 1 left, tier 3 into what remains, and so on. **A lower-priority
target can never displace a higher-priority one.**

Two practical consequences:

- **Few tiers beat many.** Three tiers of 10 targets gives the scheduler room to
  work. Thirty tiers of one target each is just a hand-written running order,
  and it will leave the night full of holes, because each tier can only use the
  gaps the one before it left.
- **Tier 1 should not be the whole list.** If everything is priority 1, you have
  told the scheduler nothing. A useful split is roughly: *must observe* / *would
  like* / *filler if there is room*.

Priorities can also be set in the viewer, per target, on the priorities page.
Those are written to `targets_with_priority.csv` in the plan's output directory —
so a GUI plan can always be reproduced from the command line with that file.

---

## 5b. Setting a target's time yourself: `t_target` and `required`

Two optional columns let you overrule the planner for individual targets
(added 2026-11-07, goal T3.3):

```
name,ra_deg,dec_deg,mag,t_target,required
TGT0590,123.4,+45.6,20.1,45,yes
TGT0595,210.0,+12.3,19.4,,
```

- **`t_target`** is the time on target in **minutes**, and it is used as given:
  the ETC does not resize it. The ETC estimate is still worked out and shown
  beside it in the plan table ("user (ETC 31)"), so you can see how far apart
  they are. Treat it as the whole on-target block: no readout is added on top.
  On LRIS, `--no-etc-for-user-times` skips the ETC call for these rows.
- **`required`** means "the full time or nothing". A target that is not
  required and runs out of room can be squeezed into idle time as a shortened
  *partial* exposure (Kast does this by default). A required target never is:
  if its full time does not fit, it is rejected with
  `required: needs N min, no gap that long`.
  - LRIS has no partial backfill, so `required` changes nothing there yet.
- Values that can't be read (`t_target = soon`, `required = maybe`) don't
  stop the table from loading. The row is treated as having no user time /
  as not required, and the target-table page lists the offending values.

## 6. What makes a list *good*, not just valid

A file that loads cleanly can still be a bad night. The checker reports each of
these.

### Declination

The Shane 3m cannot point above **Dec +82°**. Targets above it are kept in the
output and reported as rejected with a reason, not silently dropped — but they
are not observed. Including them is harmless; counting on them is not.

At the southern end there is no mechanical limit, but there is physics: from
Lick (latitude +37.3°), a target at Dec −30° transits at airmass 2.6 and never
does better. The checker flags anything that cannot beat airmass 2.0 as *poor
airmass*. A few of those are fine as filler; a list made of them is a wasted
night.

### Right ascension and the season

There are **no RA limits** — but the hour-angle limits (−5h40m to +3h45m) plus
the length of the night mean only a band of RA is reachable on any given date,
and it moves about 2 hours per month.

| Month | Roughly observable RA |
|-------|-----------------------|
| Feb | 0h – 10h |
| May | 8.5h – 18.5h |
| Aug | 14h – 8h (through 0h) |
| Nov | 19.5h – 5.5h |

Use [`scripts/observable_ra_calculator.py`](../scripts/observable_ra_calculator.py)
for a specific date. A list drawn entirely from the wrong side of the sky will
produce a plan with almost nothing in it, and the rejection reasons will all
read *"never inside the Shane HA window"*.

### How many targets

Aim to **oversubscribe by roughly 1.5 to 2×**. The checker prints the total
on-source hours; compare that with the length of the night.

- **Too few** and the scheduler leaves idle time it has nothing to fill with.
  This is the common failure, and no amount of clever scheduling fixes it —
  partial-exposure backfill can only truncate targets that exist.
- **Too many** is nearly free. Unscheduled targets cost nothing but a row in
  the rejection table, and a deep pool is what lets the scheduler fill the
  awkward 25-minute gaps.

Remember the overheads the list does not show: 5 min slew between targets,
10 min focus at the start, 10 min per flux standard.

### RA spread

Targets clustered in a narrow RA band all peak at once and all set at once. A
list spread across the reachable RA range gives the scheduler something to do
early and something to do late. The checker's output is sorted by RA, which
makes a cluster obvious at a glance.

---

## 7. FFFF-PZ tables

A table pulled with `chime_ffff_pz_targets` works as-is — do not reshape it.
It is recognised automatically by carrying the burst position, the DM, and
PATH's ranked host candidates, and the planner maps `Pri_RA`/`Pri_Dec`/`Pri_mag`
to the host without being told.

If it also carries `Sec_RA`/`Sec_Dec`/`Sec_POx` (a second host candidate), the
planner can offer **slit-angle mode** — orienting the slit to catch both
candidates in one exposure. The checker says so when it is available.

The one thing worth adding by hand is a `priority` column. Everything else
should come from the Resource definition upstream.

---

## 8. Checklist

Before handing a file to the planner:

- [ ] `python scripts/check_target_csv.py my_targets.csv` exits 0
- [ ] RA column is named `ra_deg` or `ra_hours` — not bare `ra`
- [ ] Positions are the **host**, not the burst
- [ ] No duplicate names
- [ ] Magnitudes are real r-band values, not placeholders
- [ ] Priorities are numbers, and there are a handful of tiers, not thirty
- [ ] Total exposure is 1.5–2× the length of the night
- [ ] Nothing critical sits above Dec +82° or below airmass 2
- [ ] RA range matches the season of the observing date

---

## Worked example

Start with what came out of a spreadsheet:

```csv
Object,RA,DEC,Rmag,Rank,Comments
TGT0534,09:40:56.2,+37:52:52,19.4,high,repeater - must get
FRB20260104C,13:27:59.6,+12:02:30,17.2,high,bright host
FRB20260118B,20:49:45.8,+55:36:47,21.8,low,faint - filler
TGT0534,09:40:56.2,+37:52:52,19.4,high,duplicate from merge
```

The checker refuses it outright: `TGT0534` appears twice. The mapping it
prints before refusing also shows `priority <- Rank` — so once the duplicate is
removed, the next run warns that `high`/`low` are not numbers and the ranking
was thrown away.

Fixed:

```csv
Object,RA,DEC,Rmag,priority,Comments
TGT0534,09:40:56.2,+37:52:52,19.4,1,repeater - must get
FRB20260104C,13:27:59.6,+12:02:30,17.2,1,bright host
FRB20260118B,20:49:45.8,+55:36:47,21.8,3,faint - filler
```

`Object`, `RA`, `DEC` and `Rmag` are all recognised spellings; the sexagesimal
coordinates settle the unit question on their own; `Comments` rides along into
the output. Three targets is far too few for a real night — but as a file, this
one is correct.
