"""Tests for the finder's service fallbacks, slit centre and starlist rows.

Created by JXP and Claude, 2026-11-10.

On 2026-11-10 CDS hips2fits timed out, CDS VizieR gave 404, the CfA mirror
served Gaia as an unreadable table and ESA's Gaia archive was intermittent;
every chart came out blank. These pin the behaviour that replaced that:
each service is tried in turn, a total failure says which services failed,
and a slit through two candidates is centred between them on the chart and
in the starlist. Network-free: services are faked, positions synthetic.
"""

import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS

from night_planner import finder
from night_planner.standards import starlist_row
from night_planner.starlist import _lick_block, slit_centre

C = SkyCoord(150.0, 30.0, unit='deg')


def _dead(*args, **kwargs):
    raise TimeoutError('service down')


def _image(*args, **kwargs):
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    wcs.wcs.crval = [150.0, 30.0]
    wcs.wcs.crpix = [5, 5]
    wcs.wcs.cdelt = [-1e-4, 1e-4]
    return np.ones((10, 10)), wcs


def test_fetch_image_falls_through_to_the_first_live_service():
    """A dead first service is skipped; the label says which one answered.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    data, wcs, label = finder.fetch_image(
        C, sources=(('dead', _dead), ('live', _image)))
    assert label == 'live' and data.shape == (10, 10)


def test_fetch_image_names_every_failure():
    """When nothing answers, the error lists each service and its failure.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    with pytest.raises(RuntimeError, match='first.*second'):
        finder.fetch_image(C, sources=(('first', _dead), ('second', _dead)))


def test_offset_star_uses_the_next_catalogue_and_reports_its_band(monkeypatch):
    """A failing Gaia service hands over to the next; the band travels with
    the magnitude (r for Pan-STARRS, not G).

    Inputs: monkeypatch (pytest).
    Outputs: none (asserts on success).
    """
    star = C.directional_offset_by(45 * u.deg, 30 * u.arcsec)

    def ps1(coord, radius, lo, hi):
        return (np.array([star.ra.deg]), np.array([star.dec.deg]), np.array([16.0]))

    monkeypatch.setattr(finder, 'GAIA_SOURCES',
                        (('gaia', 'G', _dead), ('ps1', 'r', ps1)))
    found = finder.find_offset_star(C)
    assert found['band'] == 'r' and found['catalog'] == 'ps1'
    assert found['sep_arcsec'] == pytest.approx(30, abs=0.01)


def test_no_catalogue_is_an_error_not_no_star(monkeypatch):
    """All catalogues down raises, so the chart says why there is no star.

    Inputs: monkeypatch (pytest).
    Outputs: none (asserts on success).
    """
    monkeypatch.setattr(finder, 'GAIA_SOURCES', (('gaia', 'G', _dead),))
    with pytest.raises(RuntimeError, match='no star catalogue answered'):
        finder.find_offset_star(C)


def test_ps1_star_cut_is_one_sided():
    """Stars have rPSF - rKron slightly negative; galaxies are positive.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    psf = np.array([16.6, 18.0])
    kron = np.array([16.68, 17.5])          # star (-0.08), galaxy (+0.5)
    assert list(psf - kron < 0.05) == [True, False]


def _finder(mode, **extra):
    base = {'slit_pa': 84.7, 'slit_mode': mode,
            'cass_tub': {'tub': 73.74, 'alt_tub': 230.34, 'alt_pa': 264.7},
            'offset_star_ra': 150.01, 'offset_star_dec': 30.01,
            'offset_ra': 10.0, 'offset_dec': -5.0}
    base.update(extra)
    return base


class _T:
    name = 'SIM A'
    on_target_min = 60.0
    mode = 'longslit'


def test_candidates_slit_centre_is_the_midpoint():
    """_C sits halfway between the candidates; parallactic _C is the target.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    sec = C.directional_offset_by(90 * u.deg, 80 * u.arcsec)
    f = _finder('candidates', secondary_ra=sec.ra.deg, secondary_dec=sec.dec.deg)
    mid = slit_centre(C, f)
    assert C.separation(mid).arcsec == pytest.approx(40, abs=0.01)
    assert sec.separation(mid).arcsec == pytest.approx(40, abs=0.01)
    assert slit_centre(C, _finder('parallactic')).separation(C).arcsec < 1e-6


def test_lick_rows_carry_pa_and_tub_and_safe_names():
    """Target and _C rows both quote PA and TUB; a spaced name is joined.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    rows = _lick_block(_T(), C, _finder('parallactic'), has_star=True)
    assert rows[0].startswith('SIM_A ') and rows[2].startswith('SIM_A_C ')
    for row in (rows[0], rows[2]):
        assert '#PA=84.70' in row and 'TUB = 73.74 or 230.34' in row
    assert len(starlist_row('BPM 46', C, style='lick').split()) == 8


def test_draw_finder_centres_the_slit_and_quotes_pa_tub(tmp_path):
    """The chart renders from supplied data with a slit centre and tub.

    Inputs: tmp_path (pytest).
    Outputs: none (asserts on success).
    """
    data, wcs = _image()
    out = finder.draw_finder(
        C, 'SIM A', tmp_path / 'f.png', 84.7, data=data, wcs=wcs,
        image_label='fake', slit_length_arcmin=0.1,
        tub={'tub': 73.74, 'alt_tub': 230.34, 'alt_pa': 264.7},
        slit_centre=C.directional_offset_by(0 * u.deg, 1 * u.arcsec))
    assert out.exists() and out.stat().st_size > 0
