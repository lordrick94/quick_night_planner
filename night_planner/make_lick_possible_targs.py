# Created by JXP and Claude
"""Build a Lick/Kast observing spreadsheet from an FFFF-PZ targets CSV.

Created by JXP and Claude

Converts the primary-host decimal-degree coordinates in a
``chime_ffff_pz_targets`` CSV to sexagesimal, applies the Shane 3 m
pointing limit (no targets above a declination limit, default +82 deg),
sorts by RA, and writes an .xlsx that mimics the columns of the
``possible_targs.xlsx`` templates in obs_docs/2026:
TNS, RA_HMS, DEC_DMS, Epoch, Pri_mag, Sec_mag.
"""

import argparse

import pandas as pd
from astropy.coordinates import Angle
import astropy.units as u


def load_targets(csv_path):
    """Load an FFFF-PZ targets CSV.

    Created by JXP and Claude

    Parameters
    ----------
    csv_path : str
        Path to the CSV written by ``chime_ffff_pz_targets`` (must contain
        at least TNS, Pri_RA, Pri_Dec, Pri_mag, Sec_mag columns).

    Returns
    -------
    pandas.DataFrame
        The targets table, unmodified.
    """
    return pd.read_csv(csv_path)


def deg_to_sexagesimal(ra_deg, dec_deg):
    """Convert decimal-degree coordinates to sexagesimal strings.

    Created by JXP and Claude

    Parameters
    ----------
    ra_deg : float
        Right ascension in decimal degrees.
    dec_deg : float
        Declination in decimal degrees.

    Returns
    -------
    tuple of str
        (RA as ``HH:MM:SS.ss``, Dec as ``±DD:MM:SS.ss``).
    """
    ra_hms = Angle(ra_deg * u.deg).to_string(
        unit=u.hourangle, sep=':', precision=2, pad=True)
    dec_dms = Angle(dec_deg * u.deg).to_string(
        unit=u.deg, sep=':', precision=2, pad=True, alwayssign=True)
    return ra_hms, dec_dms


def build_possible_targs(targets, dec_limit=82.0, epoch=2000.0):
    """Build the possible-targets table from an FFFF-PZ targets DataFrame.

    Created by JXP and Claude

    Parameters
    ----------
    targets : pandas.DataFrame
        Table from :func:`load_targets` with TNS, Pri_RA, Pri_Dec (decimal
        degrees), Pri_mag, and Sec_mag columns.
    dec_limit : float, optional
        Maximum declination in degrees (Shane pointing limit).  Rows with
        primary-host Dec above this value are excluded.  Default 82.0.
    epoch : float, optional
        Coordinate epoch written to the Epoch column.  Default 2000.0.

    Returns
    -------
    tuple of pandas.DataFrame
        (possible_targs, dropped): the spreadsheet table with columns
        TNS, RA_HMS, DEC_DMS, Epoch, Pri_mag, Sec_mag sorted by RA, and
        the rows removed by the declination cut (original CSV columns).
    """
    keep = targets['Pri_Dec'] <= dec_limit
    dropped = targets[~keep].copy()
    kept = targets[keep].copy()

    ra_hms, dec_dms = [], []
    for _, row in kept.iterrows():
        ra_s, dec_s = deg_to_sexagesimal(row['Pri_RA'], row['Pri_Dec'])
        ra_hms.append(ra_s)
        dec_dms.append(dec_s)

    possible = pd.DataFrame({
        'TNS': kept['TNS'].values,
        'RA_HMS': ra_hms,
        'DEC_DMS': dec_dms,
        'Epoch': epoch,
        'Pri_mag': kept['Pri_mag'].values,
        'Sec_mag': kept['Sec_mag'].values,
        'RA_deg': kept['Pri_RA'].values,
    })
    possible = possible.sort_values('RA_deg').drop(columns='RA_deg')
    possible = possible.reset_index(drop=True)
    return possible, dropped


def write_xlsx(possible, xlsx_path, sheet_name='possible_targs'):
    """Write the possible-targets table to an Excel file.

    Created by JXP and Claude

    Parameters
    ----------
    possible : pandas.DataFrame
        Table from :func:`build_possible_targs`.
    xlsx_path : str
        Output .xlsx path.
    sheet_name : str, optional
        Name of the worksheet.  Default ``possible_targs`` (matches the
        obs_docs/2026 templates).

    Returns
    -------
    None
        Writes ``xlsx_path`` to disk.
    """
    possible.to_excel(xlsx_path, sheet_name=sheet_name,
                      index=False, engine='openpyxl')


def main():
    """Command-line driver: CSV in, xlsx out, with a declination cut.

    Created by JXP and Claude

    Inputs (argparse)
    -----------------
    csv : str
        Input FFFF-PZ targets CSV.
    xlsx : str
        Output spreadsheet path.
    --dec_limit : float, optional
        Maximum declination in degrees (default 82.0).

    Returns
    -------
    None
        Writes the xlsx and prints kept/dropped targets to stdout.
    """
    parser = argparse.ArgumentParser(
        description='Build a Lick/Kast possible_targs.xlsx from an '
                    'FFFF-PZ targets CSV.')
    parser.add_argument('csv', help='Input targets CSV from chime_ffff_pz_targets')
    parser.add_argument('xlsx', help='Output .xlsx path')
    parser.add_argument('--dec_limit', type=float, default=82.0,
                        help='Maximum Dec in deg (Shane pointing limit; '
                             'default 82.0)')
    args = parser.parse_args()

    targets = load_targets(args.csv)
    possible, dropped = build_possible_targs(targets, dec_limit=args.dec_limit)
    write_xlsx(possible, args.xlsx)

    print(f'Wrote {len(possible)} targets to {args.xlsx}')
    if len(dropped) > 0:
        print(f'Dropped {len(dropped)} target(s) with Dec > '
              f'{args.dec_limit:.1f} deg:')
        for _, row in dropped.iterrows():
            print(f"  {row['TNS']}  Pri_Dec={row['Pri_Dec']:.4f}")
    print(possible.to_string(index=False))


if __name__ == '__main__':
    main()
