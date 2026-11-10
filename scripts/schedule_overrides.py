"""
Shared scheduling-override helpers: manual night start + blocked-out
windows (e.g. a Target-of-Opportunity interrupt). Used by both the Keck
and Lick scheduling loops so the block-fitting logic exists in exactly
one place.

Created by JXP and Claude
"""

from datetime import timedelta

# One implementation, in the library: the adapters need it too.
from night_planner.sky import advance  # noqa: F401


def resolve_start(default_start, override_start=None):
    """
    Pick the effective night-start time.

    Parameters
    ----------
    default_start : datetime
        The normal twilight-based start (evening twilight + standard/focus
        buffer), as already computed by each script.
    override_start : datetime, optional
        A manually-entered start (e.g. after a ToO hands the telescope
        back). Takes precedence whenever given, even if earlier than the
        default -- the caller is responsible for not passing something
        before evening twilight.

    Returns
    -------
    datetime
    """
    return override_start if override_start is not None else default_start


def _overlapping_block(start, end, blocks):
    """Return the first block overlapping [start, end), or None."""
    for b_start, b_end, reason in blocks:
        if start < b_end and end > b_start:
            return (b_start, b_end, reason)
    return None


def fit_around_blocks(start, duration_min, window_end, blocks):
    """
    Find a [start, end) slot of `duration_min` that clears every block,
    pushing `start` later as needed, without crossing `window_end`.

    Parameters
    ----------
    start : datetime
        Earliest the observation could begin (already clipped to the
        target's own observable-window start and the scheduler's current
        time).
    duration_min : float
        On-target duration in minutes (slew should already be included by
        the caller if slew also needs to dodge a block, or added
        separately if not -- see each scheduler's own convention).
    window_end : datetime
        The target's own observability window close (HA/airmass limit) --
        a hard ceiling independent of blocks.
    blocks : list of (start, end, reason) tuples
        Already resolved to tz-aware datetimes, e.g. via
        night_plan_io.resolve_blocks().

    Returns
    -------
    (new_start, new_end) if a clear slot exists before window_end,
    else (None, None) with the blocking reason available via
    `blocking_reason()` on the same inputs.
    """
    candidate_start = start
    # A block can be adjacent to another; loop until genuinely clear.
    for _ in range(len(blocks) + 1):
        candidate_end = advance(candidate_start, duration_min)
        hit = _overlapping_block(candidate_start, candidate_end, blocks)
        if hit is None:
            if candidate_end <= window_end:
                return candidate_start, candidate_end
            return None, None
        candidate_start = hit[1]  # push past this block's end, retry
        if candidate_start >= window_end:
            return None, None
    return None, None


def blocking_reason(start, duration_min, blocks):
    """Human-readable reason string if [start, start+duration) hits a block."""
    end = advance(start, duration_min)
    hit = _overlapping_block(start, end, blocks)
    if hit is None:
        return None
    b_start, b_end, reason = hit
    return f"blocked ({reason}) {b_start.strftime('%H:%M')}-{b_end.strftime('%H:%M')}"


def push_past_blocks(t, blocks):
    """Advance a bare cursor time past any block(s) it currently sits inside."""
    changed = True
    while changed:
        changed = False
        for b_start, b_end, _ in blocks:
            if b_start <= t < b_end:
                t = b_end
                changed = True
    return t
