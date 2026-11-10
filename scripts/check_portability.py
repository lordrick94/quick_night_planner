# Created by JXP and Claude
"""Created by JXP and Claude

Scan the repository for machine-specific values that would break the code
on someone else's computer.

The failure this guards against is silent: an absolute path baked into a
default argument or a docstring keeps working forever on the laptop it
was written on, and only fails for the next person who clones the repo.
``night_planner/paths.py`` is the cure (repo-relative paths derived from
__file__, machine-specific ones read from the environment); this script
is the check that it stays applied.

What counts as a finding
------------------------
- a home directory of any user (``/home/<user>``, ``/Users/<user>``)
- an interpreter inside a named conda/micromamba environment
- observatory scratch space (``/mnt/scratch/...``)

What is deliberately ignored
----------------------------
- ``night_planner/paths.py`` itself, which names these paths to explain
  why they are gone
- ``Logs/``, ``Night_plans/``, ``pvt_Nighplans/``, ``claude_prompts/`` and
  ``context/``:
  logs, generated run products and Claude's running notes are records of
  what happened on one machine on one night, not code anyone re-runs
- this file

Inputs
------
argv : list of str, optional
    ``--root PATH`` to scan somewhere other than the repo root.

Outputs
-------
Prints one line per finding (``path:line: text``) and returns 1 when
anything was found, 0 when clean, so it can run in CI or a pre-commit
hook.
"""

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Extensions worth scanning: code, config and the docs people copy
# commands out of.
SCANNED_SUFFIXES = {'.py', '.md', '.toml', '.cfg', '.txt', '.yaml', '.yml',
                    '.json', '.js', '.html', '.css', '.sh'}

# Directories whose contents are run records, not code.
SKIPPED_DIRS = {'.git', 'Logs', 'Night_plans', 'pvt_Nighplans', 'pvt_templates', 'claude_prompts', 'context',
                '__pycache__', '.pytest_cache', 'test_targs', 'build',
                'dist', '.venv'}

SKIPPED_FILES = {'night_planner/paths.py', 'scripts/check_portability.py'}

PATTERNS = [
    (re.compile(r'/home/[A-Za-z0-9_.-]+'), 'home directory of a named user'),
    (re.compile(r'/Users/[A-Za-z0-9_.-]+'), 'home directory of a named user'),
    (re.compile(r'(?:miniconda3|anaconda3|micromamba)[^\s"\']*/envs/[^\s"\']+'),
     'interpreter inside a named conda environment'),
    (re.compile(r'/mnt/scratch/[A-Za-z0-9_./-]+'), 'observatory scratch path'),
]


def scanned_files(root):
    """
    Every file in the repo worth scanning.

    Created by JXP and Claude

    Inputs
    ------
    root : Path
        Directory to walk.

    Outputs
    -------
    Sorted list of Paths, skipping SKIPPED_DIRS, SKIPPED_FILES and any
    suffix outside SCANNED_SUFFIXES.
    """
    found = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        rel = path.relative_to(root)
        if set(rel.parts) & SKIPPED_DIRS:
            continue
        if rel.as_posix() in SKIPPED_FILES:
            continue
        found.append(path)
    return found


def scan_file(path, root):
    """
    Machine-specific values in one file.

    Created by JXP and Claude

    Inputs
    ------
    path : Path
        File to read (undecodable bytes are ignored, so a stray binary
        does not stop the scan).
    root : Path
        Repo root, used to report a relative path.

    Outputs
    -------
    List of dicts: relpath, lineno, kind, text (the line, stripped).
    """
    hits = []
    text = path.read_text(errors='ignore')
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern, kind in PATTERNS:
            if pattern.search(line):
                hits.append({'relpath': path.relative_to(root).as_posix(),
                             'lineno': lineno, 'kind': kind,
                             'text': line.strip()})
                break
    return hits


def check(root=REPO_ROOT):
    """
    Scan the whole repo.

    Created by JXP and Claude

    Inputs
    ------
    root : Path
        Repo root to scan.

    Outputs
    -------
    List of finding dicts, as scan_file() returns them.
    """
    hits = []
    for path in scanned_files(Path(root)):
        hits.extend(scan_file(path, Path(root)))
    return hits


def main(argv=None):
    """
    Command-line driver.

    Created by JXP and Claude

    Inputs
    ------
    argv : list of str, optional

    Outputs
    -------
    int exit status: 1 if anything machine-specific was found, else 0.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(REPO_ROOT),
                        help='directory to scan [the repo root]')
    args = parser.parse_args(argv)

    hits = check(args.root)
    for hit in hits:
        print(f"{hit['relpath']}:{hit['lineno']}: {hit['kind']}\n"
              f"    {hit['text']}")
    if hits:
        print(f'\n{len(hits)} machine-specific value(s) found. Derive repo '
              f'paths from __file__ and read the rest from the environment '
              f'(see night_planner/paths.py).')
        return 1
    print('No machine-specific paths found.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
