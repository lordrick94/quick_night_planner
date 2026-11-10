# FFFF-PZ Target Selection Pipeline Investigation

**Created by JXP and Claude**
**Date:** 2026-08-14

## Problem

When querying `chime_ffff_pz_targets Lick-2026B-1`, we got 4 targets but missed better ones (TGT0568, TGT0567 with P_Ux=0.000, mag 15-17).

## Pipeline Workflow Discovered

### Step 1: Create Resource JSON

```bash
# Create JSON with criteria
cat > Lick-2026B-1.json <<EOF
{
    "instrument": "KAST",
    "name": "Lick-2026B-1",
    "valid_start": "2026-08-14T03:38:00Z",
    "valid_stop": "2026-08-14T12:23:00Z",
    "num_targ_longslit": 6,
    "max_AM": 2.0,
    "frb_surveys": "all",
    "max_mag": 20.5
}
EOF
```

### Step 2: Add Resource to FFFF-PZ DB

```bash
cd "$FFFF_PZ_REPO"   # your chime-ffff-pz checkout
chime_ffff_pz_add_furesource chime_ffff_pz/data/Observing/Lick-2026B-1/Lick-2026B-1.json
# Output: "Your request succeeded!"
```

**Result:** Resource created in DB (pagination: returns 100/page, Lick-2026B-1 on page 2)

### Step 3: Query Targets

```bash
chime_ffff_pz_targets Lick-2026B-1
# Output: Lick-2026B-1_targets.csv with 4 FRBs
```

**Targets returned:**
- TGT0252 (RA=5.25h, mag=16.27, P_Ux=0.035)
- TGT0472 (RA=2.86h, mag=18.75, P_Ux=0.015)
- TGT0407 (RA=6.93h, mag=13.32, P_Ux=0.013) ← NOT observable (RA > 6.8h)!
- TGT0508 (RA=10.07h, mag=16.37, P_Ux=0.000) ← NOT observable (RA 10h)!

**Targets MISSED (from hco_batch_jul26.csv):**
- TGT0568 (RA=13.87h, mag=**15.36**, P_Ux=**0.000**) ← BEST!
- TGT0567 (RA=13.59h, mag=16.93, P_Ux=**0.000**) ← EXCELLENT!

## Key Finding

**The API returns FRBs already ASSIGNED to the resource**, not all FRBs matching criteria!

Server-side logic (unknown) assigns FRBs based on:
1. Time window
2. Criteria (max_AM, max_mag, etc.)
3. **Unknown additional filters** (status? tags? manual curation?)

## Better Approach: Manual Selection

### Method 1: Query All FRBs, Filter Manually

```python
from chime_ffff_pz.utils import ffff_pz_utils
import pandas as pd

# Get all FRBs from local DB
frbs = ffff_pz_utils.get_transients()
df = pd.DataFrame(frbs)

# Filter by Dec, RA range, P_Ux
observable = df[
    (df['dec'] < 82) &
    (((df['ra']/15 >= 13.28) | (df['ra']/15 <= 6.80))) &
    (df['P_Ux'] < 0.1)  # Has identified host
]

# Check for PATH results
for name in observable['name']:
    year = name[3:7]
    chime_path = os.environ['CHIME_PATH_REPO']   # your chime-path checkout
    path_file = f'{chime_path}/chime_path/{year}/{name}/{name}_PATH_candidates.csv'
    if exists(path_file):
        # Read magnitudes, check if suitable
        ...
```

### Method 2: Use Pre-Selected Lists (e.g., hco_batch_jul26.csv)

```python
# Read batch file
hco_df = pd.read_csv('hco_batch_jul26.csv')

# Query each FRB in local DB
for name in hco_df['name']:
    frb = ffff_pz_utils.grab_frb(name)
    # Check P_Ux, PATH results, observability
    ...
```

**This is what we did and found the best targets!**

## Scripts Used (Chronological)

1. `query_ffffpz_targets.py` - Query all observable FRBs from local DB
2. `chime_ffff_pz_add_furesource` - Add resource to DB
3. `chime_ffff_pz_targets` - Query assigned targets (limited results)
4. Manual Python query of hco_batch_jul26.csv FRBs (found best targets!)
5. `fix_ha_limits.py` - Calculate HA-corrected observable windows
6. `chime_ffff_pz_finder` - Generate finder charts (needs FFFF-PZ API running)
7. `chime_ffff_pz_starlist` - Generate telescope starlist from finders

## Recommendation

**Do NOT rely on `chime_ffff_pz_targets` alone for target selection!**

Instead:
1. Start with curated lists (hco_batch_jul26.csv, etc.)
2. Query local FFFF-PZ DB for full info
3. Filter by P_Ux, PATH results, observability
4. Calculate HA windows manually
5. Generate finders for final selection

## Files Created During Investigation

### night-planner/Night_plans/Lick-2026B-01/
- `ffffpz_candidates.csv` - All 314 observable FRBs (query_ffffpz_targets.py)
- `NEW_TARGETS_FROM_FFFFPZ.md` - Initial analysis (WRONG - used P_Ux backwards!)
- `Lick-2026B-1_targets.csv` - API-returned targets (limited)
- `FFFF-PZ_TARGETS.md` - Comparison original vs API targets
- `HCO_BATCH_COMPARISON.md` - **BEST analysis** - found TGT0568, TGT0567
- `selected_targets_ha_corrected.csv` - HA-clipped windows for original 6
- `HA_LIMIT_FIX.md` - HA limit violation analysis
- `hco_batch_jul26.csv` - Pre-selected batch (19 FRBs)

### night-planner/scripts/
- `query_ffffpz_targets.py` - Query all observable FRBs
- `fix_ha_limits.py` - Calculate HA-corrected windows

### chime-ffff-pz/chime_ffff_pz/data/Observing/Lick-2026B-1/
- `Lick-2026B-1.json` - Resource definition
- `Lick-2026B-1_targets.csv` - API-returned targets
- `lick.starlist` - Telescope starlist (5 of 6 targets)
- `FRB*_finder.json/png` - Finder charts (5 of 6)

## Lessons Learned

1. **P_Ux meaning**: P_Ux=1 → hostless (BAD), P_Ux=0 → has host (GOOD)
2. **API limitations**: `chime_ffff_pz_targets` returns pre-assigned FRBs, not all matching criteria
3. **HA limits critical**: Shane -5h to +3.75h reduces observable time significantly
4. **Pre-selected lists valuable**: hco_batch_jul26.csv had better targets than API query
5. **PATH results required**: Check existence before generating finders
6. **Manual filtering necessary**: Automated selection missed best targets

## Recommended Workflow for Future Nights

1. Check for pre-selected batch files (hco_batch_*.csv)
2. Query local FFFF-PZ for batch FRBs
3. Filter: P_Ux < 0.1, has PATH results, observable RA/Dec
4. Calculate HA windows with fix_ha_limits.py
5. Select 4-6 targets based on brightness, P_Ux, observable time
6. Generate finders (if FFFF-PZ API running)
7. Generate starlist
8. Update night plan
