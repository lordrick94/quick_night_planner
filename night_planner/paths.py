"""Where everything lives, worked out rather than written down.

Created by JXP and Claude

Hardcoded absolute paths like ``/home/lordrick/Projects/night-planner`` were
scattered through this repo, which meant the code only ran on one laptop.
``night_planner/make_lick_night_plan.py`` already carried a ``/home/xavier/...``
default that had been broken on the other author's machine for months -- the
failure mode is silent until someone else runs it.

Paths split into two kinds, and they want opposite treatment:

**Inside the repo** -- the repo root, ``scripts/``, ``test_targs/``. These are
*derived* from this file's own location and are never configurable. Making them
settings would be strictly worse: one more thing to get wrong, and they cannot
be wrong when computed.

**Night plans are private.** The repo is public but the targets in a night
plan (unpublished FRB host positions) are not, so plans never live in a
tracked directory. They go to ``NIGHT_PLANNER_PLANS`` when set, else to the
git-ignored ``<repo>/pvt_Nighplans/``. ``Night_plans/`` is git-ignored too, as
a safety net for old commands that still spell it out.

**Outside the repo** -- the FFFF-PZ checkout, the Lick night-plan template on
``/mnt/scratch``. These genuinely differ per machine, so they read from
environment variables, with a sensible guess where one exists and a plain error
naming the variable where it does not.

Environment variables
---------------------
``NIGHT_PLANNER_PLANS``
    Private plan directory. Defaults to ``<repo>/pvt_Nighplans`` (git-ignored).
    JXP/LK set it in the conda env:
    ``conda env config vars set NIGHT_PLANNER_PLANS=<repo>/pvt_Nighplans``.
``FFFF_PZ_REPO``
    The ``chime-ffff-pz`` checkout. Defaults to a sibling of this repo, which
    is how both authors have it laid out.
``LICK_NIGHT_PLAN_TEMPLATE``
    The template .xlsx the Lick workbook builder copies its checklist from.
    No default -- it lives on observatory scratch space with no portable
    location.
"""

import os
from pathlib import Path

# This file is <repo>/night_planner/paths.py, so the repo root is two up.
# Same idiom already used by night_planner/cli.py and backend/app.py.
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / 'scripts'
TEST_TARGS_DIR = REPO_ROOT / 'test_targs'
# Default home of the (private, git-ignored) night plans.
PRIVATE_PLANS_DIR = REPO_ROOT / 'pvt_Nighplans'


def plans_dir():
    """
    Directory the generated night plans are written into.

    Created by JXP and Claude

    Inputs
    ------
    none (reads NIGHT_PLANNER_PLANS).

    Outputs
    -------
    Path. NIGHT_PLANNER_PLANS when set, else ``<repo>/pvt_Nighplans``. Both
    are private: real targets must never land in a tracked directory.
    """
    override = os.getenv('NIGHT_PLANNER_PLANS')
    return Path(override).expanduser() if override else PRIVATE_PLANS_DIR


def plan_dir(name):
    """
    One named run's plan directory, e.g. plan_dir('Lick-2026B-02').

    Created by JXP and Claude

    Inputs
    ------
    name : str
        Run directory name.

    Outputs
    -------
    Path (not created, and not required to exist).
    """
    return plans_dir() / name


def ffffpz_root(required=True):
    """
    The chime-ffff-pz checkout this repo reads target and finder data from.

    Created by JXP and Claude

    Inputs
    ------
    required : bool
        Raise if it cannot be found. Pass False to test for its presence.

    Outputs
    -------
    Path, or None when required=False and nothing was found.

    Raises
    ------
    FileNotFoundError
        Naming the environment variable to set, rather than failing later
        with a confusing missing-file error deep inside a data read.
    """
    override = os.getenv('FFFF_PZ_REPO')
    if override:
        path = Path(override).expanduser()
        if path.is_dir():
            return path
        if required:
            raise FileNotFoundError(
                f'FFFF_PZ_REPO is set to {path}, which is not a directory')
        return None

    # Both authors keep the two repos side by side; guess that before giving up.
    sibling = REPO_ROOT.parent / 'chime-ffff-pz'
    if sibling.is_dir():
        return sibling
    if required:
        raise FileNotFoundError(
            'cannot find the chime-ffff-pz checkout. Set FFFF_PZ_REPO to it, '
            f'or put it beside this repo at {sibling}')
    return None


def ffffpz_data(*parts, required=True):
    """
    A path inside chime-ffff-pz's package data directory.

    Created by JXP and Claude

    Inputs
    ------
    *parts : str
        Path components below ``chime_ffff_pz/data``, e.g. 'Observing'.
    required : bool
        Passed through to ffffpz_root().

    Outputs
    -------
    Path, or None when required=False and the checkout was not found.
    """
    root = ffffpz_root(required=required)
    if root is None:
        return None
    return root.joinpath('chime_ffff_pz', 'data', *parts)


def ffffpz_module(*parts, required=True):
    """
    A path inside the chime_ffff_pz package itself (not its data directory).

    Created by JXP and Claude

    Inputs
    ------
    *parts : str
        Path components below ``chime_ffff_pz``, e.g. 'pypeit_reduce'.
    required : bool
        Passed through to ffffpz_root().

    Outputs
    -------
    Path, or None when required=False and the checkout was not found.
    """
    root = ffffpz_root(required=required)
    if root is None:
        return None
    return root.joinpath('chime_ffff_pz', *parts)


def lick_template(required=True):
    """
    The Lick night-plan template workbook, copied for its checklist sheet.

    Created by JXP and Claude

    It has no default: the only known copy lives on observatory scratch
    space, and guessing a path for a file the builder opens read-only would
    turn a clear "set this variable" into a confusing missing-file trace.

    Inputs
    ------
    required : bool
        Raise if LICK_NIGHT_PLAN_TEMPLATE is unset.

    Outputs
    -------
    Path, or None when required=False and the variable is unset.

    Raises
    ------
    FileNotFoundError
        Naming the environment variable to set.
    """
    override = os.getenv('LICK_NIGHT_PLAN_TEMPLATE')
    if override:
        return Path(override).expanduser()
    if required:
        raise FileNotFoundError(
            'set LICK_NIGHT_PLAN_TEMPLATE to the night-plan template .xlsx '
            '(e.g. .../Lick_Kast/obs_docs/2026/Lick-2026A-4/'
            'Lick_2026A-4_Night_plan.xlsx) -- it has no portable location')
    return None
