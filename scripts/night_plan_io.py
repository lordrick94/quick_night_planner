"""
Shared JSON input/output plumbing for night-plan scripts (Lick and Keck).

Design
------
Two JSON files per night, both living next to the plan's CSVs:

- **Input config** (hand-edited by the author, or later by a GUI):
  observatory, date, file paths, and optional overrides -- a manual night
  start time and/or blocked-out time windows (e.g. a ToO). This is the
  "all inputs in one JSON" file.
- **night_meta.json** (written by the calculations script, read by the
  Excel builder): the *resolved* start time, twilight, and blocks, so the
  builder never hardcodes its own copy of the start time. Two independent
  hardcoded start-time constants (one per script) is exactly the bug this
  replaces -- see the 2026-10-06 ToO, where the Excel builder's start time
  silently diverged from the scheduler's.

Manual start times and blocks are real local wall-clock entries (what an
observer would type), so they are parsed as DST-aware local time via
`zoneinfo` -- Lick is America/Los_Angeles (PST/PDT depending on time of
year), Keck is Pacific/Honolulu (HST, no DST, but resolved the same way
for consistency). This is independent of whatever fixed-offset convention
a given script's own twilight printing already uses (e.g. Lick's
deliberate fixed-PST calendar-matching convention) -- only override/block
*input parsing* is DST-aware.

Created by JXP and Claude
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

OBSERVATORY_TZ = {
    'lick': ZoneInfo('America/Los_Angeles'),
    'keck': ZoneInfo('Pacific/Honolulu'),
}


@dataclass
class NightPlanConfig:
    observatory: str               # 'lick' or 'keck'
    date: str                      # 'YYYY-MM-DD', the evening (local) date
    targets_csv: str
    output_dir: str
    max_targets: int = 20
    start_override: Optional[str] = None   # 'HH:MM' or full ISO local datetime
    blocks: list = field(default_factory=list)  # [{'start': 'HH:MM'/ISO, 'end': ..., 'reason': str}]
    notes: Optional[str] = None
    # Instrument configuration and observing assumptions (2026-11-07, M4):
    # config = {grism, grating, dichroic, slit, binning}; CLI flags win.
    config: Optional[dict] = None
    seeing: Optional[float] = None         # FWHM arcsec
    mag_band: Optional[str] = None         # band of the mag column
    # Milestone 5 (T1.3, T3.4).
    airmass_rule: Optional[str] = None     # 'worst' | 'mid' | 'best'
    etc: Optional[str] = None              # registry name or 'pkg.mod:func'
    target_sn: Optional[float] = None      # per sub-exposure

    def tz(self):
        return OBSERVATORY_TZ[self.observatory]


def load_config(path) -> NightPlanConfig:
    with open(path) as f:
        data = json.load(f)
    data.setdefault('blocks', [])
    return NightPlanConfig(**data)


def save_config(config: NightPlanConfig, path):
    with open(path, 'w') as f:
        json.dump(asdict(config), f, indent=2)


def resolve_local_dt(date_str, time_spec, tz):
    """
    Resolve a manual-entry time into a tz-aware local datetime.

    Parameters
    ----------
    date_str : str
        The night's evening date, 'YYYY-MM-DD'.
    time_spec : str
        Either 'HH:MM' (rolled to the next calendar day if hour < 12,
        the same post-midnight convention used throughout this repo's
        twilight/window searches) or a full ISO datetime
        ('YYYY-MM-DDTHH:MM'), used as-is.
    tz : tzinfo
        Timezone to attach (DST-aware for Lick, fixed for Keck).

    Returns
    -------
    datetime (tz-aware)
    """
    if 'T' in time_spec:
        dt = datetime.fromisoformat(time_spec)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt

    hour, minute = (int(x) for x in time_spec.split(':'))
    base = datetime.strptime(date_str, '%Y-%m-%d')
    if hour < 12:
        base += timedelta(days=1)
    return base.replace(hour=hour, minute=minute, tzinfo=tz)


def resolve_blocks(date_str, blocks, tz):
    """Resolve a config's raw block entries into (start_dt, end_dt, reason) tuples."""
    resolved = []
    for b in blocks:
        start = resolve_local_dt(date_str, b['start'], tz)
        end = resolve_local_dt(date_str, b['end'], tz)
        resolved.append((start, end, b.get('reason', 'blocked')))
    return resolved


def save_night_meta(output_dir, **meta):
    """
    Write the resolved night_meta.json sidecar.

    Datetimes are serialized with isoformat(); the Excel builder re-parses
    them with datetime.fromisoformat(), which round-trips tz-aware ISO
    strings correctly.
    """
    serializable = {}
    for k, v in meta.items():
        if isinstance(v, datetime):
            serializable[k] = v.isoformat()
        elif isinstance(v, list) and v and isinstance(v[0], tuple):
            serializable[k] = [
                {'start': t[0].isoformat(), 'end': t[1].isoformat(), 'reason': t[2]}
                for t in v
            ]
        else:
            serializable[k] = v

    path = os.path.join(output_dir, 'night_meta.json')
    with open(path, 'w') as f:
        json.dump(serializable, f, indent=2)
    return path


def load_night_meta(output_dir):
    """Read night_meta.json back; returns None if it doesn't exist yet."""
    path = os.path.join(output_dir, 'night_meta.json')
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    for key in ('start_local', 'evening_twilight_local', 'morning_twilight_local'):
        if data.get(key):
            data[key] = datetime.fromisoformat(data[key])
    if 'blocks' in data:
        data['blocks'] = [
            (datetime.fromisoformat(b['start']), datetime.fromisoformat(b['end']), b['reason'])
            for b in data['blocks']
        ]
    return data
