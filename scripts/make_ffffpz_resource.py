"""
Write an FFFF-PZ FRBFollowUpResource JSON for one night.

The only field that needs real computing is the validity window: FFFF-PZ
wants it in UTC, while the run is defined by a local date at the
telescope, and the two differ by a calendar day for Keck. This derives it
from actual twilight for that site and date rather than hand-arithmetic.

    python scripts/make_ffffpz_resource.py --name Keck-2026B-03 --date 2026-11-07

Writes the JSON only. Adding it to a server is a separate, deliberate
step (`chime_ffff_pz_add_furesource`), and is not done here.

Created by JXP and Claude
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import timezone

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
from night_planner.paths import plans_dir

_PLANS = plans_dir()
from night_planner.adapters import SITES
from night_planner.sun_events import find_sun_events

# Which pair of sun events brackets the Resource's validity window.
BRACKETS = {
    'nautical': ('dusk_nautical', 'dawn_nautical'),
    'astronomical': ('dusk_astronomical', 'dawn_astronomical'),
    'sun': ('sunset', 'sunrise'),
}


def parse_args(argv=None):
    """
    Parameters
    ----------
    argv : list of str, optional

    Returns
    -------
    argparse.Namespace
    """
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--name', required=True, help='Resource name, e.g. Keck-2026B-03.')
    p.add_argument('--date', required=True,
                   help='Local evening date of the run, YYYY-MM-DD.')
    p.add_argument('--instrument', default='LRIS',
                   help='FFFF-PZ instrument name [LRIS].')
    p.add_argument('--site', default='lris', choices=sorted(SITES),
                   help='Which observatory the instrument is on [lris].')
    p.add_argument('--bracket', default='nautical', choices=sorted(BRACKETS),
                   help='Sun events bounding valid_start/valid_stop [nautical]. '
                        'Nautical is a little wider than the dark window; the '
                        'planner applies the real airmass/HA cuts downstream.')
    p.add_argument('--num-mask', type=int, default=10)
    p.add_argument('--num-longslit', type=int, default=20)
    p.add_argument('--num-img', type=int, default=0)
    p.add_argument('--max-am', type=float, default=2.0)
    p.add_argument('--min-mag', type=float, default=19.0,
                   help='Keck rule: do not spend 10m time on what Lick can '
                        'reach [19.0].')
    p.add_argument('--max-mag', type=float, default=None)
    p.add_argument('--out', help='Output path [Night_plans/<name>/<name>.json].')
    return p.parse_args(argv)


def validity_window(date, site, bracket):
    """
    UTC validity window for a local observing date.

    Parameters
    ----------
    date : str, local evening date 'YYYY-MM-DD'
    site : str, key into SITES
    bracket : str, key into BRACKETS

    Returns
    -------
    (str, str) : valid_start, valid_stop as 'YYYY-MM-DDTHH:MM:SSZ'
    """
    info = SITES[site]
    sun = find_sun_events(date, info['location'], info['tz'])
    start_key, stop_key = BRACKETS[bracket]

    def as_utc(dt):
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    return as_utc(getattr(sun, start_key)), as_utc(getattr(sun, stop_key))


def build_resource(args):
    """
    Assemble the Resource dict.

    min_POx / frb_tags / frb_statuses are left null deliberately -- the
    FFFF-PZ HOWTO warns that setting them narrows the pull in ways that
    are easy to misread as "no targets available".

    Returns
    -------
    dict
    """
    valid_start, valid_stop = validity_window(args.date, args.site, args.bracket)
    return {
        'instrument': args.instrument,
        'name': args.name,
        'valid_start': valid_start,
        'valid_stop': valid_stop,
        'num_targ_img': args.num_img,
        'num_targ_mask': args.num_mask,
        'num_targ_longslit': args.num_longslit,
        'max_AM': args.max_am,
        'frb_surveys': 'all',
        'obs_type': None,
        'Program': None,
        'Period': None,
        'min_POx': None,
        'frb_tags': None,
        'frb_statuses': None,
        'min_mag': args.min_mag,
        'max_mag': args.max_mag,
    }


def main(argv=None):
    """Write the Resource JSON and print what it covers."""
    args = parse_args(argv)
    resource = build_resource(args)

    out = args.out or (f'{_PLANS}/'
                       f'{args.name}/{args.name}.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as f:
        json.dump(resource, f, indent=4)
        f.write('\n')

    print(f'Wrote {out}')
    print(f'  {args.instrument} at {SITES[args.site]["telescope"]}, '
          f'local night of {args.date}')
    print(f'  valid {resource["valid_start"]} -> {resource["valid_stop"]} '
          f'({args.bracket} twilight)')
    print(f'  asking for {args.num_mask} mask + {args.num_longslit} longslit, '
          f'min_mag {args.min_mag}, max_AM {args.max_am}')
    print('\nTo add it to FFFF-PZ (deliberate step, not done here):')
    print(f'  cp {out} <chime-ffff-pz>/chime_ffff_pz/data/Observing/{args.name}/')
    print(f'  chime_ffff_pz_add_furesource {args.name}.json')
    print(f'  chime_ffff_pz_targets {args.name}')
    return out


if __name__ == '__main__':
    main()
