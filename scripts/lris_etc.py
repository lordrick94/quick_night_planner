"""
Real LRIS exposure-time calculator: a thin client for the UCO/Lick
Observatories web S/N calculator (the same physical engine that serves the
official web LRIS/Kast/DEIMOS/ESI/HIRES ETCs at etc.ucolick.org). It models
real throughput, sky background, seeing/slit losses, dichroic split, and a
template spectrum -- not a magnitude-bucket lookup table.

Created by JXP and Claude
"""

import os
import statistics

import certifi
import numpy as np
import requests

ETC_URL = "https://etc.ucolick.org/web_s2n/gen_inst_s2n"

# etc.ucolick.org's leaf cert is real (InCommon/Sectigo-issued) but the
# server doesn't send its intermediate, so default trust stores fail to
# verify it (confirmed via `openssl s_client -showcerts`, 2026-09-10).
# Rather than disabling verification, ship the one missing intermediate
# alongside certifi's bundle so the chain still validates properly.
_CERT_DIR = os.path.join(os.path.dirname(__file__), "certs")
CA_BUNDLE = os.path.join(_CERT_DIR, "ca_bundle_with_incommon.pem")
if not os.path.exists(CA_BUNDLE):
    with open(certifi.where(), "rb") as f:
        base = f.read()
    with open(os.path.join(_CERT_DIR, "incommon_rsa_server_ca_2.pem"), "rb") as f:
        inter = f.read()
    with open(CA_BUNDLE, "wb") as f:
        f.write(base + b"\n" + inter)

# LRIS setup for CHIME/FRB host spectroscopy (per the author, 2026-09-10):
# grism 600/4000 (blue), grating 600/7500 centered ~7200 A (red). D560 is the
# only dichroic the ETC models; it's also our standard one.
DEFAULT_DICHROIC = "D560"
DEFAULT_GRISM = "B600"       # 600/4000
DEFAULT_GRATING = "600/7500"
DEFAULT_SLITWIDTH = 1.0
DEFAULT_BINNING = "2x2"
DEFAULT_SEEING = 0.8

# Continuum windows sampled per arm (avoiding the ~5600 A dichroic split and
# strong sky lines) for a median S/N estimate.
BLUE_WINDOW = (4200.0, 5200.0)
RED_WINDOW = (6500.0, 7500.0)


def query_lris_etc(mag_r, exptime, airmass=1.2, seeing=DEFAULT_SEEING,
                    redshift=0.0, dichroic=DEFAULT_DICHROIC,
                    slitwidth=DEFAULT_SLITWIDTH, binning=DEFAULT_BINNING,
                    grism=DEFAULT_GRISM, grating=DEFAULT_GRATING,
                    template="", mtype=2, ffilter="sdss_r.dat", timeout=20):
    """
    Query the real UCO/Lick LRIS S/N calculator for one exposure time.

    Parameters
    ----------
    mag_r : float
        r-band magnitude (AB, unless mtype=1 for Vega).
    exptime : float
        Single-exposure integration time in seconds.
    airmass, seeing, redshift : float
    dichroic, grism, grating : str
        Must be one of the ETC's supported values. Blue grism: only "B300"
        (300/5000) and "B600" (600/4000) return real results -- "B400"
        (400/3400) and "B1200" silently return an empty spectrum despite no
        error message (verified 2026-09-10). Red grating: "600/7500",
        "600/10000", "1200/9000", "400/8500", "831/8200" all work. Dichroic:
        only "D560" is modeled.
    template : str
        FITS template filename per the ETC's dropdown, or "" for a flat
        spectrum (the ETC's default -- used here since FRB host spectral
        type/redshift is unknown pre-observation).

    Returns
    -------
    wave : ndarray (Angstrom)
    s2n : ndarray (per pixel)
    """
    data = {
        "inst": "lris",
        "dichroic": dichroic,
        "slitwidth": slitwidth,
        "binning": binning,
        "exptime": exptime,
        "mag": mag_r,
        "ffilter": ffilter,
        "mtype": mtype,
        "grism": grism,
        "grating": grating,
        "seeing": seeing,
        "template": template,
        "airmass": airmass,
        "redshift": redshift,
        "submitbutton": "Show signal to noise",
    }
    r = requests.post(ETC_URL, data=data, timeout=timeout, verify=CA_BUNDLE)
    r.raise_for_status()
    d = r.json()
    if not d["s2n"]:
        raise ValueError(f"LRIS ETC returned no data for grism={grism}, "
                          f"grating={grating} (unsupported combination?)")
    wave = np.array([p[0] for p in d["s2n"]])
    s2n = np.array([p[1] for p in d["s2n"]])
    return wave, s2n


def median_sn_in_window(wave, s2n, window):
    """Median S/N per pixel within a (wmin, wmax) Angstrom window."""
    mask = (wave >= window[0]) & (wave <= window[1])
    if not mask.any():
        return 0.0
    return float(statistics.median(s2n[mask]))


def required_exptime(mag_r, target_sn=5.0, window=RED_WINDOW, airmass=1.2,
                      seeing=DEFAULT_SEEING, redshift=0.0, t_guess=600.0,
                      t_min=60.0, t_max=7200.0, max_iter=6, tol=0.05,
                      **etc_kwargs):
    """
    Find the exposure time (real ETC calls, not a formula) needed to reach
    a target median S/N per pixel in the given continuum window.

    S/N is photon-noise-dominated over the exptime range used here, so
    S/N ~ sqrt(t) is a good step direction -- but every step is verified
    with an actual ETC call rather than assumed, and iteration stops once
    the achieved S/N is within `tol` of the target (or max_iter is hit).

    Returns
    -------
    t : float (seconds)
    achieved_sn : float
    """
    t = t_guess
    achieved_sn = 0.0
    for _ in range(max_iter):
        t = min(max(t, t_min), t_max)
        wave, s2n = query_lris_etc(mag_r, t, airmass=airmass, seeing=seeing,
                                    redshift=redshift, **etc_kwargs)
        achieved_sn = median_sn_in_window(wave, s2n, window)
        if achieved_sn <= 0:
            t *= 4.0
            continue
        ratio = (target_sn / achieved_sn) ** 2
        if abs(ratio - 1.0) < tol:
            break
        if t >= t_max and ratio > 1.0:
            break
        if t <= t_min and ratio < 1.0:
            break
        t = t * ratio
    return min(max(t, t_min), t_max), achieved_sn


def estimate_lris_exposure_real(mag_r, airmass=1.2, target_sn=10.0,
                                 seeing=DEFAULT_SEEING, n_sub_min=3,
                                 config=None, band='r'):
    """
    Real-ETC replacement for the old magnitude-bucket LRIS exposure
    heuristic. Computes the exptime needed for *one* exposure in each arm
    (blue: 600/4000 grism, red: 600/7500 grating) to reach `target_sn`
    median per-pixel continuum S/N *per single sub-exposure* -- not spread
    across a combined total -- then uses the longer of the two arms as the
    per-sub-exposure length (both arms expose simultaneously).

    That single-exposure length is repeated `n_sub_min` times (default 3):
    a real cosmic-ray-rejection floor from the author's own practice, not
    derived from S/N -- 2 frames can only flag a CR discrepancy, 3+ lets
    you median-reject it. This replaced an earlier version that instead
    found a *combined* exposure time and divided it across sub-exposures,
    which silently under-delivered S/N per individual frame (see
    KECK_LRIS_2026OCT06_SUMMARY.md, Prompt 8).

    Parameters
    ----------
    mag_r : float
    airmass : float
        Use the target's actual airmass at observation time, not a default.
    target_sn : float
        Target median per-pixel continuum S/N for one sub-exposure
        (default 10, per the author).
    seeing : float
    n_sub_min : int
        Minimum number of sub-exposures (default 3, per the author).
    config : dict, optional
        grism / grating / dichroic / slit / binning; missing keys fall back
        to this module's defaults (added 2026-11-07, T3.1).
    band : str
        Band of mag_r, mapped to the ETC filter file through
        night_planner.instrument_params.ETC_FILTERS (T3.5).

    Returns
    -------
    dict with 'red_exp', 'blue_exp', 'science_min', 'total_min', 'mode',
    'achieved_sn_blue', 'achieved_sn_red', and the recipe as numbers,
    'n_sub' and 'sub_len_s' (so callers needn't parse "3 x 600").
    """
    from night_planner.instrument_params import etc_filter

    config = config or {}
    seeing = DEFAULT_SEEING if seeing is None else seeing
    etc_kwargs = dict(grism=config.get('grism', DEFAULT_GRISM),
                      grating=config.get('grating', DEFAULT_GRATING),
                      dichroic=config.get('dichroic', DEFAULT_DICHROIC),
                      slitwidth=config.get('slit', DEFAULT_SLITWIDTH),
                      binning=config.get('binning', DEFAULT_BINNING),
                      ffilter=etc_filter(band))
    t_blue, sn_blue = required_exptime(mag_r, target_sn=target_sn,
                                        window=BLUE_WINDOW, airmass=airmass,
                                        seeing=seeing, **etc_kwargs)
    t_red, sn_red = required_exptime(mag_r, target_sn=target_sn,
                                      window=RED_WINDOW, airmass=airmass,
                                      seeing=seeing, **etc_kwargs)

    sub_len = int(np.ceil(max(t_blue, t_red) / 10.0) * 10)  # round to 10s
    n_sub = n_sub_min
    science_sec = n_sub * sub_len
    science_min = science_sec / 60.0

    exp_str = f"{n_sub} x {sub_len}"

    return {
        "red_exp": exp_str,
        "blue_exp": exp_str,
        "science_min": round(science_min, 1),
        # + flat 5 min slew/acquisition. The Keck scheduler ignores this and
        # charges slews per transition instead (keck_overheads.py).
        "total_min": round(science_min + 5, 1),
        "mode": "longslit",
        "achieved_sn_blue": round(sn_blue, 1),
        "achieved_sn_red": round(sn_red, 1),
        "n_sub": n_sub,
        "sub_len_s": sub_len,
    }
