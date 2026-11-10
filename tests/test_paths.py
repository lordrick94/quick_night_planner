"""Tests that nothing in this repo is pinned to one person's home directory.

Created by JXP and Claude.

The failure these guard against is silent: an absolute path under one
person's home directory keeps working perfectly for whoever wrote it and
breaks for everyone else, which is how make_lick_night_plan.py carried a
default pointing at the other author's laptop for months without anyone
noticing.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from night_planner.paths import (
    REPO_ROOT, ffffpz_root, lick_template, plan_dir, plans_dir,
)

# Directories whose contents are generated or vendored, not authored here.
SKIP_DIRS = {'__pycache__', '.git', '.pytest_cache', 'Night_plans',
             'pvt_Nighplans', 'node_modules'}

# The portability checker necessarily spells these patterns out, so it
# cannot be scanned by the rule it enforces.
SKIP_FILES = {'scripts/check_portability.py'}

# An absolute path under a user's home or observatory scratch space.
HARDCODED = re.compile(r'''['"(]\s*(/home/[a-z]+/|/Users/|/mnt/scratch/)''')


def _source_files():
    """Every authored source file in the repo.

    Inputs: none.
    Outputs: iterator of Path.
    """
    for path in REPO_ROOT.rglob('*'):
        if not path.is_file() or path.suffix not in {'.py', '.js', '.html'}:
            continue
        rel = path.relative_to(REPO_ROOT)
        if SKIP_DIRS & set(rel.parts):
            continue
        if rel.as_posix() in SKIP_FILES:
            continue
        yield path


def test_no_source_file_hardcodes_a_home_directory():
    """No code path is pinned to one machine's layout.

    Comments and docstrings may still mention such a path by way of
    explanation; only string literals that code actually uses are caught,
    which is why the pattern requires a quote or an open paren.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    offenders = []
    for path in _source_files():
        for n, line in enumerate(path.read_text().splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith('#') or stripped.startswith('*'):
                continue
            if HARDCODED.search(line):
                offenders.append(f'{path.relative_to(REPO_ROOT)}:{n}: {stripped}')
    assert not offenders, (
        'hardcoded machine-specific paths found; use night_planner.paths:\n'
        + '\n'.join(offenders))


def test_repo_root_is_this_checkout():
    """REPO_ROOT is derived from the file's location, not configured.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    assert (REPO_ROOT / 'night_planner' / 'paths.py').exists()
    assert (REPO_ROOT / 'setup.cfg').exists()


def test_plans_dir_defaults_inside_the_repo_and_can_be_overridden(monkeypatch):
    """Plans land in the git-ignored <repo>/pvt_Nighplans unless
    NIGHT_PLANNER_PLANS says otherwise.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    monkeypatch.delenv('NIGHT_PLANNER_PLANS', raising=False)
    assert plans_dir() == REPO_ROOT / 'pvt_Nighplans'
    assert plan_dir('Lick-2026B-02') == REPO_ROOT / 'pvt_Nighplans' / 'Lick-2026B-02'

    monkeypatch.setenv('NIGHT_PLANNER_PLANS', '/tmp/elsewhere')
    assert plans_dir() == Path('/tmp/elsewhere')
    assert plan_dir('Keck-2026B-02') == Path('/tmp/elsewhere/Keck-2026B-02')


def test_private_plan_directories_are_git_ignored():
    """Real targets live in plan directories; both must stay out of git.

    Created by JXP and Claude

    Inputs: none.
    Outputs: none (asserts on success). Uses ``git check-ignore``, which is
    read-only, and skips when git is unavailable (e.g. an sdist).
    """
    if shutil.which('git') is None or not (REPO_ROOT / '.git').exists():
        pytest.skip('not a git checkout')
    for name in ('pvt_Nighplans/x.csv', 'Night_plans/x.csv'):
        res = subprocess.run(['git', 'check-ignore', '-q', name], cwd=REPO_ROOT)
        assert res.returncode == 0, f'{name} is not git-ignored'


def test_missing_external_checkout_names_the_variable_to_set(monkeypatch):
    """A missing FFFF-PZ checkout fails with instructions, not a stray path.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    monkeypatch.setenv('FFFF_PZ_REPO', '/tmp/definitely-not-a-checkout')
    with pytest.raises(FileNotFoundError, match='FFFF_PZ_REPO'):
        ffffpz_root()
    assert ffffpz_root(required=False) is None


def test_lick_template_has_no_default(monkeypatch):
    """The template must be pointed at; guessing it would confuse the error.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    monkeypatch.delenv('LICK_NIGHT_PLAN_TEMPLATE', raising=False)
    assert lick_template(required=False) is None
    with pytest.raises(FileNotFoundError, match='LICK_NIGHT_PLAN_TEMPLATE'):
        lick_template()

    monkeypatch.setenv('LICK_NIGHT_PLAN_TEMPLATE', '/tmp/template.xlsx')
    assert lick_template() == Path('/tmp/template.xlsx')


def test_check_portability_script_reports_a_clean_repo():
    """scripts/check_portability.py agrees the repo is portable.

    It scans wider than the test above -- docs, config and shell commands
    people copy out of markdown, where a path under someone's home
    directory is just as fatal and nothing else was checking.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    sys.path.insert(0, str(REPO_ROOT / 'scripts'))
    import check_portability

    hits = check_portability.check(REPO_ROOT)
    assert not hits, '\n'.join(
        f"{h['relpath']}:{h['lineno']}: {h['text']}" for h in hits)
