"""A user-supplied ETC, as `--etc tests.fake_etc:etc` would load it.

Created by JXP and Claude.

It records every call, so tests can check that a plan used it and what it
was asked.
"""

CALLS = []


def etc(mag, band, airmass, seeing, config, target_sn, n_sub_min):
    """
    Fixed 3 x 300 s for every target; records the call.

    Returns
    -------
    dict in the night_planner.etc signature.
    """
    CALLS.append({'mag': mag, 'band': band, 'airmass': airmass,
                  'seeing': seeing, 'config': dict(config),
                  'target_sn': target_sn})
    return {'sub_len_s': 300, 'n_sub': n_sub_min,
            'sn_sub': {'blue': 7.0, 'red': 8.0}, 'wave': [], 's2n': []}
