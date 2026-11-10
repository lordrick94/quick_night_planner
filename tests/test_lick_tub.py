"""
Shane Cassegrain tub conversion, checked against calcint.c.

Created by JXP and Claude
"""

import numpy as np

from night_planner.lick_tub import TUB_TABLE, cass_tub_readout, tub_settings


def test_table_rows_are_exact():
    """Every tabulated angle returns its own tabulated readout."""
    for pa, readout in TUB_TABLE:
        assert cass_tub_readout(pa) == pytest_approx(readout)


def pytest_approx(value):
    """Local tolerance helper, to keep the import list short."""
    import pytest
    return pytest.approx(value, abs=1e-9)


def test_wraps_small_angles_like_calcint():
    """calcint.c lifts 0 <= PA < 20 into the 360-380 range first."""
    assert cass_tub_readout(0.0) == pytest_approx(313.24)
    assert cass_tub_readout(10.0) == pytest_approx(321.94)


def test_conversion_is_not_the_identity():
    """The whole point: the tub readout is not the sky PA."""
    assert abs(cass_tub_readout(108.92) - 108.92) > 10


def test_table_matches_its_linear_form():
    """readout = 0.87 * PA + 0.05, to a hundredth of a count."""
    fit = 0.87 * TUB_TABLE[:, 0] + 0.05
    assert np.max(np.abs(fit - TUB_TABLE[:, 1])) < 0.02


def test_both_settings_are_180_apart():
    """A slit has no head or tail, so each angle has two tub positions."""
    both = tub_settings(100.58)
    assert both['alt_pa'] == pytest_approx(280.58)
    assert both['tub'] != both['alt_tub']
