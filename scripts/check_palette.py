"""
Check the plan timeline's colours are distinguishable, including for
colour-blind viewers (goal T2.1).

Created by JXP and Claude

For every pair of timeline colours, compute the CIEDE2000 colour difference
under normal vision and under simulated protanopia and deuteranopia
(Viénot, Brettel & Mollon 1999 matrices, applied in linear RGB). A pair
passes when every difference is at least --min-de (default 12, a clear
step between flat swatches, not a just-noticeable 2).

Colours are read from frontend/style.css (the --science, --mos, ...
tokens), so this checks what the app actually draws.

    python scripts/check_palette.py
"""

import argparse
import itertools
import re
import sys
from pathlib import Path

import numpy as np

CSS = Path(__file__).resolve().parent.parent / 'frontend' / 'style.css'
TOKENS = ('science', 'mos', 'forced', 'partial', 'slew', 'acq', 'overhead',
          'blocked', 'idle')

# Viénot, Brettel & Mollon (1999), linear RGB -> simulated dichromat.
CVD = {
    'normal': np.eye(3),
    'protan': np.array([[0.11238, 0.88762, 0.0],
                        [0.11238, 0.88762, 0.0],
                        [0.00401, -0.00401, 1.0]]),
    'deutan': np.array([[0.29275, 0.70725, 0.0],
                        [0.29275, 0.70725, 0.0],
                        [-0.02234, 0.02234, 1.0]]),
}


def read_tokens(css_path=CSS):
    """
    Timeline colour tokens from the stylesheet.

    Parameters
    ----------
    css_path : Path

    Returns
    -------
    dict token -> '#rrggbb'
    """
    text = Path(css_path).read_text()
    out = {}
    for token in TOKENS:
        m = re.search(rf'--{token}:\s*(#[0-9a-fA-F]{{6}})', text)
        if m:
            out[token] = m.group(1)
    return out


def hex_to_linear(hex_color):
    """'#rrggbb' -> linear-light RGB in [0, 1]."""
    rgb = np.array([int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def linear_to_lab(lin):
    """Linear RGB (D65) -> CIE L*a*b*."""
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = m @ np.clip(lin, 0, 1) / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def ciede2000(lab1, lab2):
    """
    CIEDE2000 colour difference (Sharma, Wu & Dalal 2005).

    Parameters
    ----------
    lab1, lab2 : array-like, L*a*b*

    Returns
    -------
    float
    """
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    if C1p * C2p == 0:
        dh = 0
    elif dh > 180:
        dh -= 360
    elif dh < -180:
        dh += 360
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    else:
        hbp = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dtheta = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc
    return float(np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                         + Rt * (dCp / Sc) * (dHp / Sh)))


def check(colors, min_de=12.0):
    """
    Pairwise CIEDE2000 under each vision type.

    Parameters
    ----------
    colors : dict name -> '#rrggbb'
    min_de : float

    Returns
    -------
    (rows, failures) : list of (a, b, {vision: dE}), and the failing subset.
    """
    labs = {v: {n: linear_to_lab(m @ hex_to_linear(c)) for n, c in colors.items()}
            for v, m in CVD.items()}
    rows, failures = [], []
    for a, b in itertools.combinations(colors, 2):
        de = {v: ciede2000(labs[v][a], labs[v][b]) for v in CVD}
        rows.append((a, b, de))
        if min(de.values()) < min_de:
            failures.append((a, b, de))
    return rows, failures


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--css', default=str(CSS))
    p.add_argument('--min-de', type=float, default=12.0)
    args = p.parse_args(argv)

    colors = read_tokens(args.css)
    missing = [t for t in TOKENS if t not in colors]
    if missing:
        print(f'missing tokens in {args.css}: {", ".join(missing)}')
        return 2
    rows, failures = check(colors, args.min_de)
    worst = sorted(rows, key=lambda r: min(r[2].values()))[:8]
    print('closest pairs (CIEDE2000; normal / protan / deutan):')
    for a, b, de in worst:
        print(f'  {a:>8} {colors[a]} vs {b:<8} {colors[b]}: '
              + ' / '.join(f'{de[v]:5.1f}' for v in CVD))
    if failures:
        print(f'{len(failures)} pair(s) below dE {args.min_de:g}')
        return 1
    print(f'all {len(rows)} pairs >= dE {args.min_de:g} under all three')
    return 0


if __name__ == '__main__':
    sys.exit(main())
