"""
General Lick/Kast night planning: any target table, any date.

The machinery this stands on is already general -- `target_window()`,
`find_twilight()` and the earliest-window-close-first scheduler all live
in lick_2026b02_calculations / lick_2026b02_night2_calculations. What was
missing was an entry point not pinned to one run: those modules hardcode
Lick-2026B-02 and 2026-09-15.

This mirrors the Keck module's interface (--targets-csv / --output-dir /
--date / --start / --block / --force) so the CLI and the viewer can drive
either instrument the same way.

Created by JXP and Claude
"""

import math
import os
import sys
from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / 'scripts'))

from scripts.lick_2026b02_calculations import (
    DEC_LIMIT, HA_MAX, HA_MIN, LICK, PST,
    calculate_lst, find_twilight, ha_at, target_window,
)

# How a placed target's start is chosen (2026-11-15). 'airmass' re-times
# the greedy pass's targets to their lowest summed airmass and inserts
# dropped targets where moving the others makes room; 'earliest' is the
# behaviour before that: each target as early as its window allows.
PLACEMENTS = ('airmass', 'earliest')
DEFAULT_PLACEMENT = 'airmass'


def _lst_hours(when):
    """Apparent LST at Lick, in hours, at a tz-aware datetime."""
    from datetime import timezone
    return calculate_lst(when.astimezone(timezone.utc)).hour
from night_planner.instrument_params import (DEFAULT_CONFIG, ConfigError,
                                             add_config_args, lick_gap_minutes,
                                             readout_minutes, resolve_options)

# Minutes from one target's end to the next one's science start: Lick slew
# + acquisition (2 + 3 = 5 min, Lordrick 2026-11-07). Read from
# instrument_params, not the run-specific lick_2026b02_* scripts, so
# adapters._attribute_kast_slews splits exactly the gap this leaves.
SLEW_MINUTES = lick_gap_minutes()


def kast_readout(red, blue):
    """
    Readout minutes a Kast recipe adds (slow mode, 20 s per frame; T1.1).

    Parameters
    ----------
    red, blue : str
        Exposure recipes, e.g. '6 x 600', '3 x 1200'.

    Returns
    -------
    float minutes, or None if NOT SET.
    """
    return readout_minutes('kast', red, blue, DEFAULT_CONFIG['kast'])


def make_kast_exposure(etc_opts=None, spectra=None):
    """
    The exposure function the Kast schedulers call (T1.3, T3.4).

    Everything goes through night_planner.etc: the UCO/Lick ETC by default
    (S/N 10 per sub-exposure, >= 3 sub-exposures, d57 sent as d55), or the
    old empirical magnitude rule with --etc empirical.

    Parameters
    ----------
    etc_opts : dict, optional
        From instrument_params.resolve_options('kast'). None = the
        empirical rule, which is what the scheduling functions fall back
        to when called directly.
    spectra : dict, optional
        Filled with TNS -> S/N spectrum of the latest call, for
        <plan>/etc/<target>.json.

    Returns
    -------
    callable exposure(row, start=None, minutes=None) -> dict with 'red',
    'blue', 'dur_s', plus 'airmass_used', 'airmass_rule' and the S/N
    columns. With start=None the ETC runs at the best airmass in the
    target's HA window (the first guess); with a placed span, at the
    --airmass-rule airmass over it.
    """
    from night_planner import etc as etc_mod
    from night_planner.instrument_params import DEFAULT_SEEING, ETC_FILTERS
    from night_planner.sky import block_airmass
    from night_planner.targets_io import has_own_sn, row_target_sn

    opts = dict(etc_opts or {'etc': 'empirical'})
    spec = opts.get('etc') or 'kast'
    empirical = etc_mod.load_etc(spec) is etc_mod.empirical_kast_etc
    rule = opts.get('airmass_rule', 'worst')
    plan_sn = opts.get('target_sn') or etc_mod.TARGET_SN['kast']
    best = {}

    def exposure(row, start=None, minutes=None):
        # A target with its own S/N goal (target_sn column, --set-sn) is
        # sized by the UCO Kast ETC even on an empirical plan: the empirical
        # rule has no S/N, so it could not honour the request (2026-11-10).
        own_sn = has_own_sn(row)
        row_empirical = empirical and not own_sn
        row_spec = 'kast' if (empirical and own_sn) else spec
        sn_goal = None if row_empirical else row_target_sn(row, plan_sn)
        airmass, used_rule = 1.0, ''
        if not row_empirical:
            ra = row['RA_hours'] * 15.0
            if row['TNS'] not in best:
                best[row['TNS']] = (block_airmass(ra, row['Dec_deg'], row['entry_pst'],
                                                  row['exit_pst'], 'best', LICK)
                                    if pd.notna(row.get('entry_pst')) else None)
            airmass, used_rule = best[row['TNS']] or 1.2, 'best'
            if start is not None and minutes:
                am = block_airmass(ra, row['Dec_deg'], start,
                                   advance(start, minutes), rule, LICK)
                if am is not None:
                    airmass, used_rule = am, rule
        band = row.get('mag_band')
        band = '' if band is None or (not isinstance(band, str) and pd.isna(band)) \
            else str(band).strip()
        if band not in ETC_FILTERS:
            band = opts.get('mag_band') or 'r'
        e = etc_mod.exposure(row_spec, row['mag_r'], band, airmass,
                             opts.get('seeing') or DEFAULT_SEEING['kast'],
                             opts.get('config') or DEFAULT_CONFIG['kast'],
                             sn_goal or plan_sn,
                             opts.get('n_sub_min') or etc_mod.N_SUB_MIN['kast'])
        if spectra is not None and e.get('wave'):
            spectra[row['TNS']] = {'wave': e['wave'], 's2n': e['s2n'],
                                   'airmass': airmass, 'sub_len_s': e['sub_len_s'],
                                   'n_sub': e['n_sub'], 'band': band,
                                   'target_sn': sn_goal}
        sn, comb = e.get('sn_sub') or {}, e.get('sn_combined') or {}
        out = {'red': e['red_exp'], 'blue': e['blue_exp'],
               'dur_s': e['science_min'] * 60.0,
               'airmass_used': None if row_empirical else airmass,
               'airmass_rule': used_rule,
               'sn_sub_blue': sn.get('blue'), 'sn_sub_red': sn.get('red'),
               'sn_comb_blue': comb.get('blue'), 'sn_comb_red': comb.get('red'),
               'time_source': 'empirical' if row_empirical else 'ETC',
               'sn_goal': sn_goal, 'sn_goal_own': own_sn,
               'etc_min': e['science_min'],
               'required': bool(row.get('required', False))}
        # A user t_target sets the time (T3.3); the estimate stays as etc_min.
        user_t = row.get('t_target')
        if user_t is not None and pd.notna(user_t):
            out.update(red=f'{float(user_t):g} min (user)',
                       blue=f'{float(user_t):g} min (user)',
                       dur_s=float(user_t) * 60.0, time_source='user',
                       airmass_used=None, airmass_rule='', sn_goal=None)
        return out

    return exposure


_EMPIRICAL = make_kast_exposure()
# schedule_greedy is general (observable frame + explicit start/end, with
# blocked-window support); it just happens to live in the night-2 module.
from scripts.lick_2026b02_night2_calculations import schedule_greedy
# _overlapping_block is the one place that knows how a slot and a block
# collide; a forced slot has to truncate on the same rule the scheduler
# fits around, so it is borrowed rather than reimplemented here.
from schedule_overrides import (advance, _overlapping_block, fit_around_blocks,
                                push_past_blocks)
from night_planner.targets_io import load_targets
from night_plan_io import (
    OBSERVATORY_TZ, load_config, resolve_blocks, resolve_local_dt,
    save_night_meta,
)
from night_planner.estimate_kast_exposures import estimate_exposure

# Opening overheads, matching the Lick Excel builders.
FOCUS_MINUTES = 10
STD_STAR_MINUTES = 10

# Shortest partial exposure worth pointing the telescope at. A target the
# scheduler dropped for want of time is put in anyway for whatever is left,
# but a two-minute slot buys nothing and costs a slew either side.
MIN_PARTIAL_MINUTES = 10


def _clip_to_airmass(ra_deg, dec_deg, entry, exit_, airmass_max):
    """
    Shrink an HA window to the part where the airmass is below a ceiling.

    Created by JXP and Claude

    Inside the Shane HA limits a target crosses the meridian at most once,
    so the minutes below any airmass ceiling form one interval.

    Inputs: ra_deg, dec_deg (float), entry, exit_ (datetimes), airmass_max.
    Outputs: (entry, exit) datetimes, or None if never below the ceiling.
    """
    from night_planner.retime import airmass_on_grid, time_grid
    times = time_grid(entry, exit_, 1.0)
    am = airmass_on_grid(ra_deg, dec_deg, times, LICK)
    ok = np.where(am <= airmass_max)[0]
    if not len(ok):
        return None
    return times[ok[0]], min(times[ok[-1]], exit_)


def analyze_targets(targets_csv, date_str, mapping=None, time_overrides=None,
                    sn_overrides=None, limits=None):
    """
    Per-target HA window for a Lick night.

    Unlike lick_2026b02_calculations.analyze_targets, a target above the
    Dec limit is kept with a reason rather than dropped: the viewer's
    rejection page should be able to say *why* something is absent, and
    "silently filtered out" is the one answer that helps nobody.

    Parameters
    ----------
    targets_csv : str or DataFrame
        Any table; columns normalized by night_planner.targets_io.
    date_str : str
    mapping : targets_io.ColumnMapping, optional

    Returns
    -------
    (results_df, twilight)

    time_overrides : list of "NAME@MINUTES", optional (--set-time): sets
        those targets' t_target as if the table had said so.
    sn_overrides : list of "NAME@SN", optional (--set-sn): sets those
        targets' target_sn (S/N per sub-exposure) the same way.
    limits : dict, optional
        From night_planner.site_limits.load_site_limits('lick', ...);
        None = the file's values. An airmass_max (none by default at Lick)
        shrinks each window to the minutes below it.
    """
    from night_planner.site_limits import load_site_limits
    from night_planner.targets_io import apply_sn_overrides, apply_time_overrides
    limits = limits or load_site_limits('lick')
    dec_max = limits['dec_max'] if limits['dec_max'] is not None else float('inf')
    dec_min = limits['dec_min']
    df = load_targets(targets_csv, mapping=mapping)
    try:
        df = apply_time_overrides(df, time_overrides)
        df = apply_sn_overrides(df, sn_overrides)
    except ValueError as err:
        raise SystemExit(f'error: {err}')
    twilight = find_twilight(date_str)

    rows = []
    for _, row in df.iterrows():
        ra_hours = row['ra_deg'] / 15.0
        dec_deg = row['dec_deg']
        rec = {
            'TNS': row['name'], 'RA_deg': row['ra_deg'], 'Dec_deg': dec_deg,
            'RA_hours': ra_hours, 'mag_r': row['mag'], 'POx': row['pox'],
            'tags': row['tags'], 'DM': row['dm'],
            'priority': row['priority'], 'mag_band': row.get('mag_band', ''),
            't_target': row.get('t_target', float('nan')),
            'target_sn': row.get('target_sn', float('nan')),
            'required': bool(row.get('required', False)),
            'schedule_before': row.get('schedule_before', ''),
        }

        if dec_deg > dec_max:
            rec.update(observable=False, entry_pst=None, exit_pst=None,
                       ha_entry=None, ha_exit=None, window_min=0,
                       limit_reason=(f'Dec {dec_deg:+.2f} > +{dec_max:.0f}: '
                                      f'above the Shane mechanical limit'))
            rows.append(rec)
            continue
        if dec_min is not None and dec_deg < dec_min:
            rec.update(observable=False, entry_pst=None, exit_pst=None,
                       ha_entry=None, ha_exit=None, window_min=0,
                       limit_reason=(f'Dec {dec_deg:+.2f} < {dec_min:+.0f}: '
                                      f'below the southern Dec limit'))
            rows.append(rec)
            continue

        window = target_window(ra_hours, dec_deg, twilight,
                               ha_min=limits['ha_east'], ha_max=limits['ha_west'],
                               dec_max=dec_max)
        if window is not None and limits['airmass_max'] is not None:
            clipped = _clip_to_airmass(row['ra_deg'], dec_deg, window[0],
                                       window[1], limits['airmass_max'])
            if clipped is None:
                rec.update(observable=False, entry_pst=None, exit_pst=None,
                           ha_entry=None, ha_exit=None, window_min=0,
                           limit_reason=(f"never below airmass "
                                         f"{limits['airmass_max']:g} inside the "
                                         f"Shane HA window tonight"))
                rows.append(rec)
                continue
            window = (clipped[0], clipped[1],
                      ha_at(ra_hours, _lst_hours(clipped[0])),
                      ha_at(ra_hours, _lst_hours(clipped[1])))
        if window is None:
            rec.update(observable=False, entry_pst=None, exit_pst=None,
                       ha_entry=None, ha_exit=None, window_min=0,
                       limit_reason=(f"never inside the Shane HA window "
                                      f"({limits['ha_east']:+.2f}h to "
                                      f"{limits['ha_west']:+.2f}h) "
                                      f'during the night'))
        else:
            entry, exit_, ha_entry, ha_exit = window
            rec.update(observable=True, entry_pst=entry, exit_pst=exit_,
                       ha_entry=ha_entry, ha_exit=ha_exit, limit_reason='',
                       window_min=(exit_ - entry).total_seconds() / 60.0)
        rows.append(rec)

    results_df = pd.DataFrame(rows).sort_values('RA_hours').reset_index(drop=True)
    return results_df, twilight


def reserve_forced(results_df, forced, science_start, night_end, blocks,
                    failures=None, exposure=None):
    """
    Place forced targets inside their own windows, ahead of the greedy pass.

    Appending a forced target after the normal schedule only ever works
    for something still up at the end of the night. The targets actually
    worth rescuing are the opposite case: a fast-setting host the
    scheduler dropped because its *full* exposure would not fit the
    sliver of HA window it had left. By the time the normal schedule
    finishes, that window shut hours ago, so an append-only rescue can
    only fail.

    Each forced target is therefore placed at the earliest clock time the
    mount can legally point there, truncated to whatever its window and
    the night allow, and the slot -- plus a slew either side -- is handed
    back as a blocked window so schedule_greedy fills the rest of the
    night around it instead of over it.

    Parameters
    ----------
    results_df : DataFrame
        Output of analyze_targets().
    forced : list of (TNS, minutes)
    science_start, night_end : datetime
    blocks : list of (start, end, reason)
        Blocks already in force (ToO, weather); forced slots dodge these.
    failures : list, optional
        Appended with {'TNS', 'reason'} for every target not placed, so
        the viewer can say why rather than silently dropping the request.

    Returns
    -------
    (rows, reservations)
        Schedule rows to concatenate, and (start, end, reason) tuples to
        add to the block list before scheduling the rest.
    """
    rows, reservations = [], []
    res = results_df.set_index('TNS')
    slew = timedelta(minutes=SLEW_MINUTES)

    def fail(tns, reason):
        if failures is not None:
            failures.append({'TNS': tns, 'reason': reason})
        print(f'  Forced {tns}: {reason}')

    for tns, minutes in forced:
        if tns not in res.index:
            fail(tns, 'not in the target table')
            continue
        row = res.loc[tns]
        if not row['observable'] or row['exit_pst'] is None:
            fail(tns, f"not observable tonight -- {row['limit_reason']}")
            continue

        taken = list(blocks) + reservations
        close = min(row['exit_pst'], night_end)
        earliest = push_past_blocks(max(science_start, row['entry_pst']), taken)
        if earliest >= close:
            fail(tns, f"window closes {close:%H:%M}, and the earliest clear "
                      f"slot is {earliest:%H:%M}")
            continue

        # As late inside its own window as the requested time allows. A
        # setting target lands at the top of the night because that is all
        # it has; a rising one lands at the end, where it was going to be
        # observed anyway -- either way the reservation eats the least of
        # everyone else's time.
        start = max(earliest, advance(close, -minutes))
        start = push_past_blocks(start, taken)
        end = min(advance(start, minutes), close)
        # Truncate at the next block rather than refusing the target: a
        # partial spectrum is the whole point of forcing it in.
        hit = _overlapping_block(start, end, taken)
        if hit is not None:
            end = hit[0]
        got = (end - start).total_seconds() / 60.0
        if got < 1:
            fail(tns, f"no usable time at {start:%H:%M} before the next "
                      f"block or its {close:%H:%M} window close")
            continue

        red_blue = (exposure or _EMPIRICAL)(row, start, got)
        red, blue = red_blue['red'], red_blue['blue']
        rows.append(dict(row, TNS=tns, scheduled=True, start_pst=start,
                         end_pst=end, duration_min=got, red_side=red,
                         blue_side=blue,
                         skip_reason=(f'FORCED truncated exposure: {got:.0f} of '
                                       f'{minutes:g} min requested')))
        reservations.append((start - slew, end + slew, f'forced {tns}'))
        print(f'  Forced {tns}: {start:%H:%M}-{end:%H:%M} ({got:.0f} min)')
    return rows, reservations


def parse_args(argv=None):
    """CLI mirroring the Keck module, so the dispatcher can drive either."""
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', help='Night-plan JSON config; CLI flags win.')
    p.add_argument('--start', help='Manual night-start override, HH:MM real '
                                   'local Lick time (PST or PDT by date).')
    p.add_argument('--block', action='append', default=[],
                   help='Blocked window, "HH:MM-HH:MM[@reason]", local time; '
                        'write "HH:MM UT" for UT. Repeatable.')
    p.add_argument('--force', action='append', default=[],
                   help='Force a target in with a truncated exposure, '
                        '"TNS@MINUTES". Repeatable.')
    p.add_argument('--set-time', action='append', default=[],
                   help='Set a target\'s time on target, "TNS@MINUTES", as if '
                        'the table\'s t_target said so; it is then scheduled '
                        'normally. Repeatable.')
    p.add_argument('--set-sn', action='append', default=[],
                   help='Set a target\'s S/N per sub-exposure, "TNS@SN", as if '
                        'the table\'s target_sn said so. The target is then '
                        'sized by the Kast ETC, even under --etc empirical. '
                        'Repeatable.')
    p.add_argument('--targets-csv')
    p.add_argument('--output-dir')
    p.add_argument('--date')
    p.add_argument('--max-targets', type=int)
    p.add_argument('--no-partials', action='store_true',
                   help='Do not backfill idle time with truncated exposures '
                        'of targets that were dropped for want of time.')
    p.add_argument('--min-partial', type=float, default=MIN_PARTIAL_MINUTES,
                   help=f'Shortest partial exposure worth scheduling, in '
                        f'minutes (default {MIN_PARTIAL_MINUTES}).')
    p.add_argument('--placement', choices=PLACEMENTS, default=None,
                   help='How a target\'s start is chosen once the greedy pass '
                        'has picked the targets: "airmass" moves them to the '
                        'lowest summed airmass and inserts dropped targets '
                        'where that makes room; "earliest" starts each as '
                        f'early as possible (the old rule) [{DEFAULT_PLACEMENT}].')
    p.add_argument('--previous-plan',
                   help='A plan directory (or plan_result.json) whose start '
                        'times this run should keep unless moving a target '
                        'clearly lowers its airmass.')
    p.add_argument('--limit', action='append', default=[],
                   help='Override a Lick pointing limit for this run, '
                        '"KEY=VALUE" (keys ha_east, ha_west, dec_max, dec_min, '
                        'airmass_max; VALUE "none" removes it). Defaults: '
                        'night_planner/data/site_limits.json. Repeatable.')
    add_config_args(p, 'kast')
    return p.parse_args(argv)


def _parse_block_flag(spec):
    window, _, reason = spec.partition('@')
    start, end = window.split('-')
    return {'start': start, 'end': end, 'reason': reason or 'blocked'}


def free_gaps(placements, window_start, window_end, slew_min=SLEW_MINUTES):
    """
    Idle intervals left over between a set of placements.

    Created by JXP and Claude

    Written here rather than reused because nothing existing fits: the
    well-formed one, PlanResult.idle_gaps(), needs an assembled PlanResult
    and so runs a layer after the scheduler, while free_intervals() in
    lick_2026b02_extras.py is bound to one run's CSV paths and date. This
    is the same sweep as the inline one in lick_2026b02_night2_calculations,
    kept as a function so the tier loop and its tests can both call it.

    Each gap is shrunk by a slew at both ends, because the mount has to get
    there and then get back to whatever was already booked.

    Inputs
    ------
    placements : iterable of mapping
        Rows with 'start_pst' and 'end_pst'; anything else is ignored.
    window_start, window_end : datetime
        Bounds of the night being filled.
    slew_min : float
        Minutes reserved either side of every existing placement.

    Outputs
    -------
    list of (start, end) datetime pairs, in time order, each strictly
    positive in length. Includes the leading and trailing edges -- time
    before the first target and after the last is just as fillable as a
    hole in the middle.
    """
    busy = sorted((p['start_pst'], p['end_pst']) for p in placements)

    gaps, cursor = [], window_start
    for start, end in busy:
        gap_end = advance(start, -slew_min)
        if gap_end > cursor:
            gaps.append((cursor, gap_end))
        # max(): placements can abut or overlap (a forced reservation sits
        # across one), and a cursor that walked backwards would invent a gap.
        cursor = max(cursor, advance(end, slew_min))
    if window_end > cursor:
        gaps.append((cursor, window_end))
    return gaps


def backfill_partials(schedule_rows, science_start, night_end, blocks,
                      min_minutes=MIN_PARTIAL_MINUTES, exposure=None,
                      before=None):
    """
    Put dropped targets into the leftover gaps, truncated to fit.

    Created by JXP and Claude

    The scheduler is all-or-nothing: a target needing 90 minutes with 60
    left in its window is dropped, and those 60 minutes are then spent on
    nothing at all. A short spectrum is usually worth more than an empty
    telescope -- it can still classify, and it is data where otherwise
    there was none -- so anything dropped for want of time is placed anyway
    for however long is actually available.

    These are marked, not hidden. Every row this adds carries a skip_reason
    beginning 'PARTIAL', which the viewer turns into its own colour and a
    note saying how much of the needed exposure it got, so the observer can
    drop it at the telescope if they would rather have the idle time.

    Targets that were never observable are untouched -- no amount of
    truncation fixes a target below the horizon.

    Inputs
    ------
    schedule_rows : DataFrame
        The schedule so far, scheduled and rejected rows together.
    science_start, night_end : datetime
        Bounds of the schedulable night.
    blocks : list of (start, end, reason)
        Blocked windows, which partials must dodge like anything else.
    min_minutes : float
        Shortest partial worth placing.
    before : dict, optional
        schedule_before constraints (precedence_map); a partial is only
        placed where it keeps them.

    Outputs
    -------
    DataFrame with the same rows, except that any target this pass could
    place is replaced by its scheduled, truncated row.
    """
    # On a night where nothing is up, schedule_greedy returns a frame with no
    # columns at all -- see the schema guarantee in run(). Nothing to backfill
    # into, and asking for 'scheduled' would raise.
    if not len(schedule_rows) or 'scheduled' not in schedule_rows.columns:
        return schedule_rows

    scheduled_mask = schedule_rows['scheduled'].fillna(False).astype(bool)
    placed = schedule_rows[scheduled_mask].to_dict('records')
    dropped = schedule_rows[~scheduled_mask]
    if not len(dropped):
        return schedule_rows

    # Only targets that have a real window tonight and simply ran out of
    # room in it. A missing entry/exit means it was never up.
    # A required target gets its full time or nothing (T3.3): never a
    # partial. Its rejection says so.
    required = {r['TNS'] for _, r in dropped.iterrows() if r.get('required')}
    candidates = [r for _, r in dropped.iterrows()
                  if r.get('observable') and pd.notna(r.get('entry_pst'))
                  and pd.notna(r.get('exit_pst')) and r['TNS'] not in required]
    if required:
        records = schedule_rows.to_dict('records')
        for rec in records:
            if rec['TNS'] in required and not rec.get('scheduled'):
                need = (exposure or _EMPIRICAL)(rec)['dur_s'] / 60.0
                rec['skip_reason'] = (f'required: needs {need:.0f} min, no gap '
                                      f'that long -- not truncated into a '
                                      f'partial ({rec.get("skip_reason") or "dropped"})')
        schedule_rows = pd.DataFrame(records)
    if not candidates:
        return schedule_rows

    # Best targets first: a partial of a P1 host beats a partial of a P3
    # filler when both want the same gap.
    candidates.sort(key=lambda r: (r.get('priority', 1.0), r['exit_pst']))

    filled = {}
    for row in candidates:
        for gap_start, gap_end in free_gaps(placed, science_start, night_end):
            # The usable slice is the overlap of the gap with the target's
            # own HA window -- truncating does not excuse pointing the
            # mount somewhere it cannot go.
            start = max(gap_start, row['entry_pst'])
            close = min(gap_end, row['exit_pst'])
            if (close - start).total_seconds() / 60.0 < min_minutes:
                continue
            start, end = fit_around_blocks(
                start, (close - start).total_seconds() / 60.0, close, blocks)
            if start is None:
                continue

            got = (end - start).total_seconds() / 60.0
            if got < min_minutes:
                continue
            if before and not precedence_clear(row['TNS'], start, end,
                                               placed, before):
                continue

            e = (exposure or _EMPIRICAL)(row, start, got)
            red, blue, dur_s = e['red'], e['blue'], e['dur_s']
            needed = dur_s / 60.0
            new_row = dict(
                row, scheduled=True, start_pst=start, end_pst=end,
                duration_min=got, red_side=red, blue_side=blue,
                skip_reason=(
                    f'PARTIAL: {got:.0f} of the {needed:.0f} min this target '
                    f'needs ({got / needed * 100:.0f}%). Scheduled into idle '
                    f'time rather than left out -- expect low S/N, and drop '
                    f'it if you would rather have the gap.'))
            filled[row['TNS']] = new_row
            placed.append(new_row)
            break

    if not filled:
        return schedule_rows

    total = sum(r['duration_min'] for r in filled.values())
    print(f'\nBackfilled {len(filled)} partial exposure(s) into idle time '
          f'({total:.0f} min): ' + ', '.join(sorted(filled)))

    # Rebuild from records throughout: mixing Series and dicts in the list
    # makes pandas try to align them and fail on the dtype.
    rows = [filled.get(r['TNS'], r) for r in schedule_rows.to_dict('records')]
    return pd.DataFrame(rows).reset_index(drop=True)


def schedule_by_priority(observable, science_start, night_end, blocks,
                         exposure=None):
    """
    Schedule in priority tiers, best first, lower tiers filling the gaps.

    Created by JXP and Claude

    The model is the UCSC AstroScheduler's priority-sequential solve (see
    docs/priority_comparison_astroscheduler.md): tiers are scheduled in
    order and everything already placed is immovable, so a lower-priority
    target can never displace a higher-priority one.

    Lower tiers are scheduled gap by gap rather than by one more pass over
    the whole night with the earlier placements passed as blocks. That is
    forced by the machinery, not a preference: fit_around_blocks() can only
    ever push a target *later* (schedule_overrides.py), and schedule_greedy
    walks a cursor that never rewinds -- so a single later pass would sail
    past every gap it had already crossed. Restarting inside each gap is
    what the night-2 module does, and it works.

    With one tier this makes exactly one schedule_greedy call over the whole
    night, which is the call this function replaced -- an un-prioritised
    table therefore schedules precisely as it did before tiers existed.

    Inputs
    ------
    observable : DataFrame
        Observable targets from analyze_targets(), carrying 'priority'.
    science_start, night_end : datetime
        Bounds of the schedulable night.
    blocks : list of (start, end, reason)
        Blocked windows, honoured by every tier.

    Outputs
    -------
    DataFrame of schedule rows, one per target: the scheduled rows from
    every tier, plus one rejected row for each target no tier could place.
    """
    tiers = sorted(observable['priority'].dropna().unique())
    if len(tiers) <= 1:
        # The single-tier path is the old behaviour, preserved exactly.
        sched, _ = schedule_greedy(observable, science_start, night_end,
                                   blocks=blocks, slew_min=SLEW_MINUTES,
                                   readout=kast_readout, exposure=exposure)
        return sched

    print(f'\nScheduling in {len(tiers)} priority tiers: '
          + ', '.join(f'P{t:g}' for t in tiers))

    frames = []
    placed = []     # every row placed so far, across all tiers

    for position, tier in enumerate(tiers):
        pool = observable[observable['priority'] == tier]
        if not len(pool):
            continue

        if position == 0:
            sched, _ = schedule_greedy(pool, science_start, night_end,
                                       blocks=blocks, slew_min=SLEW_MINUTES,
                                   readout=kast_readout, exposure=exposure)
            frames.append(sched)
            got = sched[sched['scheduled']] if len(sched) else sched
            placed.extend(got.to_dict('records'))
            print(f'  P{tier:g}: {len(got)}/{len(pool)} scheduled '
                  f'(first pass, whole night)')
            continue

        # Lower tiers: one pass per idle interval the tiers above left.
        gaps = free_gaps(placed, science_start, night_end)
        remaining = pool
        for gap_start, gap_end in gaps:
            if not len(remaining):
                break
            sched, _ = schedule_greedy(remaining, gap_start, gap_end,
                                       blocks=blocks, slew_min=SLEW_MINUTES,
                                   readout=kast_readout, exposure=exposure)
            got = sched[sched['scheduled']] if len(sched) else sched
            if not len(got):
                continue
            frames.append(got)
            placed.extend(got.to_dict('records'))
            remaining = remaining[~remaining['TNS'].isin(got['TNS'])]

        # One rejection per target, not one per gap it failed in: a target
        # that missed four gaps is still a single target the observer has
        # to decide about, and four identical rows only bury that.
        for _, row in remaining.iterrows():
            dur_s = (exposure or _EMPIRICAL)(row)['dur_s']
            frames.append(pd.DataFrame([dict(
                row, scheduled=False,
                skip_reason=(f'priority P{tier:g}: needs '
                             f'{dur_s / 60.0:.0f} min, and no idle interval '
                             f'left by the {position} higher-priority '
                             f'tier(s) was long enough inside its HA window'))]))

        print(f'  P{tier:g}: {len(pool) - len(remaining)}/{len(pool)} '
              f'scheduled into {len(gaps)} gap(s)')

    return pd.concat(frames, ignore_index=True)


def precedence_map(frame):
    """
    The schedule_before constraints of a target frame.

    Created by JXP and Claude

    Inputs: frame with 'TNS' and (optionally) 'schedule_before' columns.
    Outputs: dict name -> set of names it must finish before. Names not in
    the frame are dropped (a constraint on an absent target is vacuous, as
    in AstroScheduler).
    """
    from night_planner.targets_io import parse_name_list
    if 'schedule_before' not in frame.columns:
        return {}
    names = set(frame['TNS'])
    out = {}
    for _, r in frame.iterrows():
        later = {n for n in parse_name_list(r.get('schedule_before'))
                 if n in names and n != r['TNS']}
        if later:
            out[r['TNS']] = later
    return out


def precedence_clear(name, start, end, placed, before):
    """
    Would [start, end) for `name` respect precedence against placed rows?

    Inputs: name (str), start/end (datetime), placed (list of row dicts
    with TNS/start_pst/end_pst), before (dict from precedence_map).
    Outputs: bool.
    """
    for p in placed:
        other = p['TNS']
        if other in before.get(name, ()) and not end <= p['start_pst']:
            return False
        if name in before.get(other, ()) and not p['end_pst'] <= start:
            return False
    return True


def load_previous_starts(path):
    """
    Science start of every target in an earlier plan.

    Created by JXP and Claude

    Inputs: path to a plan directory or its plan_result.json.
    Outputs: dict name -> tz-aware datetime ({} if the plan has none).

    Raises SystemExit if the path holds no plan.
    """
    import json
    from datetime import datetime
    p = Path(path)
    if p.is_dir():
        p = p / 'plan_result.json'
    if not p.exists():
        raise SystemExit(f'--previous-plan: no plan_result.json at {p}')
    with open(p) as f:
        plan = json.load(f)
    out = {}
    for t in plan.get('schedule') or []:
        when = t.get('science_start') or t.get('start')
        if t.get('name') and when:
            out[t['name']] = datetime.fromisoformat(when)
    return out


def partial_note(got, needed):
    """
    The skip_reason every partial row carries (the viewer keys on 'PARTIAL').

    Inputs: got, needed (minutes). Outputs: str.
    """
    return (f'PARTIAL: {got:.0f} of the {needed:.0f} min this target '
            f'needs ({got / needed * 100:.0f}%). Scheduled into idle '
            f'time rather than left out -- expect low S/N, and drop '
            f'it if you would rather have the gap.')


def retime_schedule(sched, science_start, night_end, blocks, exposure=None,
                    placement=DEFAULT_PLACEMENT, previous=None,
                    airmass_rule='worst', insert=True, partial_min=None):
    """
    Re-time the placed targets, insert dropped ones, enforce precedence.

    Created by JXP and Claude

    The greedy tier pass decides which targets fit, starting each as early
    as it can. This keeps that set (no placed target is ever dropped, except
    to satisfy a schedule_before constraint that cannot otherwise hold) and
    then:

    1. orders the placed targets by start, moved only as far as precedence
       requires;
    2. with placement='airmass', picks the start times with the lowest
       summed block airmass (night_planner.retime.solve_order), plus a
       charge for moving away from a previous plan's start; with
       'earliest', the earliest feasible starts (used only to enforce
       precedence -- otherwise the schedule is returned unchanged);
    3. with placement='airmass' and insert=True, offers every dropped target,
       best priority first, the cheapest position where all placed targets
       still fit (night_planner.retime.insert_target);
    4. with partial_min set, offers each target still dropped (not
       required) the longest partial of at least partial_min minutes that
       fits when the placed targets shift. The goals are thus ranked: full
       targets, then partial minutes, then airmass -- re-timing never
       costs a partial that the earliest placement would have allowed
       purely to gain airmass;
    5. re-sizes ETC exposures at the new placements (up to 3 rounds),
       keeping the last placement that fits.

    Inputs
    ------
    sched : DataFrame from schedule_by_priority (scheduled and rejected rows)
    science_start, night_end : datetime
    blocks : list of (start, end, reason); forced reservations included
    exposure : callable as in make_kast_exposure, or None (empirical)
    placement : 'airmass' or 'earliest'
    previous : dict name -> datetime, optional (load_previous_starts)
    airmass_rule : 'worst', 'mid' or 'best'; how a block's airmass is taken
    insert : bool
    partial_min : float or None
        Shortest partial worth inserting; None = no partial insertion
        (backfill_partials still fills idle gaps afterwards).

    Outputs
    -------
    DataFrame with the same rows. Moved rows get new start_pst/end_pst;
    every scheduled row gets 'airmass_block' (block airmass under the rule);
    inserted rows get a 'placement_note'; rows dropped for precedence get
    scheduled=False and a skip_reason.
    """
    from night_planner import retime as rt

    if placement not in PLACEMENTS:
        raise ValueError(f'placement must be one of {PLACEMENTS}')
    if not len(sched) or 'scheduled' not in sched.columns:
        return sched
    rows = sched.to_dict('records')
    before = precedence_map(sched)
    is_sched = [bool(r.get('scheduled')) and not pd.isna(r.get('start_pst'))
                for r in rows]
    if placement == 'earliest' and not before:
        return _annotate_airmass(sched, airmass_rule)

    times = rt.time_grid(science_start, night_end)
    n = len(times)
    step = rt.STEP_MIN
    t_index = np.arange(n) * step               # minutes after science_start
    am_cache = {}

    def airmass_of(row):
        key = row['TNS']
        if key not in am_cache:
            am_cache[key] = rt.airmass_on_grid(row['RA_hours'] * 15.0,
                                               row['Dec_deg'], times, LICK)
        return am_cache[key]

    def cost_of(row, length):
        ok = rt.legal_starts(times, length, row['entry_pst'],
                             min(row['exit_pst'], night_end), blocks)
        if placement == 'earliest':
            base = t_index / 1000.0
        else:
            base = rt.block_metric(airmass_of(row), length, airmass_rule)
            prev = (previous or {}).get(row['TNS'])
            if prev is not None:
                moved = np.abs(t_index - (prev - science_start).total_seconds() / 60.0)
                base = base + rt.STABILITY_PER_MIN * moved
        return np.where(ok, base, np.inf)

    def readout_of(red, blue):
        return kast_readout(red, blue) or 0.0

    # The sequence: placed targets by greedy start, then precedence.
    seq = sorted([i for i, s in enumerate(is_sched) if s],
                 key=lambda i: rows[i]['start_pst'])
    names = [rows[i]['TNS'] for i in seq]
    ordered, cycle = rt.precedence_order(names, before)
    if cycle:
        print(f'  schedule_before has a cycle among {", ".join(cycle)}; '
              f'those constraints are ignored')
        before = {a: {b for b in v if not (a in cycle and b in cycle)}
                  for a, v in before.items()}
    by_name = {rows[i]['TNS']: i for i in seq}
    seq = [by_name[nm] for nm in ordered]

    lengths = {i: float(rows[i]['duration_min']) for i in seq}
    starts, _ = rt.solve_order([cost_of(rows[i], lengths[i]) for i in seq],
                               [lengths[i] for i in seq], SLEW_MINUTES)
    # Precedence can make the greedy set impossible: drop the latest-
    # placed successor of a constraint and try again.
    while starts is None and seq:
        pairs = [(a, b) for a in names for b in before.get(a, ()) if b in names]
        if not pairs:
            print('  re-timing found no placement for the greedy set on the '
                  f'{step:g}-min grid; keeping the greedy starts')
            return _annotate_airmass(sched, airmass_rule)
        drop = max((b for _, b in pairs), key=lambda b: rows[by_name[b]]['start_pst'])
        pred = next(a for a, b in pairs if b == drop)
        i = by_name[drop]
        rows[i].update(scheduled=False, start_pst=pd.NaT, end_pst=pd.NaT,
                       skip_reason=(f'schedule_before: must start after {pred} '
                                    f'ends, and no slot after it fits'))
        seq.remove(i)
        names.remove(drop)
        starts, _ = rt.solve_order([cost_of(rows[j], lengths[j]) for j in seq],
                                   [lengths[j] for j in seq], SLEW_MINUTES)

    inserted = set()
    if placement == 'airmass' and insert and starts is not None:
        dropped = [i for i, r in enumerate(rows)
                   if not r.get('scheduled') and r.get('observable')
                   and not pd.isna(r.get('entry_pst'))
                   and not pd.isna(r.get('exit_pst'))]
        dropped.sort(key=lambda i: (rows[i].get('priority', 1.0), rows[i]['exit_pst']))
        for i in dropped:
            row = rows[i]
            e = (exposure or _EMPIRICAL)(row)
            length = e['dur_s'] / 60.0 + readout_of(e['red'], e['blue'])
            pos, new_starts, _ = rt.insert_target(
                [cost_of(rows[j], lengths[j]) for j in seq],
                [lengths[j] for j in seq], [rows[j]['TNS'] for j in seq],
                cost_of(row, length), length, row['TNS'], SLEW_MINUTES, before)
            if pos is None:
                continue
            extra = {k: v for k, v in e.items() if k not in ('red', 'blue', 'dur_s')}
            row.update(scheduled=True, duration_min=length, red_side=e['red'],
                       blue_side=e['blue'], readout_min=readout_of(e['red'], e['blue']),
                       skip_reason='', **extra)
            seq.insert(pos, i)
            lengths[i] = length
            starts = new_starts
            inserted.add(i)
            print(f"  Inserted {row['TNS']} (P{row.get('priority', 1.0):g}) by "
                  f"re-timing the placed targets")

        # Partials that need the placed targets to shift. Feasibility is
        # monotone in length, so bisect for the longest one.
        partial_rows = set()
        for i in dropped if partial_min else []:
            row = rows[i]
            if row.get('scheduled') or row.get('required'):
                continue
            need = (exposure or _EMPIRICAL)(row)['dur_s'] / 60.0
            window = (min(row['exit_pst'], night_end)
                      - max(row['entry_pst'], science_start)).total_seconds() / 60.0
            lo, hi, best = float(partial_min), min(need, window), None
            others = ([cost_of(rows[j], lengths[j]) for j in seq],
                      [lengths[j] for j in seq], [rows[j]['TNS'] for j in seq])

            def attempt(length):
                return rt.insert_target(*others, cost_of(row, length), length,
                                        row['TNS'], SLEW_MINUTES, before)

            if hi < lo:
                continue
            trial = attempt(hi)
            if trial[0] is not None:
                best = (hi, trial)
            else:
                trial = attempt(lo)
                if trial[0] is None:
                    continue
                best = (lo, trial)
                while hi - lo > 1.0:
                    mid = (lo + hi) / 2.0
                    trial = attempt(mid)
                    if trial[0] is not None:
                        lo, best = mid, (mid, trial)
                    else:
                        hi = mid
            got, (pos, new_starts, _) = best
            got = math.floor(got / rt.STEP_MIN) * rt.STEP_MIN
            pos, new_starts, _ = attempt(got)
            if pos is None:
                continue
            seq.insert(pos, i)
            lengths[i] = got
            starts = new_starts
            partial_rows.add(i)
            row.update(scheduled=True, duration_min=got, readout_min=0.0,
                       skip_reason=partial_note(got, need))
            print(f"  Partial {row['TNS']}: {got:.0f} of {need:.0f} min, by "
                  f"re-timing the placed targets")
    else:
        partial_rows = set()

    # Re-size ETC exposures at the new placements; keep the last fit.
    # Partials are allocations: their length stays, only the recipe follows.
    for _ in range(3 if exposure is not None else 0):
        new = {}
        for i, s in zip(seq, starts):
            r = rows[i]
            if i in partial_rows:
                new[i] = (None, lengths[i])
                continue
            sci = lengths[i] - float(r.get('readout_min') or 0.0)
            e = exposure(r, times[s], sci)
            new[i] = (e, e['dur_s'] / 60.0 + readout_of(e['red'], e['blue']))
        if all(abs(new[i][1] - lengths[i]) <= 0.5 for i in seq):
            break
        trial = {i: new[i][1] for i in seq}
        s2, _ = rt.solve_order([cost_of(rows[i], trial[i]) for i in seq],
                               [trial[i] for i in seq], SLEW_MINUTES)
        if s2 is None:
            break
        for i in seq:
            e, length = new[i]
            if e is None:
                continue
            extra = {k: v for k, v in e.items() if k not in ('red', 'blue', 'dur_s')}
            rows[i].update(red_side=e['red'], blue_side=e['blue'], duration_min=length,
                           readout_min=readout_of(e['red'], e['blue']), **extra)
            lengths[i] = length
        starts = s2

    for i, s in zip(seq, starts or []):
        r = rows[i]
        r['start_pst'] = times[s]
        r['end_pst'] = advance(times[s], lengths[i])
        r['duration_min'] = lengths[i]
        if i in partial_rows:
            # The recipe for the time actually given, as backfill_partials does.
            e = (exposure or _EMPIRICAL)(r, times[s], lengths[i])
            extra = {k: v for k, v in e.items() if k not in ('red', 'blue', 'dur_s')}
            r.update(red_side=e['red'], blue_side=e['blue'], **extra)
            r['placement_note'] = ('partial inserted by re-timing the placed '
                                   'targets')
        if i in inserted:
            r['placement_note'] = ('inserted after the greedy pass: it fits once '
                                   'the placed targets are re-timed')
    out = pd.DataFrame(rows)
    if 'placement_note' not in out.columns:
        out['placement_note'] = ''
    out['placement_note'] = out['placement_note'].fillna('')
    return _annotate_airmass(out, airmass_rule)


def _annotate_airmass(sched, rule='worst'):
    """
    Add 'airmass_block': each scheduled row's airmass over its block.

    Inputs: schedule DataFrame; rule ('worst', 'mid', 'best').
    Outputs: the DataFrame with the column added (NaN for unscheduled rows).
    """
    from night_planner.sky import block_airmass
    vals = []
    for _, r in sched.iterrows():
        if r.get('scheduled') and not pd.isna(r.get('start_pst')):
            vals.append(block_airmass(r['RA_hours'] * 15.0, r['Dec_deg'],
                                      r['start_pst'], r['end_pst'], rule, LICK))
        else:
            vals.append(np.nan)
    sched = sched.copy()
    sched['airmass_block'] = vals
    return sched


def run(args):
    """Execute the pipeline for an already-parsed args namespace."""
    cfg = load_config(args.config) if args.config else None

    targets_csv = args.targets_csv or (cfg.targets_csv if cfg else None)
    output_dir = args.output_dir or (cfg.output_dir if cfg else None)
    date = args.date or (cfg.date if cfg else None)
    if not (targets_csv and output_dir and date):
        raise SystemExit('kast needs --targets-csv, --output-dir and --date')
    try:
        etc_opts = resolve_options(args, cfg, 'kast')
    except ConfigError as err:
        raise SystemExit(f'error: {err}')

    tz = OBSERVATORY_TZ['lick']
    start_spec = args.start or (cfg.start_override if cfg else None)
    block_specs = list(cfg.blocks) if cfg else []
    block_specs += [_parse_block_flag(b) for b in args.block]
    blocks = resolve_blocks(date, block_specs, tz)
    start_override = resolve_local_dt(date, start_spec, tz) if start_spec else None

    forced = []
    for spec in args.force:
        tns, _, minutes = spec.partition('@')
        forced.append((tns, float(minutes)))

    from night_planner.site_limits import (describe_limits, load_site_limits,
                                           parse_limit_overrides)
    try:
        limits = load_site_limits('lick', parse_limit_overrides(
            getattr(args, 'limit', None) or []))
    except (KeyError, ValueError) as err:
        raise SystemExit(f'error: {err}')
    placement = getattr(args, 'placement', None) or DEFAULT_PLACEMENT
    previous = (load_previous_starts(args.previous_plan)
                if getattr(args, 'previous_plan', None) else None)

    os.makedirs(output_dir, exist_ok=True)

    results_df, twilight = analyze_targets(
        targets_csv, date, time_overrides=getattr(args, 'set_time', None),
        sn_overrides=getattr(args, 'set_sn', None), limits=limits)
    print(f'Pointing limits: {describe_limits(limits)}')
    print(f'Placement: {placement}'
          + (f' (keeping starts from {args.previous_plan})' if previous else ''))
    night_start = start_override or twilight['evening_pst']
    night_end = twilight['morning_pst']
    if night_start >= night_end:
        # A start past dawn is a typo, not a short night. Without this
        # the run reports a negative-length night and schedules nothing,
        # which reads as "no targets are up".
        raise SystemExit(
            f'--start {night_start:%H:%M} is at or after morning twilight '
            f'({night_end:%H:%M}); there is no night left to schedule')

    print(f"\n=== LICK/KAST {date} ===")
    print(f"Evening 18deg twilight: {twilight['evening_pst']:%H:%M} "
          f"{twilight['evening_pst'].tzname()}")
    print(f"Morning 18deg twilight: {night_end:%H:%M} {night_end.tzname()}")
    if start_override:
        print(f'Manual night start: {night_start:%H:%M}')
    for b_start, b_end, reason in blocks:
        print(f'  blocked {b_start:%H:%M}-{b_end:%H:%M} ({reason})')

    n_obs = int(results_df['observable'].sum())
    print(f'\nObservable: {n_obs} / {len(results_df)}')

    # Science starts after the dome-open focus, the evening standard, and the
    # slew + acquisition to the first target (that last term added
    # 2026-11-07: before, the first target started with no slew at all).
    science_start = advance(night_start,
                            FOCUS_MINUTES + STD_STAR_MINUTES + SLEW_MINUTES)
    # Exposures through night_planner.etc at each target's scheduled
    # airmass (T1.3, T3.4); --etc empirical restores the old rule.
    spectra = {}
    exposure = make_kast_exposure(etc_opts, spectra)
    forced_failures, forced_rows, reservations = [], [], []
    if forced:
        forced_rows, reservations = reserve_forced(
            results_df, forced, science_start, night_end, blocks,
            failures=forced_failures, exposure=exposure)

    observable = results_df[results_df['observable']]
    placed = {r['TNS'] for r in forced_rows}
    if placed:
        # Already slotted above; leaving it in would schedule it twice.
        observable = observable[~observable['TNS'].isin(placed)]

    sched = schedule_by_priority(observable, science_start, night_end,
                                  list(blocks) + reservations, exposure=exposure)
    # Re-time / insert / precedence (2026-11-15). Partials come after, so
    # they fill the gaps of the final placement.
    sched = retime_schedule(sched, science_start, night_end,
                            list(blocks) + reservations, exposure=exposure,
                            placement=placement, previous=previous,
                            airmass_rule=etc_opts.get('airmass_rule') or 'worst',
                            partial_min=(None if getattr(args, 'no_partials', False)
                                         else getattr(args, 'min_partial',
                                                      MIN_PARTIAL_MINUTES)))
    before = precedence_map(results_df)
    if not getattr(args, 'no_partials', False):
        sched = backfill_partials(sched, science_start, night_end,
                                   list(blocks) + reservations,
                                   min_minutes=getattr(args, 'min_partial',
                                                       MIN_PARTIAL_MINUTES),
                                   exposure=exposure, before=before)
    if forced_rows:
        sched = pd.concat([sched, pd.DataFrame(forced_rows)], ignore_index=True)

    # schedule_greedy builds a dict per row and only a *scheduled* row
    # gets a start time, so on a night where nothing is observable these
    # columns are absent entirely rather than empty. "Nothing is up
    # tonight" is a legitimate answer -- running a winter table on a
    # summer date, say -- and it must produce an empty plan, not a
    # KeyError. Guaranteeing the schema here fixes every consumer at
    # once, the written CSV included.
    for column in ('scheduled', 'start_pst', 'end_pst', 'duration_min',
                    'red_side', 'blue_side', 'skip_reason'):
        if column not in sched.columns:
            sched[column] = False if column == 'scheduled' else pd.NA

    if args.max_targets:
        # Trim by priority first, then by time. Trimming by start time alone
        # -- which is what this did before tiers existed -- would throw away
        # a top-priority target late in the night to keep a filler that
        # happened to start early, quietly undoing the tier loop above.
        keep = (sched[sched['scheduled']]
                .sort_values(['priority', 'start_pst'])
                .head(args.max_targets))
        sched = pd.concat([keep, sched[~sched['scheduled']]], ignore_index=True)

    done = sched[sched['scheduled'].fillna(False).astype(bool)]
    from night_planner.etc import write_spectra
    write_spectra(output_dir, list(done['TNS']) if 'TNS' in done.columns else [],
                  spectra)
    science_min = done['duration_min'].sum() if len(done) else 0
    night_min = (night_end - night_start).total_seconds() / 60
    share = 100 * science_min / night_min if night_min else 0
    print(f'Scheduled {len(done)} targets, {science_min:.0f} min science / '
          f'{night_min:.0f} min night ({share:.0f}%)')
    for _, r in done.sort_values('start_pst').iterrows():
        print(f"  {r['start_pst']:%H:%M}-{r['end_pst']:%H:%M}  {r['TNS']:14s} "
              f"mag {r['mag_r']:.2f}  red {r['red_side']} blue {r['blue_side']}")

    results_df.to_csv(f'{output_dir}/target_analysis.csv', index=False)
    sched.to_csv(f'{output_dir}/selected_targets.csv', index=False)
    save_night_meta(output_dir, start_local=night_start,
                     evening_twilight_local=twilight['evening_pst'],
                     morning_twilight_local=night_end,
                     blocks=blocks, date=date)
    print(f'\nWrote target_analysis.csv, selected_targets.csv, '
          f'night_meta.json to {output_dir}')

    return {
        'repeat_analysis': results_df,
        'spare_analysis': results_df.iloc[0:0],
        'frb_sched': sched,
        'spare_sched': sched.iloc[0:0],
        'twilight': twilight,
        'start_local': night_start,
        'night_end': night_end,
        'blocks': blocks,
        'forced_failures': forced_failures,
        'output_dir': output_dir,
        'date': date,
        'config': etc_opts['config'],
        'seeing': etc_opts['seeing'],
        'mag_band': etc_opts['mag_band'],
        'etc_opts': {k: etc_opts[k] for k in ('etc', 'target_sn', 'n_sub_min',
                                              'airmass_rule')},
        'limits': limits,
        'placement': placement,
        'previous_plan': getattr(args, 'previous_plan', None),
    }


def main():
    """Standalone entry point."""
    return run(parse_args())


if __name__ == '__main__':
    main()
