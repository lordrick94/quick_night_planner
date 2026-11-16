# Created by JXP and Claude, 2026-11-11 (Shane TUB vs sky PA check; see Logs 2026-11-11)
"""
Survey Kast red-arm frames: TUB vs parallactic angle, to test calcint.c's scale.

Inputs : directories of raw Kast frames (argv).
Outputs: tub_survey.csv (one row per on-sky red frame) + printed summary.
Model A (calcint.c): slit PA = (TUB - 0.05) / 0.87
Model B (pure offset): slit PA = TUB + c, c fitted.
All angles folded onto a slit axis (mod 180).
"""
import sys, glob, os
import numpy as np
from astropy.io import fits

LAT = np.radians(37.3414)

def sex(t):
    s = -1.0 if str(t).strip().startswith('-') else 1.0
    p = [abs(float(x)) for x in str(t).strip().lstrip('+-').split(':')] + [0, 0]
    return s * (p[0] + p[1] / 60 + p[2] / 3600)

def parallactic(ha_h, dec_d):
    h, d = np.radians(ha_h * 15), np.radians(dec_d)
    return np.degrees(np.arctan2(np.sin(h), np.tan(LAT) * np.cos(d) - np.sin(d) * np.cos(h)))

def fold(x):  # signed difference on a slit axis, in (-90, 90]
    return (np.asarray(x) + 90) % 180 - 90

rows, seen = [], set()
for d in sys.argv[1:]:
    for f in sorted(glob.glob(os.path.join(d, 'r*.fits*'))):
        h = fits.getheader(f)
        key = h.get('DATE-OBS')
        if key in seen:
            continue
        seen.add(key)
        lamps_on = any(str(h[k]).lower() == 'on' for k in h if k.startswith('LAMPSTA'))
        obj = str(h.get('OBJECT', ''))
        if lamps_on or float(h.get('EXPTIME', 0)) < 30 or any(s in obj.lower() for s in ('flat', 'arc', 'bias', 'dark')):
            continue
        ha, dec, tub = sex(h['HA']), sex(h['DEC']), float(h['TUB'])
        rows.append(dict(file=os.path.basename(f), date=key[:16], obj=obj, exp=float(h['EXPTIME']),
                         ha=ha, dec=dec, am=float(h.get('AIRMASS', np.nan)), tub=tub,
                         par=parallactic(ha, dec) % 180))

import pandas as pd
df = pd.DataFrame(rows).sort_values('date').reset_index(drop=True)
df['slitA'] = ((df.tub - 0.05) / 0.87) % 180
df['resA'] = fold(df.slitA - df.par)
# Model B: best constant offset (circular mean on the doubled angle)
dB = np.radians(2 * (df.par - df.tub))
cB = np.degrees(np.arctan2(np.sin(dB).mean(), np.cos(dB).mean())) / 2
df['resB'] = fold(df.tub + cB - df.par)
# Model C: free scale + offset, robust grid search
best = None
for s in np.arange(0.80, 1.20, 0.001):
    d2 = np.radians(2 * (df.par - df.tub / s))
    c = np.degrees(np.arctan2(np.median(np.sin(d2)), np.median(np.cos(d2)))) / 2
    r = np.median(np.abs(fold(df.tub / s + c - df.par)))
    if best is None or r < best[0]:
        best = (r, s, c)
df.to_csv('tub_survey.csv', index=False)
pd.set_option('display.width', 200); pd.set_option('display.max_rows', 300)
print(df[['date', 'obj', 'exp', 'ha', 'dec', 'am', 'tub', 'par', 'slitA', 'resA', 'resB']].round(2).to_string())
print(f"\nN frames = {len(df)}   TUB range {df.tub.min():.1f} .. {df.tub.max():.1f}")
print(f"Model A (calcint 0.87):  median|res| = {np.median(abs(df.resA)):.2f}  frac<5deg = {(abs(df.resA)<5).mean():.2f}")
print(f"Model B (offset only, c={cB:.2f}): median|res| = {np.median(abs(df.resB)):.2f}  frac<5deg = {(abs(df.resB)<5).mean():.2f}")
print(f"Model C free fit: readout = {best[1]:.3f} x (PA - {best[2]:.2f})   median|res| = {best[0]:.2f}")
