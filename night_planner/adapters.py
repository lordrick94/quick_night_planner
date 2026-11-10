"""
Per-instrument adapters: translate what each instrument's scheduler
actually returns into the one normalized PlanResult shape.

These live here rather than inside the instrument scripts on purpose. The
scripts are per-run one-offs (`keck_2026oct06_*`, `lick_2026b02_night2_*`)
that get copied for the next night; the translation is stable and
shouldn't be copy-pasted along with them. Keyed by instrument, a central
adapter keeps working when next month's script is a copy with the same
function names.

Created by JXP and Claude
"""

import pandas as pd
from astropy import units as u
from astropy.coordinates import EarthLocation
from zoneinfo import ZoneInfo

from .plan_result import PlanResult, ScheduledTarget, TargetDecision
from .targets_io import DEFAULT_PRIORITY
from .sun_events import find_sun_events

# Site constants, matching what each instrument script already uses.
# Verified against astropy's EarthLocation.of_site() (IRAF Observatory
# Database); see keck_2026oct06_calculations.py / lick_2026b02_calculations.py.
# Morning flux standard (Feige 110), for the closing-slew estimate.
MORNING_STANDARD_DEC = -5.1656

SITES = {
    'lris': {
        'telescope': 'Keck I',
        'location': EarthLocation(lat=19.828333 * u.deg, lon=-155.478333 * u.deg,
                                   height=4160 * u.m),
        'tz': ZoneInfo('Pacific/Honolulu'),
        # Longslit footprint drawn on finder charts, matching what
        # chime_ffff_pz_finder draws for LRIS.
        'slit_length_arcmin': 2.9,      # 175 arcsec, per chime_ffff_pz
        'slit_width_arcsec': 1.0,
        'starlist_style': 'keck',
    },
    'kast': {
        'telescope': 'Shane 3m (Lick)',
        'location': EarthLocation(lat=37.3414 * u.deg, lon=-121.6429 * u.deg,
                                   height=1283 * u.m),
        'tz': ZoneInfo('America/Los_Angeles'),
        # Kast's longslit is ~145 arcsec, and this programme's standard
        # setup uses the 2 arcsec slit (see Lick-2026B-01 HOWTO).
        'slit_length_arcmin': 2.42,     # 145 arcsec, per chime_ffff_pz
        'slit_width_arcsec': 2.0,
        'starlist_style': 'lick',
        # The Shane sets a Cassegrain tub readout, not a sky PA
        # (helpful_scripts/calcint.c); see night_planner.lick_tub.
        'rotator': 'cass_tub',
    },
}


def _f(value, default=None):
    """float() that passes NaN/None through as `default`."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value):
    """bool() that turns None/NaN into False."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return False
    return bool(value)


def _s(value):
    """str() that turns None/NaN into ''."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ''
    return str(value)


def _with_priority(value, reason):
    """Prefix a decision's reason with its priority tier, when it has one.

    The rejection page's whole job is explaining a judgement, and after
    tiered scheduling "ran out of window" is only half the story -- which
    tier the target was competing in is the other half. A plan where
    everything sits in the default tier gains nothing from the label, so
    it is left off entirely rather than stamping P1 on every row.
    """
    prio = _f(value)
    if prio is None or prio == DEFAULT_PRIORITY:
        return reason
    return f'P{prio:g} -- {reason}'


def _dt(value):
    """Coerce a pandas/py datetime to a plain tz-aware datetime, or None."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, str):
        value = pd.to_datetime(value)
    return value.to_pydatetime() if hasattr(value, 'to_pydatetime') else value


def keck_lris(out):
    """
    Build a PlanResult from scripts/keck_2026oct06_calculations.run()'s output.

    Parameters
    ----------
    out : dict
        As returned by that module's run().

    Returns
    -------
    PlanResult
    """
    site = SITES['lris']
    results_df = out['results_df']
    selected = out['selected']
    skips = out['skips']

    schedule = []
    for _, r in selected.iterrows():
        schedule.append(ScheduledTarget(
            name=r['TNS'],
            ra_deg=_f(r['RA_deg']),
            dec_deg=_f(r['Dec_deg']),
            mag=_f(r['mag_r']),
            mode=r['lris_mode'],
            start=_dt(r['scheduled_start']),
            science_start=_dt(r['science_start']),
            end=_dt(r['scheduled_end']),
            slew_min=_f(r['slew_min'], 0.0),
            acq_min=_f(r.get('acq_min'), 0.0),
            slew_reason=_s(r.get('slew_reason')),
            readout_min=_f(r.get('readout_min'), 0.0),
            on_target_min=_f(r['on_target_min'], 0.0),
            exposure_red=str(r.get('red_exp', '')),
            exposure_blue=str(r.get('blue_exp', '')),
            # The airmass the ETC actually ran at (T1.3); the night's best
            # for blocks that don't depend on airmass.
            airmass=_f(r.get('airmass_used'), _f(r.get('min_airmass'))),
            airmass_min=_f(r.get('min_airmass')),
            airmass_rule=_s(r.get('airmass_rule')),
            sn_sub_blue=_f(r.get('sn_sub_blue')),
            sn_sub_red=_f(r.get('sn_sub_red')),
            sn_comb_blue=_f(r.get('sn_comb_blue')),
            sn_comb_red=_f(r.get('sn_comb_red')),
            time_source=_s(r.get('time_source')),
            etc_min=_f(r.get('etc_min')),
            required=_bool(r.get('required')),
            tags=_s(r.get('tags')),
            dm=_f(r.get('DM')),
            window_start=_dt(r.get('window_start')),
            window_end=_dt(r.get('window_end')),
            notes=str(r.get('info') or ''),
        ))

    decisions = _keck_decisions(out, results_df, selected, skips)
    overheads = _keck_overheads(out['start_local'], schedule)

    night_end = out['twilight']['morning_hst']
    return PlanResult(
        instrument='lris',
        telescope=site['telescope'],
        date=out['date'],
        output_dir=out['output_dir'],
        timezone=str(site['tz']),
        sun=find_sun_events(out['date'], site['location'], site['tz']),
        night_start=out['start_local'],
        night_end=night_end,
        schedule=schedule,
        decisions=decisions,
        blocks=list(out['blocks']),
        overheads=overheads,
        assumptions=plan_assumptions('lris', out.get('config'),
                                     out.get('seeing'), out.get('mag_band'),
                                     out.get('etc_opts')),
        config=_plan_config(out),
    )


def _keck_overheads(night_start, schedule):
    """
    The non-science blocks the Keck sequence always runs.

    Mirrors print_night_plan()/build_keck_night_plan(): evening standard
    and focus before the first target, then a slew to the morning
    standard and the standard itself after the last one. Emitting them
    explicitly keeps 'idle' meaning time that could have held another
    target, instead of silently counting planned work.

    Arcs and flats are deliberately absent (2026-11-07, T1.5): the observer
    decides when to take them, and they're tracked on the Observing log
    page's calibrations checklist rather than as timeline blocks.
    """
    from datetime import timedelta
    from keck_overheads import keck_slew_minutes

    out, cursor = [], night_start
    for label, minutes in (('Evening standard (BD+28 4211)', 5),
                            ('Focus check', 5)):
        out.append((cursor, cursor + timedelta(minutes=minutes), label))
        cursor += timedelta(minutes=minutes)

    if not schedule:
        return out

    cursor = max(t.end for t in schedule)
    last_dec = sorted(schedule, key=lambda t: t.end)[-1].dec_deg
    closing = (('Slew to Feige 110', keck_slew_minutes(last_dec, MORNING_STANDARD_DEC)),
               ('Morning standard (Feige 110)', 5))
    for label, minutes in closing:
        out.append((cursor, cursor + timedelta(minutes=minutes), label))
        cursor += timedelta(minutes=minutes)
    return out


def _keck_decisions(out, results_df, selected, skips):
    """
    One TargetDecision per target in the original pulled table.

    Mirrors the staging in keck_2026oct06_rejection_analysis.py (a per-run
    script, now kept privately with the Keck-2026B-02 plan):
    1. Keck selection -> 2. Sky -> 2b. Mask -> 3. Scheduling.
    """
    # Imported lazily: the instrument module is on sys.path only once
    # night_planner.cli has added scripts/ (see _load_module there).
    from keck_2026oct06_calculations import KECK_MAG_FAINT_LIMIT, LICK_DEC_LIMIT

    from .targets_io import load_targets

    pulled = load_targets(out['targets_csv'])
    res = results_df.set_index('TNS')
    sel = selected.set_index('TNS') if len(selected) else pd.DataFrame()

    window = (None, None)
    decisions = []
    for _, p in pulled.iterrows():
        tns, mag, dec = p['name'], _f(p['mag']), _f(p['dec_deg'])
        ra = _f(p['ra_deg'])

        if tns not in res.index:
            status, stage = 'rejected', '1. Keck selection'
            reason = (f"mag {mag:.2f} <= {KECK_MAG_FAINT_LIMIT} and Dec "
                      f"{dec:+.1f} <= {LICK_DEC_LIMIT} (Lick can take it)")
        elif str(res.loc[tns, 'limit_reason']).startswith('No mask'):
            status, stage = 'rejected', '2b. Mask'
            reason = res.loc[tns, 'limit_reason']
        elif not res.loc[tns, 'observable']:
            r = res.loc[tns]
            status, stage = 'rejected', '2. Sky'
            reason = (f"{r['limit_reason']} (min AM {r['min_airmass']:.2f}, "
                      f"{r['observable_hours']:.2f} h at AM<2.0; need >0.5 h)")
        elif len(sel) and tns in sel.index:
            s = sel.loc[tns]
            status, stage = 'scheduled', '3. Scheduling'
            acq = s.get('acq_min')
            acq_txt = (f" + acq {int(acq)} min"
                       if acq is not None and pd.notna(acq) else '')
            reason = (f"slew {_dt(s['scheduled_start']):%H:%M} "
                      f"({int(s['slew_min'])} min{acq_txt}), on target "
                      f"{_dt(s['science_start']):%H:%M}-{_dt(s['scheduled_end']):%H:%M} "
                      f"({s['on_target_min']:g} min, {s['lris_mode']})")
        else:
            status, stage = 'rejected', '3. Scheduling'
            skip = skips.get(tns)
            if isinstance(skip, dict):
                reason = skip['reason']
                window = (skip.get('window_start'), skip.get('window_end'))
            else:
                reason = skip or 'not reached (max_targets hit)'
                window = (None, None)

        # Priority tier, as on the Kast path (T1.6): read from the table.
        prio = _f(p.get('priority'))
        decisions.append(TargetDecision(
            name=tns, ra_deg=ra, dec_deg=dec, mag=mag,
            status=status, stage=stage, reason=_with_priority(prio, reason),
            window_start=_dt(window[0]), window_end=_dt(window[1]),
            priority=prio))

    # A forced target the scheduler could not place must not vanish --
    # the caller asked for it by name.
    for failure in out.get('forced_failures') or []:
        decisions = [d for d in decisions if d.name != failure['TNS']]
        row = res.loc[failure['TNS']] if failure['TNS'] in res.index else None
        decisions.append(TargetDecision(
            name=failure['TNS'],
            ra_deg=_f(row['RA_deg']) if row is not None else None,
            dec_deg=_f(row['Dec_deg']) if row is not None else None,
            mag=_f(row['mag_r']) if row is not None else None,
            status='rejected', stage='4. Forced',
            reason=f"forced but not placed -- {failure['reason']}"))
    return decisions


def _attribute_kast_slews(schedule, night_start):
    """
    Charge the inter-target gap to the slew that actually fills it.

    The Kast scheduler advances its cursor by the per-target gap
    (lick_gap_minutes(): slew + acquisition) after each target rather than
    emitting a slew row, so without this every slew would surface as idle
    time in the viewer. Walk the sorted schedule and, where the preceding
    target (or the evening overheads) ends at least one gap earlier, extend
    this target's start back over that gap and split it into slew and
    acquisition (2026-11-07: 2 min slew + 3 min acquisition, Lordrick).

    Must use the same gap as the scheduler (kast_calculations reads it from
    instrument_params too); if the two ever differ, slews turn back into
    idle time.
    """
    from .instrument_params import LICK_ACQ_MIN, LICK_SLEW_MIN, lick_gap_minutes
    from .sky import advance

    gap = lick_gap_minutes()
    prev_end = night_start
    for target in schedule:
        # Elapsed time, not wall clock: subtracting a timedelta across a
        # spring-forward gap lands the slew *after* the exposure it
        # precedes, which is how a 60-minute block came out spanning
        # five minutes of UTC.
        slew_start = advance(target.science_start, -gap)
        if slew_start >= prev_end:
            target.start = slew_start
            target.slew_min = float(LICK_SLEW_MIN)
            target.acq_min = float(LICK_ACQ_MIN)
        prev_end = target.end


def lick_kast(out):
    """
    Build a PlanResult from
    scripts/lick_2026b02_night2_calculations.run()'s output.

    That scheduler already carries its own per-row `skip_reason` and a
    `scheduled` flag, so decisions come straight off the two schedule
    frames (FRB repeats + spare/filler) rather than being reconstructed.
    """
    site = SITES['kast']

    frames = [f for f in (out['frb_sched'], out['spare_sched']) if len(f)]
    sched_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    schedule, decisions = [], []
    for _, r in sched_df.iterrows():
        name = r['TNS']
        ra_deg = _f(r.get('RA_hours'))
        ra_deg = ra_deg * 15.0 if ra_deg is not None else None
        dec_deg, mag = _f(r.get('Dec_deg')), _f(r.get('mag_r'))

        if r.get('scheduled'):
            start, end = _dt(r['start_pst']), _dt(r['end_pst'])
            # duration_min is the whole block; readout (T1.1) sits inside it,
            # after the exposures. Partial and forced rows are allocations
            # with no readout split out.
            readout = _f(r.get('readout_min'), 0.0)
            schedule.append(ScheduledTarget(
                name=name, ra_deg=ra_deg, dec_deg=dec_deg, mag=mag,
                mode='longslit',
                start=start, science_start=start, end=end,
                slew_min=0.0,  # Kast scheduler models slew as a gap, not a block
                readout_min=readout,
                on_target_min=_f(r.get('duration_min'), 0.0) - readout,
                airmass=_f(r.get('airmass_used')),
                airmass_rule=_s(r.get('airmass_rule')),
                sn_sub_blue=_f(r.get('sn_sub_blue')),
                sn_sub_red=_f(r.get('sn_sub_red')),
                sn_comb_blue=_f(r.get('sn_comb_blue')),
                sn_comb_red=_f(r.get('sn_comb_red')),
                time_source=_s(r.get('time_source')),
                etc_min=_f(r.get('etc_min')),
                required=_bool(r.get('required')),
                tags=_s(r.get('tags')),
                dm=_f(r.get('DM')),
                exposure_red=str(r.get('red_side', '')),
                exposure_blue=str(r.get('blue_side', '')),
                window_start=_dt(r.get('entry_pst')),
                window_end=_dt(r.get('exit_pst')),
                notes=str(r.get('skip_reason') or ''),
            ))
            decisions.append(TargetDecision(
                name=name, ra_deg=ra_deg, dec_deg=dec_deg, mag=mag,
                status='scheduled', stage='3. Scheduling',
                priority=_f(r.get('priority')),
                reason=_with_priority(
                    r.get('priority'),
                    f"{start:%H:%M}-{end:%H:%M} "
                    f"({_f(r.get('duration_min'), 0):.0f} min)")))
        else:
            decisions.append(TargetDecision(
                name=name, ra_deg=ra_deg, dec_deg=dec_deg, mag=mag,
                status='rejected', stage='3. Scheduling',
                priority=_f(r.get('priority')),
                reason=_with_priority(
                    r.get('priority'),
                    str(r.get('skip_reason') or 'not scheduled'))))

    # Targets that never reached the scheduler: no HA-legal window tonight.
    scheduled_or_skipped = {d.name for d in decisions}
    for frame in (out['repeat_analysis'], out['spare_analysis']):
        for _, r in frame.iterrows():
            if r['TNS'] in scheduled_or_skipped or r.get('observable'):
                continue
            ra_deg = _f(r.get('RA_hours'))
            # analyze_targets() already worked out *why* -- above the +82
            # mechanical limit reads very differently from never entering
            # the HA window, and collapsing both to one sentence throws
            # away the only thing the observer can act on.
            reason = str(r.get('limit_reason') or '').strip()
            decisions.append(TargetDecision(
                name=r['TNS'],
                ra_deg=ra_deg * 15.0 if ra_deg is not None else None,
                dec_deg=_f(r.get('Dec_deg')), mag=_f(r.get('mag_r')),
                status='rejected', stage='2. Sky',
                priority=_f(r.get('priority')),
                reason=_with_priority(
                    r.get('priority'),
                    reason or 'never HA-legal tonight (Shane mount limit)')))

    # A forced target the scheduler could not place must not vanish --
    # the caller asked for it by name, and silence reads as "it worked".
    res = out['repeat_analysis'].set_index('TNS')
    for failure in out.get('forced_failures') or []:
        decisions = [d for d in decisions if d.name != failure['TNS']]
        row = res.loc[failure['TNS']] if failure['TNS'] in res.index else None
        ra_deg = _f(row['RA_hours']) if row is not None else None
        decisions.append(TargetDecision(
            name=failure['TNS'],
            ra_deg=ra_deg * 15.0 if ra_deg is not None else None,
            dec_deg=_f(row['Dec_deg']) if row is not None else None,
            mag=_f(row['mag_r']) if row is not None else None,
            status='rejected', stage='4. Forced',
            priority=_f(row['priority']) if row is not None else None,
            reason=_with_priority(
                row['priority'] if row is not None else None,
                f"forced but not placed -- {failure['reason']}")))

    schedule.sort(key=lambda t: t.start)
    overheads = _kast_overheads(out['start_local'])
    _attribute_kast_slews(schedule, overheads[-1][1] if overheads
                          else out['start_local'])

    return PlanResult(
        instrument='kast',
        telescope=site['telescope'],
        date=out['date'],
        output_dir=out['output_dir'],
        timezone=str(site['tz']),
        sun=find_sun_events(out['date'], site['location'], site['tz']),
        night_start=out['start_local'],
        night_end=out['night_end'],
        schedule=schedule,
        decisions=decisions,
        blocks=list(out['blocks']),
        overheads=overheads,
        assumptions=plan_assumptions('kast', out.get('config'),
                                     out.get('seeing'), out.get('mag_band'),
                                     out.get('etc_opts')),
        config=_plan_config(out),
    )


def _plan_config(out):
    """The run's resolved configuration, with seeing and band, for PlanResult."""
    config = dict(out.get('config') or {})
    if out.get('seeing') is not None:
        config['seeing'] = out['seeing']
    if out.get('mag_band'):
        config['mag_band'] = out['mag_band']
    return config


def plan_assumptions(instrument, config=None, seeing=None, mag_band=None,
                     etc_opts=None):
    """
    What a plan assumed, for the plan page's assumptions panel (T2.8).

    Parameters
    ----------
    instrument : str
    config : dict, optional
        The configuration used; defaults to DEFAULT_CONFIG[instrument].
    seeing : float, optional
        FWHM arcsec; defaults to DEFAULT_SEEING[instrument].
    mag_band : str, optional
        Plan-wide magnitude band; defaults to DEFAULT_MAG_BAND.
    etc_opts : dict, optional
        The run's resolved options (etc, target_sn, n_sub_min,
        airmass_rule); defaults to the instrument's.

    Returns
    -------
    dict of label -> value (str or number). Values nobody has given us are
    'NOT SET', never 0.
    """
    from .instrument_params import (DEFAULT_CONFIG, DEFAULT_MAG_BAND,
                                    DEFAULT_SEEING, LICK_ACQ_MIN, LICK_SLEW_MIN,
                                    config_label, etc_config, etc_filter,
                                    readout_arms, readout_seconds)

    config = config if config is not None else DEFAULT_CONFIG.get(instrument, {})
    seeing = seeing if seeing is not None else DEFAULT_SEEING.get(instrument)
    mag_band = mag_band or DEFAULT_MAG_BAND
    arms = readout_arms(instrument, config)
    per_frame = readout_seconds(instrument, config)
    _, standins = etc_config(instrument, config)
    out = {
        'configuration': config_label(instrument, config),
        'seeing [arcsec]': f'{seeing:g}',
        'magnitude band': (f'{mag_band} (ETC filter {etc_filter(mag_band)}); '
                           f'a per-row mag_band column wins'),
        'readout [s per frame]': (f"{per_frame:g} (blue {arms['blue']:g}, red "
                                  f"{arms['red']:g}; arms in parallel)"
                                  if per_frame is not None else 'NOT SET'),
        'readout applies to': ('exposure recipes; MOS blocks and forced / '
                               'partial allocations already include it'),
    }
    if instrument == 'lris':
        from keck_overheads import (KECK_ACQ_MIN, KECK_SLEW_BASE_MIN,
                                    KECK_SLEW_DEC_CROSS_MIN)
        out.update({
            'slew [min]': (f'{KECK_SLEW_BASE_MIN} base; {KECK_SLEW_DEC_CROSS_MIN} '
                           'for a S\N{RIGHTWARDS ARROW}N Dec +20\N{DEGREE SIGN} crossing'),
            'acquisition [min]': (f"{KECK_ACQ_MIN['longslit']} longslit, "
                                  f"{KECK_ACQ_MIN['mask']} mask"),
            'mask buffer [min]': '+5 per mask, inside the MOS block (kept, Q7)',
        })
    elif instrument == 'kast':
        out.update({'slew [min]': f'{LICK_SLEW_MIN}',
                    'acquisition [min]': f'{LICK_ACQ_MIN}'})
    from .etc import DEFAULT_ETC, N_SUB_MIN, TARGET_SN, empirical_kast_etc, load_etc
    opts = dict(etc_opts or {})
    etc_name = opts.get('etc') or DEFAULT_ETC.get(instrument, '')
    empirical = bool(etc_name) and load_etc(etc_name) is empirical_kast_etc
    if empirical:
        out['exposure model'] = ('empirical Kast magnitude rule (--etc empirical): '
                                 'no airmass, seeing, band or S/N dependence')
    else:
        out['exposure model'] = (f'{etc_name} ETC'
                                 + (' (UCO/Lick, etc.ucolick.org)'
                                    if etc_name in ('lris', 'kast') else ''))
        out['target S/N'] = (f"{opts.get('target_sn', TARGET_SN.get(instrument)):g} "
                             f"per sub-exposure (median continuum per pixel), "
                             f">= {opts.get('n_sub_min', N_SUB_MIN.get(instrument))} "
                             f"sub-exposures")
        out['airmass rule'] = (f"{opts.get('airmass_rule', 'worst')}: the ETC is run "
                               'at that airmass over each target\'s scheduled '
                               'science span')
    if instrument == 'lris':
        out['MOS blocks'] = 'operational allocations: no ETC, no airmass dependence'
    if standins and not empirical:
        out['ETC stand-in'] = '; '.join(standins)
    return out


def _kast_overheads(night_start):
    """
    The opening Kast overheads: dome-open focus, then the evening standard.

    kast_calculations starts science after them (FOCUS_MINUTES +
    STD_STAR_MINUTES), but used to emit no blocks, so the viewer drew them
    as idle (fixed 2026-11-07, T1.2). Both lengths are read from the
    scheduler so the two can't drift.

    Parameters
    ----------
    night_start : datetime

    Returns
    -------
    list of (start, end, label)
    """
    from kast_calculations import FOCUS_MINUTES, STD_STAR_MINUTES

    from .sky import advance

    focus_end = advance(night_start, FOCUS_MINUTES)
    return [(night_start, focus_end, 'Focus'),
            (focus_end, advance(focus_end, STD_STAR_MINUTES),
             'Evening standard')]


ADAPTERS = {
    'lris': keck_lris,
    'kast': lick_kast,
}
