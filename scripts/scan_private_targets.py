"""Find every real (private) target name that leaks into the git repo.

Created by JXP and Claude

The night plans hold unpublished FRB host positions. The repo is public, so
those plans now live in a git-ignored directory (``pvt_Nighplans/``, or
wherever NIGHT_PLANNER_PLANS points). This script

1. builds a catalogue of real target names from that private directory
   (every CSV name column, every starlist, plus FRB/TNS/J-name tokens found
   in any text file there); synthetic ``SIM*`` objects and the
   spectrophotometric standards are excluded;
2. scans every file tracked at HEAD -- text files directly, and the text
   inside .xlsx/.pptx/.docx (zip XML) and .pdf -- and lists which files
   mention those names;
3. scans the whole history (all branches, all commits) for file *paths* and
   file *contents* that mention them, so the rewrite plan can name every
   path that has to go.

Usage
-----
    python scripts/scan_private_targets.py \
        [--private-dir pvt_Nighplans] [--out Logs/private_target_scan.md]

Inputs
------
--private-dir : directory holding the real plans (default: NIGHT_PLANNER_PLANS
    or <repo>/pvt_Nighplans).
--out : Markdown report path. The report itself lists *file paths and hit
    counts only*, never the names, so it is safe to commit.
--names-out : optional path for the full name list (keep it git-ignored,
    e.g. inside the private directory).
--filter-out : optional directory (keep it git-ignored) to receive
    ``replace_text.txt`` for ``git filter-repo --replace-text`` and
    ``pseudonyms.csv`` (real name -> pseudonym, the only way back).

Outputs
-------
The Markdown report and, if asked, the name list and filter-repo inputs.
"""

import argparse
import io
import os
import re
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent

# Columns that hold an object name in the plan CSVs.
NAME_COLUMNS = ('TNS', 'name', 'Name', 'object', 'Object', 'target', 'Pri_name',
                'Sec_name', 'cand_gal_names', 'Host')

# Token patterns for real objects: FRB TNS names, TNS transient names
# (e.g. 20YYabc), IAU J-names (with or without the DLA_ prefix).
TOKEN_PATTERNS = [
    re.compile(r'\bFRB ?20\d{6}[A-Z]{1,2}\b'),
    re.compile(r'\b(?:SN|AT)? ?20[12]\d[a-z]{3,4}\b'),
    re.compile(r'\bJ\d{4,6}(?:\.\d+)?[+-]\d{4,6}(?:\.\d+)?\b'),
]

# Names that are public and fine to keep (standards, synthetic, placeholders).
# Compared case-insensitively: starlists spell standards bd284211, BD28d4211...
SAFE_PREFIXES = ('sim', 'sdss_j0000', 'feige', 'bd', 'hz', 'g191', 'hd',
                 'gd', 'ltt', 'wolf', 'eg', 'pg', 'bpm', 'cd', 'lds')

# Paths the scrub removes outright from every commit. Positions inside them
# need no blanking rules. Read from the same file git filter-repo uses
# (--paths-from-file), so the two cannot drift apart.
REMOVED_PATHS_FILE = REPO / 'claude_prompts' / 'target_scrub_paths.txt'
REMOVED_PREFIXES = tuple(
    line.strip() for line in
    (REMOVED_PATHS_FILE.read_text().splitlines()
     if REMOVED_PATHS_FILE.exists() else [])
    if line.strip() and not line.startswith('#'))

TEXT_SUFFIXES = {'.md', '.csv', '.txt', '.json', '.py', '.starlist', '.yaml',
                 '.yml', '.js', '.html', '.css', '.cfg', '.toml', '.c', '.ipynb',
                 '.sh', ''}
ZIP_SUFFIXES = {'.xlsx', '.pptx', '.docx'}


def is_safe(name):
    """
    Whether a candidate name is public/synthetic and may stay in the repo.

    Inputs
    ------
    name : str

    Outputs
    -------
    bool
    """
    return name.lower().startswith(SAFE_PREFIXES) or len(name) < 5


def normalise(name):
    """
    Strip starlist suffixes (_S, _C, _A ...) and spaces from a target name.

    Inputs
    ------
    name : str

    Outputs
    -------
    str
    """
    name = str(name).strip().replace(' ', '')
    return re.sub(r'_(?:S|C|A|B|P|Pri|Sec|sky|off)$', '', name)


def tokens_in_text(text):
    """
    Pull FRB / TNS / J-name tokens out of a block of text.

    Inputs
    ------
    text : str

    Outputs
    -------
    set of str
    """
    found = set()
    for pat in TOKEN_PATTERNS:
        for m in pat.findall(text):
            found.add(m.replace(' ', ''))
    return found


def read_any_text(path_or_bytes, suffix):
    """
    Return the searchable text of a file: raw text, zip XML, or PDF text.

    Inputs
    ------
    path_or_bytes : Path or bytes
    suffix : str, lower-case file extension

    Outputs
    -------
    str ('' if the file cannot be read as text)
    """
    data = (path_or_bytes if isinstance(path_or_bytes, bytes)
            else Path(path_or_bytes).read_bytes())
    if suffix in ZIP_SUFFIXES:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                return ' '.join(zf.read(n).decode('utf-8', 'ignore')
                                for n in zf.namelist() if n.endswith('.xml'))
        except zipfile.BadZipFile:
            return ''
    if suffix == '.pdf':
        # poppler's pdftotext reads from stdin ('-') and writes to stdout ('-').
        try:
            return subprocess.run(['pdftotext', '-', '-'], input=data,
                                  capture_output=True).stdout.decode('utf-8', 'ignore')
        except FileNotFoundError:  # poppler not installed
            return ''
    if suffix in TEXT_SUFFIXES:
        return data.decode('utf-8', 'ignore')
    return ''


RA_COLUMNS = ('Pri_RA', 'Sec_RA', 'RA_deg', 'ra', 'FRB_RA', 'cand_ra')
DEC_COLUMNS = ('Pri_Dec', 'Sec_Dec', 'Dec_deg', 'dec', 'FRB_Dec', 'cand_dec')


def trunc(value, ndp=3):
    """
    Truncate a float to ndp decimals and format it (truncation, not rounding,
    so that 40.40742 and 40.4070 both give '40.407').

    Inputs
    ------
    value : float
    ndp : int

    Outputs
    -------
    str
    """
    scale = 10 ** ndp
    v = int(abs(value) * scale) / scale
    return ('-' if value < 0 else '') + f'{v:.{ndp}f}'


def build_coords(private_dir):
    """
    Collect real target positions as (RA string, Dec string) pairs, in
    decimal degrees (3 dp) and sexagesimal "hh mm ss" / "hh:mm:ss" form.

    Inputs
    ------
    private_dir : Path

    Outputs
    -------
    set of (str, str)
    """
    pairs = set()
    for path in private_dir.rglob('*.csv'):
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        first = df.columns[0]
        df = df[~df[first].astype(str).str.startswith('SIM')]
        for rc, dc in zip(RA_COLUMNS, DEC_COLUMNS):
            if rc in df.columns and dc in df.columns:
                ra = pd.to_numeric(df[rc], errors='coerce')
                dec = pd.to_numeric(df[dc], errors='coerce')
                for r, d in zip(ra, dec):
                    # Skip round numbers: they are placeholders, not positions.
                    if pd.notna(r) and pd.notna(d) and r != round(r):
                        pairs.add((trunc(r), trunc(d)))
                        # Logs also quote RA in decimal hours.
                        pairs.add((trunc(r / 15., 4), trunc(d)))
    for path in private_dir.rglob('*.starlist'):
        for line in path.read_text(errors='ignore').splitlines():
            f = line.split()
            # Column widths vary between starlists, so split on whitespace.
            if not f or f[0].startswith('#') or is_safe(normalise(f[0])):
                continue
            f = f[1:]
            if len(f) >= 6:
                ra = f'{f[0]} {f[1]} {f[2].split(".")[0]}'
                dec = f'{f[3]} {f[4]} {f[5].split(".")[0]}'.lstrip('+')
                pairs.add((ra, dec))
                pairs.add((ra.replace(' ', ':'), dec.replace(' ', ':')))
    return pairs


def coord_hits(text, pairs):
    """
    Number of real positions whose RA and Dec strings both occur in text.

    Inputs
    ------
    text : str
    pairs : set of (str, str)

    Outputs
    -------
    int
    """
    if not text:
        return 0
    return sum(1 for r, d in pairs if r in text and d in text)


def build_positions(private_dir):
    """
    Real target positions as floats, for the coarse (rounded-number) audit.

    Inputs
    ------
    private_dir : Path

    Outputs
    -------
    numpy array, shape (N, 2): RA deg, Dec deg (synthetic rows dropped).
    """
    import numpy as np
    rows = []
    for path in private_dir.rglob('*.csv'):
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        first = df.columns[0]
        df = df[~df[first].astype(str).str.startswith('SIM')]
        for rc, dc in zip(RA_COLUMNS, DEC_COLUMNS):
            if rc in df.columns and dc in df.columns:
                ra = pd.to_numeric(df[rc], errors='coerce')
                dec = pd.to_numeric(df[dc], errors='coerce')
                ok = ra.notna() & dec.notna() & (ra != ra.round())
                rows += list(zip(ra[ok], dec[ok]))
    return np.unique(np.round(np.array(rows, dtype=float), 4), axis=0)


def coarse_audit(positions, tol=0.1):
    """
    Flag lines in surviving tracked text files whose numbers match a real
    position after rounding: some number within tol of a real RA (in degrees,
    or in hours to tol/15) and another within tol of that target's Dec.
    Catches positions truncated or rounded to 1-2 decimals, which the 3-dp string check misses. False
    positives are expected; review each hit by eye.

    Inputs
    ------
    positions : array (N, 2) of RA, Dec in degrees
    tol : float, degrees

    Outputs
    -------
    list of (path, line number) -- no values, so it is safe to print.
    """
    import numpy as np
    num = re.compile(r'(?<![\w.])[-+]?\d{1,3}\.\d+')
    ra, dec = positions[:, 0], positions[:, 1]
    hits = []
    for rel in git('ls-files').splitlines():
        path = REPO / rel
        if (rel.startswith(REMOVED_PREFIXES) or not path.is_file()
                or path.suffix.lower() not in TEXT_SUFFIXES):
            continue
        for i, line in enumerate(path.read_text(errors='ignore').splitlines(), 1):
            vals = np.array([float(v) for v in num.findall(line)])
            if vals.size < 2:
                continue
            dec_ok = (np.abs(vals[:, None] - dec[None, :]) < tol).any(axis=0)
            ra_ok = ((np.abs(vals[:, None] - ra[None, :]) < tol)
                     | (np.abs(vals[:, None] * 15 - ra[None, :]) < 2 * tol)).any(axis=0)  # 2-dp hours: <= 0.075 deg off
            if (ra_ok & dec_ok).any():
                hits.append((rel, i))
    return hits


def build_catalogue(private_dir):
    """
    Collect every real target name found in the private plans directory.

    Inputs
    ------
    private_dir : Path

    Outputs
    -------
    set of str, normalised names with safe/synthetic ones removed.
    """
    names = set()
    for path in private_dir.rglob('*'):
        # Skip non-files, this script's own name list, and synthetic finders.
        if (not path.is_file() or path.name.startswith(('SIM', '_real_target'))):
            continue
        suffix = path.suffix.lower()
        # File names of finder charts are target names too.
        names |= tokens_in_text(path.name)
        if suffix == '.csv':
            try:
                df = pd.read_csv(path, dtype=str)
            except Exception:
                df = None
            if df is not None:
                # Synthetic rows carry made-up J-names; drop them first.
                first = df.columns[0]
                df = df[~df[first].fillna('').str.startswith('SIM')]
                for col in NAME_COLUMNS:
                    if col in df.columns:
                        for val in df[col].dropna():
                            # Cells may hold python-list strings: "['J0..', 'J0..']".
                            for part in re.split(r'[;,|\s\[\]\'"]+', val):
                                if part:
                                    names.add(normalise(part))
        if suffix == '.starlist':
            for line in path.read_text(errors='ignore').splitlines():
                if line.strip() and not line.startswith('#'):
                    names.add(normalise(line.split()[0]))
        names |= {normalise(t) for t in tokens_in_text(read_any_text(path, suffix))}
    # Drop numbers, NaNs and public/synthetic names.
    return {n for n in names
            if not is_safe(n) and not re.fullmatch(r'[-+.\d]+|nan|None', n)}


def git(*args):
    """
    Run a read-only git command in the repo and return stdout.

    Inputs
    ------
    *args : str

    Outputs
    -------
    str
    """
    return subprocess.run(['git', *args], cwd=REPO, capture_output=True,
                          check=True).stdout.decode('utf-8', 'ignore')


def scan_head(names, pairs):
    """
    Count real-name and real-position hits in every file tracked at HEAD
    (working-tree copy).

    Inputs
    ------
    names : set of str
    pairs : set of (RA str, Dec str)

    Outputs
    -------
    dict path -> (distinct real names mentioned, real positions present)
    """
    pattern = re.compile('|'.join(re.escape(n) for n in
                                  sorted(names, key=len, reverse=True)))
    hits = {}
    for rel in git('ls-files').splitlines():
        path = REPO / rel
        if not path.is_file():
            continue
        text = read_any_text(path, path.suffix.lower())
        found = set(pattern.findall(rel)) | set(pattern.findall(text))
        ncoord = coord_hits(text, pairs)
        if found or ncoord:
            hits[rel] = (len(found), ncoord)
    return hits


def scan_history(names, pairs):
    """
    Find every path, in any commit on any branch, whose name or content
    mentions a real target.

    Inputs
    ------
    names : set of str
    pairs : set of (RA str, Dec str)

    Outputs
    -------
    dict path -> set of short commit hashes in which it leaked
    """
    pattern = re.compile('|'.join(re.escape(n) for n in
                                  sorted(names, key=len, reverse=True)))
    leaks = defaultdict(set)
    seen_blobs = {}
    for commit in git('rev-list', '--all').split():
        for line in git('ls-tree', '-r', commit).splitlines():
            meta, rel = line.split('\t', 1)
            blob = meta.split()[2]
            if blob not in seen_blobs:
                text = read_any_text(git_blob(blob), Path(rel).suffix.lower())
                seen_blobs[blob] = bool(pattern.search(text)) or coord_hits(text, pairs) > 0
            if seen_blobs[blob] or pattern.search(rel):
                leaks[rel].add(commit[:7])
    return leaks


def git_blob(blob):
    """
    Raw bytes of one git blob.

    Inputs
    ------
    blob : str, object id

    Outputs
    -------
    bytes
    """
    return subprocess.run(['git', 'cat-file', 'blob', blob], cwd=REPO,
                          capture_output=True, check=True).stdout


def surviving_texts(extra_paths):
    """
    Text of every version, in every commit, of every path the scrub keeps,
    plus the working-tree copy of extra (e.g. new, uncommitted) paths.

    Inputs
    ------
    extra_paths : iterable of str, repo-relative paths

    Outputs
    -------
    list of str
    """
    texts, seen = [], set()
    for commit in git('rev-list', '--all').split():
        for line in git('ls-tree', '-r', commit).splitlines():
            meta, rel = line.split('\t', 1)
            blob = meta.split()[2]
            if blob in seen or rel.startswith(REMOVED_PREFIXES):
                continue
            seen.add(blob)
            texts.append(read_any_text(git_blob(blob), Path(rel).suffix.lower()))
    for rel in extra_paths:
        f = REPO / rel
        if f.is_file() and not rel.startswith(REMOVED_PREFIXES):
            texts.append(read_any_text(f, f.suffix.lower()))
    return texts


def write_filter_inputs(names, pairs, leaked_paths, out_dir):
    """
    Write the git-filter-repo --replace-text file and the pseudonym key.

    Real names become stable pseudonyms (TGT0001, ...) so the narrative logs
    stay readable; every real position seen in a surviving file becomes a
    regex that blanks it. Longest names go first so no name is rewritten
    inside a longer one.

    Inputs
    ------
    names : set of str
    pairs : set of (RA str, Dec str)
    leaked_paths : iterable of str, paths (any commit) that mention a target
    out_dir : Path

    Outputs
    -------
    (Path to replace_text.txt, number of names, number of coordinate rules)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    # D1 (2026-11-09): scrub every real name, including the two that the
    # synthetic fixtures happen to reuse; one of them is a real target in the
    # kept docs. Fixtures are renamed consistently, so tests are unaffected.
    keep = set()
    ordered = sorted(names - keep)
    key = {n: f'TGT{i + 1:04d}' for i, n in enumerate(ordered)}
    lines = ['# git filter-repo --replace-text input. PRIVATE: never commit.']
    # Hand-made rules (e.g. old test fixtures that held real positions) go
    # first, so the generated ones never pre-empt them.
    extra = out_dir / 'extra_rules.txt'
    if extra.exists():
        lines += [ln for ln in extra.read_text().splitlines() if ln.strip()]
    for n in sorted(ordered, key=len, reverse=True):
        lines.append(f'{n}==>{key[n]}')

    # Coordinates: only those that actually occur in some surviving blob,
    # to keep the rule list short. Separators may be space or colon.
    texts = surviving_texts(leaked_paths)
    blob = '\n'.join(texts)
    ncoord = 0
    for ra, dec in sorted(pairs):
        if ra in blob and dec in blob:
            for val, ph in ((ra, 'RA_REDACTED'), (dec, 'DEC_REDACTED')):
                if re.fullmatch(r'-?\d+\.\d+', val):  # decimal degrees
                    rx = r'(?<![\d.])' + re.escape(val) + r'\d*'
                else:  # sexagesimal, space or colon separated
                    rx = (r'(?<!\d)[+-]?'
                          + '[ :]'.join(re.escape(x) for x in re.split('[ :]', val))
                          + r'(?:\.\d+)?')
                lines.append(f'regex:{rx}==>{ph}')
            ncoord += 1
    path = out_dir / 'replace_text.txt'
    path.write_text('\n'.join(lines) + '\n')
    pd.DataFrame({'real_name': list(key), 'pseudonym': list(key.values())}
                 ).to_csv(out_dir / 'pseudonyms.csv', index=False)
    return path, len(key), ncoord


def apply_rules(rules_path, target):
    """
    Apply a filter-repo --replace-text file to one file in place, with the
    same semantics (literal or ``regex:`` lines, applied in order).

    Inputs
    ------
    rules_path : Path, replace_text.txt
    target : Path, text file to rewrite

    Outputs
    -------
    int, number of replacements made
    """
    text = target.read_text()
    total = 0
    for line in rules_path.read_text().splitlines():
        if line.startswith('#') or '==>' not in line:
            continue
        pat, rep = line.rsplit('==>', 1)
        if pat.startswith('regex:'):
            text, n = re.subn(pat[len('regex:'):], rep, text)
        else:
            n = text.count(pat)
            text = text.replace(pat, rep)
        total += n
    target.write_text(text)
    return total


def verify_rules(rules_path, names, pairs, positions, tol=0.1):
    """
    Dry-run the scrub: apply the replace-text rules to every version of every
    surviving path in history, and to new uncommitted files, then look for
    real names, exact positions and rounded positions that would survive.

    Synthetic tables (test_targs/, tests/test_data/) are skipped by the
    rounded-position check: their random positions hit by chance.

    Inputs
    ------
    rules_path : Path, replace_text.txt
    names : set of str
    pairs : set of (RA str, Dec str)
    positions : array (N, 2) RA, Dec in degrees
    tol : float, degrees, for the rounded-position check

    Outputs
    -------
    (sorted list of paths with exact leaks, sorted list of 'path:line'
    rounded-position hits). Values are never returned.
    """
    import numpy as np
    rules = []
    for line in rules_path.read_text().splitlines():
        if line.startswith('#') or '==>' not in line:
            continue
        pat, rep = line.rsplit('==>', 1)
        rx = re.compile(pat[len('regex:'):]) if pat.startswith('regex:') else None
        rules.append((rx, pat, rep))
    namepat = re.compile('|'.join(re.escape(n) for n in
                                  sorted(names, key=len, reverse=True)))
    num = re.compile(r'(?<![\w.])[-+]?\d{1,3}\.\d+')
    ra, dec = positions[:, 0], positions[:, 1]

    def versions():
        seen = set()
        for commit in git('rev-list', '--all').split():
            for line in git('ls-tree', '-r', commit).splitlines():
                meta, rel = line.split('\t', 1)
                blob = meta.split()[2]
                if blob not in seen and not rel.startswith(REMOVED_PREFIXES):
                    seen.add(blob)
                    yield rel, git_blob(blob)
        for rel in git('ls-files', '--others', '--exclude-standard').splitlines():
            f = REPO / rel
            if f.is_file() and not rel.startswith(REMOVED_PREFIXES):
                yield rel, f.read_bytes()

    exact, coarse = set(), set()
    for rel, data in versions():
        suffix = Path(rel).suffix.lower()
        text = read_any_text(data, suffix)
        for rx, pat, rep in rules:
            # filter-repo rewrites contents only, never path names.
            text = rx.sub(rep, text) if rx else text.replace(pat, rep)
        if namepat.search(rel) or namepat.search(text) or coord_hits(text, pairs):
            exact.add(rel)
        if rel.startswith(('test_targs/', 'tests/test_data/')):
            continue
        for i, ln in enumerate(text.splitlines(), 1):
            v = np.array([float(x) for x in num.findall(ln)])
            if v.size < 2:
                continue
            d_ok = (np.abs(v[:, None] - dec[None, :]) < tol).any(axis=0)
            r_ok = ((np.abs(v[:, None] - ra[None, :]) < tol)
                    | (np.abs(v[:, None] * 15 - ra[None, :]) < 2 * tol)).any(axis=0)  # 2-dp hours: <= 0.075 deg off
            if (r_ok & d_ok).any():
                coarse.add(f'{rel}:{i}')
    return sorted(exact), sorted(coarse)


def group(path):
    """
    Collapse a path to the directory used in the report (Night_plans/<run>).

    Inputs
    ------
    path : str

    Outputs
    -------
    str
    """
    parts = path.split('/')
    if parts[0] in ('Night_plans', 'Keck-2026B-02_test1000') and len(parts) > 2:
        return '/'.join(parts[:2]) + '/'
    return path


def main():
    """
    Parse arguments, scan, and write the report.

    Inputs
    ------
    command-line arguments (see module docstring).

    Outputs
    -------
    none; writes files.
    """
    default_private = os.getenv('NIGHT_PLANNER_PLANS') or str(REPO / 'pvt_Nighplans')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--private-dir', default=default_private)
    parser.add_argument('--out', default=str(REPO / 'Logs' / 'private_target_scan.md'))
    parser.add_argument('--names-out', default=None)
    parser.add_argument('--filter-out', default=None)
    parser.add_argument('--apply-to', nargs='*', default=[],
                        help='apply the generated rules in place to these '
                             'files (needs --filter-out)')
    parser.add_argument('--verify', action='store_true',
                        help='dry-run the rules in --filter-out over all history')
    parser.add_argument('--coarse', action='store_true',
                        help='also list file:line of rounded real positions')
    args = parser.parse_args()

    private = Path(args.private_dir).expanduser()
    names = build_catalogue(private)
    pairs = build_coords(private)
    head = scan_head(names, pairs)
    hist = scan_history(names, pairs)

    head_groups = defaultdict(lambda: (0, 0))
    for p, (n, c) in head.items():
        old = head_groups[group(p)]
        head_groups[group(p)] = (max(old[0], n), max(old[1], c))
    hist_groups = defaultdict(set)
    for p, commits in hist.items():
        hist_groups[group(p)] |= commits
    gone = sorted(g for g in hist_groups if g not in head_groups)

    lines = ['# Private-target scan', '',
             'Created by JXP and Claude -- generated by '
             '`scripts/scan_private_targets.py`. Lists paths only, never names.',
             '', f'- Real target names catalogued: **{len(names)}**',
             f'- Real positions catalogued (RA/Dec string pairs): **{len(pairs)}**',
             f'- Files at HEAD mentioning them: **{len(head)}** '
             f'({len(head_groups)} groups)',
             f'- Paths in history (all branches) mentioning them: **{len(hist)}**',
             '', '## At HEAD (tracked now)', '',
             '| path / group | max real names in one file | max real positions in one file |',
             '|---|---|---|']
    lines += [f'| `{g}` | {n} | {c} |' for g, (n, c) in sorted(head_groups.items())]
    lines += ['', '## Only in history (already deleted at HEAD, still in old commits)',
              '', '| path / group | commits |', '|---|---|']
    lines += [f'| `{g}` | {len(hist_groups[g])} |' for g in gone]
    Path(args.out).write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))

    if args.names_out:
        Path(args.names_out).write_text('\n'.join(sorted(names)) + '\n')
        print(f'\nwrote {len(names)} names to {args.names_out}')

    if args.coarse:
        hits = coarse_audit(build_positions(private))
        print(f'\ncoarse audit: {len(hits)} line(s) to review by eye')
        for rel, i in hits:
            print(f'  {rel}:{i}')

    if args.filter_out:
        # New, not-yet-committed files (e.g. docs rescued from Night_plans/)
        # count as surviving files too.
        untracked = git('ls-files', '--others', '--exclude-standard').splitlines()
        path, nn, nc = write_filter_inputs(names, pairs, list(hist) + untracked,
                                           Path(args.filter_out).expanduser())
        print(f'wrote {path}: {nn} name rules, {nc} positions blanked')
        if args.verify:
            exact, coarse = verify_rules(path, names, pairs,
                                         build_positions(private))
            print(f'verify: {len(exact)} path(s) would still leak exactly'
                  + (': ' + ', '.join(exact) if exact else ''))
            print(f'verify: {len(coarse)} rounded-position line(s) to review'
                  + (': ' + ', '.join(coarse) if coarse else ''))
        for target in args.apply_to:
            n = apply_rules(path, Path(target))
            print(f'applied rules to {target}: {n} replacement(s)')


if __name__ == '__main__':
    main()
