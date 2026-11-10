"""
Read a table of targets -- from FFFF-PZ or from anywhere else -- into one
canonical schema.

The night plan should not care where its targets came from. Everything
downstream reads the canonical columns below; this module is the single
place that knows FFFF-PZ calls a host position `Pri_RA` and someone
else's spreadsheet calls it `RA`.

Canonical columns
-----------------
Required: name, ra_deg, dec_deg, mag
Optional: pox, tags, dm   (created empty when the source lacks them)

Source columns that don't map are passed through untouched, so nothing
is lost.

Column detection is automatic for the common spellings and only asks for
help when it would otherwise have to guess -- see detect_mapping().

Created by JXP and Claude
"""

import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from astropy.coordinates import Angle
from astropy import units as u

REQUIRED_FIELDS = ('name', 'ra', 'dec', 'mag')
OPTIONAL_FIELDS = ('pox', 'tags', 'dm', 'priority', 'mag_band', 't_target',
                   'required', 'target_sn')

# Priority convention, shared with the UCSC AstroScheduler so the two stay
# comparable: a float, lower = more important. Every target defaults to the
# same value, which puts them all in one tier -- and one tier schedules
# exactly as the pipeline did before priority existed.
DEFAULT_PRIORITY = 1.0

# Candidate source-column spellings per field, highest priority first.
#
# FRB_RA/FRB_Dec are deliberately absent: in an FFFF-PZ table those are the
# *burst* position, while Pri_RA/Pri_Dec are the host galaxy -- the thing
# the telescope actually points at. Auto-matching the burst position would
# silently observe the wrong place, so a table that only carries FRB_RA has
# to be mapped by hand.
ALIASES = {
    'name': ['tns', 'name', 'target', 'target_name', 'objname', 'object', 'id'],
    'ra': ['pri_ra', 'ra_deg', 'radeg', 'ra_hours', 'ra', 'rightascension',
           'right_ascension', 'ra_j2000'],
    'dec': ['pri_dec', 'dec_deg', 'decdeg', 'dec', 'de', 'declination',
            'dec_j2000'],
    'mag': ['pri_mag', 'mag_r', 'rmag', 'r_mag', 'mag', 'magnitude'],
    'pox': ['pri_pox', 'pox', 'p_ox'],
    'tags': ['frb_tags', 'tags', 'tag'],
    'dm': ['frb_dm', 'dm'],
    'priority': ['priority', 'prio', 'rank'],
    # Band of the mag column for this row (T3.5, 2026-11-07); beats the
    # plan-wide --mag-band. 'filter' is deliberately not an alias: too many
    # tables use it for something else.
    # FFFF-PZ's Pri_filter is the band of Pri_mag, written as
    # 'Survey:Instrument-band' (e.g. 'Blanco:DECam-r'); normalize_band()
    # keeps just the band.
    'mag_band': ['mag_band', 'band', 'mag_filter', 'pri_filter'],
    # Milestone 6 (T3.3): minutes on target set by the user (the ETC is then
    # only shown alongside), and whether a target must get its full time or
    # nothing (never truncated into a partial).
    't_target': ['t_target', 't_obs', 'exptime_min'],
    'required': ['required'],
    # Target S/N per sub-exposure for this row (2026-11-10); beats the
    # plan-wide --target-sn. Bare 'snr'/'sn' are deliberately not aliases:
    # tables use them for a *measured* S/N.
    'target_sn': ['target_sn', 'sn_target', 'snr_target', 'target_snr'],
}

_TRUE = {'true', 'yes', 'y', '1', 't'}
_FALSE = {'false', 'no', 'n', '0', 'f', ''}


def parse_required(value):
    """
    A `required` cell as a bool.

    Parameters
    ----------
    value : any
        true/false, yes/no, y/n, 1/0 (any case), a bool, or empty/NaN.

    Returns
    -------
    bool or None : None for a value that isn't recognisably either (the
    caller treats it as False and reports it).
    """
    if isinstance(value, bool):
        return value
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return False
    text = str(value).strip().lower()
    if text.endswith('.0'):
        text = text[:-2]
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def parse_t_target(value):
    """
    A `t_target` cell as minutes.

    Parameters
    ----------
    value : any

    Returns
    -------
    float, NaN for an empty cell, or None for a value that isn't a positive
    number (the caller treats it as unset and reports it).
    """
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return np.nan
    if isinstance(value, str) and not value.strip():
        return np.nan
    try:
        minutes = float(value)
    except (TypeError, ValueError):
        return None
    return minutes if minutes > 0 else None


def normalize_band(value):
    """
    The photometric band in a table cell.

    Parameters
    ----------
    value : any
        e.g. 'r', ' g ', 'Blanco:DECam-r', 'Pan-STARRS1:GPC1-r', NaN.

    Returns
    -------
    str : the band after the last '-' or ':' (case kept, since R/I are
    Cousins and r/i are SDSS), or '' for an empty cell.
    """
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ''
    text = str(value).strip()
    for sep in ('-', ':'):
        if sep in text:
            text = text.rsplit(sep, 1)[1].strip()
    return text

# Source columns whose name already settles the unit question. Anything
# outside these two sets is "bare" (e.g. plain 'ra') and gets the
# all-values-<=24 ambiguity check below.
_HOUR_NAMES = ('ra_hours', 'rahours', 'ra_h', 'rah')
_DEG_NAMES = ('ra_deg', 'radeg', 'pri_ra')  # pri_ra: FFFF-PZ, always degrees


class TargetTableError(ValueError):
    """Raised when a table can't be read without guessing.

    Carries the partial `mapping` so a caller (the GUI) can show the user
    what was detected and ask only about what's genuinely unclear.
    """

    def __init__(self, message, mapping):
        super().__init__(message)
        self.mapping = mapping


@dataclass
class ColumnMapping:
    """Which source column feeds each canonical field."""
    columns: dict = field(default_factory=dict)    # field -> source column
    ra_unit: str = 'deg'                            # 'deg' or 'hour'
    issues: list = field(default_factory=list)      # why it isn't usable as-is
    candidates: dict = field(default_factory=dict)  # field -> plausible columns

    @property
    def ok(self):
        return not self.issues

    def to_dict(self):
        return {'columns': dict(self.columns), 'ra_unit': self.ra_unit,
                'issues': list(self.issues),
                'candidates': {k: list(v) for k, v in self.candidates.items()},
                'ok': self.ok}


def _norm(header):
    """Normalize a header for matching: lowercase, strip punctuation/space."""
    return ''.join(ch for ch in str(header).lower() if ch.isalnum() or ch == '_')


def _looks_sexagesimal(series):
    """True if the values look like '01:56:29' / '+13 51 58' rather than numbers."""
    sample = series.dropna().astype(str).head(20)
    if sample.empty:
        return False
    return bool((sample.str.contains(':') | sample.str.contains(r'\s')).mean() > 0.5)


def detect_mapping(df):
    """
    Work out which columns hold name/RA/Dec/mag (and the optional extras).

    Only flags an issue when it would otherwise have to guess: a missing
    required field, two equally-good candidates, or a bare numeric RA
    column whose values are all <= 24 (hours or degrees? getting that
    wrong silently points the telescope somewhere else entirely).

    Parameters
    ----------
    df : DataFrame

    Returns
    -------
    ColumnMapping
    """
    normalized = {_norm(c): c for c in df.columns}
    mapping = ColumnMapping()

    for fieldname in REQUIRED_FIELDS + OPTIONAL_FIELDS:
        hits = [normalized[a] for a in ALIASES[fieldname] if a in normalized]
        mapping.candidates[fieldname] = hits
        if hits:
            mapping.columns[fieldname] = hits[0]
        elif fieldname in REQUIRED_FIELDS:
            mapping.issues.append(
                f"no column found for '{fieldname}' "
                f"(looked for: {', '.join(ALIASES[fieldname])})")

    ra_col = mapping.columns.get('ra')
    if ra_col is not None:
        if _norm(ra_col) in _HOUR_NAMES:
            mapping.ra_unit = 'hour'
        elif _looks_sexagesimal(df[ra_col]):
            # Sexagesimal RA is conventionally hours; Dec is always degrees.
            mapping.ra_unit = 'hour'
        elif _norm(ra_col) in _DEG_NAMES:
            mapping.ra_unit = 'deg'
        else:
            values = pd.to_numeric(df[ra_col], errors='coerce').dropna()
            if len(values) and values.abs().max() <= 24:
                mapping.issues.append(
                    f"'{ra_col}' is numeric and every value is <= 24, so it "
                    f"could be hours or degrees -- say which (ra_unit)")
    return mapping


# An FFFF-PZ pull is recognisable by what only it carries: the *burst*
# position and DM alongside PATH's ranked host candidates with their
# probabilities. No hand-made observing list has that combination, and
# no other source produces Pri_POx/Sec_POx at all.
FFFFPZ_SIGNATURE = {
    'burst': ('frb_ra', 'frb_dec', 'frb_dm'),
    'primary': ('pri_ra', 'pri_dec', 'pri_pox'),
    'secondary': ('sec_ra', 'sec_dec', 'sec_pox'),
}


def detect_format(df):
    """
    Decide whether a table is an FFFF-PZ pull or a generic target list.

    This matters because PATH ranks the host candidates of a *burst*. A
    second candidate is meaningful for a localised FRB and meaningless
    for a supernova or a DLA sightline, so "may I fit the slit through
    two candidates?" is a question about where the table came from, not
    about any individual row. Deciding it once, at inspection, beats
    guessing per row from object names.

    Parameters
    ----------
    df : DataFrame

    Returns
    -------
    dict with
        format   : 'ffff-pz' or 'generic'
        groups   : which signature groups were found
        missing  : which were not
        has_candidates : True when a second candidate can be used for a
                         slit angle
    """
    present = {_norm(c) for c in df.columns}
    found = {group: all(col in present for col in cols)
             for group, cols in FFFFPZ_SIGNATURE.items()}

    # Burst position plus ranked primary is the minimum that identifies
    # the format; the secondary group is what makes candidates mode
    # possible, and an FFFF-PZ table can legitimately lack it.
    is_ffffpz = found['burst'] and found['primary']
    return {
        'format': 'ffff-pz' if is_ffffpz else 'generic',
        'groups': sorted(g for g, ok in found.items() if ok),
        'missing': sorted(g for g, ok in found.items() if not ok),
        'has_candidates': bool(is_ffffpz and found['secondary']),
    }


def _angle_to_deg(series, unit, is_ra):
    """Convert a coordinate column to degrees, sexagesimal or numeric."""
    if _looks_sexagesimal(series):
        default = u.hourangle if is_ra else u.deg
        return np.array([
            Angle(str(v), unit=default).to(u.deg).value if pd.notna(v) else np.nan
            for v in series])
    values = pd.to_numeric(series, errors='coerce')
    return values * 15.0 if (is_ra and unit == 'hour') else values


def load_targets(source, mapping=None):
    """
    Load any target table into the canonical schema.

    Parameters
    ----------
    source : str, Path or DataFrame
        CSV path, or an already-loaded frame.
    mapping : ColumnMapping, optional
        Supply this to override/complete auto-detection (what the GUI
        sends back after asking the user). When omitted, detection must
        succeed on its own or TargetTableError is raised.

    Returns
    -------
    DataFrame
        The source columns, plus canonical `name`, `ra_deg`, `dec_deg`,
        `mag` and the optional `pox`, `tags`, `dm`.

    Raises
    ------
    TargetTableError
        If the table can't be read without guessing. The partial mapping
        is attached to the exception.
    """
    # A Path is the natural thing for a caller to hold, so accept it
    # alongside str rather than failing on .copy() deep inside pandas.
    df = (pd.read_csv(source) if isinstance(source, (str, os.PathLike))
          else source.copy())

    if mapping is None:
        mapping = detect_mapping(df)
    if not mapping.ok:
        raise TargetTableError(
            'cannot read this target table unambiguously: '
            + '; '.join(mapping.issues), mapping)

    out = df.copy()
    out['name'] = df[mapping.columns['name']].astype(str)
    out['ra_deg'] = _angle_to_deg(df[mapping.columns['ra']], mapping.ra_unit,
                                   is_ra=True)
    out['dec_deg'] = _angle_to_deg(df[mapping.columns['dec']], 'deg', is_ra=False)
    out['mag'] = pd.to_numeric(df[mapping.columns['mag']], errors='coerce')

    # Optional fields always exist downstream, empty if the source lacked them.
    for fieldname, empty in (('pox', np.nan), ('tags', ''), ('dm', np.nan)):
        source_col = mapping.columns.get(fieldname)
        out[fieldname] = df[source_col] if source_col else empty
    source_col = mapping.columns.get('mag_band')
    out['mag_band'] = (df[source_col].map(normalize_band) if source_col else '')
    # Unreadable t_target / required values fall back to unset / False, like
    # priority; field_coercions() reports them.
    source_col = mapping.columns.get('t_target')
    out['t_target'] = (df[source_col].map(parse_t_target).map(
        lambda v: np.nan if v is None else v).astype(float)
        if source_col else np.nan)
    source_col = mapping.columns.get('required')
    out['required'] = (df[source_col].map(parse_required).map(bool)
                       if source_col else False)
    source_col = mapping.columns.get('target_sn')
    out['target_sn'] = (df[source_col].map(parse_t_target).map(
        lambda v: np.nan if v is None else v).astype(float)
        if source_col else np.nan)

    # Priority is handled apart from the loop above because it is the one
    # optional field the scheduler *computes with*: every consumer may assume
    # a float. A value that isn't a number falls back to the default rather
    # than raising -- a table whose priority column reads 'A'/'B' is still a
    # perfectly good target table, it just has no usable ranking. Callers that
    # need to tell the user so should use priority_coercions().
    source_col = mapping.columns.get('priority')
    out['priority'] = (
        pd.to_numeric(df[source_col], errors='coerce').fillna(DEFAULT_PRIORITY)
        if source_col else DEFAULT_PRIORITY)

    bad = out['ra_deg'].isna() | out['dec_deg'].isna()
    if bad.any():
        names = ', '.join(out.loc[bad, 'name'].head(5))
        raise TargetTableError(
            f'{int(bad.sum())} row(s) have unreadable coordinates: {names}',
            mapping)

    # A repeated name is almost always a merge that went wrong, and the
    # scheduler has no way to know: it happily books the same object
    # twice and spends the night observing it. Tables built by merging
    # two sources -- which is how the baseband targets reached
    # Lick-2026B-03 -- are exactly where this happens.
    duplicated = out['name'][out['name'].duplicated(keep=False)]
    if len(duplicated):
        names = ', '.join(sorted(set(duplicated))[:5])
        raise TargetTableError(
            f'{duplicated.nunique()} target name(s) appear more than once: '
            f'{names} -- each target must be one row, or it will be '
            f'scheduled twice', mapping)
    return out


def priority_coercions(source, mapping=None):
    """
    Count priority values that are not numbers, for reporting to the user.

    Created by JXP and Claude

    `load_targets` quietly falls back to DEFAULT_PRIORITY for anything it
    cannot read as a float, because an unreadable ranking is not a reason
    to refuse a target table. Quiet is not the same as hidden, though:
    dropping a priority column on the floor without saying so is the exact
    behaviour this field was added to fix. Callers that have somewhere to
    put a warning -- the GUI's inspect step -- ask here.

    Inputs
    ------
    source : str, Path or pandas.DataFrame
        The target table, as given to load_targets.
    mapping : ColumnMapping, optional
        A mapping already detected for this table; re-detected if omitted.

    Outputs
    -------
    dict with keys:
        'column'  -- the source column priority was read from, or None if
                     the table has no priority column at all
        'n_total' -- rows in the table
        'n_coerced' -- rows whose priority was not a number and therefore
                     fell back to DEFAULT_PRIORITY
        'examples' -- up to 3 distinct offending values, as strings
    """
    df = (pd.read_csv(source) if isinstance(source, (str, os.PathLike))
          else source)
    if mapping is None:
        mapping = detect_mapping(df)

    column = mapping.columns.get('priority')
    if not column:
        return {'column': None, 'n_total': len(df), 'n_coerced': 0,
                'examples': []}

    numeric = pd.to_numeric(df[column], errors='coerce')
    # A blank cell is a missing value, not a typo: the user left it to the
    # default on purpose, so it is not worth warning about.
    bad = numeric.isna() & df[column].notna()
    examples = [str(v) for v in df.loc[bad, column].drop_duplicates().head(3)]
    return {'column': column, 'n_total': len(df),
            'n_coerced': int(bad.sum()), 'examples': examples}


def parse_value_spec(spec, flag='--set-time', what='minutes'):
    """
    One NAME@VALUE flag value (--set-time, --set-sn).

    Parameters
    ----------
    spec : str, e.g. 'SIMFRB123@45'. The last '@' splits, so a name may
        itself contain '@'.
    flag : str, the flag's name, for the error message
    what : str, what VALUE is, for the error message

    Returns
    -------
    (name, value) with value a positive float.

    Raises
    ------
    ValueError for a malformed spec or a non-positive value.
    """
    name, sep, value = str(spec).rpartition('@')
    if not sep or not name.strip():
        raise ValueError(f'{flag} wants NAME@{what.upper()}, got {spec!r}')
    number = parse_t_target(value.strip())
    if number is None or pd.isna(number):
        raise ValueError(f'{flag} {spec!r}: {what} must be a positive number')
    return name.strip(), float(number)


def parse_time_spec(spec):
    """
    One --set-time value, "NAME@MINUTES".

    Parameters
    ----------
    spec : str

    Returns
    -------
    (name, minutes) with minutes a positive float.

    Raises
    ------
    ValueError for a malformed spec or a non-positive time.
    """
    return parse_value_spec(spec, '--set-time', 'minutes')


def _apply_overrides(df, overrides, column, flag, what):
    """
    Set `column` for named targets from NAME@VALUE overrides (a copy).

    Parameters
    ----------
    df : DataFrame from load_targets (has 'name' and `column`)
    overrides : list of "NAME@VALUE" strings, or of (name, value)
    column, flag, what : str, the column to set; the flag and the value's
        meaning, for error messages

    Returns
    -------
    DataFrame (df itself when there is nothing to apply, else a copy)

    Raises
    ------
    ValueError naming any target that is not in the table.
    """
    pairs = [parse_value_spec(o, flag, what) if isinstance(o, str)
             else (str(o[0]), float(o[1])) for o in (overrides or [])]
    if not pairs:
        return df
    out = df.copy()
    if column not in out:
        out[column] = np.nan
    missing = [n for n, _ in pairs if not (out['name'] == n).any()]
    if missing:
        raise ValueError(f'{flag}: no target named ' + ', '.join(missing)
                         + ' in the target table')
    for name, value in pairs:
        out.loc[out['name'] == name, column] = value
    return out


def apply_time_overrides(df, overrides):
    """
    Set t_target (minutes on target, used as given) for named targets, as
    if the table had said so. Used by --set-time, so an observer can change
    a scheduled target's time from the GUI without editing the table.

    Parameters
    ----------
    df : DataFrame from load_targets (has 'name' and 't_target')
    overrides : list of "NAME@MINUTES" strings, or of (name, minutes)

    Returns
    -------
    DataFrame (a copy, with t_target set for those rows)

    Raises
    ------
    ValueError naming any target that is not in the table.
    """
    return _apply_overrides(df, overrides, 't_target', '--set-time', 'minutes')


def apply_sn_overrides(df, overrides):
    """
    Set target_sn (S/N per sub-exposure the ETC sizes this target for) for
    named targets, as if the table had said so. Used by --set-sn.

    Parameters
    ----------
    df : DataFrame from load_targets (has 'name' and 'target_sn')
    overrides : list of "NAME@SN" strings, or of (name, sn)

    Returns
    -------
    DataFrame (a copy, with target_sn set for those rows)

    Raises
    ------
    ValueError naming any target that is not in the table.
    """
    return _apply_overrides(df, overrides, 'target_sn', '--set-sn', 'S/N')


def row_target_sn(row, plan_sn):
    """
    The S/N goal for one target: its own target_sn when set, else the plan's.

    Parameters
    ----------
    row : mapping, may carry 'target_sn'
    plan_sn : float, the plan-wide target S/N

    Returns
    -------
    float
    """
    own = row.get('target_sn') if hasattr(row, 'get') else None
    try:
        own = float(own)
    except (TypeError, ValueError):
        return float(plan_sn)
    return own if own > 0 else float(plan_sn)


def has_own_sn(row):
    """True when a row carries its own positive target_sn."""
    own = row.get('target_sn') if hasattr(row, 'get') else None
    try:
        return float(own) > 0
    except (TypeError, ValueError):
        return False


def field_coercions(source, mapping=None):
    """
    Unreadable t_target / required values, for reporting to the user
    (the same idea as priority_coercions).

    Created by JXP and Claude

    Inputs
    ------
    source : str, Path or pandas.DataFrame
    mapping : ColumnMapping, optional

    Outputs
    -------
    dict field -> {'column', 'n_coerced', 'examples'} for t_target,
    required and target_sn; fields the table doesn't have are left out.
    """
    df = (pd.read_csv(source) if isinstance(source, (str, os.PathLike))
          else source)
    if mapping is None:
        mapping = detect_mapping(df)
    out = {}
    for field, parse in (('t_target', parse_t_target),
                         ('required', parse_required),
                         ('target_sn', parse_t_target)):
        column = mapping.columns.get(field)
        if not column:
            continue
        bad = [v for v in df[column] if parse(v) is None]
        out[field] = {'column': column, 'n_coerced': len(bad),
                      'examples': sorted({str(v) for v in bad})[:3]}
    return out
