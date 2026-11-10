# Priority: night-planner vs. UCSC AstroScheduler

Created by JXP and Claude

> Companion to [`priority_system.md`](priority_system.md), which documents
> night-planner's own behaviour. This file reads a local checkout of
> UCSC-Transients/AstroScheduler as of 2026-10-16 and compares the two.
> AstroScheduler is a separate repository and was read only.

---

## Why the comparison is fair

AstroScheduler targets **the same telescope** — Lick Shane 3 m — from the same
site, and adopts the **same hour-angle limits** we do:

```python
self.ha_limit_east = -5.6667   # -05:40
self.ha_limit_west = 3.75      # +03:45
```
(`scheduler.py:503-505`; ours: `HA_MIN = -(5 + 40/60)`, `HA_MAX = 3 + 45/60`)

So the physics layer is shared and the difference really is the priority
model, not the observatory.

**One discrepancy worth resolving with the author:** AstroScheduler's
`ShaneTelescope` declares `dec_min=-35.0, dec_max=72.0` (`scheduler.py:502`),
while night-planner uses `DEC_LIMIT = 82.0` and imposes **no southern limit at
all**. Both cannot be right. Also, their slew is a flat 7 min against our
`SLEW_MINUTES = 5`.

---

## AstroScheduler's priority model

### 1. Priority is a real, first-class field

```python
self.priority = float(priority)  # 1 (highest), 2, 3... supports float
```
(`scheduler.py:604`)

- **Float, ascending = worse.** 1.2 beats 1.8; the test
  `test_float_priority_scheduling` asserts exactly that, with two targets at
  the same position competing for one transit window.
- **`priority == 0.0` is reserved for standard stars** — a sentinel, not a
  rank. It is checked by identity throughout (`is_standard = (target.priority
  == 0.0)`, `scheduler.py:936`) and grants a different twilight rule: standards
  may run from 30 min after sunset, while non-standard twilight targets are
  capped at 12-degree twilight.
- **Authored by the observer, by hand.** Ingested from the target file as a
  `priority = X` keyword or as a positional field (`static/app.js:2255-2329`,
  default 3.0), or typed in the UI; the API defaults to 1.0 (`app.py:159`).
  Priority also drives sky-map colour and the default list sort.

### 2. The scheduler consumes it as strict tiers

`_solve_internal()` (`scheduler.py:1743`) is a **priority-sequential Branch and
Bound**:

```python
obs_targets_by_prio.setdefault(t.priority, []).append(t)
sorted_priorities = sorted(obs_targets_by_prio.keys())
...
for prio in sorted_priorities:
    S_active   = [previously scheduled, non-manual]   # MANDATORY
    new_active = [this tier's targets]                # OPTIONAL
    targets_to_schedule = S_active + new_active
```

This is the key design move and it is worth stating precisely:

- Tiers are solved in order, best first.
- Everything already placed re-enters the next tier's search as **mandatory**
  (`S_active`), while the new tier's targets are **optional**. If the solver
  cannot place a mandatory target, the whole tier attempt is abandoned
  (`mandatory_has_no_slots`) rather than sacrificing it.
- **Therefore a lower-priority target can never displace a higher-priority
  one — but it can cause a higher one to be *moved* to a different slot**, as
  long as it stays scheduled. That is a genuinely better guarantee than
  "schedule the good ones first and hope," because the re-optimisation lets a
  P1 target shift 20 minutes to let a P2 target exist, which a one-pass greedy
  cannot do.

### 3. Within a tier: a cost function, not a sort key

Each candidate start slot is priced:

```python
costs[s_idx] = median_airmass + 1000.0 * twilight_dist
```
(`scheduler.py:1900`)

and the search minimises the **sum** of those costs. Two details carry most of
the behaviour:

- **The drop penalty.** An unplaced optional target adds `100000.0`
  (`scheduler.py:2003`, and in the greedy warm start at `:2022`). Against
  airmass values of order 1-2, that makes the objective **lexicographic in
  practice**: maximise the number of targets scheduled first, then minimise
  airmass. Priority is not in the cost at all — it is in the tier loop.
- **`1000.0 * twilight_dist`** is a soft constraint implemented as cost:
  observing outside 18-degree twilight is permitted but priced so high it only
  happens when nothing else fits.

### 4. Mechanics that make the search tractable

- **Greedy warm start** gives an upper bound before the B&B runs
  (`scheduler.py:1974-2027`), accepted only if it placed every mandatory
  target.
- **Suffix-minimum pruning**: `if cost + suffix_min_costs[idx] >= best_cost:
  return`.
- **Hard cap `max_search_iterations = 20000`** — so the result is
  *good*, not provably optimal. Worth knowing before anyone calls it exact.
- **1-minute chunk granularity** (`num_chunks = total_seconds // 60`), with
  visibility precomputed per target per chunk into `visibility_cache`.

### 5. Three override channels above priority

- **`manual_start_time`** — pre-scheduled and its chunks reserved *before* tier
  1 runs (`scheduler.py:1824-1838`). Effectively infinite priority.
- **`schedule_before`** — precedence constraints, resolved by topological sort
  and enforced inside the search; cycles degrade gracefully (unranked nodes get
  rank 999999) rather than raising.
- **Previous solution stability** — `previous_start_chunks`/`s_prev` is tried
  *first* among slots, so re-solving mid-night ("start from now") does not
  churn the rest of the night. This matters for their real-time observing mode
  and we have no equivalent.

### 6. What priority does *not* do there

Exposure time comes from magnitude, S/N mode (`classification` 0.5 / `normal`
1.0 / `high_sn` 2.0), moon brightness and extinction — **not** from priority
(`Target.calculate_exposure_time`). Same as ours. Standard-star selection uses
its own score (100 for a `good`-quality standard, +20 airmass bonuses,
`scheduler.py:1522-1618`), unrelated to science priority.

The client-side JS fallback solver (`static/app.js:5362-5668`) reimplements the
identical algorithm — same tiers, same `1000.0` twilight weight, same
`100000.0` drop penalty — so the dashboard still works with the server down.

---

## Side by side

| | night-planner | AstroScheduler |
|---|---|---|
| **Priority field** | None. `priority` is not in `targets_io.ALIASES`; a `priority` column is silently dropped | `Target.priority`, float, 1 = highest, 0.0 = standard-star sentinel |
| **Who sets it** | FFFF-PZ server (tag-weighted stochastic draw over `NeedSpectrum` hosts) + author statements in prose | The observer, by hand, in the target file or UI |
| **Granularity of value** | Binary at best: in the pool or not; primary pool vs. `Extras (Gap-Fill)` | Continuous float, arbitrarily many tiers |
| **Scheduler input** | Window-close time only | Priority tiers (outer loop) + airmass/twilight cost (inner objective) |
| **Algorithm** | One-pass greedy, earliest-window-close-first | Priority-sequential Branch and Bound, greedy warm start, suffix pruning, 20 000-iteration cap |
| **Can a low-value target bump a high-value one?** | **Yes** — documented: TGT0456 bumped in both Keck plans | **No** — scheduled targets become mandatory in later tiers |
| **Can a high-value target be re-positioned to fit others?** | No — placement is final | Yes — that is the point of `S_active` re-entering the search |
| **Objective** | None (sort key) | Σ (median airmass + 1000 × twilight distance), with 100 000 per dropped target |
| **Time granularity** | Minutes, continuous datetimes | 1-minute chunks, precomputed visibility |
| **Overrides** | `--force TNS:minutes` (`reserve_forced`), `FORCED_FIRST_TNS`, `--block` | `manual_start_time` (pre-reserved), `schedule_before` precedence |
| **Re-solve stability** | Not addressed | Previous start chunk tried first |
| **Why a target was rejected** | Staged + reasoned: `1. Keck selection` → `2. Sky` → `2b. Mask` → `3. Scheduling` → `4. Forced`, each with a `limit_reason` | Flat `conflicts` / `unobservable` name lists, no reason |
| **Catalog / science provenance** | FFFF-PZ statuses, P(O\|x), DM, tags, host-vs-burst position safety | None — no catalog concept |
| **Multi-facility** | Yes: Keck mag-19/Dec-82 handoff back to Lick, MOS vs. longslit | Shane and a `Keck1Telescope` class, but no handoff rule |
| **Slew model** | `SLEW_MINUTES = 5` (Lick), 10/20 min Keck with Dec-crossing rule | Flat 7 min |
| **Shane Dec limits** | `DEC_LIMIT = 82.0`, no southern limit | `dec_min=-35.0, dec_max=72.0` |

---

## What night-planner should take from it

In increasing order of effort:

1. **The field, with the sentinel convention.** Add `priority` to
   `targets_io.ALIASES` (the test tables already emit the column) and keep
   their reading: lower = better, float, with a reserved value for
   calibrators. Costs nothing and makes the data expressible.
2. **The tier loop.** This is the cheapest *real* upgrade and it wraps
   `schedule_greedy` rather than replacing it: partition by priority, schedule
   tier 1, then re-run with tier-1 placements held as mandatory while tier 2
   competes for what is left. It fixes the TGT0456 failure directly,
   without writing a solver.
3. **The drop penalty idiom.** When we do get an objective, make "number of
   targets observed" dominate "airmass quality" by scale rather than by a
   second sort pass. It is one constant and it is easy to reason about.
4. **Re-solve stability.** We re-run plans constantly (forced targets, revised
   starts, night 2 repeats). Trying each target's previous slot first would
   stop our outputs churning between runs — a property the author will notice
   immediately.
5. **The cost function itself.** Ours would differ: median airmass plus a
   twilight penalty is right for them, but we would want window-close urgency
   in there too, since our targets are often placed in a sliver.

## What night-planner has that AstroScheduler does not

Worth saying plainly, because the comparison is not one-directional:

- **Provenance.** Every rejection carries a stage and a human-readable reason;
  AstroScheduler returns a bare list of names. For a pipeline whose output a
  PI has to defend, that is the more valuable property.
- **An actual catalog.** Priority in AstroScheduler is whatever the observer
  typed. Ours is derived from FFFF-PZ status and tag weights, i.e. from a
  shared, versioned record of which hosts still need spectra. Their model has
  no answer to "who decides"; ours has no answer to "how is it consumed".
  **The two repos are missing opposite halves of the same system.**
- **Correctness guards on the input** — `load_targets()` refuses a burst
  position standing in for a host, the one mistake that silently observes the
  wrong sky.
- **Multi-facility reasoning** and MOS/longslit mode selection.
- **Reproducible per-run scripts and logs.**

---

## Bottom line

AstroScheduler answers the question night-planner cannot: *given a priority,
how does the schedule respect it?* Its answer — strict tiers with mandatory
carry-over, and a cost function inside each tier — is sound and is the design
we should copy, in roughly that order. night-planner answers the question
AstroScheduler never asks: *where does a priority legitimately come from, and
how do you explain what the schedule did?*

The merge, if we build one: keep our FFFF-PZ-derived value and our rejection
staging, adopt their tier loop as the consumer, and record the priority in the
`TargetDecision` reason so the judgement is auditable alongside the physics.
