# Created by JXP and Claude, 2026-11-11 (Shane TUB vs sky PA check; see Logs 2026-11-11)
"""
List catalogue sources (PATH stars + galaxy candidates) within RMAX arcsec of the slit's acquisition object.

Inputs : stars csv, candidates csv, acq RA, acq Dec (deg), RMAX.
Outputs: table of sep (arcsec), PA (deg E of N, folded to 0-180), mag, kind.
"""
import sys, numpy as np, pandas as pd
from astropy.coordinates import SkyCoord; import astropy.units as u
st, ca, ra0, de0, rmax = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
c0 = SkyCoord(ra0*u.deg, de0*u.deg)
rows = []
for f, kind in ((st, 'star'), (ca, 'galaxy')):
    df = pd.read_csv(f)
    rc = next(c for c in df.columns if c.lower() in ('ra', 'ra_deg', 'ramean', 'raj2000', 'ra_x'))
    dc = next(c for c in df.columns if c.lower() in ('dec', 'dec_deg', 'decmean', 'dej2000', 'decj2000', 'dec_x'))
    mc = [c for c in df.columns if 'mag' in c.lower() and 'err' not in c.lower()][:1]
    cc = SkyCoord(df[rc].values*u.deg, df[dc].values*u.deg)
    sep = c0.separation(cc).arcsec; pa = c0.position_angle(cc).deg
    for i in np.where(sep < rmax)[0]:
        rows.append(dict(kind=kind, sep=round(sep[i], 1), PA=round(pa[i], 1), PA_axis=round(pa[i] % 180, 1),
                         mag=df[mc[0]].iloc[i] if mc else np.nan))
print(f"(mag column: {mc})")
print(pd.DataFrame(rows).sort_values('sep').to_string(index=False))
