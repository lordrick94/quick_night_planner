# How Priority Assigns Targets to the Night

Created by JXP and Claude

> **Scope:** you have a target table — any table, from FFFF-PZ, a collaborator,
> a catalogue query, or typed by hand — and some rows matter more than others.
> This document describes what the planner *does* with those numbers: where
> priority is read, what it changes, what outranks it, and what it provably
> does not touch. Current as of 2026-10-21.
>
> **See also:** [`target_csv_guide.md`](target_csv_guide.md) — how to *write*
> the column.

---

## The contract

| Property | Value |
|----------|-------|
| Type | float |
| Direction | **lower = more important** (1 beats 2 beats 3) |
| Default | `DEFAULT_PRIORITY = 1.0` ([`night_planner/targets_io.py:40`](../night_planner/targets_io.py#L40)) |
| Accepted column names | `priority`, `prio`, `rank` (`ALIASES`, case/punctuation insensitive) |
| Non-numeric values | coerced to the default, **never** an error |
| Blank cells | the default, on purpose |

Three consequences fall straight out of the contract:

1. **A table with no priority column is still a valid table.** Every row gets
   1.0, which is one tier, which schedules exactly as the pipeline did before
   priority existed. This is asserted, not assumed —
   `test_one_tier_is_identical_to_the_plain_greedy_pass`.
2. **A ranking the loader could not read is silently lost.** `'A'`/`'B'`,
   `'high'`, `'must'` all coerce to 1.0 and collapse your tiers into one.
   Silent in the loader, *not* silent overall: `priority_coercions()`
   ([`targets_io.py:305`](../night_planner/targets_io.py#L305)) counts the
   offending rows and both the checker
   ([`scripts/check_target_csv.py`](../scripts/check_target_csv.py)) and the
   GUI's inspect step print that count. Read it.
3. **The values are tier labels, not weights.** `1, 2, 3` and `1, 10, 100`
   produce identical schedules — only the sort order of the distinct values is
   used. Fractions (`1.5`) exist to insert a tier without renumbering.

---

## Where priority enters and what it reaches

```
target table (any source)
  └─ load_targets()            priority read / defaulted / coerced to float
      └─ analyze_targets()     carried onto every row, untouched by the gates
          └─ reserve_forced()  IGNORES priority — the observer already ranked these
              └─ schedule_by_priority()   <-- the one place priority decides anything
                  └─ backfill_partials()  tie-break for leftover idle time
                      └─ --max-targets    trim keeps the best tiers
                          └─ PlanResult   priority stored + stamped on reasons
```

Only the three boxes after `reserve_forced` behave differently because of a
priority value. Everything above them carries the number along unchanged.

---

## The tier loop — `schedule_by_priority()`

[`scripts/kast_calculations.py:396`](../scripts/kast_calculations.py#L396).

```
tiers = sorted(unique priority values)        # 1.0, 2.0, 3.0 ...
```

**Tier 1 (best):** one `schedule_greedy()` pass over the *whole* night.
Inside a tier, order is earliest-window-close-first — the target you lose if
you wait goes first — and each is placed as late inside its own HA window as it
will fit.

**Every lower tier:** the idle intervals left by the tiers above are computed
with `free_gaps()`, and `schedule_greedy()` is run **once inside each gap**,
with the targets still unplaced. A target placed by a higher tier is immovable.

**Hence the guarantee:** *a lower-priority target can never displace a
higher-priority one* (`test_a_lower_tier_never_displaces_a_higher_one`). The
converse is also true and is the point of the whole mechanism: promote a target
and it stops being bumped by a cheaper neighbour whose window happened to close
first (`test_a_promoted_target_is_no_longer_bumped`).

**One tier short-circuits** to a single `schedule_greedy` call — not a loop of
one — so an un-prioritised table takes the exact code path it always did.

### Why per-gap, and not "pass the placed slots as blocks"

Because `fit_around_blocks()` can only ever push a candidate *later*, and
`schedule_greedy`'s cursor never rewinds. A second full-night pass with tier 1
handed over as blocked time would sail straight past every gap it had already
crossed and place almost nothing. Restarting the cursor inside each gap is the
only form that works here.

### What a target rejected by the loop is told

One row per target, not one per gap it failed in:

```
priority P2: needs 45 min, and no idle interval left by the 1 higher-priority
tier(s) was long enough inside its HA window
```

### Worked shape

```
night           |=========================================|
P1 (whole night)   [A====]   [B======]        [C=====]
free gaps       |--|      |-|         |------|       |---|
P2 (per gap)                           [D===]
P3 (per gap)    [E]
```

`D` and `E` fit the holes. Anything in P2/P3 needing more than a hole gets the
rejection above — it is *not* allowed to move `A`, `B` or `C`.

---

## What outranks priority

| Mechanism | Beats priority because |
|-----------|------------------------|
| **Feasibility** (Dec limit, HA window, twilight) | Physics. An unobservable P1 is unobservable. It is kept with a `limit_reason`, never silently dropped. |
| **`--block`** (ToO, weather, engineering) | Every tier dodges blocked windows. |
| **`--force TNS@minutes`** | `reserve_forced()` runs *before* the tier loop and hands its slot back as a blocked window. Forcing is the observer stating a priority the table does not express; a truncated exposure is accepted deliberately. |

So the real precedence is: **feasible → blocks → forced → tier → urgency within
tier → table order**.

---

## The two smaller places priority is used

- **Partial backfill.** Targets no tier could fully fit are retried into
  leftover idle time, truncated, and labelled `PARTIAL: n of m min`. Candidates
  are sorted `(priority, exit_pst)` — a partial of a P1 beats a partial of a P3
  when both want the same gap ([`kast_calculations.py:348`](../scripts/kast_calculations.py#L348)).
  Partials never displace a full exposure.
- **`--max-targets n`.** Trims the finished schedule by `(priority, start_pst)`.
  Trimming by start time alone — the old behaviour — would drop a top-priority
  late target to keep a filler that happened to start early, quietly undoing
  the tier loop.

---

## What priority does *not* do

- **It does not change exposure time.** `estimate_exposure(mag_r)` reads
  magnitude and nothing else. No target gets longer integration for being
  important.
- **It does not relax a gate.** No tier is exempt from the Dec limit, the HA
  window or a block.
- **It does not reorder within a tier.** Inside a tier the sort key is window
  close; two targets at the same priority are tied and broken by table order.
- **It does not displace.** This is a priority-*sequential* scheduler, not a
  cost function. There is no "value × feasibility" trade: a P1 that cannot fit
  the night as found is simply rejected, and nothing is re-solved around it.
- **It does not touch standard stars** (ranked by airmass,
  [`night_planner/standards.py`](../night_planner/standards.py)) or **workbook
  sheet order** (RA order, for the observer's convenience, not an observing
  order).
- **The Keck/LRIS path tiers too (since 2026-11-07).**
  [`scripts/keck_2026oct06_calculations.py`](../scripts/keck_2026oct06_calculations.py)
  runs the top tier through its usual window-order greedy pass
  (`_greedy_pass`) over the whole night, then places each lower tier into
  the gaps left (`_insert_tier`), with every placed target immovable. The
  Keck-specific twist is the slew: it depends on the previous target's Dec,
  so slotting X between A and B can change B's slew (the 14 min S→N Dec +20°
  crossing). The fit test is therefore exact rather than padded: X fits when
  `A.end + slew(A→X) + acq(X) + X + slew(X→B) + acq(B) <= B.science_start`,
  and B's slew is then recomputed. Forced targets still come first
  (`reserve_forced_targets` / `append_forced_targets`), as on Kast. With one
  tier the schedule is exactly the old one
  (`tests/snapshots/lris_single_tier.json` pins it).
  - Unlike Kast, LRIS has no partial backfill, so a lower-tier target either
    fits whole in a gap or is rejected with `priority Pn: no gap ...`.

---

## How priority reaches the plan files

| Route | What it writes |
|-------|----------------|
| Hand-edited column in the source table | read directly by `load_targets` |
| Viewer's priorities page | a derived `targets_with_priority.csv` in the plan directory, which the CLI can be re-run on for an identical schedule — the GUI never passes priorities as a request field |
| Upstream catalogue | whatever that catalogue chose to emit; see below |

Downstream, every `TargetDecision` carries `priority`, and a non-default value
is stamped onto the reason string the rejection page shows
(`P2 -- needs 45 min, and no idle interval ...`,
[`adapters.py:69`](../night_planner/adapters.py#L69)). A plan where everything
sits in the default tier is left unstamped rather than reading `P1` on every
row.

### A note on catalogue-sourced tables

Some sources already encode importance *before* you get the table. FFFF-PZ is
the example in this repo: its Resource pull applies a tag-weighted stochastic
draw, so "this FRB is more interesting" changes the *probability of appearing
in the table at all*, and the rows that arrive are unranked and unrepeatable
between pulls. Such a table reaches the planner as one flat tier unless you add
a column. That is a property of the source, not of the planner — the planner's
view is only ever the column in front of it.

---

## Choosing values

- **Few tiers beat many.** Three tiers of ten targets gives the scheduler room.
  Thirty tiers of one target each is a hand-written running order, and it will
  leave holes, because each tier can only use what the one before it left.
- **Everything at P1 tells the scheduler nothing.** A useful split: *must
  observe* / *would like* / *filler if there is room*.
- **Re-derive per run.** Precedent: on a repeat night, the previous night's
  tier split is not carried over — priority is set from the current framing,
  not inherited from a stale category.

---

## File map

| Concern | File |
|---------|------|
| Column recognition, default, coercion report | [`night_planner/targets_io.py`](../night_planner/targets_io.py) |
| Carried onto analysis rows | [`scripts/kast_calculations.py`](../scripts/kast_calculations.py) (`analyze_targets`) |
| Tier loop | `kast_calculations.schedule_by_priority` |
| Gap arithmetic | `kast_calculations.free_gaps`; `fit_around_blocks` ([`scripts/schedule_overrides.py`](../scripts/schedule_overrides.py)) |
| Forced targets / blocks | `kast_calculations.reserve_forced` |
| Partial backfill tie-break | `kast_calculations.backfill_partials` |
| Priority in decisions / reasons | [`night_planner/adapters.py`](../night_planner/adapters.py), [`night_planner/plan_result.py`](../night_planner/plan_result.py) |
| GUI priorities page → derived CSV | [`backend/app.py`](../backend/app.py), [`frontend/app.js`](../frontend/app.js) |
| Pre-flight check of a table | [`scripts/check_target_csv.py`](../scripts/check_target_csv.py) |
| Guarantees | [`tests/test_priority_tiers.py`](../tests/test_priority_tiers.py) |
