"""Tests for reading arbitrary target tables into the canonical schema.

The cases that matter most here are the refusals: silently guessing a
coordinate's units, or silently substituting an FRB's burst position for
its host galaxy, would both point the telescope somewhere else while
producing an output that looks perfectly normal.

Created by JXP and Claude.
"""

import pandas as pd
import pytest

from night_planner.targets_io import (
    TargetTableError, detect_mapping, load_targets,
)


def test_ffffpz_columns_map_to_host_not_burst():
    """Pri_RA/Pri_Dec (host) win over FRB_RA/FRB_Dec (burst position).

    Inputs: none.
    Outputs: none (asserts on success).
    """
    df = pd.DataFrame({'TNS': ['FRB1'], 'FRB_RA': [1.0], 'FRB_Dec': [2.0],
                       'Pri_RA': [150.25], 'Pri_Dec': [40.5],
                       'Pri_mag': [22.4], 'Pri_POx': [0.99],
                       'FRB_tags': ['CHIME'], 'FRB_DM': [800.0]})
    out = load_targets(df)
    assert out.loc[0, 'ra_deg'] == 150.25
    assert out.loc[0, 'dec_deg'] == 40.5
    assert out.loc[0, 'name'] == 'FRB1'
    assert out.loc[0, 'tags'] == 'CHIME'


def test_burst_position_alone_is_refused():
    """A table carrying only FRB_RA/FRB_Dec must not be read as pointings.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    df = pd.DataFrame({'TNS': ['FRB1'], 'FRB_RA': [150.0], 'FRB_Dec': [40.0],
                       'Pri_mag': [22.4]})
    with pytest.raises(TargetTableError):
        load_targets(df)


def test_sexagesimal_coordinates():
    """'10:30:00.00' is read as hours of RA, '+45:15:36.0' as degrees of Dec.

    Made-up position (no real target: this repo is public).

    Inputs: none.
    Outputs: none (asserts on success).
    """
    df = pd.DataFrame({'Name': ['A'], 'RA': ['10:30:00.00'],
                       'Dec': ['+45:15:36.0'], 'magnitude': [15.9]})
    out = load_targets(df)
    assert out.loc[0, 'ra_deg'] == pytest.approx(157.5, abs=1e-5)
    assert out.loc[0, 'dec_deg'] == pytest.approx(45.26, abs=1e-5)


def test_ra_in_hours_when_named_so():
    """A column called ra_hours is multiplied up to degrees.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    df = pd.DataFrame({'id': ['Y'], 'ra_hours': [10.5], 'dec': [40.0],
                       'mag': [22.4]})
    assert load_targets(df).loc[0, 'ra_deg'] == pytest.approx(157.5)


def test_ambiguous_numeric_ra_is_refused():
    """A bare numeric RA with every value <= 24 could be hours or degrees.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    df = pd.DataFrame({'name': ['Z'], 'ra': [10.5], 'dec': [40.0],
                       'mag': [22.4]})
    with pytest.raises(TargetTableError) as excinfo:
        load_targets(df)
    assert 'hours or degrees' in str(excinfo.value)
    # The partial mapping rides along so a caller can ask just this one thing.
    assert excinfo.value.mapping.columns['ra'] == 'ra'


def test_explicit_mapping_resolves_ambiguity():
    """Supplying ra_unit lets an otherwise-ambiguous table through.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    df = pd.DataFrame({'name': ['Z'], 'ra': [10.5], 'dec': [40.0],
                       'mag': [22.4]})
    mapping = detect_mapping(df)
    mapping.ra_unit = 'hour'
    mapping.issues.clear()
    assert load_targets(df, mapping=mapping).loc[0, 'ra_deg'] == pytest.approx(157.5)


def test_optional_columns_always_exist():
    """pox/tags/dm are created empty when the source table lacks them.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    df = pd.DataFrame({'object': ['A'], 'RA_deg': [10.0], 'DEC': [20.0],
                       'Rmag': [19.5]})
    out = load_targets(df)
    for column in ('pox', 'tags', 'dm'):
        assert column in out.columns


def test_source_columns_are_preserved():
    """Unmapped source columns survive into the canonical frame.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    df = pd.DataFrame({'object': ['A'], 'RA_deg': [10.0], 'DEC': [20.0],
                       'Rmag': [19.5], 'notes': ['from my spreadsheet']})
    assert load_targets(df).loc[0, 'notes'] == 'from my spreadsheet'


def test_unreadable_coordinates_are_reported_with_names():
    """Bad coordinate rows fail loudly, naming the offending targets.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    df = pd.DataFrame({'name': ['GOOD', 'BAD'], 'RA_deg': [10.0, None],
                       'dec': [20.0, 20.0], 'mag': [19.5, 19.5]})
    with pytest.raises(TargetTableError) as excinfo:
        load_targets(df)
    assert 'BAD' in str(excinfo.value)


def test_duplicate_target_names_are_refused():
    """A repeated name would be scheduled twice, costing a whole block.

    Merging two sources is how this happens in practice -- the baseband
    targets merged into Lick-2026B-03 are exactly that shape -- and the
    scheduler has no way to notice on its own.
    """
    import pandas as pd
    import pytest

    from night_planner.targets_io import TargetTableError, load_targets

    frame = pd.DataFrame({
        'name': ['TGT0534', 'TGT0537', 'TGT0534'],
        'ra_deg': [10.0, 20.0, 10.0],
        'dec_deg': [40.0, 41.0, 40.0],
        'mag': [18.0, 19.0, 18.0],
    })
    with pytest.raises(TargetTableError, match='more than once'):
        load_targets(frame)


def test_priority_defaults_when_the_table_has_no_column():
    """Every target lands in one tier, which is the pre-priority behaviour.

    This is the backwards-compatibility guarantee the tier scheduler rests
    on: an ordinary target table must schedule exactly as it always did.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    from night_planner.targets_io import DEFAULT_PRIORITY

    frame = pd.DataFrame({'name': ['A', 'B'], 'ra_deg': [10.0, 20.0],
                          'dec_deg': [40.0, 41.0], 'mag': [18.0, 19.0]})
    out = load_targets(frame)
    assert list(out['priority']) == [DEFAULT_PRIORITY, DEFAULT_PRIORITY]


def test_priority_column_is_recognised_and_numeric():
    """A priority column is read, including fractional tiers.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    frame = pd.DataFrame({'name': ['A', 'B'], 'ra_deg': [10.0, 20.0],
                          'dec_deg': [40.0, 41.0], 'mag': [18.0, 19.0],
                          'priority': [2, 1.5]})
    out = load_targets(frame)
    assert list(out['priority']) == [2.0, 1.5]


def test_unreadable_priority_falls_back_but_is_reportable():
    """An 'A'/'B' priority column defaults, and says so when asked.

    scripts/make_test_target_tables.py emits exactly this, so the case is
    real rather than hypothetical. Defaulting is right -- an unreadable
    ranking is no reason to refuse a usable target table -- but it must be
    reportable, because silently dropping the column is the behaviour this
    field exists to fix.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    from night_planner.targets_io import DEFAULT_PRIORITY, priority_coercions

    frame = pd.DataFrame({'name': ['A', 'B'], 'ra_deg': [10.0, 20.0],
                          'dec_deg': [40.0, 41.0], 'mag': [18.0, 19.0],
                          'priority': ['A', 'B']})
    assert list(load_targets(frame)['priority']) == [DEFAULT_PRIORITY] * 2

    report = priority_coercions(frame)
    assert report['column'] == 'priority'
    assert report['n_coerced'] == 2
    assert sorted(report['examples']) == ['A', 'B']


def test_blank_priority_cell_is_not_reported_as_an_error():
    """A missing value is a deliberate default, not a typo worth warning about.

    Inputs: none.
    Outputs: none (asserts on success).
    """
    from night_planner.targets_io import DEFAULT_PRIORITY, priority_coercions

    frame = pd.DataFrame({'name': ['A', 'B'], 'ra_deg': [10.0, 20.0],
                          'dec_deg': [40.0, 41.0], 'mag': [18.0, 19.0],
                          'priority': [2.0, None]})
    assert list(load_targets(frame)['priority']) == [2.0, DEFAULT_PRIORITY]
    assert priority_coercions(frame)['n_coerced'] == 0
