"""
Calculate LST, twilight, HA-observable windows, and a feasible schedule
for Lick 2026B-02, NIGHT 2 (2026-09-15/16).

Created by JXP and Claude

Night 1 (2026-09-14) results, per the author:
  - TGT0602 and TGT0583 got a redshift -- DONE, not repeated.
  - The other 6 targets observed night 1 (3 primary: TGT0604
    [forced-first, only a truncated/partial exposure -- see
    lick_2026b02_calculations.py's FORCED_FIRST_TNS], TGT0176,
    TGT0574; 3 gap-fill extras: TGT0182, TGT0231,
    TGT0474) did not yield a redshift and are REPEATED tonight,
    all pooled together as this run's FRB priority list (FRBs are always
    the main priority -- per the author).
  - The author also supplied 6 spare/filler targets (non-FRB transients,
    given RA/Dec/mag directly, not from FFFF-PZ) to fill any remaining
    idle time: TGT0004, TGT0003, TGT0002, TGT0005, TGT0006, TGT0001.
    Per the author, TGT0003 is a priority filler -- "really interesting,
    but it's rising right now... you can definitely get it in twilight" --
    so it is checked for a forced/relaxed attempt near evening or morning
    twilight if its strict HA window does not otherwise allow it (same
    precedent as TGT0604's forced-first override on night 1).

Reuses the HA-window-first machinery from lick_2026b02_calculations.py
(target_window computes each target's -05:40<=HA<=+03:45 window, clipped to
the twilight-bounded night, *before* scheduling -- see that module's
docstring for why).
"""

import sys
from pathlib import Path
from datetime import timedelta

import pandas as pd
from astropy import units as u
from astropy.coordinates import SkyCoord

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
from night_planner.paths import plans_dir

_PLANS = plans_dir()
from scripts.lick_2026b02_calculations import (
    HA_MAX, HA_MIN, DEC_LIMIT, find_twilight, target_window, ha_at, time_at_lst,
)
from night_planner.estimate_kast_exposures import estimate_exposure
from schedule_overrides import (advance, resolve_start, fit_around_blocks,
                                 blocking_reason, push_past_blocks)
from night_plan_io import load_config, resolve_local_dt, resolve_blocks, save_night_meta, OBSERVATORY_TZ

OUT_DIR = f'{_PLANS}/Lick-2026B-02'
PRIMARY_TARGETS_CSV = f'{OUT_DIR}/Lick-2026B-02_targets.csv'
EXTRAS_ANALYSIS_CSV = f'{OUT_DIR}/extras_analysis.csv'
DATE = '2026-09-15'
SLEW_MINUTES = 5

# --- Repeats: everything observed night 1 EXCEPT the two confirmed z's ---
REPEAT_PRIMARY_TNS = ['TGT0604', 'TGT0176', 'TGT0574']
REPEAT_EXTRA_TNS = ['TGT0182', 'TGT0231', 'TGT0474']

# --- Spare/filler targets, author-supplied 2026-09-15 (RA/Dec/mag as
# given verbatim; magnitude filter varies by target -- C/V/g/r/L -- and
# is used directly as a stand-in for the r-mag exposure heuristic since
# no host r-band photometry exists for these; noted as an approximation
# in the schedule comments, not a science-grade calibration). ---
SPARE_TARGETS = [
    dict(TNS='TGT0004',  ra_str='RA_REDACTED',  dec_str='DEC_REDACTED', mag=15.9, filt='C'),
    dict(TNS='TGT0003',  ra_str='RA_REDACTED',  dec_str='DEC_REDACTED', mag=12.1, filt='V'),
    dict(TNS='TGT0002', ra_str='RA_REDACTED',  dec_str='DEC_REDACTED', mag=18.6, filt='g'),
    dict(TNS='TGT0005',  ra_str='RA_REDACTED',  dec_str='DEC_REDACTED', mag=17.4, filt='r'),
    dict(TNS='TGT0006',  ra_str='RA_REDACTED',  dec_str='DEC_REDACTED', mag=18.5, filt='L'),
    dict(TNS='TGT0001',  ra_str='RA_REDACTED',  dec_str='DEC_REDACTED', mag=20.3, filt='r'),
]

# Author's explicit call, 2026-09-15 message: "TGT0003 is really
# interesting, but it's rising right now. You can definitely get it in
# twilight." Checked directly (see never_legal_diagnostic() below):
# TGT0003 is circumpolar from Lick (Dec 53.51 > 90-lat 52.66) but the
# Shane's HA mount limit is not a horizon limit -- its -05:40<=HA<=+03:45
# window this specific night does not open until 07:03 PDT, 13 min AFTER
# sunrise (06:50 PDT). Unlike TGT0604's forced-first override on
# night 1 (a legal-but-short window, exposure truncated), this is not a
# truncation case -- the telescope mechanically cannot point there before
# the window opens, and by then it's daylight. NOT forced into the
# schedule; flagged for the author instead (see diagnostic output).


def load_repeat_targets():
    """Build the pooled FRB-repeat target list (primary + extras from
    night 1), all treated as this run's main priority.

    Returns
    -------
    pd.DataFrame with TNS, RA_hours, RA_deg, Dec_deg, mag_r, POx, tags, DM
    """
    primary = pd.read_csv(PRIMARY_TARGETS_CSV)
    primary = primary[primary['TNS'].isin(REPEAT_PRIMARY_TNS)].copy()
    primary_rows = [
        dict(TNS=row['TNS'], RA_hours=row['Pri_RA'] / 15.0, RA_deg=row['Pri_RA'],
             Dec_deg=row['Pri_Dec'], mag_r=row['Pri_mag'], POx=row['Pri_POx'],
             tags=row['FRB_tags'], DM=row['FRB_DM'], origin='repeat_primary')
        for _, row in primary.iterrows()
    ]

    extras = pd.read_csv(EXTRAS_ANALYSIS_CSV)
    extras = extras[extras['TNS'].isin(REPEAT_EXTRA_TNS)].copy()
    extras_rows = [
        dict(TNS=row['TNS'], RA_hours=row['RA_hours'], RA_deg=row['RA_deg'],
             Dec_deg=row['Dec_deg'], mag_r=row['mag_r'], POx=row['POx'],
             tags=row['Tags'], DM=None, origin='repeat_extra')
        for _, row in extras.iterrows()
    ]

    df = pd.DataFrame(primary_rows + extras_rows)
    missing = set(REPEAT_PRIMARY_TNS + REPEAT_EXTRA_TNS) - set(df['TNS'])
    if missing:
        raise ValueError(f'Could not find repeat targets: {missing}')
    return df


def load_spare_targets():
    """Parse the author-supplied spare/filler targets into the same
    RA_hours/RA_deg/Dec_deg/mag_r schema as the FRB targets.
    """
    rows = []
    for t in SPARE_TARGETS:
        c = SkyCoord(f"{t['ra_str']} {t['dec_str']}", unit=(u.hourangle, u.deg))
        rows.append(dict(TNS=t['TNS'], RA_hours=c.ra.hour, RA_deg=c.ra.deg,
                          Dec_deg=c.dec.deg, mag_r=t['mag'], POx=None,
                          tags=f"spare/filler ({t['filt']}-band mag given, "
                               "used as r-mag proxy)",
                          DM=None, origin='spare'))
    return pd.DataFrame(rows)


def analyze(df, twilight):
    rows = []
    for _, row in df.iterrows():
        window = target_window(row['RA_hours'], row['Dec_deg'], twilight)
        rec = dict(row)
        if window is None:
            rec.update(observable=False, entry_pst=None, exit_pst=None,
                       ha_entry=None, ha_exit=None, window_min=0)
        else:
            entry_time, exit_time, ha_entry, ha_exit = window
            rec.update(observable=True, entry_pst=entry_time, exit_pst=exit_time,
                       ha_entry=ha_entry, ha_exit=ha_exit,
                       window_min=(exit_time - entry_time).total_seconds() / 60.0)
        rows.append(rec)
    return pd.DataFrame(rows).sort_values('RA_hours').reset_index(drop=True)


def schedule_greedy(observable_df, start_time, end_time, forced_first=None, blocks=None,
                    slew_min=SLEW_MINUTES, readout=None, exposure=None):
    """Earliest-window-close-first greedy scheduler over a single
    continuous time span [start_time, end_time) (mirrors schedule_night()
    in lick_2026b02_calculations.py).

    Parameters
    ----------
    forced_first : str, optional
        TNS of a target to force-schedule at start_time regardless of
        whether its ideal exposure fits before its window closes
        (truncated instead of skipped). Reused tonight for
        TGT0604 -- same fast-setting-target problem as night 1
        (see FORCED_FIRST_TNS in lick_2026b02_calculations.py), since its
        HA-legal window is again only ~42 min wide at the very start of
        the night, too short for schedule_greedy's normal
        earliest-close-first pass to keep once it starts consuming that
        window for other targets.
    blocks : list of (start, end, reason) tuples, optional
        Blacked-out windows (ToO, weather hold) -- see schedule_overrides.py.
        Called on every sub-window (the main FRB pass and each spare
        gap-fill pass in main()), so a block is honored everywhere this
        function is used, not just on the first call.
    slew_min : float
        Gap left after each target before the next can start. Defaults to
        this run's SLEW_MINUTES; the general Kast path
        (kast_calculations) passes instrument_params.lick_gap_minutes()
        (slew + acquisition), added 2026-11-07.
    readout : callable, optional
        readout(red, blue) -> minutes of detector readout the recipe adds
        (or None if NOT SET). Default: none, as this run was planned. The
        general Kast path passes instrument_params.readout_minutes (T1.1,
        added 2026-11-07). A forced-first truncation is an allocation, so
        it gets no readout added.
    exposure : callable, optional
        exposure(row, start, minutes) -> dict with 'red', 'blue', 'dur_s'
        and any extra columns to keep on the row. start/minutes are None
        for the first guess; afterwards they are the placed science span,
        so the exposure can follow the airmass there (T1.3). Default: this
        run's empirical estimate_exposure. When given, a placed target is
        re-sized at its placement and re-placed if it grew, up to
        max_rounds times (added 2026-11-07).
    """
    def _readout(red, blue):
        return (readout(red, blue) or 0.0) if readout else 0.0

    def _exposure(row, start=None, minutes=None):
        if exposure is None:
            red, blue, dur_s = estimate_exposure(row['mag_r'])
            return {'red': red, 'blue': blue, 'dur_s': dur_s}
        return exposure(row, start, minutes)

    max_rounds = 3

    blocks = blocks or []
    observable = observable_df.copy()
    schedule = []
    current_time = push_past_blocks(start_time, blocks)

    if forced_first is not None and (observable['TNS'] == forced_first).any():
        mask = observable['TNS'] == forced_first
        row = observable[mask].iloc[0]
        observable = observable[~mask]

        e = _exposure(row)
        red, blue, dur_s = e['red'], e['blue'], e['dur_s']
        dur_min = dur_s / 60.0
        start = max(current_time, row['entry_pst'])
        window_close = min(row['exit_pst'], end_time)

        if start >= window_close:
            # A manual start (or a block) can push past this target's own
            # fast-closing window entirely -- forced_first means "attempt a
            # partial exposure if there's anything left," not "schedule it
            # regardless of whether its window has already closed."
            schedule.append(dict(row, scheduled=False,
                                  skip_reason=f"forced-first window already "
                                              f"closed by the time scheduling "
                                              f"starts (start {start:%H:%M} >= "
                                              f"exit {window_close:%H:%M})"))
        else:
            ideal_end = advance(start, dur_min)
            end = min(ideal_end, window_close)
            got_min = (end - start).total_seconds() / 60.0
            reason = ('' if end >= ideal_end else
                       f"forced first (faint, fast-setting, same problem as night "
                       f"1): truncated by HA_MAX cutoff to {got_min:.0f} of "
                       f"{dur_min:.0f} min ideal exposure -- partial spectrum")
            schedule.append(dict(row, scheduled=True, start_pst=start, end_pst=end,
                                  duration_min=got_min, red_side=red, blue_side=blue,
                                  skip_reason=reason))
            current_time = advance(end, slew_min)

    observable = observable.sort_values('exit_pst').reset_index(drop=True)
    for _, row in observable.iterrows():
        e = _exposure(row)
        red, blue, dur_s = e['red'], e['blue'], e['dur_s']
        readout_min = _readout(red, blue)
        dur_min = dur_s / 60.0 + readout_min

        raw_start = max(current_time, row['entry_pst'])
        window_close = min(row['exit_pst'], end_time)

        if raw_start >= window_close:
            schedule.append(dict(row, scheduled=False,
                                  skip_reason=f"window already closed by the "
                                              f"time this target would be "
                                              f"reached (start {raw_start:%H:%M})"))
            continue

        start, end = fit_around_blocks(raw_start, dur_min, window_close, blocks)
        # Re-size at the placement (airmass there) and re-place. The block is
        # always re-fitted to the latest exposure; iteration stops once a
        # re-size changes it by <= 0.5 min.
        for _ in range(max_rounds if exposure is not None else 0):
            if start is None:
                break
            e2 = _exposure(row, start, dur_s / 60.0)
            settled = abs(e2['dur_s'] - dur_s) / 60.0 <= 0.5
            e = e2
            red, blue, dur_s = e['red'], e['blue'], e['dur_s']
            readout_min = _readout(red, blue)
            dur_min = dur_s / 60.0 + readout_min
            start, end = fit_around_blocks(raw_start, dur_min, window_close, blocks)
            if settled:
                break
        if start is None:
            reason = blocking_reason(raw_start, dur_min, blocks)
            if reason:
                schedule.append(dict(row, scheduled=False,
                                      skip_reason=f"{reason} -- doesn't clear "
                                                  f"before its window closes "
                                                  f"({window_close:%H:%M})"))
            else:
                schedule.append(dict(row, scheduled=False,
                                      skip_reason=f"needs {dur_min:.0f} min but "
                                                  f"only {(window_close - raw_start).total_seconds() / 60:.0f} "
                                                  f"min left in its HA window"))
            continue

        extra = {k: v for k, v in e.items() if k not in ('red', 'blue', 'dur_s')}
        schedule.append(dict(row, scheduled=True, start_pst=start, end_pst=end,
                              duration_min=dur_min, red_side=red, blue_side=blue,
                              readout_min=readout_min, skip_reason='', **extra))
        current_time = advance(end, slew_min)

    return pd.DataFrame(schedule), current_time


def never_legal_diagnostic(name, ra_hours, twilight):
    """For a spare target whose HA window never opens during the
    twilight-bounded night, compute exactly when (clock time) it WOULD
    reach HA=-5.0 (window entry) and HA=+3.75 (window exit) relative to
    that night's 18-deg twilights and to actual sunset/sunrise, so a
    borderline miss (like TGT0003) can be reported precisely instead of
    just labeled unobservable.
    """
    sun_times = find_twilight(DATE, twilight_alt=-0.833 * u.deg)
    sunrise = sun_times['morning_pst']
    sunset = sun_times['evening_pst']

    lst_entry = (ra_hours - 5.0) % 24
    lst_exit = (ra_hours + 3.75) % 24
    entry_time = time_at_lst(lst_entry, twilight['evening_lst'].hour, twilight['evening_pst'])
    exit_time = time_at_lst(lst_exit, twilight['evening_lst'].hour, twilight['evening_pst'])

    print(f"  {name}: Shane HA window ({HA_MIN:+.2f}h..{HA_MAX:+.2f}h) would run "
          f"{entry_time:%m-%d %H:%M} -> {exit_time:%m-%d %H:%M} {exit_time.tzname()} "
          f"(sunset {sunset:%H:%M}, sunrise {sunrise:%H:%M} {sunrise.tzname()}) -- "
          f"{'overlaps' if entry_time < sunrise and exit_time > sunset else 'does NOT overlap'} "
          "the physically-dark-or-twilight part of the night")
    return entry_time, exit_time, sunset, sunrise


def parse_args(argv=None):
    """
    Parameters
    ----------
    argv : list of str, optional
        Defaults to sys.argv[1:]. Passed explicitly by night_planner.cli.
    """
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', help='Path to a night-plan JSON config '
                   '(night_plan_io.NightPlanConfig). CLI flags below '
                   'override whatever the config contains.')
    p.add_argument('--start', help='Manual night-start override, HH:MM '
                   'real local Lick wall-clock time (America/Los_Angeles -- '
                   'PST or PDT depending on time of year) or full ISO '
                   'datetime. Overrides the normal evening-twilight start.')
    p.add_argument('--block', action='append', default=[],
                   help='Blocked-out window, "HH:MM-HH:MM" or '
                   '"HH:MM-HH:MM@reason". Repeatable.')
    return p.parse_args(argv)


def _parse_block_flag(spec):
    """Parse '--block HH:MM-HH:MM' or '--block HH:MM-HH:MM@reason'."""
    window, _, reason = spec.partition('@')
    start, end = window.split('-')
    return {'start': start, 'end': end, 'reason': reason or 'blocked'}


def run(args):
    """Execute the calculation pipeline for an already-parsed args namespace
    (see keck_2026oct06_calculations.run() for why this is split from main())."""
    cfg = load_config(args.config) if args.config else None

    start_spec = args.start or (cfg.start_override if cfg else None)
    block_specs = list(cfg.blocks) if cfg else []
    block_specs += [_parse_block_flag(b) for b in args.block]

    tz = OBSERVATORY_TZ['lick']  # America/Los_Angeles: real PST/PDT by date
    start_override_local = resolve_local_dt(DATE, start_spec, tz) if start_spec else None
    blocks = resolve_blocks(DATE, block_specs, tz)

    twilight = find_twilight(DATE)

    if blocks:
        print(f"=== BLOCKED WINDOWS ===")
        for b_start, b_end, reason in blocks:
            print(f"  {b_start.strftime('%H:%M')}-{b_end.strftime('%H:%M')} "
                  f"{b_start.tzname()}: {reason}")
    if start_override_local is not None:
        print(f"Manual night start: {start_override_local.strftime('%H:%M')} "
              f"{start_override_local.tzname()}")

    repeats = load_repeat_targets()
    spares = load_spare_targets()

    repeat_analysis = analyze(repeats, twilight)
    spare_analysis = analyze(spares, twilight)

    print(f"=== TWILIGHT for {DATE} (18 deg astronomical, real DST-aware Lick clock) ===")
    print(f"Evening: {twilight['evening_pst']:%H:%M} {twilight['evening_pst'].tzname()} "
          f"(LST {twilight['evening_lst'].hour:.3f}h)")
    print(f"Morning: {twilight['morning_pst']:%H:%M} {twilight['morning_pst'].tzname()} "
          f"(LST {twilight['morning_lst'].hour:.3f}h)")
    night_min = (twilight['morning_pst'] - twilight['evening_pst']).total_seconds() / 60
    print(f"Night length: {night_min:.0f} min ({night_min / 60:.2f} h)\n")

    print("=== FRB REPEATS: HA-WINDOW ANALYSIS (main priority) ===")
    disp = repeat_analysis.copy()
    disp['entry_pst'] = disp['entry_pst'].apply(lambda t: t.strftime('%H:%M') if pd.notna(t) else '-')
    disp['exit_pst'] = disp['exit_pst'].apply(lambda t: t.strftime('%H:%M') if pd.notna(t) else '-')
    print(disp[['TNS', 'origin', 'RA_hours', 'Dec_deg', 'mag_r', 'observable',
                'entry_pst', 'exit_pst', 'ha_entry', 'ha_exit', 'window_min']]
          .to_string(index=False))

    print("\n=== SPARE/FILLER TARGETS: HA-WINDOW ANALYSIS ===")
    disp2 = spare_analysis.copy()
    disp2['entry_pst'] = disp2['entry_pst'].apply(lambda t: t.strftime('%H:%M') if pd.notna(t) else '-')
    disp2['exit_pst'] = disp2['exit_pst'].apply(lambda t: t.strftime('%H:%M') if pd.notna(t) else '-')
    print(disp2[['TNS', 'RA_hours', 'Dec_deg', 'mag_r', 'observable',
                 'entry_pst', 'exit_pst', 'ha_entry', 'ha_exit', 'window_min']]
          .to_string(index=False))

    # 1) Schedule FRB repeats first across the full night (main priority).
    # TGT0604 forced first again (same fast-setting problem as
    # night 1 -- see schedule_greedy's forced_first docstring).
    night_start = resolve_start(twilight['evening_pst'], start_override_local)
    frb_sched, t_after_frbs = schedule_greedy(
        repeat_analysis[repeat_analysis['observable']],
        night_start, twilight['morning_pst'],
        forced_first='TGT0604', blocks=blocks)

    # 2) Idle intervals left between/after the FRB blocks -> offer to spares.
    frb_scheduled_sorted = (frb_sched[frb_sched['scheduled']]
                             .sort_values('start_pst').reset_index(drop=True))
    gaps = []
    cursor = night_start
    for _, row in frb_scheduled_sorted.iterrows():
        if (row['start_pst'] - cursor).total_seconds() > 0:
            gaps.append((cursor, row['start_pst']))
        cursor = advance(row['end_pst'], SLEW_MINUTES)
    if (twilight['morning_pst'] - cursor).total_seconds() > 0:
        gaps.append((cursor, twilight['morning_pst']))

    spare_schedule_rows = []
    spare_pool = spare_analysis[spare_analysis['observable']].copy()
    for gap_start, gap_end in gaps:
        if spare_pool.empty:
            break
        sched, _ = schedule_greedy(spare_pool, gap_start, gap_end, blocks=blocks)
        placed = sched[sched['scheduled']] if len(sched) else sched
        if len(placed):
            spare_schedule_rows.append(placed)
            spare_pool = spare_pool[~spare_pool['TNS'].isin(placed['TNS'])]

    spare_sched = (pd.concat(spare_schedule_rows, ignore_index=True)
                   if spare_schedule_rows else pd.DataFrame())

    unplaced_spares = spare_pool[~spare_pool['TNS'].isin(
        spare_sched['TNS'] if len(spare_sched) else [])]

    # 3) Diagnostic for spare targets that never enter the Shane HA-legal
    # window tonight at all (excluded from spare_pool before scheduling
    # even started) -- report exactly when their window WOULD open,
    # relative to sunrise/sunset, rather than just calling them
    # unobservable. Directly answers the author's "TGT0003... you can
    # definitely get it in twilight" call with real numbers.
    never_legal = spare_analysis[~spare_analysis['observable']]
    if len(never_legal):
        print("\n=== Never HA-legal tonight (Shane mount limit, not horizon) ===")
        for _, row in never_legal.iterrows():
            never_legal_diagnostic(row['TNS'], row['RA_hours'], twilight)

    print("\n=== SCHEDULE: FRB repeats (earliest-window-close-first) ===")
    for _, row in frb_sched.sort_values(
            'start_pst' if 'start_pst' in frb_sched.columns else 'TNS').iterrows():
        if row['scheduled']:
            print(f"  {row['start_pst']:%H:%M}-{row['end_pst']:%H:%M} {row['end_pst'].tzname()}  "
                  f"{row['TNS']:14s} ({row['origin']}) RA {row['RA_hours']:.2f}h "
                  f"mag {row['mag_r']:.2f} HA[{row['ha_entry']:.2f},{row['ha_exit']:.2f}]  "
                  f"red {row['red_side']} blue {row['blue_side']}")
        else:
            print(f"  SKIPPED  {row['TNS']:14s} ({row['origin']}) -- {row['skip_reason']}")

    print("\n=== SCHEDULE: spare/filler targets in idle gaps ===")
    if len(spare_sched):
        for _, row in spare_sched.sort_values('start_pst').iterrows():
            print(f"  {row['start_pst']:%H:%M}-{row['end_pst']:%H:%M} {row['end_pst'].tzname()}  "
                  f"{row['TNS']:10s} RA {row['RA_hours']:.2f}h mag {row['mag_r']:.2f}  "
                  f"red {row['red_side']} blue {row['blue_side']}"
                  + (f"  [{row['skip_reason']}]" if row['skip_reason'] else ''))
    else:
        print("  none scheduled")
    if len(unplaced_spares):
        for _, row in unplaced_spares.iterrows():
            print(f"  NOT SCHEDULED  {row['TNS']}")

    n_frb = int(frb_sched['scheduled'].sum()) if len(frb_sched) else 0
    n_spare = int(spare_sched['scheduled'].sum()) if len(spare_sched) else 0
    sci_min = ((frb_sched.loc[frb_sched['scheduled'], 'duration_min'].sum() if n_frb else 0)
               + (spare_sched.loc[spare_sched['scheduled'], 'duration_min'].sum() if n_spare else 0))
    print(f"\n{n_frb} of {len(frb_sched)} FRB repeats scheduled; "
          f"{n_spare} spare/filler targets scheduled; "
          f"{sci_min:.0f} min science / {night_min:.0f} min night "
          f"({100 * sci_min / night_min:.0f}% utilization)")

    repeat_analysis.to_csv(f'{OUT_DIR}/night2_frb_repeat_analysis.csv', index=False)
    spare_analysis.to_csv(f'{OUT_DIR}/night2_spare_analysis.csv', index=False)
    frb_sched.to_csv(f'{OUT_DIR}/night2_frb_repeat_schedule.csv', index=False)
    spare_sched.to_csv(f'{OUT_DIR}/night2_spare_schedule.csv', index=False)
    print(f"\nWrote night2_frb_repeat_analysis.csv, night2_spare_analysis.csv, "
          f"night2_frb_repeat_schedule.csv, night2_spare_schedule.csv to {OUT_DIR}")

    meta_path = save_night_meta(
        OUT_DIR, start_local=night_start,
        evening_twilight_local=twilight['evening_pst'],
        morning_twilight_local=twilight['morning_pst'],
        blocks=blocks, date=DATE)
    print(f"Wrote night_meta.json: resolved start/blocks for the Excel builder ({meta_path})")

    return {
        'repeat_analysis': repeat_analysis,
        'spare_analysis': spare_analysis,
        'frb_sched': frb_sched,
        'spare_sched': spare_sched,
        'twilight': twilight,
        'start_local': night_start,
        'night_end': twilight['morning_pst'],
        'blocks': blocks,
        'output_dir': OUT_DIR,
        'date': DATE,
    }


def main():
    """Standalone entry point: `python scripts/lick_2026b02_night2_calculations.py ...`."""
    return run(parse_args())


if __name__ == '__main__':
    main()
