"""General Excel night-plan builder: any saved plan, any instrument.

Created by JXP and Claude

Writes the observers' Excel night plan (format: docs/excel_night_plan_format.md)
from one or more saved ``PlanResult`` objects -- one night sheet per plan --
with the quirks of the hand-made reference fixed:

- UT and LST offsets are computed for each night and kept in labelled cells
  (``$V$3``, ``$V$4``) that columns A and B reference, instead of typed
  constants;
- the local-time headers carry the plan's real zone abbreviation (PDT, PST,
  HST), not a fixed "PST";
- RA and Dec are written as text, so a spreadsheet can never turn them into
  times;
- twilight times are computed from the plan's sun events;
- Done and calibration cells keep a TRUE/FALSE drop-down;
- the timeline is as long as the night needs, with idle time and blocked
  time as their own rows so the durations add up to the plan exactly.

Inputs
------
Saved plan directories (``plan_result.json``), or PlanResult objects.

Outputs
-------
An .xlsx workbook. ``write_plan_excel`` puts it in the (first) plan
directory as ``<dir name>_Night_plan.xlsx``.
"""

import argparse
import os
import re
from datetime import time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

import pandas as pd
from astropy import units as u
from astropy.coordinates import Angle
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from .plan_store import FILENAME as PLAN_FILENAME
from .plan_store import load_plan
from .sky import lst_hours

FONT = 'Arial'
EDIT_FILL = PatternFill('solid', fgColor='FFC9DAF8')     # the one input column
HEADER_FILL = PatternFill('solid', fgColor='FFD9EAD3')   # checklist header
PRE_FILL = PatternFill('solid', fgColor='FFFCE5CD')
POST_FILL = PatternFill('solid', fgColor='FFC9DAF8')
USED_FILL = PatternFill('solid', fgColor='FF00FF00')     # standard the plan uses
THIN = Side(style='thin')
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
GREEN = 'FF38761D'
TIME_FMT = 'h:mm'

FIRST_ROW = 4        # first timed row, as in the reference
SLEW = 'slew to --> '
SIDEREAL_GAIN = 0.00273791   # LST day / solar day - 1
SCIENCE = 'Science + overhead'
STANDARD = 'standard'

NIGHT_WIDTHS = {'A': 18.63, 'B': 11.0, 'C': 11.0, 'D': 11.0, 'E': 10.0,
                'F': 24.0, 'G': 18.0, 'H': 13.25, 'I': 13.0, 'J': 9.63,
                'K': 8.5, 'L': 11.0, 'M': 12.5, 'N': 10.0, 'O': 44.5,
                'Q': 12.0, 'U': 22.0, 'V': 11.0, 'W': 9.0, 'X': 9.0}

CHECKLIST_PRE = [
    ('Make Follow-up Resource', ''),
    ('Make Obs directory on chime_ffff_pz', 'Please start on a clean main branch'),
    ('Uploaded FU Resource to git', ''),
    ('Add FU Resource to FFFF-PZ', ''),
    ('Make Observing folder on google Drive', ''),
    ('Make Target List', ''),
    ('Vet Target List for non-feasible Targets',
     '1. Note some of these targets for future automation (E.g Telescope '
     'Pointing Limits); Also look at airmass charts'),
    ('Make Nightplan(s)', ''),
    ('Make pending List', ''),
    ('Add pending List to repo', ''),
    ('Ingest pending List to FFFF-PZ', ''),
    ('Add in relevant info to google Drive', ''),
    ('Make Finder Charts', ''),
    ('Make Starlist', ''),
]
CHECKLIST_GO = 'Proceed with Obs (DO NOT GO ROGUE!!)'
CHECKLIST_POST = [
    ('Download RAW files from Telescope servers', ''),
    ('Add RAW files to CANFAR (use script)', ''),
    ('Reduce Files', ''),
    ('Make Redshift Table', ''),
    ('Make obs log', 'Refine pending list if need be'),
    ('Ingest Obs log to FFFF-PZ', ''),
    ('Ingest Redshifts to FFFF-PZ', ''),
    ('Clean up Reductions files', ''),
    ('Add Redshift Table and obs log to REPO', ''),
    ('Add Reduction and Science files to CANFAR', ''),
    ('Upload Redshift Screenshots to REPO', ''),
    ('Send Repo PR for merging', ''),
]

TRACKING = [  # header, width, drop-down values (None = free text)
    ('TNS', 18.25, None),
    ('Reduction Status', 26.75, 'Not started,In progress,Fluxed,Marz redshifts'),
    ('Primary', 23.13, 'Not Checked,No Continuum,Continuum No Redshift,z acquired'),
    ('Secondary', 23.13,
     'Not Checked,Not needed,No Continuum,Continuum No Redshift,z acquired'),
    ('Uploaded To F4PZ', 25.75, 'Not Yet,Done'),
    ('Uploaded To Repo', 24.0, 'Not Yet,Done'),
    ('Notes', 23.88, None),
]

# Site weather links, by instrument. Lick's are the two in the reference plan.
WEATHER_LINKS = {
    'kast': ('Lick Weather Links', [
        ('Forecast', 'https://forecast.weather.gov/MapClick.php?lon=-121.62&lat=37.34'),
        ('Clear Sky clock', 'https://server3.cleardarksky.com/c/MtHamCAkey.html?1'),
    ]),
    'lris': ('Maunakea Weather Links', [
        ('Maunakea Weather Center', 'http://mkwc.ifa.hawaii.edu/'),
    ]),
}

CALIBRATIONS = ('Focus', 'Bias', 'Flats', 'Arcs')


# --------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------

def sheet_name_for(date_str):
    """
    Night-sheet name in the reference style, e.g. '2026-05-15' -> 'May 15th'.

    Inputs
    ------
    date_str : str, YYYY-MM-DD (the evening the night starts)

    Outputs
    -------
    str
    """
    d = pd.Timestamp(date_str)
    day = d.day
    suffix = 'th' if 11 <= day % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    return f'{d:%b} {day}{suffix}'


def ra_text(ra_deg):
    """RA in degrees -> 'hh:mm:ss.ss' text ('' if missing)."""
    if ra_deg is None or pd.isna(ra_deg):
        return ''
    return Angle(ra_deg, u.deg).to_string(unit=u.hour, sep=':', precision=2, pad=True)


def dec_text(dec_deg):
    """Dec in degrees -> '+dd:mm:ss.s' text ('' if missing)."""
    if dec_deg is None or pd.isna(dec_deg):
        return ''
    return Angle(dec_deg, u.deg).to_string(unit=u.deg, sep=':', precision=1,
                                           pad=True, alwayssign=True)


def _round_minute(dt):
    """Round a datetime to the nearest whole minute."""
    return (dt + timedelta(seconds=30)).replace(second=0, microsecond=0)


def _as_time_s(hours):
    """Hours (any real) -> datetime.time on a 24 h clock, to the second."""
    seconds = int(round((hours % 24) * 3600)) % 86400
    return time(seconds // 3600, (seconds // 60) % 60, seconds % 60)


def _as_time(hours):
    """Hours (any real) -> datetime.time on a 24 h clock, to the minute."""
    minutes = int(round((hours % 24) * 60)) % (24 * 60)
    return time(minutes // 60, minutes % 60)


def _clock_hours(dt):
    """Local clock time of a datetime, in hours."""
    return dt.hour + dt.minute / 60 + dt.second / 3600


def _duration(minutes):
    """Whole minutes (< 24 h) -> datetime.time for an h:mm duration cell."""
    minutes = int(round(minutes))
    return time(minutes // 60, minutes % 60)


def plan_tz(plan):
    """
    The plan's named time zone (e.g. America/Los_Angeles), so headers read
    PDT/PST/HST. A reloaded plan's datetimes carry only a fixed offset.

    Inputs
    ------
    plan : PlanResult

    Outputs
    -------
    tzinfo
    """
    try:
        return ZoneInfo(plan.timezone)
    except Exception:
        return plan.night_start.tzinfo


def _site_location(plan):
    """EarthLocation for the plan's instrument, or None if unknown."""
    from .adapters import SITES
    return SITES.get(plan.instrument, {}).get('location')


def time_offsets(plan, location):
    """
    UT and LST offsets from local clock time, for one night.

    The LST offset is taken at the middle of the night. LST runs faster than
    the clock by SIDEREAL_GAIN (about 4 min per day), so the sheet adds
    ``(C - reference) * SIDEREAL_GAIN`` to stay exact across the night.

    Inputs
    ------
    plan : PlanResult
    location : astropy EarthLocation (None -> LST offset is None)

    Outputs
    -------
    (ut_hours, lst_hours, reference): offsets to ADD to local time, each in
    [0, 24), and the datetime the LST offset is exact at (None without a
    location).
    """
    tz = plan_tz(plan)
    ut = (-plan.night_start.astimezone(tz).utcoffset().total_seconds() / 3600) % 24
    if location is None:
        return ut, None, None
    mid = (plan.night_start + (plan.night_end - plan.night_start) / 2).astimezone(tz)
    lst = float(lst_hours([mid], location)[0])
    return ut, (lst - _clock_hours(mid)) % 24, mid


def secondary_mags(plan):
    """
    Secondary-candidate magnitudes by target name, from the plan's own
    target table (``--targets-csv`` in plan.request). Empty when the table
    is gone or has no secondary-magnitude column.

    Inputs
    ------
    plan : PlanResult

    Outputs
    -------
    dict name -> float
    """
    argv = list((plan.request or {}).get('argv') or [])
    path = None
    for i, tok in enumerate(argv):
        if tok == '--targets-csv' and i + 1 < len(argv):
            path = argv[i + 1]
        elif tok.startswith('--targets-csv='):
            path = tok.split('=', 1)[1]
    if not path or not os.path.exists(path):
        return {}
    try:
        df = pd.read_csv(path)
    except Exception:
        return {}
    name_col = next((c for c in ('TNS', 'name', 'Name') if c in df), None)
    sec_col = next((c for c in df.columns if c.lower().startswith('sec_mag')), None)
    if name_col is None or sec_col is None:
        return {}
    vals = pd.to_numeric(df[sec_col], errors='coerce')
    return {str(n): float(v) for n, v in zip(df[name_col], vals) if pd.notna(v)}


# --------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------

def _overhead_row(label):
    """Map an overhead label to (action, target, is_standard)."""
    low = label.lower()
    named = re.search(r'\(([^)]+)\)', label)
    if low.startswith('slew to'):
        return SLEW, label[len('slew to'):].strip(), False
    if 'standard' in low:
        return STANDARD, named.group(1).strip() if named else '', True
    return label, '', False


def timeline_rows(plan, sec_mags=None):
    """
    The night as consecutive rows (each starts when the previous ends).

    Events -- overheads, each target's slew and science, blocks -- are put
    in time order on whole-minute boundaries. Uncovered time becomes an
    'idle' row, so the durations add up to the plan exactly; an event that
    starts before the previous one ends is shortened to start at its end.

    Inputs
    ------
    plan : PlanResult
    sec_mags : dict name -> secondary magnitude, optional

    Outputs
    -------
    list of dict with keys start (datetime), minutes (int), action, target,
    ra, dec, mag, sec_mag, red, blue, comment, standard (bool)
    """
    sec_mags = sec_mags or {}
    events = []
    for start, end, label in plan.overheads:
        action, target, is_std = _overhead_row(label)
        events.append(dict(start=start, end=end, action=action, target=target,
                           standard=is_std))
    for t in plan.schedule:
        sci_start = t.start + timedelta(minutes=t.slew_min or 0)
        if (t.slew_min or 0) > 0:
            events.append(dict(start=t.start, end=sci_start, action=SLEW,
                               target=t.name))
        comment = '; '.join(x for x in (
            '' if (t.mode or '').lower() == 'longslit' else t.mode,
            'required' if getattr(t, 'required', False) else '',
            t.tags, t.notes) if x)
        events.append(dict(start=sci_start, end=t.end, action=SCIENCE,
                           target=t.name, ra=ra_text(t.ra_deg), dec=dec_text(t.dec_deg),
                           mag=t.mag, sec_mag=sec_mags.get(t.name),
                           red=t.exposure_red, blue=t.exposure_blue, comment=comment))
    for start, end, reason in plan.blocks:
        events.append(dict(start=start, end=end, action=f'blocked: {reason}'))
    events.sort(key=lambda e: (e['start'], e['end']))

    rows = []

    tz = plan_tz(plan)

    def add(start, end, **kw):
        minutes = (end - start).total_seconds() / 60
        if minutes >= 1:
            rows.append(dict(start=start.astimezone(tz),
                             minutes=int(round(minutes)), **kw))

    first = _round_minute(plan.night_start)
    dusk12 = getattr(plan.sun, 'dusk_nautical', None)
    twelve = _round_minute(dusk12) if dusk12 is not None else None
    if twelve is not None and twelve < first:
        add(twelve, first, action='Start (~12 deg twilight)')

    cursor = first
    for ev in events:
        start, end = _round_minute(ev['start']), _round_minute(ev['end'])
        if end <= cursor:
            continue
        if start > cursor:
            add(cursor, start, action='idle (nothing scheduled)')
        start = max(start, cursor)
        fields = {k: v for k, v in ev.items() if k not in ('start', 'end')}
        add(start, end, **fields)
        cursor = end
    night_end = _round_minute(plan.night_end)
    if cursor < night_end:
        add(cursor, night_end, action='idle (nothing scheduled)')
        cursor = night_end
    rows.append(dict(start=cursor.astimezone(tz), minutes=0, action='End of night'))
    return rows


# --------------------------------------------------------------------
# Sheets
# --------------------------------------------------------------------

def _font(**kw):
    return Font(name=FONT, **kw)


def _bool_validation(ws, ref):
    """Attach a TRUE/FALSE drop-down to a cell range."""
    dv = DataValidation(type='list', formula1='"TRUE,FALSE"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(ref)


def write_checklist(wb):
    """
    Add the 'Observing Checklist' sheet, every Done box FALSE.

    Inputs
    ------
    wb : openpyxl Workbook

    Outputs
    -------
    the worksheet
    """
    ws = wb.create_sheet('Observing Checklist')
    ws.column_dimensions['A'].width = 41.75
    ws.column_dimensions['C'].width = 89.38
    for col, text in zip('ABC', ('Action', 'Done', 'Notes')):
        c = ws[f'{col}1']
        c.value, c.font, c.fill = text, _font(), HEADER_FILL
    row = 2
    ws.cell(row, 1, 'Pre Obs').fill = PRE_FILL
    first_box = row + 1
    for action, note in CHECKLIST_PRE:
        row += 1
        ws.cell(row, 1, action)
        ws.cell(row, 2, False)
        if note:
            ws.cell(row, 3, note).alignment = Alignment(wrap_text=True)
    row += 1
    ws.cell(row, 1, CHECKLIST_GO).font = _font(bold=True)
    row += 4
    ws.cell(row, 1, 'Post Obs').fill = POST_FILL
    for action, note in CHECKLIST_POST:
        row += 1
        ws.cell(row, 1, action)
        ws.cell(row, 2, False)
        if note:
            ws.cell(row, 3, note).alignment = Alignment(wrap_text=True)
    for r in ws.iter_rows(min_row=1, max_row=row, max_col=3):
        for c in r:
            if c.font is None or c.font.name != FONT:
                c.font = _font(bold=bool(c.font and c.font.b))
            if c.column == 2 and isinstance(c.value, bool):
                c.font = _font(color='FF00FF00')
                c.alignment = Alignment(horizontal='center')
    _bool_validation(ws, f'B{first_box}:B{row}')
    return ws


def write_night_sheet(wb, plan, title, sec_mags=None, library=None):
    """
    Add one night sheet for a plan.

    Inputs
    ------
    wb : openpyxl Workbook
    plan : PlanResult
    title : str, sheet name
    sec_mags : dict name -> secondary magnitude, optional
    library : dict name -> SkyCoord of flux standards, optional (for the
        standard-star table; names only when absent)

    Outputs
    -------
    the worksheet
    """
    ws = wb.create_sheet(title)
    for col, width in NIGHT_WIDTHS.items():
        ws.column_dimensions[col].width = width
    location = _site_location(plan)
    ut_off, lst_off, lst_ref = time_offsets(plan, location)
    tz = plan_tz(plan)
    zone = plan.night_start.astimezone(tz).tzname() or 'local'
    band = (plan.config or {}).get('mag_band') or 'r'

    headers = ['Start (LST)', 'Start (UT)', f'Start ({zone})', 'Duration\n(hh:min)',
               f'End ({zone})', 'Action', 'target', 'RA', 'DEC', f'mag ({band})',
               'sec mag', 'red side', 'blue side', 'Redshift', 'Comments']
    for i, text in enumerate(headers, 1):
        c = ws.cell(1, i, text)
        c.font = _font(bold=text != 'Comments')
        c.alignment = Alignment(horizontal='center', wrap_text=True)
    ws['D1'].fill = EDIT_FILL
    ws['D2'] = 'Only edit this column'
    ws['D2'].fill, ws['D2'].alignment = EDIT_FILL, Alignment(horizontal='center')
    ws['F2'] = 'Open dome'
    ws.freeze_panes = 'A2'

    rows = timeline_rows(plan, sec_mags)
    centre = Alignment(horizontal='center')
    for i, row in enumerate(rows):
        r = FIRST_ROW + i
        if i == 0:
            ws.cell(r, 3, _as_time(_clock_hours(row['start'])))
        else:
            ws.cell(r, 3, f'=E{r - 1}')
        ws.cell(r, 1, f'=MOD(C{r}+$V$4+(C{r}-$V$5)*{SIDEREAL_GAIN},1)'
                if lst_off is not None else None)
        ws.cell(r, 2, f'=MOD(C{r}+$V$3,1)')
        ws.cell(r, 4, _duration(row['minutes'])).fill = EDIT_FILL
        ws.cell(r, 5, f'=C{r}+D{r}')
        for col in range(1, 6):
            ws.cell(r, col).number_format = TIME_FMT
            ws.cell(r, col).alignment = centre
        ws.cell(r, 6, row['action'])
        ws.cell(r, 7, row.get('target') or None)
        for col, key in ((8, 'ra'), (9, 'dec')):
            if row.get(key):
                c = ws.cell(r, col, row[key])
                c.number_format = '@'
        for col, key in ((10, 'mag'), (11, 'sec_mag')):
            v = row.get(key)
            if v is not None and not pd.isna(v):
                ws.cell(r, col, round(float(v), 2))
        for col, key in ((12, 'red'), (13, 'blue')):
            if row.get(key):
                ws.cell(r, col, str(row[key])).alignment = centre
        if row.get('comment'):
            ws.cell(r, 15, row['comment'])
    last = FIRST_ROW + len(rows) - 1
    for r in ws.iter_rows(min_row=1, max_row=last, max_col=15):
        for c in r:
            if c.font is None or c.font.name != FONT:
                c.font = _font(bold=bool(c.font and c.font.b))

    # Side panel: calibrations, offsets, twilight.
    ws['Q2'], ws['R2'], ws['S2'] = 'Calibrations', 'Red', 'Blue'
    ws['Q2'].font = _font(bold=True)
    ws['R2'].font = _font(bold=True, color='FFFF0000')
    ws['S2'].font = _font(bold=True, color='FF4A86E8')
    for i, name in enumerate(CALIBRATIONS):
        r = 3 + i
        ws.cell(r, 17, name).font = _font()
        for col in (18, 19):
            ws.cell(r, col, False).font = _font(color=GREEN)
    _bool_validation(ws, f'R3:S{2 + len(CALIBRATIONS)}')

    ws['U2'] = 'Time offsets (computed)'
    ws['U2'].font = _font(bold=True)
    ws['U3'], ws['V3'] = f'UT - {zone}', _as_time(ut_off)
    ws['U4'] = f'LST - {zone}'
    ws['V4'] = _as_time_s(lst_off) if lst_off is not None else None
    ws['U5'] = 'LST offset exact at'
    if lst_ref is not None:
        # Same day-fraction convention as column C: C4 plus elapsed days.
        c4 = _clock_hours(rows[0]['start']) / 24
        ws['V5'] = c4 + (lst_ref - rows[0]['start']).total_seconds() / 86400
        ws['V5'].number_format = TIME_FMT
    ws['U6'] = 'A = C + V4 (+ sidereal gain since V5); B = C + V3'
    ws['U6'].font = _font(italic=True)

    ws['U7'] = 'Twilight (computed)'
    ws['U7'].font = _font(bold=True)
    for col, text in zip('UVWX', ('Event', zone, 'UT', 'LST')):
        ws[f'{col}8'] = text
        ws[f'{col}8'].font = _font(bold=True)
    sun = plan.sun
    events = [(label, getattr(sun, key, None)) for label, key in (
        ('Sunset', 'sunset'), ('12 deg dusk', 'dusk_nautical'),
        ('18 deg dusk', 'dusk_astronomical'), ('18 deg dawn', 'dawn_astronomical'),
        ('12 deg dawn', 'dawn_nautical'), ('Sunrise', 'sunrise'))]
    events = [e for e in events if e[1] is not None]
    lsts = (lst_hours([e[1] for e in events], location)
            if location is not None else [None] * len(events))
    for i, ((label, when), lst) in enumerate(zip(events, lsts)):
        r = 9 + i
        when = when.astimezone(tz)
        ws.cell(r, 21, label)
        ws.cell(r, 22, _as_time(_clock_hours(when)))
        ws.cell(r, 23, _as_time(_clock_hours(when) + ut_off))
        ws.cell(r, 24, _as_time(float(lst)) if lst is not None else None)
        for col in (22, 23, 24):
            ws.cell(r, col).number_format = TIME_FMT
    ws['V3'].number_format = TIME_FMT
    ws['V4'].number_format = 'h:mm:ss'
    for r in ws.iter_rows(min_row=2, max_row=14, min_col=17, max_col=24):
        for c in r:
            if c.value is not None and (c.font is None or c.font.name != FONT):
                c.font = _font(bold=bool(c.font and c.font.b))

    _write_standards(ws, plan, last + 3, rows, library, location)
    return ws


def _norm(name):
    """Comparable standard-star name: lower-case letters and digits only
    ('BD+28 4211' and 'bd284211' match)."""
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


def _write_standards(ws, plan, top, rows, library, location):
    """Standard-star table and weather links below the timeline."""
    used = [r['target'] for r in rows if r.get('standard') and r.get('target')]
    options = []
    if library:
        from .standards import rank_standards
        for when in (plan.night_start, plan.night_end):
            try:
                options += [s['name'] for s in
                            rank_standards(when, location, library, limit=3)]
            except Exception:
                pass
    names, seen = [], set()
    for n in used + options:          # plan's own spelling wins
        if _norm(n) not in seen:
            seen.add(_norm(n))
            names.append(n)
    lib = {_norm(k): (k, v) for k, v in (library or {}).items()}

    heads = ('Standard Star Options', 'RA', 'DEC', 'FK5', 'v')
    for i, text in enumerate(heads, 1):
        c = ws.cell(top, i, text)
        c.font, c.border = _font(bold=True), BOX
        c.alignment = Alignment(horizontal='center' if i > 1 else None)
    ws.cell(top, 4).fill = EDIT_FILL
    r = top
    for name in names:
        r += 1
        hit = lib.get(_norm(name))
        coord = hit[1] if hit else None
        values = (name,
                  ra_text(coord.ra.deg) if coord is not None else '',
                  dec_text(coord.dec.deg) if coord is not None else '',
                  2000.0 if coord is not None else None, None)
        for i, v in enumerate(values, 1):
            c = ws.cell(r, i, v)
            c.font, c.border = _font(), BOX
            if i in (2, 3):
                c.number_format = '@'
        if _norm(name) in {_norm(u_) for u_ in used}:
            ws.cell(r, 1).fill = USED_FILL
    if not names:
        r += 1
        ws.cell(r, 1, '(no standards in this plan)').font = _font(italic=True)
    elif not library:
        r += 1
        ws.cell(r, 1, '(coordinates need the standard-star library: set '
                      'FFFF_PZ_REPO)').font = _font(italic=True)

    title, links = WEATHER_LINKS.get(plan.instrument, ('Weather Links', []))
    if links:
        r += 3
        ws.cell(r, 1, title).font = _font()
        for label, url in links:
            r += 1
            ws.cell(r, 1, label).font = _font()
            c = ws.cell(r, 2, 'link')
            c.hyperlink, c.font = url, Font(name=FONT, color='FF0000FF', underline='single')


def write_summary(wb, names):
    """Add 'FRB Observing Summary' with the scheduled targets pre-filled."""
    ws = wb.create_sheet('FRB Observing Summary')
    for col, (text, width) in zip('ABCD', (('Name', 18.38), ('Observing Report', 29.38),
                                           ('Target Info', 40.5), ('z', None))):
        ws[f'{col}1'] = text
        ws[f'{col}1'].font = _font()
        if width:
            ws.column_dimensions[col].width = width
    for i, name in enumerate(names, 2):
        ws.cell(i, 1, name).font = _font()
    return ws


def write_tracking(wb, names):
    """Add 'Post Observing Tracking' with drop-downs and the targets pre-filled."""
    ws = wb.create_sheet('Post Observing Tracking')
    ws.freeze_panes = 'A2'
    last = max(len(names) + 1, 2) + 50
    align = Alignment(horizontal='left', vertical='center', wrap_text=True)
    for i, (text, width, choices) in enumerate(TRACKING, 1):
        c = ws.cell(1, i, text)
        c.font, c.alignment = _font(), align
        col = c.column_letter
        ws.column_dimensions[col].width = width
        if choices:
            dv = DataValidation(type='list', formula1=f'"{choices}"', allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(f'{col}2:{col}{last}')
    for i, name in enumerate(names, 2):
        ws.cell(i, 1, name).font = _font()
    for r in range(1, len(names) + 2):
        ws.row_dimensions[r].height = 22.5
    return ws


def build_workbook(plans, out_path, sec_mags=None, library=None):
    """
    Write the night-plan workbook for one or more nights.

    Inputs
    ------
    plans : list of PlanResult, one per night (sheet order follows the list)
    out_path : str or Path
    sec_mags : dict name -> secondary magnitude, optional
    library : dict name -> SkyCoord of flux standards, optional

    Outputs
    -------
    Path of the workbook written.
    """
    wb = Workbook()
    wb.remove(wb.active)
    write_checklist(wb)
    seen = {}
    for plan in plans:
        title = sheet_name_for(plan.date)
        seen[title] = seen.get(title, 0) + 1
        if seen[title] > 1:
            title = f'{title} ({seen[title]})'
        write_night_sheet(wb, plan, title[:31], sec_mags, library)
    names = list(dict.fromkeys(t.name for p in plans for t in p.schedule))
    write_summary(wb, names)
    write_tracking(wb, names)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


def excel_path(plan_dir):
    """Where write_plan_excel puts a plan directory's workbook."""
    plan_dir = Path(plan_dir)
    return plan_dir / f'{plan_dir.name}_Night_plan.xlsx'


def excel_is_stale(plan_dir):
    """True when the workbook is missing or older than plan_result.json."""
    plan_dir = Path(plan_dir)
    xlsx, plan = excel_path(plan_dir), plan_dir / PLAN_FILENAME
    return plan.exists() and (not xlsx.exists()
                              or xlsx.stat().st_mtime < plan.stat().st_mtime)


def _try_library():
    """The flux-standard library, or None when it isn't available here."""
    try:
        from .standards import load_library
        return load_library()
    except Exception:
        return None


def write_plan_excel(plan_dirs, out_path=None):
    """
    Build the workbook for saved plan directories (one night sheet each).

    Inputs
    ------
    plan_dirs : list of str/Path holding plan_result.json, in night order
    out_path : str/Path, optional (default: excel_path(first directory))

    Outputs
    -------
    Path of the workbook written.

    Raises
    ------
    FileNotFoundError if a directory has no saved plan.
    """
    plans = []
    for d in plan_dirs:
        plan = load_plan(str(d))
        if plan is None:
            raise FileNotFoundError(f'no {PLAN_FILENAME} in {d}')
        plan.output_dir = str(d)
        plans.append(plan)
    sec = {}
    for plan in plans:
        sec.update(secondary_mags(plan))
    return build_workbook(plans, out_path or excel_path(plan_dirs[0]),
                          sec_mags=sec, library=_try_library())


def main(argv=None):
    """
    Command line: ``python -m night_planner.excel_plan DIR [DIR ...] [--out X]``.

    Inputs
    ------
    argv : list of str, optional

    Outputs
    -------
    int exit code; prints the workbook path.
    """
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('plan_dirs', nargs='+', help='plan directories, in night order')
    p.add_argument('--out', help='workbook path (default: in the first directory)')
    args = p.parse_args(argv)
    print(write_plan_excel(args.plan_dirs, args.out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
