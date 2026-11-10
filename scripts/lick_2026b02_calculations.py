"""
Calculate LST, twilight, HA-observable windows, and a feasible schedule
for Lick 2026B-02 (night of 2026-09-14/15).

Created by JXP and Claude

Shane 3m pointing limits (corrected; see Lick-2026B-01's
HOWTO_night_plan_creation.md "Critical Corrections Made"):
    Dec <= +82 deg
    -05:40 <= HA <= +03:45   (HA = LST - RA, wrapped to +-12h)
    NO RA limit -- observable RA depends on LST, which shifts with date.

Unlike the original 2026B-01 pipeline (which picked a fixed observing
order first and only checked/clipped HA afterward, producing a plan that
initially violated the limits for all 6 targets -- see fix_ha_limits.py
and the HOWTO's "Mistake 4"), this script computes each target's real
HA-window (entry/exit time clipped to twilight) *before* scheduling, then
greedily schedules by earliest window-close time (a target that exits its
window soonest is scheduled first) so every scheduled block is guaranteed
to respect the HA limits by construction.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

# Real-elapsed-time arithmetic, so a DST transition inside a night
# cannot make the schedule run backwards.
from schedule_overrides import advance
from astropy import units as u
from astropy.coordinates import SkyCoord, EarthLocation, AltAz, get_sun
from astropy.time import Time

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
from night_planner.paths import plans_dir

_PLANS = plans_dir()
from night_planner.estimate_kast_exposures import estimate_exposure

# Lick Observatory coordinates (same as Lick-2026B-01 scripts)
LICK = EarthLocation(lat=37.3414 * u.deg, lon=-121.6429 * u.deg, height=1283 * u.m)

# Real DST-aware wall-clock time at Lick (America/Los_Angeles): PDT
# (UTC-7) roughly March-November, PST (UTC-8) otherwise. Lick's own
# published calendar (ucolick.org/calendar) instead labels every night
# "PST" year-round as a fixed almanac convention (see
# docs/Lick-2026B-01_HOWTO_night_plan_creation.md, "Mistake 2") --
# this script shows real wall-clock time instead, so a human observer's
# actual clock at the telescope matches what's printed here. LST/HA/
# window-length values are identical either way; only the printed
# clock-time label (and its "PST"/"PDT" abbreviation) shifts with the
# DST offset. Still named `PST` below since nothing outside this module
# imports the constant itself (only the functions using it).
PST = ZoneInfo('America/Los_Angeles')

# Shane pointing limits. East is -05:40 and west +03:45, as the Lick
# control system states them; the mount is asymmetric, which is why the
# two differ. The east limit was -5.0 here until 2026-10-14, when the
# author adopted the published -05:40 -- worth 40 minutes of extra
# window on every target that rises into the night.
HA_MIN = -(5 + 40 / 60)      # -05:40
HA_MAX = 3 + 45 / 60         # +03:45
DEC_LIMIT = 82.0

SLEW_MINUTES = 5
FOCUS_MINUTES = 5
STD_STAR_MINUTES = 5


def calculate_lst(utc_time, location=LICK):
    t = Time(utc_time)
    return t.sidereal_time('apparent', longitude=location.lon)


def find_twilight(date_str, twilight_alt=-18 * u.deg):
    """Find evening/morning 18-degree twilight for a local PST date.

    Scans the whole 24 hours from local noon in one vectorised pass. The
    previous version stepped 1 minute at a time with a 600-iteration cap,
    which could only reach 22:00 -- so every date from late May to early
    August, when 18-degree twilight falls later than that, raised
    "Could not find evening twilight" and no summer night could be
    planned at all.

    Parameters
    ----------
    date_str : str
        Local date, YYYY-MM-DD. The night runs from this evening.
    twilight_alt : Quantity
        Sun altitude defining twilight; -18 deg for astronomical.

    Returns
    -------
    dict with evening/morning in PST, UTC and LST.
    """
    local_date = datetime.strptime(date_str, '%Y-%m-%d')
    noon_pst = datetime(local_date.year, local_date.month, local_date.day,
                         12, 0, 0, tzinfo=PST)

    minutes = np.arange(0, 24 * 60 + 1)
    times = [advance(noon_pst, int(m)) for m in minutes]
    obstime = Time([t.astimezone(timezone.utc) for t in times])
    alt = get_sun(obstime).transform_to(
        AltAz(obstime=obstime, location=LICK)).alt

    dark = alt < twilight_alt
    if not dark.any():
        raise ValueError(f'The sun never reaches {twilight_alt} on {date_str} '
                         f'at Lick -- no astronomical night')

    first_dark = int(np.argmax(dark))
    after = np.where(~dark[first_dark:])[0]
    if not len(after):
        raise ValueError(f'Could not find morning twilight for {date_str}')

    evening_pst = times[first_dark]
    morning_pst = times[first_dark + int(after[0])]

    evening_utc = evening_pst.astimezone(timezone.utc)
    morning_utc = morning_pst.astimezone(timezone.utc)

    return {
        'evening_pst': evening_pst,
        'evening_utc': evening_utc,
        'evening_lst': calculate_lst(evening_utc),
        'morning_pst': morning_pst,
        'morning_utc': morning_utc,
        'morning_lst': calculate_lst(morning_utc),
    }


def ha_at(ra_hours, lst_hours):
    """HA = LST - RA, wrapped to +-12h."""
    ha = lst_hours - ra_hours
    while ha > 12:
        ha -= 24
    while ha < -12:
        ha += 24
    return ha


def lst_for_ha(ra_hours, ha_target):
    """LST (0-24h) at which a target reaches a given HA."""
    lst = ra_hours + ha_target
    while lst < 0:
        lst += 24
    while lst >= 24:
        lst -= 24
    return lst


def time_at_lst(lst_target_hours, lst_ref_hours, time_ref):
    """UTC/PST-agnostic: time (relative to time_ref) when a given LST occurs,
    stepping forward from time_ref's LST (sidereal ~ solar to within 0.3%)."""
    dlst = lst_target_hours - lst_ref_hours
    while dlst < 0:
        dlst += 24
    dt_hours = dlst * 0.9972696  # sidereal -> solar hours
    return advance(time_ref, dt_hours * 60.0)


def target_window(ra_hours, dec_deg, twilight):
    """Compute the [entry, exit] PST window during which a target satisfies
    -05:40 <= HA <= +03:45, clipped to the twilight-bounded night.

    Returns None if the target never satisfies the HA window during the
    night (e.g. Dec > 82, or the night ends before HA reaches -5h, or HA
    passes +3.75 before the night starts).
    """
    if dec_deg > DEC_LIMIT:
        return None

    eve_lst = twilight['evening_lst'].hour
    morn_lst = twilight['morning_lst'].hour

    ha_eve = ha_at(ra_hours, eve_lst)
    ha_morn = ha_at(ra_hours, morn_lst)
    # HA increases monotonically through the night (mod wraps); unwrap
    # morning HA relative to evening HA so ha_morn >= ha_eve.
    while ha_morn < ha_eve:
        ha_morn += 24

    # The HA window repeats every 24h, and a night can straddle the wrap.
    # A target already 10.5h past the meridian at dusk is the same target
    # rising back into HA -5 before dawn, and testing only the k=0 copy of
    # [HA_MIN, HA_MAX] calls that "never HA-legal" -- silently dropping
    # every late riser. The night is shorter than 24h minus the window, so
    # at most one copy can overlap; the widest is simply the safe pick.
    best = None
    for k in (-1, 0, 1):
        entry = max(ha_eve, HA_MIN + 24 * k)
        exit_ = min(ha_morn, HA_MAX + 24 * k)
        if entry < exit_ and (best is None or exit_ - entry > best[1] - best[0]):
            best = (entry, exit_, k)
    if best is None:
        return None
    ha_entry, ha_exit, wrap = best

    if ha_entry == ha_eve:
        entry_time = twilight['evening_pst']
    else:
        lst_entry = lst_for_ha(ra_hours, ha_entry)
        entry_time = time_at_lst(lst_entry, eve_lst, twilight['evening_pst'])

    if ha_exit == ha_morn:
        exit_time = twilight['morning_pst']
    else:
        lst_exit = lst_for_ha(ra_hours, ha_exit)
        exit_time = time_at_lst(lst_exit, eve_lst, twilight['evening_pst'])

    # Report HA in the conventional +-12h frame, not the unwrapped one.
    return entry_time, exit_time, ha_entry - 24 * wrap, ha_exit - 24 * wrap


def analyze_targets(targets_csv, date_str):
    df = pd.read_csv(targets_csv)
    df = df[df['Pri_Dec'] <= DEC_LIMIT].copy()

    twilight = find_twilight(date_str)

    rows = []
    for _, row in df.iterrows():
        ra_hours = row['Pri_RA'] / 15.0
        dec_deg = row['Pri_Dec']
        window = target_window(ra_hours, dec_deg, twilight)

        rec = {
            'TNS': row['TNS'],
            'RA_deg': row['Pri_RA'],
            'Dec_deg': dec_deg,
            'RA_hours': ra_hours,
            'mag_r': row['Pri_mag'],
            'POx': row['Pri_POx'],
            'tags': row['FRB_tags'],
            'DM': row['FRB_DM'],
        }
        if window is None:
            rec.update(observable=False, entry_pst=None, exit_pst=None,
                       ha_entry=None, ha_exit=None, window_min=0)
        else:
            entry_time, exit_time, ha_entry, ha_exit = window
            rec.update(observable=True, entry_pst=entry_time,
                       exit_pst=exit_time, ha_entry=ha_entry, ha_exit=ha_exit,
                       window_min=(exit_time - entry_time).total_seconds() / 60.0)
        rows.append(rec)

    results_df = pd.DataFrame(rows).sort_values('RA_hours').reset_index(drop=True)
    return results_df, twilight


def schedule_night(results_df, twilight, forced_first=None):
    """Earliest-window-close-first greedy scheduler.

    Each observable target gets its Kast exposure time (estimate_exposure,
    same calibrated heuristic as Lick-2026B-01) plus a fixed slew. Targets
    are offered in order of window close time (exit_pst) -- the target
    that leaves the HA-legal window soonest is scheduled first, same
    principle as "observe setting targets before they're lost" from the
    2026B-01 Q&A, but generalized and computed directly instead of
    patched after the fact.

    Parameters
    ----------
    forced_first : str, optional
        TNS of a target to force-schedule first, at the very start of its
        HA-legal window, regardless of whether its ideal exposure time
        fits before the window closes (exposure is truncated to the
        window instead of being skipped). Used for TGT0604 on
        2026-09-14 -- a faint, fast-setting target `schedule_night()`
        would otherwise skip outright (needs 90 min, window is only ~45
        min) -- author's explicit call to attempt a partial exposure
        anyway rather than lose it. See
        claude_prompts/night_plans/lick_2026sep14.md, Prompt 5. All other
        observable targets are then scheduled normally, starting from
        this target's end + slew instead of evening twilight.
    """
    observable = results_df[results_df['observable']].copy()

    schedule = []
    current_time = twilight['evening_pst']

    if forced_first is not None:
        forced_mask = observable['TNS'] == forced_first
        row = observable[forced_mask].iloc[0]
        observable = observable[~forced_mask]

        red, blue, dur_s = estimate_exposure(row['mag_r'])
        dur_min = dur_s / 60.0
        # Dome-open Focus block (FOCUS_MINUTES) comes first regardless, so
        # it eats straight into this target's already-thin window; the
        # window's far end (exit_pst) is a fixed clock time (Shane HA_MAX,
        # a mechanical limit) independent of when the target starts, so
        # this is genuinely lost time, not merely deferred.
        start = max(twilight['evening_pst'] + timedelta(minutes=FOCUS_MINUTES),
                    row['entry_pst'])
        ideal_end = start + timedelta(minutes=dur_min)
        end = min(ideal_end, row['exit_pst'])
        got_min = (end - start).total_seconds() / 60.0
        reason = ('' if end >= ideal_end else
                   f"forced first (faint, fast-setting): truncated by HA_MAX "
                   f"cutoff to {got_min:.0f} of {dur_min:.0f} min ideal "
                   f"exposure -- partial spectrum, attempted anyway per "
                   f"author's call")
        schedule.append(dict(row, scheduled=True, start_pst=start,
                              end_pst=end, duration_min=got_min,
                              red_side=red, blue_side=blue,
                              skip_reason=reason))
        # The evening standard star is done right after this target
        # (instead of before, as on a normal night) so it doesn't also
        # eat into the thin window -- reserve its slew + duration here so
        # the next target's start stays consistent with the Excel sheet.
        current_time = (end + timedelta(minutes=SLEW_MINUTES)
                         + timedelta(minutes=STD_STAR_MINUTES))

    observable = observable.sort_values('exit_pst').reset_index(drop=True)

    for _, row in observable.iterrows():
        red, blue, dur_s = estimate_exposure(row['mag_r'])
        dur_min = dur_s / 60.0

        start = max(current_time, row['entry_pst'])
        end = start + timedelta(minutes=dur_min)

        if start >= row['exit_pst']:
            schedule.append(dict(row, scheduled=False,
                                  skip_reason=f"window already closed by the time "
                                              f"this target would be reached "
                                              f"(start {start:%H:%M} >= exit "
                                              f"{row['exit_pst']:%H:%M})"))
            continue
        if end > row['exit_pst']:
            schedule.append(dict(row, scheduled=False,
                                  skip_reason=f"needs {dur_min:.0f} min but only "
                                              f"{(row['exit_pst'] - start).total_seconds() / 60:.0f} "
                                              f"min left in its HA window"))
            continue
        if end > twilight['morning_pst']:
            schedule.append(dict(row, scheduled=False,
                                  skip_reason='would run past morning twilight'))
            continue

        schedule.append(dict(row, scheduled=True, start_pst=start, end_pst=end,
                              duration_min=dur_min, red_side=red, blue_side=blue))
        current_time = end + timedelta(minutes=SLEW_MINUTES)

    sched_df = pd.DataFrame(schedule)
    return sched_df


# Author's explicit override, 2026-09-14 (Prompt 5): attempt this faint,
# fast-setting target first anyway, accepting a partial exposure, rather
# than skip it outright the way schedule_night() otherwise would.
FORCED_FIRST_TNS = 'TGT0604'


def main():
    targets_csv = (f'{_PLANS}/'
                    'Lick-2026B-02/Lick-2026B-02_targets.csv')
    date = '2026-09-14'

    results_df, twilight = analyze_targets(targets_csv, date)

    print(f"=== TWILIGHT for {date} (18 deg astronomical, PST=UTC-8 fixed) ===")
    print(f"Evening: {twilight['evening_pst']:%H:%M} PST "
          f"(LST {twilight['evening_lst'].hour:.3f}h)")
    print(f"Morning: {twilight['morning_pst']:%H:%M} PST "
          f"(LST {twilight['morning_lst'].hour:.3f}h)")
    night_min = (twilight['morning_pst'] - twilight['evening_pst']).total_seconds() / 60
    print(f"Night length: {night_min:.0f} min ({night_min / 60:.2f} h)\n")

    print("=== ALL 12 DEC<=82 TARGETS: HA-WINDOW ANALYSIS ===")
    disp = results_df.copy()
    disp['entry_pst'] = disp['entry_pst'].apply(lambda t: t.strftime('%H:%M') if pd.notna(t) else '-')
    disp['exit_pst'] = disp['exit_pst'].apply(lambda t: t.strftime('%H:%M') if pd.notna(t) else '-')
    print(disp[['TNS', 'RA_hours', 'Dec_deg', 'mag_r', 'observable',
                'entry_pst', 'exit_pst', 'ha_entry', 'ha_exit', 'window_min']]
          .to_string(index=False))

    sched_df = schedule_night(results_df, twilight, forced_first=FORCED_FIRST_TNS)

    print("\n=== SCHEDULE (earliest-window-close-first) ===")
    for _, row in sched_df.iterrows():
        if row['scheduled']:
            print(f"  {row['start_pst']:%H:%M}-{row['end_pst']:%H:%M} PST  "
                  f"{row['TNS']:14s} RA {row['RA_hours']:.2f}h mag {row['mag_r']:.2f} "
                  f"HA[{row['ha_entry']:.2f},{row['ha_exit']:.2f}]  "
                  f"red {row['red_side']} blue {row['blue_side']}")
        else:
            print(f"  SKIPPED  {row['TNS']:14s} -- {row['skip_reason']}")

    n_sched = int(sched_df['scheduled'].sum()) if len(sched_df) else 0
    sci_min = sched_df.loc[sched_df['scheduled'], 'duration_min'].sum() if n_sched else 0
    print(f"\n{n_sched} of {len(sched_df)} HA-observable targets scheduled; "
          f"{sci_min:.0f} min science / {night_min:.0f} min night "
          f"({100 * sci_min / night_min:.0f}% utilization)")

    out_dir = f'{_PLANS}/Lick-2026B-02'
    results_df.to_csv(f'{out_dir}/target_analysis.csv', index=False)
    sched_df.to_csv(f'{out_dir}/selected_targets_night1.csv', index=False)
    print(f"\nWrote {out_dir}/target_analysis.csv and selected_targets_night1.csv")

    return results_df, sched_df, twilight


if __name__ == '__main__':
    main()
