"""
Keck telescope slew and acquisition rules, shared by every Keck instrument
plan (LRIS, DEIMOS, ...), not LRIS-specific.

Created by JXP and Claude

Rules:
  - Base slew between any two pointings: 5 min.
  - Moving from Dec below +20 deg to Dec above +20 deg: 14 min. Only the
    south-to-north crossing is penalized; the reverse costs the base slew.
  - Acquisition, after the slew and before science: 5 min for a longslit
    target, 10 min for a slitmask (alignment on the mask's stars).

History:
  - 2026-09-29: base 5 min, S->N Dec +20 crossing 20 min (the author).
  - 2026-09-30: base raised to 10 min (the author).
  - 2026-11-07: base back to 5 min, crossing 14 min, and acquisition is now
    its own term (Q1 of claude_prompts/development/users_comments.md, JXP).
    Before this, acquisition was folded into the 10 min slew. LRIS slitmask
    targets still carry their separate +5 min MOS_MASK_BUFFER_MIN (Q7,
    Lordrick: keep it). It is deliberate, not a double count with the 10 min
    mask acquisition.
"""

KECK_SLEW_BASE_MIN = 5
KECK_SLEW_DEC_CROSS_MIN = 14
KECK_SLEW_DEC_BOUNDARY = 20.0  # deg

KECK_ACQ_MIN = {'longslit': 5, 'mask': 10}


def keck_slew_minutes(from_dec, to_dec):
    """
    Slew time (minutes) between two Keck pointings.

    Parameters
    ----------
    from_dec : float or None
        Dec (deg) of the previous pointing. None means no previous pointing
        is known, so the base slew is used.
    to_dec : float
        Dec (deg) of the next pointing.

    Returns
    -------
    int
    """
    if (from_dec is not None and from_dec < KECK_SLEW_DEC_BOUNDARY
            and to_dec > KECK_SLEW_DEC_BOUNDARY):
        return KECK_SLEW_DEC_CROSS_MIN
    return KECK_SLEW_BASE_MIN


def keck_slew_reason(from_dec, to_dec):
    """
    Why a slew costs what it does, for the plan's hover text.

    Parameters
    ----------
    from_dec : float or None
    to_dec : float

    Returns
    -------
    str : '' for the base slew, else a sentence naming the crossing.
    """
    if keck_slew_minutes(from_dec, to_dec) == KECK_SLEW_DEC_CROSS_MIN:
        return (f'Dec +{KECK_SLEW_DEC_BOUNDARY:.0f}\N{DEGREE SIGN} crossing '
                f'(S\N{RIGHTWARDS ARROW}N): {KECK_SLEW_DEC_CROSS_MIN} min')
    return ''


def keck_acquisition_minutes(mode):
    """
    Acquisition time (minutes) for a Keck target, after the slew.

    Parameters
    ----------
    mode : str
        The target's observing mode. Any mode starting with 'MOS' is a
        slitmask; everything else (longslit, forced longslit) is longslit.

    Returns
    -------
    int
    """
    if str(mode or '').upper().startswith('MOS'):
        return KECK_ACQ_MIN['mask']
    return KECK_ACQ_MIN['longslit']
