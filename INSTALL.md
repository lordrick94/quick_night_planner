# Install night-planner

Created by JXP and Claude

Five minutes from a clean machine to a generated night plan. Nothing here
is specific to either author's laptop: every path inside the repo is
derived from where the code sits, and the few paths that live outside it
are environment variables.

---

## 1. Get the code

```bash
git clone https://github.com/profxj/night-planner.git
cd night-planner
```

## 2. Make the environment

```bash
conda env create -f environment.yml
conda activate night-planner
pip install -e .
```

`pip install -e .` is what puts the `night-planner` command on your PATH
and makes `import night_planner` work from any directory. Mamba or
micromamba work the same way (`micromamba env create -f environment.yml`).

**Without conda.** The astro stack builds from wheels on most platforms:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[gui,dev]"
pip install astroquery photutils      # finder charts only
```

## 3. Check it

```bash
pytest                                # the test suite
python scripts/check_portability.py   # no machine-specific paths crept in
night-planner --help
```

All three should pass on a machine that has never seen this repo.

## 4. Environment variables

Only needed for the features that read data living outside this repo.
Everything else works unset.

| Variable | What it points at | Needed for | Default |
|---|---|---|---|
| `NIGHT_PLANNER_PLANS` | Where generated plans are written (private: real targets) | Recommended — `conda env config vars set NIGHT_PLANNER_PLANS=<repo>/pvt_Nighplans` | `<repo>/pvt_Nighplans` (git-ignored) |
| `FFFF_PZ_REPO` | Your `chime-ffff-pz` checkout | Pulling targets and finder data from FFFF-PZ | A sibling directory beside this repo |
| `LICK_NIGHT_PLAN_TEMPLATE` | A Lick night-plan `.xlsx` | Building the Lick workbook (it copies the template's checklist sheet) | None — the builder tells you to set it |
| `FFFF_PZ_URL`, `FFFF_PZ_USER`, `FFFF_PZ_PASS` | FFFF-PZ server and credentials | Querying the FFFF-PZ database | None |

Put them in your shell profile:

```bash
export FFFF_PZ_REPO="$HOME/Projects/chime-ffff-pz"
export LICK_NIGHT_PLAN_TEMPLATE="/path/to/Lick_2026A-4_Night_plan.xlsx"
```

`night_planner/paths.py` is the single place that reads these. A missing
one fails with a message naming the variable, not a stray path.

## 5. Run something

The viewer needs no external data at all — start there:

```bash
night-planner serve          # http://127.0.0.1:8020
```

Then a plan from a target table (`test_targs/` has ready-made ones):

```bash
night-planner calc --instrument kast \
    --targets-csv test_targs/autumn_ffffpz.csv \
    --output-dir Night_plans/my-first-run \
    --date 2026-10-21
```

`calc` schedules the night; `build` writes the Excel workbook (Keck/LRIS
only for now). `night-planner calc --instrument kast --help` lists that
pipeline's own flags.

See [docs/target_csv_guide.md](docs/target_csv_guide.md) for what the
target table needs, and [docs/README.md](docs/README.md) for the rest.

---

## Troubleshooting

**`chime_ffff_pz` not found.** It is a separate repository and is not
installed by `environment.yml`. Clone it beside this one, or set
`FFFF_PZ_REPO`. Some scripts expect it in its own environment; run those
with `conda run -n <that env> python scripts/...`.

**`FileNotFoundError: set LICK_NIGHT_PLAN_TEMPLATE ...`** The Lick
workbook builder copies its checklist sheet from an existing night plan.
Point the variable at any such `.xlsx`.

**`photutils` / `astroquery` missing.** They are only needed for finder
charts and on-source checks. `environment.yml` includes them; a plain
`pip install -e .` does not.

**Plans written somewhere unexpected.** Check `NIGHT_PLANNER_PLANS`; when
it is unset, plans go to the git-ignored `<repo>/pvt_Nighplans`. Plans hold
real targets and must never be committed; `Night_plans/` is git-ignored as a
safety net.
