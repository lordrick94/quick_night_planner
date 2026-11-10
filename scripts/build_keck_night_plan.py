"""
Build night plan Excel file for Keck/LRIS Oct 6, 2026

Created by JXP and Claude
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from astropy import units as u
from astropy.coordinates import SkyCoord, EarthLocation
from astropy.time import Time

from keck_overheads import keck_slew_minutes
from keck_2026oct06_calculations import MORNING_STANDARD_DEC
from night_plan_io import load_night_meta, resolve_local_dt, OBSERVATORY_TZ

import sys
from pathlib import Path

# Repo-relative, so this runs wherever the checkout lives.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from night_planner.paths import plans_dir

_PLANS = plans_dir()

# Constants
# Verified against astropy's EarthLocation.of_site('keck') (IRAF Observatory
# Database), 2026-09-11: lat 19.828333 deg, lon -155.478333 deg, height 4160 m.
KECK = EarthLocation(lat=19.828333*u.deg, lon=-155.478333*u.deg, height=4160*u.m)
HST = timezone(timedelta(hours=-10))  # Hawaii Standard Time


def hst_to_lst(hst_dt):
    """Convert HST (UTC-10) datetime to LST at Keck."""
    if hst_dt.tzinfo is None:
        hst_dt = hst_dt.replace(tzinfo=HST)
    utc_dt = hst_dt.astimezone(timezone.utc)
    t = Time(utc_dt)
    lst = t.sidereal_time('apparent', longitude=KECK.lon)
    return lst.hour


def hst_to_ut(hst_dt):
    """Convert HST (UTC-10) datetime to UT (decimal hours)."""
    if hst_dt.tzinfo is None:
        hst_dt = hst_dt.replace(tzinfo=HST)
    utc_dt = hst_dt.astimezone(timezone.utc)
    return utc_dt.hour + utc_dt.minute/60.0 + utc_dt.second/3600.0


def format_ra_dec(ra_deg, dec_deg):
    """Format RA/Dec in sexagesimal."""
    coord = SkyCoord(ra=ra_deg*u.deg, dec=dec_deg*u.deg, frame='icrs')
    ra_str = coord.ra.to_string(unit=u.hour, sep=':', precision=2, pad=True)
    dec_str = coord.dec.to_string(unit=u.deg, sep=':', precision=1, pad=True)
    return ra_str, dec_str


def add_observing_checklist(ws):
    """Add observing checklist sheet."""
    checklist_items = [
        "Dome open",
        "Telescope tracking",
        "Focus achieved",
        "Guider configured",
        "Dichroic in place",
        "Gratings verified",
        "Standard star (evening)",
        "Science targets started",
        "Standard star (morning)",
        "Calibrations: see the Observing log page",
        "Dome closed",
        "Data transferred"
    ]

    ws['A1'] = "Keck/LRIS Oct 6, 2026 Observing Checklist"
    ws['A1'].font = Font(size=14, bold=True)

    ws['A3'] = "Task"
    ws['B3'] = "Done"
    ws['C3'] = "Notes"
    ws['A3'].font = Font(bold=True)
    ws['B3'].font = Font(bold=True)
    ws['C3'].font = Font(bold=True)

    for i, item in enumerate(checklist_items, start=4):
        ws[f'A{i}'] = item
        ws[f'B{i}'] = ""
        ws[f'C{i}'] = ""

    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 10
    ws.column_dimensions['C'].width = 30

    # Add LRIS configuration section
    config_start = len(checklist_items) + 6
    ws.cell(row=config_start, column=1, value="LRIS Configuration")
    ws.cell(row=config_start, column=1).font = Font(size=12, bold=True)

    config_items = [
        ("Dichroic", "560"),
        ("Blue Grism", "600/4000"),
        ("Red Grating", "600/7500 (centered ~7200 A)"),
        ("Blue CCD binning", "2x2"),
        ("Red CCD binning", "2x2"),
        ("Slit width", "1.0\""),
    ]

    for i, (key, val) in enumerate(config_items, start=config_start+1):
        ws.cell(row=i, column=1, value=key)
        ws.cell(row=i, column=2, value=val)


def add_night_sheet(wb, date_str, selected_targets, start_hst, blocks=None):
    """
    Add the main observing night sheet.

    Parameters
    ----------
    wb : Workbook
    date_str : str (e.g., "October 2nd")
    selected_targets : DataFrame
    start_hst : datetime
    blocks : list of (start, end, reason) tuples, optional
        Blacked-out windows (ToO, weather hold) from night_meta.json --
        rendered as explicit rows wherever they fall in the timeline. The
        scheduler already guarantees no science target overlaps a block,
        so each one always lands inside a natural gap between rows.
    """
    blocks = blocks or []
    ws = wb.create_sheet(date_str)

    # Set up column headers (Keck format)
    headers = ['Start (LST)', 'Start (UT)', 'Start (HST)', 'Duration', 'End (HST)',
               'Action', 'target', 'RA', 'DEC', 'HA start', 'HA end', 'mag(r)',
               'red side', 'blue side', 'Airmass', 'Comments']

    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")

    # Set column widths
    widths = [12, 10, 12, 10, 12, 18, 16, 12, 12, 10, 10, 8, 12, 12, 8, 35]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64+i)].width = w

    current_row = 2
    current_time = start_hst

    def add_row(action, target='', ra='', dec='', mag_r='',
                red_side='', blue_side='', airmass='', comments='',
                duration_min=0, ra_hours=None):
        nonlocal current_row, current_time

        # Calculate times
        lst_start = hst_to_lst(current_time)
        ut = hst_to_ut(current_time)
        hst_str = current_time.strftime('%H:%M')
        end_time = current_time + timedelta(minutes=duration_min)
        end_str = end_time.strftime('%H:%M')
        lst_end = hst_to_lst(end_time) if duration_min > 0 else lst_start

        # Calculate hour angles if RA provided
        ha_start_str = ''
        ha_end_str = ''
        if ra_hours is not None:
            ha_start = lst_start - ra_hours
            if ha_start > 12:
                ha_start -= 24
            elif ha_start < -12:
                ha_start += 24

            ha_end = lst_end - ra_hours
            if ha_end > 12:
                ha_end -= 24
            elif ha_end < -12:
                ha_end += 24

            ha_start_str = f"{ha_start:+.1f}h"
            ha_end_str = f"{ha_end:+.1f}h"

        duration_str = f"{duration_min:g} min" if duration_min > 0 else ""

        # Write row
        ws.cell(row=current_row, column=1, value=f"{lst_start:.1f}h")
        ws.cell(row=current_row, column=2, value=f"{ut:.1f}")
        ws.cell(row=current_row, column=3, value=hst_str)
        ws.cell(row=current_row, column=4, value=duration_str)
        ws.cell(row=current_row, column=5, value=end_str if duration_min > 0 else '')
        ws.cell(row=current_row, column=6, value=action)
        ws.cell(row=current_row, column=7, value=target)
        ws.cell(row=current_row, column=8, value=ra)
        ws.cell(row=current_row, column=9, value=dec)
        ws.cell(row=current_row, column=10, value=ha_start_str)
        ws.cell(row=current_row, column=11, value=ha_end_str)
        ws.cell(row=current_row, column=12, value=mag_r)
        ws.cell(row=current_row, column=13, value=red_side)
        ws.cell(row=current_row, column=14, value=blue_side)
        ws.cell(row=current_row, column=15, value=airmass)
        ws.cell(row=current_row, column=16, value=comments)

        current_row += 1
        current_time = end_time

    emitted_blocks = set()

    def emit_blocks_before(upto_time):
        """Write a row for any not-yet-emitted block ending at or before upto_time."""
        nonlocal current_time
        for i, (b_start, b_end, reason) in enumerate(blocks):
            if i in emitted_blocks or b_end > upto_time + timedelta(minutes=1):
                continue
            if current_time < b_start:
                current_time = b_start
            add_row(action='ToO / Blocked', comments=reason,
                    duration_min=(b_end - current_time).total_seconds() / 60)
            emitted_blocks.add(i)

    # Evening standard star (BD+28 4211)
    add_row(action="Flux Standard", target="BD28d4211",
            ra="21:51:11.02", dec="+28:51:50.4",
            mag_r="10.5",
            red_side="1 x 30", blue_side="1 x 30",
            comments="Evening standard",
            duration_min=5,
            ra_hours=21.853)

    # Focus
    add_row(action="Focus check", duration_min=5)

    # Science targets - use scheduled times
    for idx, targ in selected_targets.iterrows():
        tns = targ['TNS']
        ra_deg = targ['RA_deg']
        dec_deg = targ['Dec_deg']
        ra_hours = targ['RA_hours']
        mag_r = targ['mag_r']

        ra_str, dec_str = format_ra_dec(ra_deg, dec_deg)

        # Get scheduled times (scheduled_start = slew start)
        sched_start = targ.get('scheduled_start')
        if pd.notna(sched_start):
            if isinstance(sched_start, str):
                sched_start = pd.to_datetime(sched_start)
            if not (hasattr(sched_start, 'tzinfo') and sched_start.tzinfo is not None):
                sched_start = sched_start.replace(tzinfo=HST)

            # Any block between here and this target's start gets its own
            # row first, then jump past it (and any remaining gap) as before.
            emit_blocks_before(sched_start)
            if sched_start > current_time:
                current_time = sched_start

        slew_min = int(targ['slew_min'])
        on_target_min = float(targ['on_target_min'])
        red_exp = targ.get('red_exp', '2 x 600')
        blue_exp = targ.get('blue_exp', '2 x 600')
        am = targ.get('min_airmass', 1.5)
        tags = str(targ.get('tags', '')) if pd.notna(targ.get('tags')) else ''
        is_mos = targ.get('lris_mode') == 'MOS (mask required)'
        forced = str(targ.get('lris_mode', '')).startswith('longslit (forced')
        comment_bits = ((['MASK REQUIRED'] if is_mos else [])
                        + (['NO MASK: longslit, low S/N'] if forced else [])
                        + ([tags] if tags else []))
        comments = ' | '.join(comment_bits)[:40]

        # Slew, then acquisition (keck_overheads.py: 5 min base slew, 14 min
        # Dec<+20 -> Dec>+20; acquisition 5 min longslit, 10 min mask).
        add_row(action=f"slew to", target=tns, duration_min=slew_min)
        acq_min = targ.get('acq_min')
        if pd.notna(acq_min) and acq_min:
            add_row(action="acquire", target=tns, duration_min=int(acq_min))

        # Science observation
        add_row(action="Science" if not is_mos else "Science (MOS)",
                target=tns,
                ra=ra_str,
                dec=dec_str,
                mag_r=f"{mag_r:.1f}",
                red_side=red_exp,
                blue_side=blue_exp,
                airmass=f"{am:.2f}",
                comments=comments,
                duration_min=on_target_min,
                ra_hours=ra_hours)

    # Any block after the last science target (e.g. a late-night ToO)
    if blocks:
        emit_blocks_before(max(b[1] for b in blocks))

    # Morning standard star (Feige 110)
    last_dec = (selected_targets['Dec_deg'].iloc[-1] if len(selected_targets)
                else None)
    add_row(action="slew to", target="Feige110",
            duration_min=keck_slew_minutes(last_dec, MORNING_STANDARD_DEC))
    add_row(action="Flux Standard", target="Feige110",
            ra="23:19:58.40", dec="-05:09:56.2",
            mag_r="11.8",
            red_side="1 x 30", blue_side="1 x 30",
            comments="Morning standard",
            duration_min=5,
            ra_hours=23.333)

    # Calibrations aren't scheduled (2026-11-07, T1.5); the observer takes
    # them and ticks them off on the Observing log page.
    add_row(action="Calibrations: see the Observing log page")

    # Add notes section
    note_row = current_row + 2
    ws.cell(row=note_row, column=1, value="NOTES:")
    ws.cell(row=note_row, column=1).font = Font(bold=True)

    # Largest gap between consecutive scheduled targets (computed from the
    # actual schedule, not hardcoded -- a hardcoded gap string went stale
    # three times across earlier revisions of this plan).
    gap_note = "- No gaps: back-to-back targets all night"
    if len(selected_targets) > 1:
        starts_ends = sorted(
            (pd.to_datetime(t['scheduled_start']), pd.to_datetime(t['scheduled_end']))
            for _, t in selected_targets.iterrows())
        max_gap = pd.Timedelta(0)
        gap_start = gap_end = None
        for (s1, e1), (s2, e2) in zip(starts_ends, starts_ends[1:]):
            gap = s2 - e1
            if gap > max_gap:
                max_gap, gap_start, gap_end = gap, e1, s2
        if gap_start is not None:
            gap_note = (f"- Gap from ~{gap_start.strftime('%H:%M')}-"
                        f"{gap_end.strftime('%H:%M')} HST: no further "
                        f"observable targets in hand")

    notes = [
        gap_note,
        "- All targets observable at airmass < 2.0 when scheduled",
        "- Keck slews: 5 min base; 14 min when moving from Dec < +20 to Dec > +20",
        "- Acquisition after each slew: 5 min longslit, 10 min mask",
        "- MOS blocks include a 5 min buffer per mask on top of the 1-2h allocation",
        "- LRIS setup: 560 dichroic, 600/4000 blue grism, 600/7500 red grating (~7200A)",
        "- Exposure times from the real LRIS ETC (etc.ucolick.org): S/N=10/pixel per single exposure, 3 exposures min",
        "- MOS (mag>21) targets need ~1-2h once masked (see info column); utilization is target-count-limited: request more targets"
    ]

    for i, note in enumerate(notes, start=note_row+1):
        ws.cell(row=i, column=1, value=note)

    return ws


def build_keck_night_plan(output_path, selected_csv, output_dir, date='2026-10-06',
                           start_override=None, sheet_name='October 6th'):
    """
    Build the complete Keck night plan Excel file.

    Parameters
    ----------
    start_override : datetime, optional
        Takes precedence over night_meta.json (and that in turn over the
        2026-10-06 default) -- see night_plan_io.
    """
    # Load selected targets
    selected_targets = pd.read_csv(selected_csv)

    meta = load_night_meta(output_dir)
    if start_override is not None:
        start_hst = start_override
    elif meta is not None:
        start_hst = meta['start_local']
    else:
        # Fallback matching the original committed default, for a bare
        # selected_targets.csv with no night_meta.json yet.
        start_hst = datetime(2026, 10, 6, 19, 10, 0, tzinfo=HST)
    blocks = meta['blocks'] if meta is not None else []

    # Create workbook
    wb = Workbook()
    wb.remove(wb.active)

    # Add sheets
    checklist = wb.create_sheet("Observing Checklist")
    add_observing_checklist(checklist)

    add_night_sheet(wb, sheet_name, selected_targets, start_hst, blocks=blocks)

    # Save
    wb.save(output_path)
    print(f"Night plan saved to: {output_path}")
    print(f"Start: {start_hst.strftime('%H:%M %Z')}"
          f"{' (manual override)' if start_override is not None else ' (from night_meta.json)' if meta else ' (default)'}")
    if blocks:
        for b_start, b_end, reason in blocks:
            print(f"Block: {b_start.strftime('%H:%M')}-{b_end.strftime('%H:%M')} ({reason})")


def parse_args(argv=None):
    """
    Parameters
    ----------
    argv : list of str, optional
        Defaults to sys.argv[1:]. Passed explicitly by night_planner.cli.
    """
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selected-csv')
    p.add_argument('--output-dir')
    p.add_argument('--output-path')
    p.add_argument('--start', help='Manual start override, HH:MM local '
                   '(Pacific/Honolulu) or full ISO datetime. Overrides '
                   'night_meta.json if both are present.')
    p.add_argument('--date')
    return p.parse_args(argv)


def run(args):
    """Execute the Excel build for an already-parsed args namespace (see
    keck_2026oct06_calculations.run() for why this is split from main())."""
    output_dir = args.output_dir or f'{_PLANS}/Keck-2026B-02'
    selected_csv = args.selected_csv or f'{output_dir}/selected_targets.csv'
    output_path = args.output_path or f'{output_dir}/Keck_LRIS_2026Oct06_Night_plan.xlsx'
    date = args.date or '2026-10-06'

    start_override = (resolve_local_dt(date, args.start, OBSERVATORY_TZ['keck'])
                       if args.start else None)

    build_keck_night_plan(output_path, selected_csv, output_dir, date=date,
                           start_override=start_override)


def main():
    """Standalone entry point: `python scripts/build_keck_night_plan.py ...`."""
    return run(parse_args())


if __name__ == '__main__':
    main()
