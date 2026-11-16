# Created by JXP and Claude, 2026-11-11 (Shane TUB vs sky PA check; see Logs 2026-11-11)
"""
Compare recorded TUB with the requested slit PA (line through Pri & Sec host candidates).

Inputs : tub_survey.csv (written by tub_header_survey.py), targets CSVs (argv).
Outputs: per-target table: TUB, PA(Pri->Sec), calcint(PA), parallactic at block start,
         and which hypothesis the TUB matches.
"""
import sys
import numpy as np, pandas as pd
from astropy.coordinates import SkyCoord
import astropy.units as u

def fold(x):
    return (np.asarray(x) + 90) % 180 - 90

def calcint(pa):  # calcint.c is linear on its 20..380 table
    pa = pa % 360
    pa = pa + 360 if pa < 20 else pa
    return 0.87 * pa + 0.05

frames = pd.read_csv('tub_survey.csv')
tg = pd.concat([pd.read_csv(f) for f in sys.argv[1:]]).drop_duplicates('TNS')
frames['tns'] = frames.obj.str.extract(r'(FRB\d{8}[A-Z]+)')[0]
blocks = (frames.dropna(subset=['tns']).groupby(['tns', 'tub'], sort=False)
          .agg(date=('date', 'first'), n=('file', 'size'), obj=('obj', 'first'), par0=('par', 'first')).reset_index())
out = []
for _, b in blocks.iterrows():
    t = tg[tg.TNS == b.tns]
    if t.empty or pd.isna(t.Sec_RA.iloc[0]):
        out.append(dict(obj=b.obj, date=b.date[:10], n=b.n, tub=b.tub, note='not in targets csv'))
        continue
    t = t.iloc[0]
    p = SkyCoord(t.Pri_RA * u.deg, t.Pri_Dec * u.deg); s = SkyCoord(t.Sec_RA * u.deg, t.Sec_Dec * u.deg)
    pa2 = p.position_angle(s).deg % 180
    sep = p.separation(s).arcsec
    # candidate settings an observer could have dialed for that PA (both slit ends)
    tubA = [calcint(pa2), calcint(pa2 + 180)]
    rA = min(abs(b.tub - x) for x in tubA)          # observer dialed calcint(PA)
    rD = abs(fold(b.tub - pa2))                      # observer dialed sky PA directly
    rP = min(abs(b.tub - calcint(b.par0)), abs(b.tub - calcint(b.par0 + 180)))  # dialed calcint(parallactic)
    rPd = abs(fold(b.tub - b.par0))                  # dialed parallactic directly
    out.append(dict(obj=b.obj, date=b.date[:10], n=b.n, tub=b.tub, sep=round(sep, 1), PA_pri_sec=round(pa2, 1),
                    calcint_PA=' / '.join(f'{x:.1f}' for x in tubA), par0=round(b.par0, 1),
                    d_calcintPA=round(rA, 1), d_PA=round(rD, 1), d_calcintPar=round(rP, 1), d_Par=round(rPd, 1)))
pd.set_option('display.width', 250)
print(pd.DataFrame(out).to_string(index=False))
