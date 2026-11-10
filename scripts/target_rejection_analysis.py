"""
Detailed per-target rejection/acceptance analysis for Lick-2026B-02,
night of 2026-09-14/15.

Created by JXP and Claude

Walks all 15 targets returned by the original chime_ffff_pz_targets pull
(chime_ffff_pz/data/Observing/Lick-2026B-02/Lick-2026B-02_targets.csv,
copied to Night_plans/Lick-2026B-02/) through every filter stage in
order, and records the specific numeric reason a target was dropped (or
scheduled) at each stage:

  1. Dec cut       (Shane polar limit, Dec <= 82 deg)
  2. HA window     (-05:40 <= HA <= +03:45, HA = LST - RA)
  3. Scheduling    (does the target's Kast exposure time fit inside its
                    HA-legal window, given the greedy earliest-window-
                    close-first order used by schedule_night())

Writes Night_plans/Lick-2026B-02/target_rejection_analysis.md.
"""

import pandas as pd
from astropy import units as u

from lick_2026b02_calculations import (
    DEC_LIMIT, HA_MIN, HA_MAX, find_twilight, ha_at, target_window,
    analyze_targets, schedule_night, FORCED_FIRST_TNS,
)
from night_planner.estimate_kast_exposures import estimate_exposure

import sys
from pathlib import Path

# Repo-relative, so this runs wherever the checkout lives.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from night_planner.paths import plans_dir

_PLANS = plans_dir()

TARGETS_CSV = (f'{_PLANS}/'
               'Lick-2026B-02/Lick-2026B-02_targets.csv')
DATE = '2026-09-14'
OUTFILE = (f'{_PLANS}/'
           'Lick-2026B-02/target_rejection_analysis.md')


def fmt_hms(hours):
    hours = hours % 24
    h = int(hours)
    m = int((hours - h) * 60)
    s = ((hours - h) * 60 - m) * 60
    return f"{h:02d}h{m:02d}m{s:04.1f}s"


def fmt_dms(deg):
    sign = '-' if deg < 0 else '+'
    deg = abs(deg)
    d = int(deg)
    m = int((deg - d) * 60)
    s = ((deg - d) * 60 - m) * 60
    return f"{sign}{d:02d}d{m:02d}m{s:04.1f}s"


def dec_cut_reason(dec_deg):
    excess = dec_deg - DEC_LIMIT
    return (f"Dec = {fmt_dms(dec_deg)} exceeds the Shane polar limit "
            f"(Dec <= {DEC_LIMIT:.0f} deg) by {excess:.2f} deg -- "
            f"dropped before HA/scheduling analysis.")


def ha_never_legal_reason(ra_hours, twilight):
    eve_lst = twilight['evening_lst'].to_value(u.hourangle)
    morn_lst = twilight['morning_lst'].to_value(u.hourangle)
    ha_eve = ha_at(ra_hours, eve_lst)
    ha_morn_wrapped = ha_at(ra_hours, morn_lst)
    # Unwrap past +-12h so HA increases monotonically through the night for
    # the comparisons below; ha_morn_wrapped (kept in -12..+12) is used for
    # display instead.
    ha_morn = ha_morn_wrapped
    while ha_morn < ha_eve:
        ha_morn += 24

    ha_beg = (f"HA(beg night, evening twilight LST {fmt_hms(eve_lst)}) = "
              f"{ha_eve:+.2f}h")
    ha_end = (f"HA(end night, morning twilight LST {fmt_hms(morn_lst)}) = "
              f"{ha_morn_wrapped:+.2f}h")

    if ha_eve > HA_MAX:
        return (f"{ha_beg}, {ha_end} -- already past HA_MAX=+{HA_MAX:.2f}h "
                f"at evening twilight, and HA only increases through the "
                f"night -- never re-enters the legal window before dawn.")
    if ha_morn < HA_MIN:
        return (f"{ha_beg}, {ha_end} -- never reaching HA_MIN={HA_MIN:.2f}h "
                f"-- the target rises too late in the night.")
    return (f"{ha_beg}, {ha_end} -- range [{ha_eve:+.2f}h, "
            f"{ha_morn_wrapped:+.2f}h] vs legal [{HA_MIN:.2f}h, "
            f"+{HA_MAX:.2f}h] -- no overlap.")


def main():
    full_df = pd.read_csv(TARGETS_CSV)
    twilight = find_twilight(DATE)

    results_df, _ = analyze_targets(TARGETS_CSV, DATE)
    sched_df = schedule_night(results_df, twilight, forced_first=FORCED_FIRST_TNS)
    sched_by_tns = {r['TNS']: r for _, r in sched_df.iterrows()}

    records = []
    for _, row in full_df.iterrows():
        tns = row['TNS']
        ra_deg, dec_deg = row['Pri_RA'], row['Pri_Dec']
        ra_hours = ra_deg / 15.0
        mag = row['Pri_mag']
        pox = row['Pri_POx']
        tags = row['FRB_tags']
        dm = row['FRB_DM']

        rec = dict(TNS=tns, RA_hours=ra_hours, Dec_deg=dec_deg,
                   RA_str=fmt_hms(ra_hours), Dec_str=fmt_dms(dec_deg),
                   mag_r=mag, POx=pox, tags=tags, DM=dm)

        if dec_deg > DEC_LIMIT:
            rec.update(status='DEC-CUT', reason=dec_cut_reason(dec_deg))
            records.append(rec)
            continue

        window = target_window(ra_hours, dec_deg, twilight)
        if window is None:
            rec.update(status='NEVER HA-LEGAL',
                       reason=ha_never_legal_reason(ra_hours, twilight))
            records.append(rec)
            continue

        entry_time, exit_time, ha_entry, ha_exit = window
        window_min = (exit_time - entry_time).total_seconds() / 60.0
        red, blue, dur_s = estimate_exposure(mag)
        dur_min = dur_s / 60.0

        sched_row = sched_by_tns[tns]
        if tns == FORCED_FIRST_TNS:
            rec.update(
                status='SCHEDULED (forced, partial)',
                reason=(f"HA-legal window {entry_time:%H:%M}-{exit_time:%H:%M} "
                        f"PST ({window_min:.0f} min) is too short for the "
                        f"{dur_min:.0f} min Kast exposure needed at r={mag:.2f} "
                        f"-- author's explicit call to attempt it anyway "
                        f"(faint, fast-setting target): forced first, "
                        f"scheduled {sched_row['start_pst']:%H:%M}-"
                        f"{sched_row['end_pst']:%H:%M} PST for a truncated "
                        f"{sched_row['duration_min']:.0f} min exposure "
                        f"(partial spectrum expected)."))
        elif bool(sched_row['scheduled']):
            rec.update(
                status='SCHEDULED',
                reason=(f"HA-legal window {entry_time:%H:%M}-{exit_time:%H:%M} "
                        f"PST ({window_min:.0f} min, HA {ha_entry:+.2f}h to "
                        f"{ha_exit:+.2f}h) comfortably fits the "
                        f"{dur_min:.0f} min Kast exposure needed at "
                        f"r={mag:.2f}; scheduled {sched_row['start_pst']:%H:%M}"
                        f"-{sched_row['end_pst']:%H:%M} PST."))
        else:
            rec.update(
                status='SKIPPED (window)',
                reason=(f"HA-legal window {entry_time:%H:%M}-{exit_time:%H:%M} "
                        f"PST ({window_min:.0f} min, HA {ha_entry:+.2f}h to "
                        f"{ha_exit:+.2f}h) exists, but needs "
                        f"{dur_min:.0f} min at r={mag:.2f} -- "
                        f"{sched_row['skip_reason']}."))
        records.append(rec)

    out_df = pd.DataFrame(records).sort_values('RA_hours').reset_index(drop=True)

    status_order = {'SCHEDULED': 0, 'SCHEDULED (forced, partial)': 1,
                     'SKIPPED (window)': 2, 'NEVER HA-LEGAL': 3, 'DEC-CUT': 4}
    counts = out_df['status'].value_counts()

    lines = []
    lines.append(f"# Target rejection/acceptance analysis -- Lick-2026B-02, "
                  f"night of {DATE}/{(pd.Timestamp(DATE) + pd.Timedelta(days=1)):%Y-%m-%d}")
    lines.append("")
    lines.append(f"Evening twilight: {twilight['evening_pst']:%H:%M} PST "
                 f"(LST {fmt_hms(twilight['evening_lst'].to_value(u.hourangle))}). "
                 f"Morning twilight: {twilight['morning_pst']:%H:%M} PST "
                 f"(LST {fmt_hms(twilight['morning_lst'].to_value(u.hourangle))}).")
    lines.append("")
    lines.append(f"Shane 3m limits: Dec <= {DEC_LIMIT:.0f} deg; "
                 f"{HA_MIN:.2f}h <= HA <= +{HA_MAX:.2f}h (HA = LST - RA).")
    lines.append("")
    lines.append("**Summary:** "
                 + ", ".join(f"{int(n)} {s}" for s, n in counts.reindex(status_order).items()
                             if pd.notna(n))
                 + f" -- {len(out_df)} targets total.")
    lines.append("")
    lines.append("## Summary table")
    lines.append("")
    lines.append("| TNS | RA (HMS) | Dec (DMS) | r-mag | Status | Reason |")
    lines.append("|---|---|---|---|---|---|")
    for _, r in out_df.iterrows():
        lines.append(f"| {r['TNS']} | {r['RA_str']} | {r['Dec_str']} "
                     f"| {r['mag_r']:.2f} | {r['status']} | {r['reason']} |")
    lines.append("")
    lines.append("## Per-target detail")
    lines.append("")
    for _, r in out_df.iterrows():
        lines.append(f"### {r['TNS']} -- {r['status']}")
        lines.append("")
        lines.append(f"- RA: {r['RA_str']}, Dec: {r['Dec_str']}")
        lines.append(f"- Host r-mag: {r['mag_r']:.2f}, P(O|x): {r['POx']:.3f}, "
                     f"DM: {r['DM']:.1f}, tags: {r['tags']}")
        lines.append(f"- **Reason:** {r['reason']}")
        lines.append("")

    with open(OUTFILE, 'w') as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote: {OUTFILE}")
    print(out_df[['TNS', 'status']].to_string(index=False))


if __name__ == '__main__':
    main()
