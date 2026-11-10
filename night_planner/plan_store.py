"""
Persist a PlanResult next to the plan's other artifacts, so the viewer can
reload a night without re-running the scheduler.

Regenerating costs a minute or two (the Keck path makes live calls to the
UCO/Lick ETC for every target), which is fine for a deliberate "generate"
click and far too slow for a page load. `plan_result.json` is the
normalized plan exactly as the API serves it.

Created by JXP and Claude
"""

import json
import os

from .plan_result import PlanResult

FILENAME = 'plan_result.json'


def save_plan(plan, output_dir=None):
    """
    Write plan_result.json into the plan's output directory.

    Parameters
    ----------
    plan : PlanResult
    output_dir : str, optional
        Defaults to the plan's own output_dir.

    Returns
    -------
    str : the path written
    """
    output_dir = output_dir or plan.output_dir
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, FILENAME)
    with open(path, 'w') as f:
        json.dump(plan.to_dict(), f, indent=2)
    return path


def load_plan(output_dir):
    """
    Read back a previously-saved PlanResult.

    Parameters
    ----------
    output_dir : str

    Returns
    -------
    PlanResult, or None if this directory has no saved plan yet.
    """
    path = os.path.join(output_dir, FILENAME)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return PlanResult.from_dict(json.load(f))
