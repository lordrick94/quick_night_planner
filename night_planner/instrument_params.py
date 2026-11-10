"""
Instrument-specific numbers and rules, in one place.

Created by JXP and Claude

Plain dicts and small functions only. Each value carries its source.
A value nobody has given us stays None, and callers show it as NOT SET.
They never quietly use 0 or a guess.

Keck slew and acquisition times stay in scripts/keck_overheads.py. This
module holds everything else: default configurations, calibration rules
and the night checklist (Milestone 1). Later milestones add readout,
ETC options and limits (see
claude_prompts/development/user_comments_implementation.md).
"""

import re

# --------------------------------------------------------------------
# Default instrument configuration
# --------------------------------------------------------------------

# LRIS: the setup scripts/lris_etc.py models for CHIME/FRB host
# spectroscopy (per the author, 2026-09-10).
# Kast: the standard Lick setup from night_planner/estimate_kast_exposures.py
# (2026B-01).
DEFAULT_CONFIG = {
    'lris': {'grism': 'B600', 'grating': '600/7500', 'dichroic': 'D560',
             'slit': 1.0, 'binning': '2x2'},
    'kast': {'grism': 'G2', 'grating': '600/7500', 'dichroic': 'd57',
             'slit': 2.0, 'binning': '1x1', 'read_mode': 'slow'},
}

# Seeing (arcsec, FWHM) assumed when none is given. LRIS: lris_etc.py's
# DEFAULT_SEEING (0.8"). Kast: the UCO ETC Kast form's own default (1.5"),
# read from https://etc.ucolick.org/web_s2n/kast on 2026-11-07.
DEFAULT_SEEING = {'lris': 0.8, 'kast': 1.5}
DEFAULT_MAG_BAND = 'r'

# Display names for ETC grism codes, so labels read like the instrument.
GRISM_NAMES = {'kast': {'G2': '600/4310', 'G3': '830/3460'}}

# What the UCO/Lick ETC can model (forms read 2026-11-07). LRIS B400 and
# B1200 are on the form but return empty spectra (verified 2026-09-10), so
# they stay out until re-tested.
ETC_OPTIONS = {
    'lris': {'grism': ['B300', 'B600'],
             'grating': ['600/7500', '600/10000', '1200/9000', '400/8500',
                         '831/8200'],
             'dichroic': ['D560', 'D460', 'D500', 'D680'],
             'slit': [0.7, 1.0, 1.5],
             'binning': ['1x1', '2x1', '2x2', '3x1']},
    'kast': {'grism': ['G2', 'G3'],
             'grating': ['600/7500'],
             'dichroic': ['d55', 'd46', 'd57'],
             'slit': [1.0, 1.5, 2.0],
             'binning': ['1x1', '2x1', '2x2', '3x1']},
}

# Kast's real d57 dichroic isn't on the ETC form. The ETC is run with d55
# instead (Lordrick, 2026-11-07), and the plan's assumptions say so.
ETC_STANDIN = {'kast': {'dichroic': {'d57': 'd55'}}}

# Magnitude band -> UCO ETC filter file (the form's ffilter values,
# 2026-11-07). Lowercase ugriz are SDSS; uppercase B/V are Buser and R/I
# are Cousins.
ETC_FILTERS = {'u': 'sdss_u.dat', 'g': 'sdss_g.dat', 'r': 'sdss_r.dat',
               'i': 'sdss_i.dat', 'z': 'sdss_z.dat', 'B': 'Buser_B.dat',
               'V': 'Buser_V.dat', 'R': 'Cousins_R.dat', 'I': 'Cousins_I.dat'}


class ConfigError(ValueError):
    """A configuration (or band) the ETC can't model."""


def validate_config(instrument, config):
    """
    Check a configuration against what the ETC can model.

    Parameters
    ----------
    instrument : str
    config : dict
        Keys from ETC_OPTIONS[instrument] (grism, grating, dichroic, slit,
        binning); others are ignored.

    Returns
    -------
    dict : the config with slit as float.

    Raises
    ------
    ConfigError with a readable message naming the allowed values.
    """
    options = ETC_OPTIONS.get(instrument)
    if options is None:
        raise ConfigError(f'no ETC options known for {instrument!r}')
    clean = dict(config)
    for key, allowed in options.items():
        if key not in clean or clean[key] is None:
            continue
        value = clean[key]
        if key == 'slit':
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ConfigError(f'slit must be a number, got {clean[key]!r}')
            ok = any(abs(value - a) < 1e-6 for a in allowed)
        else:
            value = str(value)
            ok = value in allowed
        if not ok:
            raise ConfigError(
                f'{instrument} {key} {clean[key]!r} is not something the ETC can '
                f'model; choose one of {", ".join(str(a) for a in allowed)}')
        clean[key] = value
    return clean


def etc_filter(band):
    """
    The ETC filter file for a magnitude band.

    Parameters
    ----------
    band : str
        e.g. 'r', 'g', 'R'.

    Returns
    -------
    str, e.g. 'sdss_r.dat'.

    Raises
    ------
    ConfigError for a band the ETC doesn't offer.
    """
    band = str(band or DEFAULT_MAG_BAND).strip()
    if band not in ETC_FILTERS:
        raise ConfigError(f'magnitude band {band!r} is not offered by the ETC; '
                          f'choose one of {", ".join(ETC_FILTERS)}')
    return ETC_FILTERS[band]


def etc_config(instrument, config):
    """
    The configuration actually sent to the ETC, with stand-ins applied
    (Kast d57 -> d55).

    Parameters
    ----------
    instrument : str
    config : dict

    Returns
    -------
    (etc_config, notes) : (dict, list of str)
    """
    out, notes = dict(config), []
    for key, mapping in ETC_STANDIN.get(instrument, {}).items():
        if out.get(key) in mapping:
            notes.append(f'ETC run with {key} {mapping[out[key]]} '
                         f'(setup: {out[key]}; not offered by the ETC)')
            out[key] = mapping[out[key]]
    return out, notes


def add_config_args(parser, instrument):
    """
    Add the configuration / seeing / band flags to an instrument's parser.

    Parameters
    ----------
    parser : argparse.ArgumentParser
    instrument : str

    Returns
    -------
    None (the parser is modified).
    """
    d = DEFAULT_CONFIG[instrument]
    parser.add_argument('--grism', help=f"Blue grism [{d['grism']}].")
    parser.add_argument('--grating', help=f"Red grating [{d['grating']}].")
    parser.add_argument('--dichroic', help=f"Dichroic [{d['dichroic']}].")
    parser.add_argument('--slit', type=float, help=f"Slit width, arcsec [{d['slit']}].")
    parser.add_argument('--binning', help=f"Binning [{d['binning']}].")
    parser.add_argument('--seeing', type=float,
                        help=f'Seeing FWHM, arcsec [{DEFAULT_SEEING[instrument]}].')
    parser.add_argument('--mag-band', help=f'Band of the mag column '
                                           f'[{DEFAULT_MAG_BAND}]; a per-row '
                                           f'mag_band column wins.')
    # Milestone 5 (T1.3, T3.4).
    parser.add_argument('--airmass-rule', choices=('worst', 'mid', 'best'),
                        help='Airmass the ETC is run at, over each target\'s '
                             'scheduled science span [worst].')
    parser.add_argument('--etc', help='ETC: a registry name (lris, kast, '
                                      'empirical) or "package.module:function" '
                                      f'[{instrument}].')
    parser.add_argument('--target-sn', type=float,
                        help='Target median continuum S/N per sub-exposure '
                             '[LRIS 10, Kast 10].')


def resolve_options(args, cfg, instrument):
    """
    Resolve configuration, seeing and band: CLI flag > JSON config file >
    default. The result is validated.

    Parameters
    ----------
    args : argparse.Namespace from a parser that went through add_config_args
    cfg : NightPlanConfig or None
    instrument : str

    Returns
    -------
    dict with 'config' (dict), 'seeing' (float), 'mag_band' (str),
    'airmass_rule' (str), 'etc' (str), 'target_sn' (float),
    'n_sub_min' (int).

    Raises
    ------
    ConfigError for anything the ETC can't model.
    """
    file_config = dict(getattr(cfg, 'config', None) or {})
    config = dict(DEFAULT_CONFIG[instrument])
    config.update({k: v for k, v in file_config.items() if v is not None})
    for key in ('grism', 'grating', 'dichroic', 'slit', 'binning'):
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    config = validate_config(instrument, config)
    seeing = getattr(args, 'seeing', None)
    if seeing is None:
        seeing = getattr(cfg, 'seeing', None)
    seeing = float(seeing) if seeing is not None else DEFAULT_SEEING[instrument]
    if not 0 < seeing < 10:
        raise ConfigError(f'seeing {seeing}" is not plausible')
    band = getattr(args, 'mag_band', None) or getattr(cfg, 'mag_band', None) \
        or DEFAULT_MAG_BAND
    etc_filter(band)   # validates

    from .etc import DEFAULT_ETC, N_SUB_MIN, TARGET_SN, load_etc

    def pick(name):
        value = getattr(args, name, None)
        return value if value is not None else getattr(cfg, name, None)

    rule = pick('airmass_rule') or 'worst'
    if rule not in ('worst', 'mid', 'best'):
        raise ConfigError(f'airmass rule {rule!r}: use worst, mid or best')
    etc_name = pick('etc') or DEFAULT_ETC[instrument]
    try:
        load_etc(etc_name)
    except (ValueError, ImportError) as err:
        raise ConfigError(str(err))
    target_sn = pick('target_sn')
    target_sn = float(target_sn) if target_sn is not None else TARGET_SN[instrument]
    if target_sn <= 0:
        raise ConfigError('target S/N must be positive')
    return {'config': config, 'seeing': seeing, 'mag_band': band,
            'airmass_rule': rule, 'etc': etc_name, 'target_sn': target_sn,
            'n_sub_min': N_SUB_MIN[instrument]}


def config_label(instrument, config):
    """
    Short human-readable label for one instrument configuration.

    Parameters
    ----------
    instrument : str
        'lris' or 'kast' (anything else falls back to a generic join).
    config : dict
        Keys 'grism', 'grating', 'dichroic', 'slit', 'binning'. Missing keys
        are left out of the label.

    Returns
    -------
    str, e.g. 'B600 / R600/7500 / D560 / 1.0" / 2x2'.
    """
    parts = []
    if config.get('grism'):
        parts.append(GRISM_NAMES.get(instrument, {}).get(config['grism'],
                                                         str(config['grism'])))
    if config.get('grating'):
        parts.append(f"R{config['grating']}")
    if config.get('dichroic'):
        parts.append(str(config['dichroic']))
    if config.get('slit') is not None:
        parts.append(f"{float(config['slit']):.1f}\"")
    if config.get('binning'):
        parts.append(str(config['binning']))
    return ' / '.join(parts)


# --------------------------------------------------------------------
# Lick/Shane per-target overheads (Keck's live in scripts/keck_overheads.py)
# --------------------------------------------------------------------

# Lordrick, 2026-11-07 (Q8): "slew time 2 min and acquisition 3 for a total
# of 5". The total equals the old all-inclusive 5 min SLEW_MINUTES, so Kast
# timing is unchanged; only the labels split. The run-specific
# lick_2026b02_* scripts keep their own SLEW_MINUTES = 5 so those nights
# reproduce.
LICK_SLEW_MIN = 2
LICK_ACQ_MIN = 3


def lick_gap_minutes():
    """
    Minutes between one Kast target's end and the next one's science start.

    Returns
    -------
    int : LICK_SLEW_MIN + LICK_ACQ_MIN.
    """
    return LICK_SLEW_MIN + LICK_ACQ_MIN


# --------------------------------------------------------------------
# Detector readout (Milestone 3, T1.1): seconds per frame, per arm
# --------------------------------------------------------------------

# LRIS, keyed by binning. 2x2 (our default) is observer experience:
# Lordrick, 2026-11-07, "~80 s for blue and ~40 for red". Other binnings
# stay None (NOT SET) until someone needs them; don't scale from 2x2.
# For reference, Keck's web values, elapsed per 0 s frame including erase,
# were fetched 2026-11-07
# (https://www2.keck.hawaii.edu/inst/lris/win_bin.html):
#   red (Mark IV, 2 amps): 1x1 97 s, 1x2 55 s, 2x1 65 s, 2x2 39 s
#   blue: full frame 1x1 54 s, 1x2 36 s; 2x2 not published
# Kast, keyed by read mode. Slow mode is always used (Lordrick, 2026-11-07);
# "normally 20 s on the blue side". The Lick page
# (https://mthamilton.ucolick.org/techdocs/instruments/kast/hw_detectors.html)
# lists slow sub-region 7 s blue / 20 s red and slow full frame 43/34 s.
# The per-frame cost is 20 s either way.
READOUT_S = {
    'lris': {'2x2': {'blue': 80, 'red': 40},
             '1x1': {'blue': None, 'red': None}},
    'kast': {'slow': {'blue': 20, 'red': 20}},
}

# Which READOUT_S key an instrument's configuration selects.
_READOUT_KEY = {'lris': lambda c: c.get('binning', '2x2'),
                'kast': lambda c: c.get('read_mode', 'slow')}


def readout_arms(instrument, config=None):
    """
    Per-arm readout seconds for an instrument configuration.

    Parameters
    ----------
    instrument : str
    config : dict, optional
        Defaults to DEFAULT_CONFIG[instrument].

    Returns
    -------
    dict {'blue': float|None, 'red': float|None}. Both None if the
    configuration isn't in READOUT_S at all.
    """
    config = config if config is not None else DEFAULT_CONFIG.get(instrument, {})
    table = READOUT_S.get(instrument, {})
    key = _READOUT_KEY.get(instrument, lambda c: None)(config)
    return dict(table.get(key) or {'blue': None, 'red': None})


def readout_seconds(instrument, config=None):
    """
    Readout per frame of the slower arm. The arms read out in parallel, so
    the slower one sets the cost.

    Parameters
    ----------
    instrument : str
    config : dict, optional

    Returns
    -------
    float, or None (NOT SET) if either arm's value is missing. Never the
    known arm alone.
    """
    arms = readout_arms(instrument, config)
    if any(v is None for v in arms.values()):
        return None
    return float(max(arms.values()))


_FRAMES = re.compile(r'(\d+)\s*[xX×]\s*(\d+(?:\.\d+)?)')


def recipe_frames(recipe):
    """
    Frames and integration in an exposure recipe.

    Parameters
    ----------
    recipe : str
        e.g. '3 x 600', or '2 x 300, 1 x 600' (terms are summed).

    Returns
    -------
    (n_frames, seconds) : (int, float); (0, 0.0) if nothing parses (e.g.
    'MOS mask required').
    """
    terms = _FRAMES.findall(str(recipe or ''))
    return (sum(int(n) for n, _ in terms),
            sum(int(n) * float(t) for n, t in terms))


def readout_minutes(instrument, red_recipe, blue_recipe, config=None):
    """
    Readout time a dual-beam exposure recipe adds to the block.

    Each arm takes its own exposures + n_frames x its readout. The arms run
    in parallel, so the block lasts as long as the slower arm. The readout
    cost is that minus the science wall clock (the longer arm's
    integration).

    Parameters
    ----------
    instrument : str
    red_recipe, blue_recipe : str
        e.g. '6 x 600' and '3 x 1200'.
    config : dict, optional

    Returns
    -------
    float minutes, or None if a readout value is NOT SET (the caller
    charges 0 and flags it in the plan's assumptions). 0.0 for a recipe
    that doesn't parse (an allocation such as a MOS block, whose length
    already includes readout).
    """
    arms = readout_arms(instrument, config)
    if any(v is None for v in arms.values()):
        return None
    n_red, t_red = recipe_frames(red_recipe)
    n_blue, t_blue = recipe_frames(blue_recipe)
    if not (n_red or n_blue):
        return 0.0
    science = max(t_red, t_blue)
    wall = max(t_red + n_red * arms['red'], t_blue + n_blue * arms['blue'])
    return (wall - science) / 60.0


# --------------------------------------------------------------------
# Telescope elevation limits (Milestone 9, T3.6)
# --------------------------------------------------------------------

# Keck I, from https://www2.keck.hawaii.edu/inst/common/TelLimits.html
# (fetched 2026-11-07): accessible elevation 33.3-88.9 deg for azimuth
# 5.3-146.2 deg (the Nasmyth deck), 18-88.9 deg elsewhere; "stable guiding
# cannot be guaranteed for targets transiting above about 85 deg".
# No LRIS rotator check: the starlists send rotdest in sky PA (rotmode=pa)
# and the physical range (-239 < x < 189) spans 428 deg (Lordrick,
# 2026-11-07). No Shane tub check: calcint.c covers every PA.
KECK_ELEVATION_LIMITS = {
    'zenith_max': 88.9,       # deg: above this the telescope can't track
    'guide_warn': 85.0,       # deg: above this, guiding may be unstable
    'nasmyth_floor': 33.3,    # deg, inside nasmyth_az
    'nasmyth_az': (5.3, 146.2),
    'floor': 18.0,            # deg, unvignetted elsewhere
}


# --------------------------------------------------------------------
# Calibrations (T3.7): what the Observing log's checklist asks for
# --------------------------------------------------------------------

# Per Lordrick, 2026-11-07:
# - Lick: biases, flats and arcs for each configuration (usually one).
# - LRIS: flats and arcs for each configuration and for each slitmask.
# To add something (e.g. LRIS biases), edit this dict. Nothing else needs
# to change.
CALIBRATION_RULES = {
    'kast': {'per_config': ['bias', 'flat', 'arc'], 'per_mask': []},
    'lris': {'per_config': ['flat', 'arc'], 'per_mask': ['flat', 'arc']},
}

CALIBRATION_LABELS = {'bias': 'Biases', 'flat': 'Flats', 'arc': 'Arcs'}


# --------------------------------------------------------------------
# Night checklist: the fixed, non-calibration steps of a night
# --------------------------------------------------------------------

# Calibrations are deliberately not listed here. The calibrations
# checklist covers them, so they aren't asked for twice.
_COMMON_END = [
    ('data_copied', 'Data copied off the instrument machine'),
    ('log_reviewed', 'Observing log reviewed'),
    ('report_generated', 'Observing report generated'),
]

NIGHT_CHECKLIST = {
    'lris': [('focus', 'Focus'),
             ('evening_standard', 'Evening standard'),
             ('morning_standard', 'Morning standard')] + _COMMON_END,
    'kast': [('focus', 'Focus'),
             ('evening_standard', 'Evening standard'),
             ('morning_standard', 'Morning standard')] + _COMMON_END,
}


def is_mask_mode(mode):
    """
    Whether a scheduled target's mode needs a slitmask.

    Parameters
    ----------
    mode : str
        ScheduledTarget.mode, e.g. 'longslit' or 'MOS (mask required)'.

    Returns
    -------
    bool : True for any mode starting with 'MOS'.
    """
    return str(mode or '').upper().startswith('MOS')
