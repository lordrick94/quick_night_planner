"""Smoke test: the package imports and exposes a version.

Created by JXP and Claude.
"""

import night_planner


def test_import():
    """Package imports and reports a non-empty __version__ string.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    assert isinstance(night_planner.__version__, str)
    assert night_planner.__version__
