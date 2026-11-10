"""
Several plans for one night under different conditions, shown as tabs (T4.1).

Created by JXP and Claude

A scenario is a name plus what differs: seeing, start time, extra blocked
windows. Each one is generated into its own ordinary plan directory,
<base>/<slug>/, so finders, starlist and export work per tab unchanged.
<base>/scenarios.json indexes them.

Only one scenario is actually observed, so there is one observing log per
night, at <base>/observing_log.json (see find_base and the log routes in
backend/app.py).
"""

import json
import os
import re

INDEX = 'scenarios.json'

# Presets offered on the setup page. Seeing values are the ones named in the
# goal (users_comments.md, T4.1): good / median / poor. "Lost first half"
# blocks from the start of the night to local midnight.
PRESETS = [
    {'name': 'good seeing', 'seeing': 0.6},
    {'name': 'median seeing', 'seeing': 0.8},
    {'name': 'poor seeing', 'seeing': 1.2},
    {'name': 'lost first half', 'blocks': [{'start': 'night', 'end': '00:00',
                                            'reason': 'lost first half'}]},
]


def slugify(name):
    """
    A directory-safe name for a scenario.

    Parameters
    ----------
    name : str

    Returns
    -------
    str : lowercase letters, digits and '-', e.g. 'good-seeing'.
    """
    slug = re.sub(r'[^a-z0-9]+', '-', str(name).lower()).strip('-')
    return slug or 'scenario'


def scenario_argv(base_argv, scenario, base_dir, night_start_hhmm=None):
    """
    The instrument flags for one scenario.

    Parameters
    ----------
    base_argv : list of str
        The flags shared by every scenario, including --output-dir <base>.
    scenario : dict
        'name' (required), and optionally 'seeing' (float), 'start'
        ('HH:MM'), 'blocks' ([{'start', 'end', 'reason'}], added to the
        shared ones). A block start of 'night' means the start of the
        night (needs night_start_hhmm).
    base_dir : str
    night_start_hhmm : str, optional

    Returns
    -------
    (argv, out_dir) : list of str, str
    """
    out_dir = os.path.join(base_dir, slugify(scenario['name']))
    argv, skip = [], False
    for token in base_argv:
        if skip:
            skip = False
            continue
        if token in ('--output-dir',) or (token in ('--seeing', '--start')
                                          and scenario.get(token[2:]) is not None):
            skip = True
            continue
        argv.append(token)
    argv += ['--output-dir', out_dir]
    if scenario.get('seeing') is not None:
        argv += ['--seeing', str(float(scenario['seeing']))]
    if scenario.get('start'):
        argv += ['--start', str(scenario['start'])]
    for block in scenario.get('blocks') or []:
        start = block.get('start')
        if start == 'night':
            if not night_start_hhmm:
                continue
            start = night_start_hhmm
        argv += ['--block', f"{start}-{block['end']}@{block.get('reason') or 'blocked'}"]
    return argv, out_dir


def comparison(plans):
    """
    The comparison row per scenario.

    Parameters
    ----------
    plans : dict slug -> PlanResult

    Returns
    -------
    dict slug -> {'n_scheduled', 'on_target_h', 'idle_min', 'unique'}
    where 'unique' lists targets scheduled in this scenario and no other.
    """
    names = {slug: {t.name for t in p.schedule} for slug, p in plans.items()}
    out = {}
    for slug, plan in plans.items():
        s = plan.summary()
        others = set().union(*(v for k, v in names.items() if k != slug)) \
            if len(names) > 1 else set()
        out[slug] = {'n_scheduled': s['n_scheduled'],
                     'on_target_h': round(s['on_target_min'] / 60.0, 2),
                     'idle_min': round(s['idle_min'], 1),
                     'unique': sorted(names[slug] - others)}
    return out


def write_index(base_dir, entries):
    """
    Write <base>/scenarios.json.

    Parameters
    ----------
    base_dir : str
    entries : list of dict with 'name', 'slug', 'dir', and the scenario's
        seeing/start/blocks.

    Returns
    -------
    str : the path.
    """
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, INDEX)
    with open(path, 'w') as f:
        json.dump({'scenarios': entries}, f, indent=2)
    return path


def load_index(base_dir):
    """
    Read <base>/scenarios.json.

    Returns
    -------
    list of dict, or None if there is no index.
    """
    path = os.path.join(base_dir, INDEX)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f).get('scenarios') or []


def find_base(output_dir):
    """
    The scenario base for a plan directory, if it belongs to one.

    Parameters
    ----------
    output_dir : str
        Either a base (holding scenarios.json) or one scenario's directory.

    Returns
    -------
    (base_dir, slug) : (str, str or None), or (None, None) when the
    directory isn't part of a scenario set.
    """
    output_dir = os.path.abspath(output_dir)
    if load_index(output_dir) is not None:
        return output_dir, None
    parent = os.path.dirname(output_dir)
    entries = load_index(parent)
    if entries:
        slug = os.path.basename(output_dir)
        if any(e['slug'] == slug for e in entries):
            return parent, slug
    return None, None
