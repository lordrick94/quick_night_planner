"""
Created by JXP and Claude

Check the toy AstroScheduler schedule against the real AstroScheduler solver.

scripts/compare_scheduler_styles_toy.py re-implements AstroScheduler's
tiered branch and bound in miniature. This script runs the real package
(astroscheduler v1.3.0, read-only checkout) on real-sky versions of the
same toy targets and prints where it puts them, so the toy can be trusted.

Each toy target becomes a real one: RA is the local sidereal time at
(night start + transit minutes), so it transits when the toy says; Dec and
priority are copied; the block length is fixed with manual_duration =
science minutes + the 7-min overhead. The night is clamped to the toy's
540 minutes from the evening 18-degree twilight, and standards are off,
as in the toy.

Inputs
------
--repo PATH : AstroScheduler checkout (default ~/Projects/misc_repos/AstroScheduler)
--date YYYY-MM-DD : local evening date of the night (default 2026-11-20)

Outputs
-------
Prints, per scenario, each block as minutes after the night start, plus
the conflicts and unobservable lists.
"""
import argparse
import datetime
import os
import sys

import numpy as np
from astropy import units as u
from astropy.coordinates import Longitude
from astropy.time import Time

sys.path.insert(0, os.path.dirname(__file__))
from compare_scheduler_styles_toy import (AS_OVERHEAD_MIN, NIGHT_MIN,  # noqa: E402
                                          SCENARIOS)


def main():
    """Run the real solver on each toy scenario and print the placements."""
    p = argparse.ArgumentParser(description='Check the toy against AstroScheduler')
    p.add_argument('--repo', default=os.path.expanduser('~/Projects/misc_repos/AstroScheduler'))
    p.add_argument('--date', default='2026-11-20')
    args = p.parse_args()
    np.random.seed(42)  # nothing here is random; fixed by convention

    sys.path.insert(0, args.repo)
    import astroscheduler
    from astroscheduler.api import SiteSpec, SolveRequest, TargetSpec, solve
    from astroscheduler.core import Observatory

    date = datetime.date.fromisoformat(args.date)
    obs = Observatory('Lick', 37.3414, -121.6429, 1283)
    eve18 = obs.get_night_parameters(date)['solar_times']['twilight_evening_18']
    start = eve18.replace(second=0, microsecond=0)
    if start.tzinfo is None:
        start = start.replace(tzinfo=datetime.timezone.utc)
    end = start + datetime.timedelta(minutes=NIGHT_MIN)
    print(f'astroscheduler {astroscheduler.__version__}; night {start:%Y-%m-%d %H:%M} '
          f'to {end:%H:%M} UTC ({NIGHT_MIN} min)')

    for key, toy in SCENARIOS.items():
        specs = []
        for t in toy:
            when = Time(start + datetime.timedelta(minutes=t['transit']))
            lst = when.sidereal_time('apparent', longitude=Longitude(-121.6429 * u.deg))
            specs.append(TargetSpec(name=t['name'], ra=float(lst.hour), dec=t['dec'],
                                    magnitude=18.0, priority=t['priority'],
                                    manual_duration=t['exp'] + AS_OVERHEAD_MIN))
        res = solve(SolveRequest(date=date, site=SiteSpec(id='lick'), targets=specs,
                                 auto_standards=False, selected_standards=[],
                                 night_start_override=start.isoformat(),
                                 night_end_override=end.isoformat()))
        print(f'\n[{key}]')
        for b in res.blocks:
            s = datetime.datetime.fromisoformat(b.start_time)
            if s.tzinfo is None:
                s = s.replace(tzinfo=datetime.timezone.utc)
            off = (s - start).total_seconds() / 60.0
            print(f'  {b.target_name:6s} P{b.priority:g}  {off:5.0f} -> {off + b.duration_minutes:5.0f} min'
                  f'  median airmass {b.airmass_median:.3f}')
        print(f'  conflicts:    {res.conflicts}')
        print(f'  unobservable: {res.unobservable}')


if __name__ == '__main__':
    main()
