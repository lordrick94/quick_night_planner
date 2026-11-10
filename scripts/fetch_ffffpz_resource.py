"""
Check out an existing Resource from FFFF-PZ.

Uses chime_ffff_pz's own API layer
(`chime_ffff_pz.utils.ffff_pz_utils.grab_resource`, which GETs
`api/frbresources/` with HTTP Basic auth) rather than re-implementing the
request, so URL fixups and auth stay in one place.

`chime_ffff_pz` may live in a different conda environment than this one
(both authors keep it in an `frb_env`). Run this with that interpreter,
whatever it is called on your machine:

    conda run -n frb_env python scripts/fetch_ffffpz_resource.py Keck-2026B-03

Read-only: it fetches and writes a local JSON, and never PUTs anything
back to the server.

Created by JXP and Claude
"""

import argparse
import json
import os
import sys

GLOBAL_URL = 'https://frb.chimenet.ca/f4pz/'

# The fields an add_frb_resource payload carries, in the order our local
# Resource JSONs use them.
RESOURCE_FIELDS = [
    'instrument', 'name', 'valid_start', 'valid_stop', 'num_targ_img',
    'num_targ_mask', 'num_targ_longslit', 'max_AM', 'frb_surveys',
    'obs_type', 'Program', 'Period', 'min_POx', 'frb_tags', 'frb_statuses',
    'min_mag', 'max_mag',
]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('resource', help='Resource name, e.g. Keck-2026B-03.')
    p.add_argument('--url', default=GLOBAL_URL,
                   help=f'FFFF-PZ base URL [{GLOBAL_URL}]. The shell default '
                        f'usually points at the local docker instance.')
    p.add_argument('--out', help='Write the Resource JSON here.')
    p.add_argument('--raw', action='store_true',
                   help='Print every field the server returned, not just the '
                        'ones a Resource JSON carries.')
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # grab_resource() reads this at call time, so it has to be set before
    # the import-time default is captured.
    os.environ['FFFF_PZ_URL'] = args.url
    for key in ('FFFF_PZ_USER', 'FFFF_PZ_PASS'):
        if not os.getenv(key):
            raise SystemExit(f'{key} is not set -- it lives in ~/.bashrc')

    from chime_ffff_pz.utils.ffff_pz_utils import grab_resource

    frame = grab_resource(args.resource)
    if frame.empty:
        raise SystemExit(f'{args.resource} is not on {args.url}')

    row = frame.iloc[0].to_dict()

    print(f'\n=== {args.resource} on {args.url} ===')
    shown = row if args.raw else {k: row.get(k) for k in RESOURCE_FIELDS
                                   if k in row}
    for key, value in shown.items():
        print(f'  {key:20s} {value}')

    if args.raw:
        extra = sorted(set(row) - set(RESOURCE_FIELDS))
        if extra:
            print(f'\n  (server-side fields not in a Resource JSON: '
                  f'{", ".join(extra)})')

    if args.out:
        payload = {k: _clean(row.get(k)) for k in RESOURCE_FIELDS if k in row}
        # The API hands back instrument as a hyperlink; a Resource JSON
        # wants the name, so it can be re-submitted as-is.
        payload['instrument'] = _instrument_name(row.get('instrument'))
        with open(args.out, 'w') as f:
            json.dump(payload, f, indent=4)
            f.write('\n')
        print(f'\nWrote {args.out}')
    return row


def _clean(value):
    """
    Make a server value JSON-safe.

    Pandas turns absent numbers into NaN, and json.dump writes that as a
    bare `NaN` -- which Python reads back but is not valid JSON and will
    trip any other reader. Absent means null.
    """
    if isinstance(value, float) and value != value:   # NaN
        return None
    return value


def _instrument_name(value):
    """Resolve an instrument hyperlink to its name, e.g. 'LRIS'."""
    if not isinstance(value, str) or not value.startswith('http'):
        return value
    from chime_ffff_pz.utils.ffff_pz_utils import get_data

    data = get_data(value)
    return data.get('name', value) if data else value


if __name__ == '__main__':
    main()
