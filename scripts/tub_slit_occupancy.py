# Created by JXP and Claude, 2026-11-11 (Shane TUB vs sky PA check; see Logs 2026-11-11)
"""
For each hypothesised slit axis through an anchor object, list catalogue sources that fall on the slit.

Inputs : stars csv, candidates csv, anchor RA/Dec (deg); hypotheses hard-coded below.
Outputs: per hypothesis, sources with |perp offset| < 2" and |along| < 70" (Kast slit ~145" long).
"""
import sys, numpy as np, pandas as pd
from astropy.coordinates import SkyCoord; import astropy.units as u
st, ca, ra0, de0 = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
c0 = SkyCoord(ra0*u.deg, de0*u.deg)
cat = pd.concat([pd.read_csv(st)[['ra', 'dec', 'rPSFmag']].rename(columns={'rPSFmag': 'mag'}).assign(kind='star'),
                 pd.read_csv(ca)[['ra', 'dec', 'mag']].assign(kind='galaxy')])
cc = SkyCoord(cat.ra.values*u.deg, cat.dec.values*u.deg)
sep = c0.separation(cc).arcsec; pa = np.radians(c0.position_angle(cc).deg)
hyp = {f'TUB {t}, TUB = sky PA': float(t) for t in sys.argv[5:]} | {f'TUB {t}, calcint.c': (float(t)-0.05)/0.87 for t in sys.argv[5:]}
for name, slit in hyp.items():
    th = np.radians(slit)
    along, perp = sep*np.cos(pa-th), sep*np.sin(pa-th)
    m = (np.abs(perp) < 2.0) & (np.abs(along) < 70)
    t = cat[m].assign(along=along[m].round(1), perp=perp[m].round(2)).sort_values('along')
    print(f"\n### {name}: slit PA {slit:.1f}")
    print(t[['kind', 'mag', 'along', 'perp']].round(2).to_string(index=False))
