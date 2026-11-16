"""Tests for pointing limits read from data (2026-11-15).

Created by JXP and Claude.

The file must reproduce the limits that were hardcoded before, so moving
them changed no plan; overrides must parse strictly and actually change
which targets are observable.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

from night_planner.site_limits import (describe_limits, load_site_limits,  # noqa: E402
                                       parse_limit_overrides)

TARGETS = str(REPO_ROOT / 'test_targs' / 'autumn_ffffpz.csv')
DATE = '2026-10-19'


def test_file_matches_the_old_constants():
    """-05:40, +03:45, Dec +82, no airmass limit, no southern limit.

    Inputs: none. Outputs: none (asserts on success).
    """
    lim = load_site_limits('lick')
    assert lim['ha_east'] == pytest.approx(-(5 + 40 / 60))
    assert lim['ha_west'] == pytest.approx(3.75)
    assert lim['dec_max'] == 82.0
    assert lim['dec_min'] is None and lim['airmass_max'] is None
    import lick_2026b02_calculations as lc
    assert (lc.HA_MIN, lc.HA_MAX, lc.DEC_LIMIT) == (lim['ha_east'], lim['ha_west'],
                                                   lim['dec_max'])


def test_overrides_parse_and_validate():
    """KEY=VALUE, 'none' removes, unknown keys and bad values are refused.

    Inputs: none. Outputs: none (asserts on success).
    """
    assert parse_limit_overrides(['dec_max=72', 'airmass_max=1.7', 'dec_min=none']) == \
        {'dec_max': 72.0, 'airmass_max': 1.7, 'dec_min': None}
    for bad in (['dec_max'], ['color=1'], ['dec_max=high'], ['dec_max=inf']):
        with pytest.raises(ValueError):
            parse_limit_overrides(bad)
    with pytest.raises(ValueError):
        load_site_limits('lick', {'ha_east': 4.0})
    lim = load_site_limits('lick', {'dec_max': 72.0})
    assert lim['overridden'] == ['dec_max']
    assert 'overrides dec_max' in describe_limits(lim)


def test_overrides_change_observability():
    """A lower Dec ceiling and an airmass ceiling remove or shrink windows.

    Inputs: none. Outputs: none (asserts on success).
    """
    import kast_calculations as kc
    base, _ = kc.analyze_targets(TARGETS, DATE)
    north = base[(base['Dec_deg'] > 60) & (base['Dec_deg'] <= 82) & base['observable']]
    if not len(north):
        pytest.skip('no target between +60 and +82 in the test table')
    tight, _ = kc.analyze_targets(TARGETS, DATE,
                                  limits=load_site_limits('lick', {'dec_max': 60.0}))
    for name in north['TNS']:
        row = tight.set_index('TNS').loc[name]
        assert not row['observable'] and 'above the Shane' in row['limit_reason']

    clipped, _ = kc.analyze_targets(TARGETS, DATE,
                                    limits=load_site_limits('lick', {'airmass_max': 1.5}))
    b, c = base.set_index('TNS'), clipped.set_index('TNS')
    for name in b.index[b['observable']]:
        if c.loc[name, 'observable']:
            assert c.loc[name, 'window_min'] <= b.loc[name, 'window_min'] + 1e-6
