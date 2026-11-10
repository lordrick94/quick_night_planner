"""Shared pytest setup: tests never touch the network.

Created by JXP and Claude.

Every test gets, automatically:
- sockets blocked, so an accidental network call fails loudly;
- astropy's IERS table used offline (no download, no age limit) -- with
  the network blocked, a stale cache otherwise makes every sidereal-time
  calculation raise; and
- night_planner.etc.query_uco_etc replaced by fake_query(), a
  deterministic stand-in: S/N goes as sqrt(t), and degrades with magnitude,
  airmass and seeing.

A test marked @pytest.mark.network keeps the real network and the real
ETC.
"""

import math
import socket

import numpy as np
import pytest

from night_planner import etc as _etc

_REAL_QUERY = _etc.query_uco_etc


def pytest_addoption(parser):
    parser.addoption('--run-network', action='store_true', default=False,
                     help='also run tests marked network (real UCO/Lick ETC)')


def pytest_configure(config):
    config.addinivalue_line('markers',
                            'network: may call the real UCO/Lick ETC')


def pytest_collection_modifyitems(config, items):
    """Skip `network` tests unless --run-network is given."""
    if config.getoption('--run-network'):
        return
    skip = pytest.mark.skip(reason='needs --run-network (calls the real ETC)')
    for item in items:
        if 'network' in item.keywords:
            item.add_marker(skip)


def fake_query(inst, mag, exptime, airmass, seeing, config, ffilter, **kwargs):
    """
    Deterministic stand-in for night_planner.etc.query_uco_etc.

    Returns
    -------
    (wave, s2n) on a 10 A grid (3150-8000 A for Kast, 3150-10000 A for
    LRIS). S/N = 12 x 10^(-0.4 (mag - 20)) x sqrt(t / 600) / airmass^1.5
    x (0.8 / seeing), flat in wavelength. Not physics, just monotonic in the
    right directions.
    """
    top = 8000.0 if inst == 'kast' else 10000.0
    wave = np.arange(3150.0, top + 1, 10.0)
    sn = (12.0 * 10 ** (-0.4 * (mag - 20.0)) * math.sqrt(exptime / 600.0)
          / airmass ** 1.5 * (0.8 / seeing))
    return wave, np.full_like(wave, sn)


_REAL_CONNECT = socket.socket.connect


def _no_network(*args, **kwargs):
    raise RuntimeError('tests must not touch the network '
                       '(mark the test @pytest.mark.network)')


@pytest.fixture(autouse=True, scope='session')
def _offline_session():
    """Block the network and fake the ETC for the whole session.

    Session-scoped on purpose: a module- or session-scoped fixture (a plan
    shared by several tests) is set up before any function-scoped fixture,
    so a function-scoped block would arrive too late and let it reach the
    real ETC.
    """
    from astropy.utils import iers
    from night_planner import etc

    mp = pytest.MonkeyPatch()
    mp.setattr(iers.conf, 'auto_download', False)
    mp.setattr(iers.conf, 'auto_max_age', None)
    mp.setattr(socket.socket, 'connect', _no_network)
    mp.setattr(etc, 'query_uco_etc', fake_query)
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def _network_opt_in(request, monkeypatch):
    """Fresh ETC cache per test; real network only for `network` tests."""
    from night_planner import etc

    etc.clear_cache()
    if request.node.get_closest_marker('network') is not None:
        monkeypatch.setattr(socket.socket, 'connect', _REAL_CONNECT)
        monkeypatch.setattr(etc, 'query_uco_etc', _REAL_QUERY)
    yield
    etc.clear_cache()
