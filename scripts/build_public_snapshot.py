"""Build a clean, history-free copy of this repo with no real targets in it.

Created by JXP and Claude

Used for the "fresh repo" route of claude_prompts/target_scrub.md (prompt 4,
step F1). It never touches git state: it only reads ``git ls-files`` and
writes a plain directory.

1. Copy every tracked file (working-tree version) except the paths listed in
   claude_prompts/target_scrub_paths.txt.
2. Apply the private name/position rules (``replace_text.txt`` from
   scan_private_targets.py --filter-out) to every UTF-8 text file.
3. Audit the copy: real names in paths or contents (text, office XML, PDF
   text), exact real positions, and rounded real positions (within 0.1 deg; 0.2 deg for RA in hours).

Usage
-----
    python scripts/build_public_snapshot.py --dest ../quick_night_planner

Inputs
------
--dest : empty (or missing) output directory.
--rules : replace_text.txt (default pvt_Nighplans/_scrub/replace_text.txt).
--private-dir : the private plans (default NIGHT_PLANNER_PLANS or
    <repo>/pvt_Nighplans), used to build the name and position catalogue.

Outputs
-------
The scrubbed directory, and a summary printed to stdout (paths and counts
only, never names or positions).
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_private_targets as spt  # noqa: E402

REPO = spt.REPO
SYNTHETIC_PREFIXES = ('test_targs/', 'tests/test_data/')


def kept_files():
    """
    Tracked files that survive the scrub.

    Inputs
    ------
    none (reads ``git ls-files`` in REPO).

    Outputs
    -------
    list of str, repo-relative paths that exist in the working tree.
    """
    return [rel for rel in spt.git('ls-files').splitlines()
            if not rel.startswith(spt.REMOVED_PREFIXES)
            and (REPO / rel).is_file()]


def load_rules(rules_path):
    """
    Parse a filter-repo --replace-text file.

    Inputs
    ------
    rules_path : Path

    Outputs
    -------
    list of (compiled regex or None, literal pattern, replacement)
    """
    rules = []
    for line in Path(rules_path).read_text().splitlines():
        if line.startswith('#') or '==>' not in line:
            continue
        pat, rep = line.rsplit('==>', 1)
        rx = re.compile(pat[len('regex:'):]) if pat.startswith('regex:') else None
        rules.append((rx, pat, rep))
    return rules


def scrub_text(text, rules):
    """
    Apply the rules in order, as filter-repo does.

    Inputs
    ------
    text : str
    rules : output of load_rules

    Outputs
    -------
    (new text, number of replacements)
    """
    total = 0
    for rx, pat, rep in rules:
        if rx:
            text, n = rx.subn(rep, text)
        else:
            n = text.count(pat)
            text = text.replace(pat, rep)
        total += n
    return text, total


def copy_and_scrub(files, dest, rules):
    """
    Copy files into dest, scrubbing every UTF-8 text file on the way.

    Inputs
    ------
    files : list of repo-relative paths
    dest : Path, output directory
    rules : output of load_rules

    Outputs
    -------
    dict with counts: copied, scrubbed (files changed), replacements,
    binary (files copied unchanged).
    """
    stats = dict(copied=0, scrubbed=0, replacements=0, binary=0)
    for rel in files:
        src, out = REPO / rel, dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            text = None
        if text is None or Path(rel).suffix.lower() in spt.ZIP_SUFFIXES | {'.pdf'}:
            shutil.copy2(src, out)
            stats['binary'] += 1
        else:
            new, n = scrub_text(text, rules)
            out.write_bytes(new.encode('utf-8'))
            shutil.copymode(src, out)
            if n:
                stats['scrubbed'] += 1
                stats['replacements'] += n
        stats['copied'] += 1
    return stats


def audit(dest, names, pairs, positions, tol=0.1):
    """
    Look for real targets anywhere in a directory.

    Inputs
    ------
    dest : Path
    names : set of str, real target names
    pairs : set of (RA str, Dec str), exact real positions
    positions : array (N, 2), real RA, Dec in degrees
    tol : float, degrees, for the rounded-position check

    Outputs
    -------
    (list of paths with names or exact positions,
     list of 'path:line' rounded-position hits to review by eye)
    """
    namepat = re.compile('|'.join(re.escape(n) for n in
                                  sorted(names, key=len, reverse=True)))
    num = re.compile(r'(?<![\w.])[-+]?\d{1,3}\.\d+')
    ra, dec = positions[:, 0], positions[:, 1]
    exact, coarse = [], []
    for path in sorted(p for p in dest.rglob('*') if p.is_file()
                       and not {'__pycache__', '.git'} & set(p.parts)):
        rel = path.relative_to(dest).as_posix()
        suffix = path.suffix.lower()
        text = spt.read_any_text(path, suffix)
        if (suffix not in spt.TEXT_SUFFIXES | spt.ZIP_SUFFIXES | {'.pdf'}):
            text = path.read_bytes().decode('utf-8', 'ignore')
        if namepat.search(rel) or namepat.search(text) or spt.coord_hits(text, pairs):
            exact.append(rel)
        if rel.startswith(SYNTHETIC_PREFIXES):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            v = np.array([float(x) for x in num.findall(line)])
            if v.size < 2:
                continue
            d_ok = (np.abs(v[:, None] - dec[None, :]) < tol).any(axis=0)
            r_ok = ((np.abs(v[:, None] - ra[None, :]) < tol)
                    | (np.abs(v[:, None] * 15 - ra[None, :]) < 2 * tol)).any(axis=0)  # 2-dp hours: <= 0.075 deg off
            if (r_ok & d_ok).any():
                coarse.append(f'{rel}:{i}')
    return exact, coarse


def main():
    """
    Parse arguments, build the snapshot, audit it.

    Inputs
    ------
    command-line arguments (see module docstring).

    Outputs
    -------
    none; writes the directory and prints a summary. Exit code 1 if any
    exact leak remains.
    """
    default_private = os.getenv('NIGHT_PLANNER_PLANS') or str(REPO / 'pvt_Nighplans')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dest', required=True)
    parser.add_argument('--rules',
                        default=str(REPO / 'pvt_Nighplans' / '_scrub' / 'replace_text.txt'))
    parser.add_argument('--private-dir', default=default_private)
    parser.add_argument('--audit-only', action='store_true',
                        help='only audit an existing --dest')
    parser.add_argument('--update', action='store_true',
                        help='overwrite an existing --dest with fresh scrubbed '
                             'copies (lists, never deletes, files no longer kept)')
    args = parser.parse_args()

    dest = Path(args.dest).expanduser().resolve()
    if dest == REPO or REPO in dest.parents:
        sys.exit('--dest must be outside the repo')
    private = Path(args.private_dir).expanduser()

    if not args.audit_only:
        if dest.exists() and any(dest.iterdir()) and not args.update:
            sys.exit(f'{dest} is not empty; refusing to overwrite (use --update)')
        dest.mkdir(parents=True, exist_ok=True)
        files = kept_files()
        stats = copy_and_scrub(files, dest, load_rules(args.rules))
        print(f'copied {stats["copied"]} files to {dest} '
              f'({stats["binary"]} binary/office copied unchanged); '
              f'{stats["replacements"]} replacements in {stats["scrubbed"]} files')
        stale = sorted(p.relative_to(dest).as_posix() for p in dest.rglob('*')
                       if p.is_file() and '.git' not in p.relative_to(dest).parts
                       and '__pycache__' not in p.parts
                       and p.relative_to(dest).as_posix() not in set(files))
        if stale:
            print(f'{len(stale)} file(s) in dest are not in the kept list '
                  f'(left alone): ' + ', '.join(stale))

    exact, coarse = audit(dest, spt.build_catalogue(private),
                          spt.build_coords(private), spt.build_positions(private))
    print(f'audit: {len(exact)} file(s) with real names or exact positions'
          + (': ' + ', '.join(exact) if exact else ''))
    print(f'audit: {len(coarse)} rounded-position line(s) to review'
          + (': ' + ', '.join(coarse) if coarse else ''))
    sys.exit(1 if exact else 0)


if __name__ == '__main__':
    main()
