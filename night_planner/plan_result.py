"""
PlanResult: the one normalized shape every instrument's night plan is
converted into, so the GUI (and anything else downstream) never has to
special-case Keck vs Lick.

Pure data only -- no astropy, no pandas. The per-instrument adapters in
night_planner/adapters.py do the translating; sun events are computed by
night_planner/sun_events.py.

Created by JXP and Claude
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


def _iso(dt):
    """isoformat() that tolerates None."""
    return dt.isoformat() if dt is not None else None


def _dt(value):
    """Parse an ISO string back to datetime, tolerating None."""
    return datetime.fromisoformat(value) if value else None


@dataclass
class SunEvents:
    """The six sun-altitude crossings the plan viewer marks on the timeline.

    Nautical is the -12 deg crossing, astronomical the -18 deg one; sunset
    and sunrise are the 0 deg crossings. All tz-aware local datetimes.
    """
    sunset: datetime
    dusk_nautical: datetime
    dusk_astronomical: datetime
    dawn_astronomical: datetime
    dawn_nautical: datetime
    sunrise: datetime

    def to_dict(self):
        return {k: _iso(v) for k, v in asdict(self).items()}


@dataclass
class ScheduledTarget:
    """One target as actually placed in the night.

    `start` is when the telescope starts moving (slew), `science_start`
    when photons start being collected, `end` when they stop. Between
    them: `slew_min` of slew, then `acq_min` of acquisition, so
    `science_start - start == slew_min + acq_min`. On instruments whose
    scheduler doesn't model slew as its own interval, both are 0 and
    `science_start == start`. `slew_reason` explains a slew longer than the
    base one (e.g. the Keck Dec +20 crossing), '' otherwise.
    """
    name: str
    ra_deg: float
    dec_deg: float
    mag: Optional[float]
    mode: str
    start: datetime
    science_start: datetime
    end: datetime
    slew_min: float = 0.0
    on_target_min: float = 0.0
    exposure_red: str = ''
    exposure_blue: str = ''
    airmass: Optional[float] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    notes: str = ''
    # Defaulted so a plan_result.json written before 2026-11-07 still loads.
    acq_min: float = 0.0
    slew_reason: str = ''
    # Detector readout inside [science_start, end], after the exposures:
    # end - science_start = on_target_min + readout_min (T1.1, 2026-11-07).
    readout_min: float = 0.0
    # Milestone 5 (T1.3, T3.4a). `airmass` is the airmass the ETC was run at
    # under `airmass_rule` ('' when no ETC was involved: MOS blocks, fixed
    # recipes, the empirical Kast rule); `airmass_min` the night's best.
    # S/N is median continuum per pixel: one sub-exposure, and all n_sub
    # combined (sqrt(n) x per-sub). None when the ETC reports none.
    airmass_min: Optional[float] = None
    airmass_rule: str = ''
    sn_sub_blue: Optional[float] = None
    sn_sub_red: Optional[float] = None
    sn_comb_blue: Optional[float] = None
    sn_comb_red: Optional[float] = None
    # Milestone 6 (T3.3): where on_target_min came from ('ETC', 'user',
    # 'empirical', 'MOS block', 'fixed recipe'), the ETC's own estimate
    # (shown beside a user time), and whether the target was required (full
    # time or nothing).
    time_source: str = ''
    etc_min: Optional[float] = None
    required: bool = False
    # FFFF-PZ tags and DM, for the plan table (T2.5).
    tags: str = ''
    dm: Optional[float] = None
    # The S/N per sub-exposure the ETC sized this target for (2026-11-10):
    # its own target_sn (table column or --set-sn) when target_sn_own, else
    # the plan's. None when no S/N was involved (user time, MOS block,
    # fixed recipe, the empirical Kast rule).
    target_sn: Optional[float] = None
    target_sn_own: bool = False

    def to_dict(self):
        d = asdict(self)
        for k in ('start', 'science_start', 'end', 'window_start', 'window_end'):
            d[k] = _iso(d[k])
        return d


@dataclass
class TargetDecision:
    """Why one target from the original table is in, or out, of the plan.

    `stage` is the filter stage the target was decided at, so the GUI can
    group rejections by cause (selection rule / sky / mask / scheduling)
    rather than showing one flat list.
    """
    name: str
    ra_deg: Optional[float]
    dec_deg: Optional[float]
    mag: Optional[float]
    status: str      # 'scheduled' | 'rejected'
    stage: str
    reason: str
    # When the target was actually up (AM<2 window), where the scheduler
    # knew it. Lets a caller tell "ran out of time but still rising" from
    # "set hours ago", which decides whether forcing it can work at all.
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    # Defaulted, not required: from_dict() splats a saved row straight into
    # this constructor, so a plan_result.json written before priority existed
    # must still load.
    priority: Optional[float] = None

    def to_dict(self):
        d = asdict(self)
        d['window_start'] = _iso(d['window_start'])
        d['window_end'] = _iso(d['window_end'])
        return d


@dataclass
class PlanResult:
    """A complete night plan, instrument-independent."""
    instrument: str
    telescope: str
    date: str
    output_dir: str
    timezone: str
    sun: SunEvents
    night_start: datetime
    night_end: datetime
    schedule: list = field(default_factory=list)    # [ScheduledTarget]
    decisions: list = field(default_factory=list)   # [TargetDecision]
    blocks: list = field(default_factory=list)      # [(start, end, reason)]
    overheads: list = field(default_factory=list)   # [(start, end, label)]
    # How this plan was produced: {'instrument': str, 'argv': [str]}. Kept so
    # a plan can be re-run with one thing changed (force a rejected target,
    # say) without the caller having to remember the original inputs.
    request: dict = field(default_factory=dict)
    # What this plan assumed (readout per frame, ETC configuration, ...),
    # for the plan page's assumptions panel. A value nobody has given us is
    # recorded as 'NOT SET', never silently 0.
    assumptions: dict = field(default_factory=dict)
    # The instrument configuration the plan was made with (grism, grating,
    # dichroic, slit, binning), plus 'seeing' and 'mag_band'. Empty for
    # plans written before 2026-11-07 (M4).
    config: dict = field(default_factory=dict)

    def idle_gaps(self):
        """Stretches of the night with nothing scheduled and nothing blocking.

        Computed from the schedule rather than tracked by the schedulers,
        because 'idle' is the complement of everything else and only the
        assembled plan knows all of it. Standards and focus
        count as busy -- they're planned work, not dead time, and counting
        them as idle overstates what could have held another target.
        Returns [(start, end)] tz-aware, bounded by night_start/night_end.
        """
        busy = [(t.start, t.end) for t in self.schedule]
        busy += [(b[0], b[1]) for b in self.blocks]
        busy += [(o[0], o[1]) for o in self.overheads]
        busy.sort()

        gaps = []
        cursor = self.night_start
        for start, end in busy:
            if start > cursor:
                gaps.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < self.night_end:
            gaps.append((cursor, self.night_end))
        return gaps

    def overruns(self):
        """Planned overheads that extend past the end of the night.

        A tight plan can leave less time after the last target than the
        closing slew and morning standard need. It should be visible
        rather than silently clipped. (Calibrations aren't planned blocks;
        they live on the Observing log page.)
        """
        return [{'label': label, 'start': start, 'end': end,
                 'minutes_past_end': (end - self.night_end).total_seconds() / 60}
                for start, end, label in self.overheads
                if end > self.night_end]

    def summary(self):
        """Headline numbers for the plan viewer."""
        on_target = sum(t.on_target_min for t in self.schedule)
        slew = sum(t.slew_min for t in self.schedule)
        acq = sum(t.acq_min for t in self.schedule)
        readout = sum(t.readout_min for t in self.schedule)
        overhead = sum((o[1] - o[0]).total_seconds() / 60 for o in self.overheads)
        idle = sum((g[1] - g[0]).total_seconds() / 60 for g in self.idle_gaps())
        night = (self.night_end - self.night_start).total_seconds() / 60
        return {
            'n_scheduled': len(self.schedule),
            'n_rejected': sum(d.status == 'rejected' for d in self.decisions),
            'on_target_min': on_target,
            'slew_min': slew,
            'acq_min': acq,
            'readout_min': readout,
            'overhead_min': overhead,
            'idle_min': idle,
            'night_min': night,
            'utilization': (on_target / night) if night else 0.0,
        }

    def to_dict(self):
        """JSON-serializable form, for the API layer."""
        return {
            'instrument': self.instrument,
            'telescope': self.telescope,
            'date': self.date,
            'output_dir': self.output_dir,
            'timezone': self.timezone,
            'sun': self.sun.to_dict(),
            'night_start': _iso(self.night_start),
            'night_end': _iso(self.night_end),
            'schedule': [t.to_dict() for t in self.schedule],
            'decisions': [d.to_dict() for d in self.decisions],
            'blocks': [{'start': _iso(b[0]), 'end': _iso(b[1]), 'reason': b[2]}
                       for b in self.blocks],
            'overheads': [{'start': _iso(o[0]), 'end': _iso(o[1]), 'label': o[2]}
                          for o in self.overheads],
            'idle_gaps': [{'start': _iso(g[0]), 'end': _iso(g[1])}
                          for g in self.idle_gaps()],
            'overruns': [{**o, 'start': _iso(o['start']), 'end': _iso(o['end'])}
                         for o in self.overruns()],
            'request': dict(self.request),
            'assumptions': dict(self.assumptions),
            'config': dict(self.config),
            'summary': self.summary(),
        }

    @classmethod
    def from_dict(cls, data):
        """
        Rebuild a PlanResult from to_dict() output.

        `idle_gaps` and `summary` are derived, so they're ignored here and
        recomputed on demand -- a round trip can't disagree with itself.
        """
        sun = SunEvents(**{k: _dt(v) for k, v in data['sun'].items()})

        schedule = []
        for t in data['schedule']:
            t = dict(t)
            for key in ('start', 'science_start', 'end',
                         'window_start', 'window_end'):
                t[key] = _dt(t[key])
            schedule.append(ScheduledTarget(**t))

        return cls(
            instrument=data['instrument'], telescope=data['telescope'],
            date=data['date'], output_dir=data['output_dir'],
            timezone=data['timezone'], sun=sun,
            night_start=_dt(data['night_start']),
            night_end=_dt(data['night_end']),
            schedule=schedule,
            decisions=[TargetDecision(**{**d,
                                          'window_start': _dt(d.get('window_start')),
                                          'window_end': _dt(d.get('window_end'))})
                       for d in data['decisions']],
            blocks=[(_dt(b['start']), _dt(b['end']), b['reason'])
                    for b in data['blocks']],
            overheads=[(_dt(o['start']), _dt(o['end']), o['label'])
                       for o in data.get('overheads', [])],
            request=dict(data.get('request') or {}),
            assumptions=dict(data.get('assumptions') or {}),
            config=dict(data.get('config') or {}),
        )
