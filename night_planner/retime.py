"""
Re-time a schedule: keep its targets, move them to their lowest airmass.

Created by JXP and Claude

The Kast scheduler walks the night with a cursor and starts every target
as early as its window allows (earliest-window-close-first). That is a
good way to choose *which* targets fit, but it packs the night into its
first hours, so targets that transit late are observed rising, at high
airmass. Comparing with the UCSC AstroScheduler (see the Decision Map
artifact) showed the alternative: put each target where its airmass is
lowest, without giving up any target.

This module does that exactly, with no search cap. Given an ordered
sequence of blocks, the start times that minimise the summed cost, subject
to

    window entry <= start,  start + length <= window close,
    start(next) >= start + length + gap,   no overlap with blocked windows,

are a one-dimensional dynamic program over a time grid (STEP_MIN): for
each block in turn, the cheapest way to have placed everything before it
by time t is a running minimum. Cost is O(blocks x grid), milliseconds.

On top of that:
* insert_target() tries a dropped target at every position of the
  sequence and keeps the cheapest feasible one, so a target the greedy
  pass dropped gets in whenever moving the placed targets makes room
  (AstroScheduler's "placed targets may move", without its 20000-call cap);
* a stability term charges each minute a target moves away from its start
  in a previous plan, so a re-run does not shuffle the night;
* precedence (schedule_before) is honoured by ordering the sequence.
"""

import math

import numpy as np

from .sky import advance, track

# Grid step for start times, minutes. Starts snap to this grid; each block
# can lose up to one step against the greedy pass's fractional starts.
STEP_MIN = 0.5

# Cost of moving a target one minute away from its start in a previous
# plan, in units of airmass. 30 minutes then costs 0.06: a move happens
# only for a clear airmass gain, which is what stops plans from churning.
STABILITY_PER_MIN = 0.002


def time_grid(t0, t1, step=STEP_MIN):
    """
    Grid of candidate start times.

    Inputs: t0, t1 (tz-aware datetimes), step (minutes).
    Outputs: list of datetimes from t0 to t1 inclusive (last one <= t1).
    """
    n = int(math.floor((t1 - t0).total_seconds() / 60.0 / step + 1e-9)) + 1
    return [advance(t0, i * step) for i in range(max(n, 1))]


def airmass_on_grid(ra_deg, dec_deg, times, location):
    """
    Airmass of one target at every grid time.

    Inputs: ra_deg, dec_deg (float), times (list of datetime), location
    (astropy EarthLocation).
    Outputs: ndarray; np.inf where the target is down or past the useful
    limit, so any block touching it costs infinity.
    """
    am = track(ra_deg, dec_deg, times, location)['airmass']
    return np.array([np.inf if a is None else float(a) for a in am])


def steps_for(minutes, step=STEP_MIN):
    """Grid steps a span of `minutes` occupies, rounded up."""
    return int(math.ceil(minutes / step - 1e-9))


def block_metric(airmass, length_min, rule='worst', step=STEP_MIN):
    """
    Airmass of a block starting at each grid index.

    Inputs
    ------
    airmass : ndarray (grid)
    length_min : float, block length
    rule : 'worst' (max over the block), 'best' (min) or 'mid' (midpoint)

    Outputs
    -------
    ndarray of the same length; np.inf where the block runs off the grid.
    """
    n = len(airmass)
    k = steps_for(length_min, step)
    out = np.full(n, np.inf)
    if k + 1 > n:
        return out
    if rule == 'mid':
        out[:n - k] = airmass[k // 2: n - k + k // 2]
        return out
    win = np.lib.stride_tricks.sliding_window_view(airmass, k + 1)
    out[:n - k] = win.min(axis=1) if rule == 'best' else win.max(axis=1)
    return out


def legal_starts(times, length_min, entry, close, blocks):
    """
    Which grid starts keep a block inside its window and clear of blocks.

    Inputs
    ------
    times : list of datetime (grid)
    length_min : float
    entry, close : datetime; the block must start at or after entry and
        end at or before close
    blocks : list of (start, end, reason)

    Outputs
    -------
    bool ndarray over the grid.
    """
    ok = np.zeros(len(times), dtype=bool)
    for i, t in enumerate(times):
        if t < entry:
            continue
        end = advance(t, length_min)
        if end > close:
            break
        if any(t < b_end and end > b_start for b_start, b_end, _ in blocks):
            continue
        ok[i] = True
    return ok


def solve_order(costs, lengths, gap_min, step=STEP_MIN):
    """
    Cheapest start times for blocks taken in a fixed order.

    Inputs
    ------
    costs : list of ndarray, one per block, cost of starting at each grid
        index (np.inf = not allowed)
    lengths : list of float, block lengths in minutes
    gap_min : float, minutes required between one block's end and the
        next one's start

    Outputs
    -------
    (starts, total) : list of grid indices and the summed cost, or
    (None, inf) if no placement exists.
    """
    m = len(costs)
    if m == 0:
        return [], 0.0
    n = len(costs[0])
    idx = np.arange(n)
    best = costs[0].astype(float).copy()
    back = []
    for j in range(1, m):
        shift = steps_for(lengths[j - 1] + gap_min, step)
        run_min = np.minimum.accumulate(best)
        run_arg = np.maximum.accumulate(np.where(best <= run_min, idx, 0))
        prev_best = np.full(n, np.inf)
        prev_arg = np.zeros(n, dtype=int)
        if shift < n:
            prev_best[shift:] = run_min[:n - shift]
            prev_arg[shift:] = run_arg[:n - shift]
        best = costs[j] + prev_best
        back.append(prev_arg)
    last = int(np.argmin(best))
    total = float(best[last])
    if not np.isfinite(total):
        return None, math.inf
    starts = [last]
    for j in range(m - 1, 0, -1):
        starts.append(int(back[j - 1][starts[-1]]))
    return starts[::-1], total


def order_ok(names, before):
    """
    True if a sequence respects every precedence pair inside it.

    Inputs: names (list of str, in order), before (dict name -> set of
    names it must precede).
    Outputs: bool.
    """
    pos = {n: i for i, n in enumerate(names)}
    return all(pos[a] < pos[b] for a in names for b in before.get(a, ())
               if b in pos)


def precedence_order(names, before):
    """
    Reorder a sequence so every predecessor comes first, otherwise keeping
    the given order (a stable topological sort).

    Inputs: names (list of str), before (dict name -> set of names).
    Outputs: (ordered names, list of names caught in a cycle). Cycle
    members keep their given order and their constraints are ignored.
    """
    inside = set(names)
    preds = {n: {a for a in names if n in before.get(a, ())} for n in names}
    out, placed = [], set()
    remaining = list(names)
    while remaining:
        for n in remaining:
            if (preds[n] & inside) <= placed:
                out.append(n)
                placed.add(n)
                remaining.remove(n)
                break
        else:
            return out + remaining, list(remaining)
    return out, []


def insert_target(costs, lengths, names, cand_cost, cand_len, cand_name,
                  gap_min, before, step=STEP_MIN):
    """
    Try a new block at every position of a sequence; keep the cheapest.

    Inputs
    ------
    costs, lengths, names : the current sequence (as for solve_order)
    cand_cost, cand_len, cand_name : the block to insert
    gap_min : float
    before : dict name -> set of names it must precede

    Outputs
    -------
    (position, starts, total) for the cheapest feasible insertion, or
    (None, None, inf) when no position works.
    """
    best = (None, None, math.inf)
    for p in range(len(names) + 1):
        trial = names[:p] + [cand_name] + names[p:]
        if not order_ok(trial, before):
            continue
        starts, total = solve_order(costs[:p] + [cand_cost] + costs[p:],
                                    lengths[:p] + [cand_len] + lengths[p:],
                                    gap_min, step)
        if starts is not None and total < best[2]:
            best = (p, starts, total)
    return best
