"""
Created by JXP and Claude

Run night-planner's and AstroScheduler's placement rules on one toy night.

This feeds the "Compare" tab of the Night Planner Decision Map artifact.
Both rule sets are re-implemented here in miniature, on the same made-up
targets, so the two styles can be drawn side by side:

* night-planner (Kast path, scripts/kast_calculations.py): HA-only windows,
  tier 1 by one earliest-window-close-first greedy pass, lower tiers placed
  greedily inside the gaps the tiers above left (placed rows never move),
  then partial backfill of anything dropped for time (>= 10 min).
* AstroScheduler (astroscheduler/core.py, v1.3.0): 1-minute chunks valid
  only inside the HA limits, Dec -35..+72 and airmass <= 1.7; a block is
  exposure + 7 min overhead; priority tiers solved in order, with every
  earlier placement mandatory but movable, by branch and bound minimising
  the summed median airmass, 100000 per dropped optional target, and a
  20000-step cap.

Simplifications, shared by both sides: the night runs between the 18-degree
twilights (no standards, no focus), exposures are fixed (as on an empirical
Kast plan, no ETC re-sizing), and hour angle advances one hour per hour.

Also tabulates AstroScheduler's Kast block length against magnitude from
its KAST_SCIENCE_LOOKUP, for the AstroScheduler tab.

Inputs
------
--out PATH : optional; write the JSON there instead of printing it.

Outputs
-------
JSON with the toy targets, both schedules (after each tier), per-minute
AstroScheduler validity strips, one slot-cost curve, and the lookup table.
"""
import argparse
import json
import math

import numpy as np

# Site and limits --------------------------------------------------------
LAT_DEG = 37.3414                      # Lick (both tools)
HA_MIN, HA_MAX = -(5 + 40 / 60), 3.75  # Shane HA limits (both tools)
NIGHT_MIN = 540                        # 18-deg twilight to twilight, minutes

# night-planner, Kast
NP_GAP_MIN = 5.0                       # 2 slew + 3 acquisition
NP_DEC_MAX = 82.0
NP_MIN_PARTIAL = 10.0

# AstroScheduler, Lick (telescopes.json, core.py)
AS_DEC_MIN, AS_DEC_MAX = -35.0, 72.0
AS_AIRMASS_LIMIT = 1.7
AS_OVERHEAD_MIN = 7
AS_DROP_PENALTY = 100000.0
AS_MAX_ITER = 20000

# Kast lookup (AstroScheduler core.py KAST_SCIENCE_LOOKUP) and readouts
KAST_LOOKUP = {
    13.0: (637.0, 1, 300.0, 2), 13.5: (637.0, 1, 300.0, 2),
    14.0: (637.0, 1, 300.0, 2), 14.5: (637.0, 1, 300.0, 2),
    15.0: (637.0, 1, 300.0, 2), 15.5: (937.0, 1, 450.0, 2),
    16.0: (937.0, 1, 450.0, 2), 16.5: (937.0, 1, 450.0, 2),
    17.0: (1237.0, 1, 600.0, 2), 17.5: (1570.0, 1, 500.0, 3),
    18.0: (1845.0, 1, 600.0, 3), 18.5: (1230.0, 2, 600.0, 4),
    19.0: (1560.0, 2, 600.0, 5), 19.5: (1845.0, 2, 600.0, 6),
    20.0: (2145.0, 2, 600.0, 7),
}
BLUE_ERASE, RED_ERASE, BLUE_READOUT, RED_READOUT = 5.0, 20.0, 30.0, 22.0

# Toy targets: transit time (min after the night starts), Dec, science
# minutes, priority. Made up to show the two styles' differences.
# 'main': the everyday differences. 'cap': SIM-D made long enough that
# fitting it needs SIM-A (the first target the search tries) to move.
SCENARIOS = {
    'main': [
        dict(name='SIM-A', transit=150, dec=30.0, exp=80, priority=1),
        dict(name='SIM-B', transit=280, dec=30.0, exp=90, priority=1),
        dict(name='SIM-C', transit=420, dec=30.0, exp=70, priority=1),
        dict(name='SIM-D', transit=0, dec=30.0, exp=60, priority=2),
        dict(name='SIM-F', transit=300, dec=76.0, exp=40, priority=2),
        dict(name='SIM-G', transit=700, dec=30.0, exp=90, priority=2),
    ],
}
SCENARIOS['cap'] = [dict(t, exp=150) if t['name'] == 'SIM-D' else dict(t)
                    for t in SCENARIOS['main'] if t['name'] in ('SIM-A', 'SIM-B', 'SIM-C', 'SIM-D')]


def airmass(t_min, target):
    """
    Plane-parallel airmass of a toy target.

    Inputs: t_min (minutes after night start), target (dict with transit, dec).
    Output: sec z, or 999.0 below the horizon.
    """
    ha = math.radians((t_min - target['transit']) / 60.0 * 15.0)
    lat, dec = math.radians(LAT_DEG), math.radians(target['dec'])
    cosz = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(ha)
    return 1.0 / cosz if cosz > 0 else 999.0


def hour_angle(t_min, target):
    """Hour angle in hours at minute t_min, wrapped to [-12, 12)."""
    ha = (t_min - target['transit']) / 60.0
    return (ha + 12.0) % 24.0 - 12.0


# ----------------------------------------------------------------- night-planner
def np_window(target):
    """
    night-planner Kast window: the span of the night inside the Shane HA limits.

    Inputs: target dict. Output: (entry, exit) minutes, or None.
    """
    if target['dec'] > NP_DEC_MAX:
        return None
    inside = [t for t in range(NIGHT_MIN + 1) if HA_MIN <= hour_angle(t, target) <= HA_MAX]
    return (min(inside), max(inside)) if inside else None


def np_greedy(pool, start, end):
    """
    Earliest-window-close-first greedy pass over one span (schedule_greedy).

    Inputs: pool (list of target dicts with 'win'), start/end minutes.
    Outputs: (placed list, dropped list of (target, reason)).
    """
    placed, dropped, cursor = [], [], start
    for t in sorted(pool, key=lambda r: r['win'][1]):
        s = max(cursor, t['win'][0])
        close = min(t['win'][1], end)
        if s + t['exp'] > close:
            left = max(0, close - s)
            dropped.append((t, f"needs {t['exp']} min but only {left:.0f} min left in its HA window"))
            continue
        placed.append(dict(name=t['name'], start=s, end=s + t['exp'], priority=t['priority']))
        cursor = s + t['exp'] + NP_GAP_MIN
    return placed, dropped


def free_gaps(placed, start, end):
    """Idle intervals between placed blocks, each block followed by its gap."""
    gaps, cursor = [], start
    for b in sorted(placed, key=lambda b: b['start']):
        if b['start'] > cursor:
            gaps.append((cursor, b['start']))
        cursor = max(cursor, b['end'] + NP_GAP_MIN)
    if cursor < end:
        gaps.append((cursor, end))
    return gaps


def run_night_planner(targets):
    """
    Tiered night-planner schedule with partial backfill.

    Inputs: list of target dicts. Output: dict with per-step schedules and outcomes.
    """
    outcome, steps, placed = {}, [], []
    pool = []
    for t in targets:
        w = np_window(t)
        if w is None:
            outcome[t['name']] = dict(status='rejected', stage='2. Sky', reason='never inside the HA limits')
        else:
            pool.append(dict(t, win=w))
    tiers = sorted({t['priority'] for t in pool})
    for i, tier in enumerate(tiers):
        members = [t for t in pool if t['priority'] == tier]
        if i == 0:
            got, dropped = np_greedy(members, 0, NIGHT_MIN)
            placed += got
        else:
            remaining = members
            for g0, g1 in free_gaps(placed, 0, NIGHT_MIN):
                got, _ = np_greedy(remaining, g0, g1)
                placed += got
                names = {b['name'] for b in got}
                remaining = [t for t in remaining if t['name'] not in names]
            dropped = [(t, f"P{tier}: no idle interval left by the tier above was long enough "
                           f"inside its HA window") for t in remaining]
        for t, why in dropped:
            outcome[t['name']] = dict(status='rejected', stage='3. Scheduling', reason=why)
        steps.append(dict(label=f'Tier P{tier}', blocks=[dict(b) for b in placed]))

    # Partial backfill: best priority first, then earliest window close.
    cands = sorted([t for t in pool if outcome.get(t['name'], {}).get('stage') == '3. Scheduling'],
                   key=lambda r: (r['priority'], r['win'][1]))
    for t in cands:
        for g0, g1 in free_gaps(placed, 0, NIGHT_MIN):
            s, close = max(g0, t['win'][0]), min(g1, t['win'][1])
            if close - s >= NP_MIN_PARTIAL:
                placed.append(dict(name=t['name'], start=s, end=close, priority=t['priority'], partial=True))
                outcome[t['name']] = dict(status='partial', stage='',
                                          reason=f"PARTIAL: {close - s:.0f} of the {t['exp']} min it needs")
                break
    steps.append(dict(label='Partial backfill', blocks=[dict(b) for b in placed]))
    for b in placed:
        tgt = next(t for t in targets if t['name'] == b['name'])
        b['airmass'] = round(float(np.median([airmass(m + 0.5, tgt) for m in range(int(b['start']), int(b['end']))])), 3)
        outcome.setdefault(b['name'], dict(status='scheduled', stage='', reason=''))
    for st in steps:
        for b in st['blocks']:
            b['airmass'] = next(p['airmass'] for p in placed if p['name'] == b['name'])
    windows = {t['name']: list(t['win']) for t in pool}
    return dict(steps=steps, outcome=outcome, windows=windows)


# ---------------------------------------------------------------- AstroScheduler
def as_fail_reason(t_min, target):
    """
    First AstroScheduler rule a toy minute fails (is_chunk_valid order).

    Inputs: minute, target dict. Output: '' if valid, else 'dec', 'ha' or 'airmass'.
    """
    if not (AS_DEC_MIN <= target['dec'] <= AS_DEC_MAX):
        return 'dec'
    if not (HA_MIN <= hour_angle(t_min, target) <= HA_MAX):
        return 'ha'
    am = airmass(t_min, target)
    if am <= 0 or am > AS_AIRMASS_LIMIT:
        return 'airmass'
    return ''


def as_slot_costs(target, valid):
    """
    Valid start chunks and their cost (median airmass over the block).

    Inputs: target dict with 'dur', per-minute validity list.
    Output: dict start -> cost.
    """
    costs, d = {}, target['dur']
    for s in range(0, NIGHT_MIN - d + 1):
        if all(valid[s:s + d]):
            costs[s] = float(np.median([airmass(c, target) for c in range(s, s + d)]))
    return costs


def as_solve_tier(order, costs, mandatory, optional, current):
    """
    One tier's branch and bound, as in Scheduler._solve_internal.

    Inputs: order (targets in search order), costs (name -> {slot: cost}),
    mandatory/optional (name sets), current (name -> previous slot).
    Output: best schedule dict name -> start, or None.
    """
    dur = {t['name']: t['dur'] for t in order}
    slots = {}
    for t in order:
        c = costs[t['name']]
        prev = current.get(t['name'])
        rest = sorted([s for s in c if s != prev], key=lambda s: c[s])
        slots[t['name']] = ([prev] if prev in c else []) + rest

    def free(occ, s, d):
        return not occ[s:s + d].any()

    # Greedy warm start
    occ = np.zeros(NIGHT_MIN + 1, dtype=bool)
    greedy, gcost = {}, 0.0
    for t in order:
        for s in slots[t['name']]:
            if free(occ, s, t['dur']):
                greedy[t['name']] = s
                occ[s:s + t['dur']] = True
                gcost += costs[t['name']][s]
                break
        else:
            if t['name'] in optional:
                gcost += AS_DROP_PENALTY
    ok = all(n in greedy for n in mandatory)
    best = dict(sched=greedy if ok else None, cost=gcost if ok else float('inf'))

    mins = [min(costs[t['name']].values()) if costs[t['name']] else 0.0 for t in order]
    suffix = list(np.cumsum(mins[::-1])[::-1]) + [0.0]
    it = [0]
    occ = np.zeros(NIGHT_MIN + 1, dtype=bool)
    # How deep into each target's slot list the search ever got.
    reach = {t['name']: 0 for t in order}

    def search(i, sched, cost):
        it[0] += 1
        if it[0] > AS_MAX_ITER:
            return
        if i == len(order):
            if cost < best['cost']:
                best['cost'], best['sched'] = cost, dict(sched)
            return
        if cost + suffix[i] >= best['cost']:
            return
        t = order[i]
        n, d = t['name'], t['dur']
        for k, s in enumerate(slots[n]):
            if it[0] > AS_MAX_ITER:
                break
            reach[n] = max(reach[n], k + 1)
            if not free(occ, s, d):
                continue
            sched[n] = s
            occ[s:s + d] = True
            search(i + 1, sched, cost + costs[n][s])
            occ[s:s + d] = False
            del sched[n]
        if n in optional:
            search(i + 1, sched, cost + AS_DROP_PENALTY)

    search(0, {}, 0.0)
    progress = [dict(name=t['name'], tried=reach[t['name']], slots=len(slots[t['name']]),
                     mandatory=t['name'] in mandatory) for t in order]
    return best['sched'], it[0], progress


def run_astroscheduler(targets):
    """
    AstroScheduler-style tiered solve of the toy night.

    Inputs: list of target dicts. Output: dict with per-tier schedules,
    outcomes, per-minute fail strips and slot-cost curves.
    """
    outcome, strips, costs, observable = {}, {}, {}, []
    for t in targets:
        t = dict(t, dur=t['exp'] + AS_OVERHEAD_MIN)
        strips[t['name']] = [as_fail_reason(m, t) for m in range(NIGHT_MIN)]
        valid = [r == '' for r in strips[t['name']]]
        if not any(valid):
            outcome[t['name']] = dict(status='unobservable', reason='no valid minute tonight')
            continue
        costs[t['name']] = as_slot_costs(t, valid)
        if not costs[t['name']]:
            outcome[t['name']] = dict(status='conflict', reason='no slot long enough')
            continue
        observable.append(t)

    current, steps, iters = {}, [], {}
    for tier in sorted({t['priority'] for t in observable}):
        mandatory = set(current)
        new = [t for t in observable if t['priority'] == tier]
        active = [t for t in observable if t['name'] in mandatory] + new
        # Search order: placed first, then priority, then RA past LST at the
        # start (the transit time here), then longest first.
        order = sorted(active, key=lambda t: (t['name'] not in mandatory, t['priority'],
                                              (t['transit'] / 60.0) % 24.0, -t['dur']))
        sched, n_it, progress = as_solve_tier(order, costs, mandatory, {t['name'] for t in new}, current)
        iters[f'P{tier}'] = dict(calls=n_it, progress=progress)
        if sched is not None:
            current = sched
        for t in new:
            if t['name'] not in current:
                outcome[t['name']] = dict(status='conflict', reason='dropped by the solver')
        blocks = []
        for n, s in sorted(current.items(), key=lambda kv: kv[1]):
            t = next(x for x in observable if x['name'] == n)
            blocks.append(dict(name=n, start=s, end=s + t['dur'], priority=t['priority'],
                               science_start=s + AS_OVERHEAD_MIN,
                               airmass=round(costs[n][s], 3)))
        steps.append(dict(label=f'Tier P{tier}', blocks=blocks))
    for n in current:
        outcome.setdefault(n, dict(status='scheduled', reason=''))
    curves = {n: [[s, round(c, 4)] for s, c in sorted(cs.items())] for n, cs in costs.items()}
    return dict(steps=steps, outcome=outcome, iterations=iters, curves=curves,
                strips={n: ''.join({'': '.', 'dec': 'D', 'ha': 'H', 'airmass': 'A'}[r] for r in s)
                        for n, s in strips.items()})


def check_witness(targets, starts):
    """
    Check a hand-picked AstroScheduler schedule: every minute legal, no overlap.

    Inputs: target dicts, starts (name -> start minute).
    Output: dict with ok (bool), the blocks, and their summed median airmass.
    """
    blocks, ok = [], True
    for t in targets:
        d = t['exp'] + AS_OVERHEAD_MIN
        s = starts[t['name']]
        legal = all(as_fail_reason(m, t) == '' for m in range(s, s + d)) and s + d <= NIGHT_MIN
        ok &= legal
        blocks.append(dict(name=t['name'], start=s, end=s + d, legal=legal,
                           airmass=round(float(np.median([airmass(m, t) for m in range(s, s + d)])), 3)))
    spans = sorted((b['start'], b['end']) for b in blocks)
    ok &= all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))
    return dict(ok=bool(ok), blocks=blocks, cost=round(sum(b['airmass'] for b in blocks), 3))


# A schedule that fits all four 'cap' targets, which the capped search misses.
CAP_WITNESS = {'SIM-D': 0, 'SIM-A': 157, 'SIM-B': 244, 'SIM-C': 363}


def kast_lookup_durations():
    """
    AstroScheduler Kast block length (minutes, with the 7-min overhead) per
    lookup magnitude.

    Output: list of [mag, blue_s x n, red_s x n, block_min].
    """
    rows = []
    for mag, (be, bn, re_, rn) in sorted(KAST_LOOKUP.items()):
        t_red = rn * (re_ + RED_ERASE) + (rn - 1) * RED_READOUT
        t_blue = bn * (be + BLUE_ERASE) + (bn - 1) * BLUE_READOUT
        rows.append([mag, f'{bn}x{be:.0f}', f'{rn}x{re_:.0f}',
                     int(math.ceil(AS_OVERHEAD_MIN + max(t_red, t_blue) / 60.0))])
    return rows


def main():
    """Run both toy schedules and emit JSON."""
    p = argparse.ArgumentParser(description=__doc__.split('\n')[3])
    p.add_argument('--out', help='write JSON here instead of stdout')
    args = p.parse_args()
    np.random.seed(42)  # nothing here is random; fixed by convention
    res = dict(night_min=NIGHT_MIN, kast_lookup=kast_lookup_durations(), scenarios={})
    for key, toy in SCENARIOS.items():
        res['scenarios'][key] = dict(targets=toy, night_planner=run_night_planner(toy),
                                     astroscheduler=run_astroscheduler(toy))
    res['scenarios']['cap']['witness'] = check_witness(SCENARIOS['cap'], CAP_WITNESS)
    text = json.dumps(res, indent=1)
    if args.out:
        with open(args.out, 'w') as f:
            f.write(text)
    else:
        print(text)


if __name__ == '__main__':
    main()
