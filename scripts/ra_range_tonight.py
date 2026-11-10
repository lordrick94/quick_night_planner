"""
Compute the RA range accessible at some point during the night of
2026-09-14/15 at the Shane 3m (Lick-2026B-02), given the HA limits
-05:40 <= HA <= +03:45 (HA = LST - RA) and no RA limit otherwise.

Created by JXP and Claude

At evening twilight (LST_eve), the earliest-rising RA that is already
legal is RA = LST_eve - HA_MAX (a target at HA_MAX is about to leave the
window). At morning twilight (LST_morn), the latest RA that is still
legal is RA = LST_morn - HA_MIN (a target at HA_MIN has just entered).
Since LST increases monotonically through the night, the union of the
per-moment legal-RA windows [LST-HA_MAX, LST-HA_MIN] over the whole
night is the single contiguous arc from (LST_eve - HA_MAX) forward
(wrapping through 24h/0h) to (LST_morn - HA_MIN).
"""

from astropy import units as u

from lick_2026b02_calculations import find_twilight, HA_MIN, HA_MAX


def fmt_hms(hours):
    hours = hours % 24
    h = int(hours)
    m_full = (hours - h) * 60
    m = int(m_full)
    s = (m_full - m) * 60
    return f"{h:02d}h{m:02d}m{s:04.1f}s"


def main():
    twilight = find_twilight("2026-09-14")
    lst_eve = twilight["evening_lst"].to_value(u.hourangle)
    lst_morn = twilight["morning_lst"].to_value(u.hourangle)

    ra_start = (lst_eve - HA_MAX) % 24   # earliest RA legal at dusk
    ra_end = (lst_morn - HA_MIN) % 24    # latest RA legal at dawn

    span = (ra_end - ra_start) % 24
    gap = 24 - span

    print(f"Evening twilight LST: {lst_eve:.3f}h ({fmt_hms(lst_eve)})")
    print(f"Morning twilight LST: {lst_morn:.3f}h ({fmt_hms(lst_morn)})")
    print()
    print(f"RA range observable (HA-legal) at some point tonight:")
    print(f"  {fmt_hms(ra_start)} -> (through 24h/00h) -> {fmt_hms(ra_end)}")
    print(f"  total span: {span:.2f}h")
    print()
    print(f"RA range NEVER accessible tonight (dead band):")
    print(f"  {fmt_hms(ra_end)} -> {fmt_hms(ra_start)}  (width {gap:.2f}h)")


if __name__ == "__main__":
    main()
