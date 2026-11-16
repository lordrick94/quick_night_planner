"""
Telescope pointing limits, read from data rather than hardcoded.

Created by JXP and Claude

The Shane limits used to live as module constants in a run-specific script
(scripts/lick_2026b02_calculations.py). Comparing with the UCSC
AstroScheduler (which keeps them in telescopes.json) showed why that hurts:
the two codes disagree on the Shane Dec limit (+82 here, +72 there) and
nothing made the disagreement visible. The values now live in
night_planner/data/site_limits.json, each with its source, and a single run
can override any of them with ``--limit KEY=VALUE``.
"""

import json
import math
from pathlib import Path

LIMITS_FILE = Path(__file__).resolve().parent / 'data' / 'site_limits.json'

# Keys a run may override, with the unit shown in messages.
LIMIT_KEYS = {
    'ha_east': 'h', 'ha_west': 'h', 'dec_max': 'deg', 'dec_min': 'deg',
    'airmass_max': '',
}


def load_site_limits(site, overrides=None, path=LIMITS_FILE):
    """
    Pointing limits for one site, with per-run overrides applied.

    Inputs
    ------
    site : str
        Key in the limits file, e.g. 'lick'.
    overrides : dict, optional
        {key: float or None}, as returned by parse_limit_overrides().
    path : Path
        The limits file (tests may point elsewhere).

    Outputs
    -------
    dict with the LIMIT_KEYS (float or None), plus 'telescope' and
    'overridden' (sorted list of keys a run changed).

    Raises
    ------
    KeyError if the site is not in the file; ValueError for an
    inconsistent set (east limit not below west, dec_min above dec_max,
    airmass_max below 1).
    """
    with open(path) as f:
        data = json.load(f)
    if site not in data:
        raise KeyError(f'no pointing limits for site {site!r} in {path}')
    raw = data[site]
    limits = {k: (None if raw.get(k) is None else float(raw[k])) for k in LIMIT_KEYS}
    limits['telescope'] = raw.get('telescope', site)
    overrides = dict(overrides or {})
    unknown = set(overrides) - set(LIMIT_KEYS)
    if unknown:
        raise ValueError(f'unknown limit(s) {", ".join(sorted(unknown))}; '
                         f'known: {", ".join(LIMIT_KEYS)}')
    limits.update(overrides)
    limits['overridden'] = sorted(overrides)

    if limits['ha_east'] is None or limits['ha_west'] is None:
        raise ValueError('ha_east and ha_west must both be set')
    if limits['ha_east'] >= limits['ha_west']:
        raise ValueError(f"ha_east ({limits['ha_east']:+.2f}h) must be below "
                         f"ha_west ({limits['ha_west']:+.2f}h)")
    if (limits['dec_min'] is not None and limits['dec_max'] is not None
            and limits['dec_min'] >= limits['dec_max']):
        raise ValueError('dec_min must be below dec_max')
    if limits['airmass_max'] is not None and limits['airmass_max'] < 1.0:
        raise ValueError('airmass_max must be at least 1')
    return limits


def parse_limit_overrides(specs):
    """
    Parse repeated ``--limit KEY=VALUE`` flags.

    Inputs
    ------
    specs : list of str
        e.g. ['dec_max=72', 'airmass_max=1.7', 'dec_min=none'].

    Outputs
    -------
    dict {key: float or None}; 'none' (any case) removes a limit.

    Raises
    ------
    ValueError for a malformed spec, an unknown key or a non-numeric value.
    """
    out = {}
    for spec in specs or []:
        key, sep, value = str(spec).partition('=')
        key, value = key.strip(), value.strip()
        if not sep or not key:
            raise ValueError(f'--limit {spec!r}: expected KEY=VALUE')
        if key not in LIMIT_KEYS:
            raise ValueError(f'--limit {spec!r}: unknown key {key!r}; '
                             f'known: {", ".join(LIMIT_KEYS)}')
        if value.lower() in ('none', 'null', ''):
            out[key] = None
            continue
        try:
            number = float(value)
        except ValueError:
            raise ValueError(f'--limit {spec!r}: {value!r} is not a number') from None
        if not math.isfinite(number):
            raise ValueError(f'--limit {spec!r}: value must be finite')
        out[key] = number
    return out


def describe_limits(limits):
    """
    One line for the plan's assumptions.

    Inputs: limits dict from load_site_limits().
    Outputs: str, e.g. 'HA -5.67h to +3.75h, Dec <= +82, no airmass limit'.
    """
    parts = [f"HA {limits['ha_east']:+.2f}h to {limits['ha_west']:+.2f}h"]
    if limits['dec_min'] is not None and limits['dec_max'] is not None:
        parts.append(f"Dec {limits['dec_min']:+.0f} to {limits['dec_max']:+.0f}")
    elif limits['dec_max'] is not None:
        parts.append(f"Dec <= {limits['dec_max']:+.0f}")
    elif limits['dec_min'] is not None:
        parts.append(f"Dec >= {limits['dec_min']:+.0f}")
    parts.append('no airmass limit' if limits['airmass_max'] is None
                 else f"airmass <= {limits['airmass_max']:g}")
    text = ', '.join(parts)
    if limits.get('overridden'):
        text += f" (this run overrides {', '.join(limits['overridden'])})"
    return text
