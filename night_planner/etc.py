"""
Exposure-time calculators behind one plain-function interface (T3.4b).

Created by JXP and Claude

Every ETC is a function with this signature:

    etc(mag, band, airmass, seeing, config, target_sn, n_sub_min)
        -> {'sub_len_s': int, 'n_sub': int,
            'sn_sub': {'blue': float, 'red': float},
            'wave': list, 's2n': list}

That is the length of one sub-exposure that reaches `target_sn` (median
per-pixel continuum S/N) in *each* arm's window, the number of
sub-exposures (>= n_sub_min, a cosmic-ray-rejection floor), the S/N one
sub-exposure actually reaches per arm, and the S/N spectrum at that
length.

- ETC_REGISTRY maps a name to a function: 'lris' and 'kast' use the
  UCO/Lick ETC (etc.ucolick.org); 'empirical' is the Kast magnitude rule.
- load_etc("package.module:function") loads one of your own.
- Results are cached (lru_cache), because the scheduler asks again for
  every placement, and each UCO call is a network round trip.

Functions, not classes: per the repo convention. Sunil's "ETC class" was
answered with "function shape for now" (Lordrick, 2026-11-07); a class can
wrap one later without changing callers.
"""

import functools
import importlib
import math
import os
import statistics
from pathlib import Path

import numpy as np

from .instrument_params import DEFAULT_CONFIG, etc_config, etc_filter

ETC_URL = 'https://etc.ucolick.org/web_s2n/gen_inst_s2n'

# Continuum windows (Angstrom) for the median S/N per arm. They avoid the
# ~5500-5600 A dichroic split and strong sky lines, and sit inside the
# Kast ETC's 3150-8000 A grid as well as LRIS's.
BLUE_WINDOW = (4200.0, 5200.0)
RED_WINDOW = (6500.0, 7500.0)

# Search bounds for one sub-exposure, seconds.
T_MIN, T_MAX = 60.0, 7200.0

_REPO = Path(__file__).resolve().parent.parent
_CERT_DIR = _REPO / 'scripts' / 'certs'


def _ca_bundle():
    """
    certifi's bundle plus the InCommon intermediate etc.ucolick.org omits.

    The server's leaf certificate is real, but it doesn't send its
    intermediate, so default trust stores fail. Shipping the intermediate
    keeps verification on (see scripts/lris_etc.py, 2026-09-10).

    Returns
    -------
    str : path to the combined bundle (built on first use).
    """
    bundle = _CERT_DIR / 'ca_bundle_with_incommon.pem'
    if not bundle.exists():
        import certifi
        bundle.write_bytes(Path(certifi.where()).read_bytes() + b'\n'
                           + (_CERT_DIR / 'incommon_rsa_server_ca_2.pem').read_bytes())
    return str(bundle)


def query_uco_etc(inst, mag, exptime, airmass, seeing, config, ffilter,
                  mtype=2, redshift=0.0, template='', timeout=30):
    """
    One call to the UCO/Lick ETC: S/N per pixel for one exposure.

    Parameters
    ----------
    inst : str
        'lris' or 'kast'.
    mag : float
        Magnitude (AB unless mtype=1) in the band of `ffilter`.
    exptime : float
        Single-exposure length, seconds.
    airmass, seeing : float
    config : dict
        grism, grating, dichroic, slit, binning, already in the ETC's
        own codes (see instrument_params.etc_config).
    ffilter : str
        ETC filter file, e.g. 'sdss_r.dat'.
    mtype, redshift, template :
        As on the form; template '' is a flat spectrum.
    timeout : float

    Returns
    -------
    (wave, s2n) : numpy arrays (Angstrom, S/N per pixel).

    Raises
    ------
    ValueError if the ETC returns no spectrum (an unsupported combination).
    """
    import requests

    data = {
        'inst': inst, 'dichroic': config['dichroic'],
        'slitwidth': config['slit'], 'binning': config['binning'],
        'exptime': exptime, 'mag': mag, 'ffilter': ffilter, 'mtype': mtype,
        'grism': config['grism'], 'grating': config['grating'],
        'seeing': seeing, 'template': template, 'airmass': airmass,
        'redshift': redshift, 'submitbutton': 'Show signal to noise',
    }
    r = requests.post(ETC_URL, data=data, timeout=timeout, verify=_ca_bundle())
    r.raise_for_status()
    d = r.json()
    if not d.get('s2n'):
        raise ValueError(f'{inst} ETC returned no spectrum for {config} '
                         f'(unsupported combination?) {d.get("errormsg", "")}')
    wave = np.array([p[0] for p in d['s2n']], dtype=float)
    s2n = np.array([p[1] for p in d['s2n']], dtype=float)
    return wave, s2n


def median_sn(wave, s2n, window):
    """
    Median S/N per pixel within a wavelength window.

    Parameters
    ----------
    wave, s2n : array-like
    window : (float, float), Angstrom

    Returns
    -------
    float : 0.0 if no pixel falls in the window.
    """
    wave, s2n = np.asarray(wave), np.asarray(s2n)
    mask = (wave >= window[0]) & (wave <= window[1])
    return float(statistics.median(s2n[mask])) if mask.any() else 0.0


def _sub_length(inst, mag, airmass, seeing, config, ffilter, target_sn,
                window, max_iter=6, tol=0.05):
    """
    Shortest single exposure reaching target_sn in one window (real ETC
    calls; S/N ~ sqrt(t) only sets the step, every step is checked).

    Returns
    -------
    (seconds, achieved_sn) : (float, float)
    """
    t = 600.0
    achieved = 0.0
    for _ in range(max_iter):
        t = min(max(t, T_MIN), T_MAX)
        wave, s2n = query_uco_etc(inst, mag, t, airmass, seeing, config, ffilter)
        achieved = median_sn(wave, s2n, window)
        if achieved <= 0:
            t *= 4.0
            continue
        ratio = (target_sn / achieved) ** 2
        if abs(ratio - 1.0) < tol:
            break
        if (t >= T_MAX and ratio > 1) or (t <= T_MIN and ratio < 1):
            break
        t *= ratio
    return min(max(t, T_MIN), T_MAX), achieved


def _uco_etc(inst, mag, band, airmass, seeing, config, target_sn, n_sub_min):
    """Shared body of lris_etc and kast_etc."""
    cfg, _ = etc_config(inst, {**DEFAULT_CONFIG[inst], **(config or {})})
    ffilter = etc_filter(band)
    t_blue, _ = _sub_length(inst, mag, airmass, seeing, cfg, ffilter,
                            target_sn, BLUE_WINDOW)
    t_red, _ = _sub_length(inst, mag, airmass, seeing, cfg, ffilter,
                           target_sn, RED_WINDOW)
    # Both arms expose together, so the slower one sets the length.
    sub_len = int(math.ceil(max(t_blue, t_red) / 10.0) * 10)
    wave, s2n = query_uco_etc(inst, mag, sub_len, airmass, seeing, cfg, ffilter)
    return {
        'sub_len_s': sub_len,
        'n_sub': int(n_sub_min),
        'sn_sub': {'blue': round(median_sn(wave, s2n, BLUE_WINDOW), 2),
                   'red': round(median_sn(wave, s2n, RED_WINDOW), 2)},
        'wave': [float(w) for w in wave],
        's2n': [float(v) for v in s2n],
    }


def lris_etc(mag, band, airmass, seeing, config, target_sn, n_sub_min):
    """
    LRIS through the UCO/Lick ETC.

    Parameters
    ----------
    See the module docstring.

    Returns
    -------
    dict, as in the module docstring.
    """
    return _uco_etc('lris', mag, band, airmass, seeing, config, target_sn,
                    n_sub_min)


def kast_etc(mag, band, airmass, seeing, config, target_sn, n_sub_min):
    """
    Kast through the UCO/Lick ETC. Our d57 dichroic is sent as d55, the
    nearest the ETC offers (Lordrick, 2026-11-07).

    Parameters
    ----------
    See the module docstring.

    Returns
    -------
    dict, as in the module docstring.
    """
    return _uco_etc('kast', mag, band, airmass, seeing, config, target_sn,
                    n_sub_min)


def empirical_kast_etc(mag, band, airmass, seeing, config, target_sn, n_sub_min):
    """
    The old Kast magnitude rule, behind the same interface: the way back to
    pre-ETC Kast plans (`--etc empirical`). It has no airmass, seeing,
    band or S/N dependence, and reports no S/N.

    Returns
    -------
    dict : sub_len_s and n_sub from the red recipe, plus 'red_exp' and
    'blue_exp' as the rule writes them (the arms differ), sn_sub None.
    """
    from .estimate_kast_exposures import estimate_exposure

    red, blue, _ = estimate_exposure(mag)
    n, t = (int(x) for x in red.split('x'))
    return {'sub_len_s': t, 'n_sub': n, 'sn_sub': {'blue': None, 'red': None},
            'wave': [], 's2n': [], 'red_exp': red.strip(), 'blue_exp': blue.strip()}


ETC_REGISTRY = {'lris': lris_etc, 'kast': kast_etc,
                'empirical': empirical_kast_etc}

# Each instrument's default ETC and target S/N per sub-exposure.
# Kast stays on the empirical rule by default (2026-11-07): at S/N 5 per
# sub-exposure the UCO ETC gives ~0.07x the empirical time at mag 16-17 and
# ~2.4x at mag 21 (scripts/compare_kast_exposure_models.py,
# docs/data/kast_exposure_model_comparison.csv). At S/N 10 it is 0.07x at
# mag 16 and 1.75x at mag 20; at mag >= 20.5 it hits the 3 x 7200 s cap
# (docs/data/kast_exposure_model_comparison_sn10.csv). That would change every
# Kast plan, so switching is Lordrick/JXP's call. `--etc kast` uses the ETC.
DEFAULT_ETC = {'lris': 'lris', 'kast': 'empirical'}
# LRIS: S/N 10 per sub-exposure (the author, 2026-09-10). Kast: 10 per
# sub-exposure (Lordrick, 2026-11-07; was 5 earlier that day). Both use
# >= 3 sub-exposures. Only `--etc kast` uses it: the empirical rule (the
# Kast default) has no S/N dependence.
TARGET_SN = {'lris': 10.0, 'kast': 10.0}
N_SUB_MIN = {'lris': 3, 'kast': 3}


def load_etc(spec):
    """
    An ETC function from a registry name or 'package.module:function'.

    Parameters
    ----------
    spec : str or callable

    Returns
    -------
    callable with the ETC signature.

    Raises
    ------
    ValueError for an unknown name or a target that isn't callable.
    """
    if callable(spec):
        return spec
    if spec in ETC_REGISTRY:
        return ETC_REGISTRY[spec]
    if ':' not in str(spec):
        raise ValueError(f'unknown ETC {spec!r}: use one of '
                         f'{", ".join(ETC_REGISTRY)} or "package.module:function"')
    module, _, name = str(spec).partition(':')
    func = getattr(importlib.import_module(module), name, None)
    if not callable(func):
        raise ValueError(f'{spec!r} is not a callable ETC')
    return func


def _freeze(config):
    return tuple(sorted((config or {}).items()))


@functools.lru_cache(maxsize=4096)
def _cached(etc, mag, band, airmass, seeing, frozen_config, target_sn, n_sub_min):
    return etc(mag, band, airmass, seeing, dict(frozen_config), target_sn,
               n_sub_min)


def exposure(etc, mag, band, airmass, seeing, config, target_sn, n_sub_min):
    """
    Call an ETC through the cache and add the recipe fields schedulers use.

    Parameters
    ----------
    etc : callable or str
        Anything load_etc accepts.
    mag, band, airmass, seeing, config, target_sn, n_sub_min :
        As in the ETC signature. Airmass is rounded to 0.01 for the cache
        key; mag to 0.001.

    Returns
    -------
    dict : the ETC result (a copy) plus
        'red_exp', 'blue_exp' : the recipe, e.g. '3 x 600'
        'science_min' : wall-clock integration, minutes
        'sn_combined' : {'blue','red'}, sqrt(n_sub) x sn_sub (exact for n
                        identical independent frames, read noise included
                        per frame); None where sn_sub is None
        'airmass_used' : the airmass the ETC was run at
    """
    etc = load_etc(etc)
    out = dict(_cached(etc, round(float(mag), 3), band, round(float(airmass), 2),
                       float(seeing), _freeze(config), float(target_sn),
                       int(n_sub_min)))
    n, t = int(out['n_sub']), int(out['sub_len_s'])
    out.setdefault('red_exp', f'{n} x {t}')
    out.setdefault('blue_exp', f'{n} x {t}')
    from .instrument_params import recipe_frames
    out['science_min'] = max(recipe_frames(out['red_exp'])[1],
                             recipe_frames(out['blue_exp'])[1]) / 60.0
    out['sn_combined'] = {arm: (round(math.sqrt(n) * v, 2) if v is not None else None)
                          for arm, v in (out.get('sn_sub') or {}).items()}
    out['airmass_used'] = round(float(airmass), 2)
    return out


def clear_cache():
    """Forget cached ETC results (tests, or after changing an ETC)."""
    _cached.cache_clear()


def downsample(wave, s2n, n=200):
    """
    An S/N spectrum cut down to about n points for the browser.

    Parameters
    ----------
    wave, s2n : list of float
    n : int

    Returns
    -------
    (wave, s2n) : lists, every k-th point (k = ceil(len / n)).
    """
    if not wave:
        return [], []
    k = max(1, math.ceil(len(wave) / n))
    return list(wave[::k]), list(s2n[::k])


def etc_cache_dir(output_dir):
    """Where a plan's per-target S/N spectra are written."""
    path = os.path.join(output_dir, 'etc')
    os.makedirs(path, exist_ok=True)
    return path


def write_spectra(output_dir, names, spectra):
    """
    Write scheduled targets' S/N spectra to <plan>/etc/<target>.json (T3.4a).

    Parameters
    ----------
    output_dir : str
    names : iterable of str
        The scheduled targets; only these are written.
    spectra : dict
        name -> {'wave', 's2n', 'airmass', 'sub_len_s', 'n_sub', 'band',
        'target_sn'}: the latest ETC call per target, which is the one at
        its scheduled airmass.

    Returns
    -------
    int : files written.
    """
    import json

    names = [n for n in names if spectra.get(n)]
    if not names:
        return 0
    out = etc_cache_dir(output_dir)
    for name in names:
        spec = spectra[name]
        wave, s2n = downsample(spec['wave'], spec['s2n'])
        with open(os.path.join(out, f'{name}.json'), 'w') as f:
            json.dump({**spec, 'wave': wave, 's2n': s2n,
                       'windows': {'blue': BLUE_WINDOW, 'red': RED_WINDOW}}, f)
    return len(names)
