"""
Shane Cassegrain tub: the number a Lick observer actually dials.

A sky position angle is not what gets set at the Shane. The instrument
hangs in a Cassegrain tub whose position is read out in Nixie units, and
the two differ by about 13 per cent: PA 108.9 deg is tub 94.8, not 108.9.
Handing a Lick observer a bare PA is handing them a number in the wrong
units, which is exactly the kind of instrument quirk this planner exists
to remember.

The conversion table is `helpful_scripts/calcint.c` (Lick Observatory),
reproduced verbatim and interpolated the same way. It is linear to a
hundredth of a count -- readout = 0.87 x PA + 0.05 -- but the table is
kept rather than the fit, so this stays the same object the observatory
distributes.

Every angle has two tub settings 180 degrees apart, and which one is
reachable depends on where the tub already sits, so both are always
reported, as `pa.c` does.

The zero point is confirmed against real data: Lick-2025B-3 frame r2046
(TGT0415, 2025-10-24) records TUB 194.80 with HA -2:23:23 and Dec
+78:14:43, and inverting the table gives a slit axis of 43.85 deg
against a parallactic angle of 42.54 deg at that instant -- agreement to
1.3 deg, which is the precision of setting a tub by hand. calcint.c's
table needs no offset.

Created by JXP and Claude
"""

import numpy as np

# calcint.c: position angle (deg) -> Cassegrain tub readout (Nixie units).
TUB_TABLE = np.array([
    [20, 17.45], [30, 26.15], [40, 34.85], [50, 43.55], [60, 52.25],
    [70, 60.95], [80, 69.65], [90, 78.35], [100, 87.05], [110, 95.75],
    [120, 104.45], [130, 113.15], [140, 121.85], [150, 130.55],
    [160, 139.25], [170, 147.95], [180, 156.65], [190, 165.35],
    [200, 174.05], [210, 182.75], [220, 191.45], [230, 200.15],
    [240, 208.85], [250, 217.55], [260, 226.25], [270, 234.95],
    [280, 243.65], [290, 252.35], [300, 261.05], [310, 269.74],
    [320, 278.44], [330, 287.14], [340, 295.84], [350, 304.54],
    [360, 313.24], [370, 321.94], [380, 330.64],
])


def cass_tub_readout(pa_deg):
    """
    Cassegrain tub Nixie readout for one position angle (calcint.c).

    Parameters
    ----------
    pa_deg : float
        Position angle, degrees. An angle below 20 is wrapped up into the
        360-380 range first, exactly as calcint.c does, because the table
        does not start at zero.

    Returns
    -------
    float
        Nixie readout units.
    """
    pa = float(pa_deg)
    # The table runs 20..380, so its last 20 degrees deliberately repeat
    # the first 20. Only normalise an angle that falls outside it, or 380
    # would be folded onto 20 and read 17.45 instead of 330.64.
    if not 0.0 <= pa <= 380.0:
        pa %= 360.0
    if pa < 20.0:
        pa += 360.0
    return float(np.interp(pa, TUB_TABLE[:, 0], TUB_TABLE[:, 1]))


def tub_settings(pa_deg):
    """
    Both tub settings for a slit angle.

    A slit has no head or tail, so PA and PA+180 put the same slit on the
    sky but leave the tub in two different places. Which is reachable
    depends on where it already is, so the plan quotes both and the
    observer picks -- the same thing pa.c prints as "(or ...)".

    Parameters
    ----------
    pa_deg : float

    Returns
    -------
    dict with 'pa', 'alt_pa', 'tub', 'alt_tub'
    """
    pa = float(pa_deg) % 360.0
    alt = (pa + 180.0) % 360.0
    return {'pa': pa, 'alt_pa': alt,
            'tub': cass_tub_readout(pa), 'alt_tub': cass_tub_readout(alt)}
