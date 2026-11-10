## Target security
In most cases, This code is in a public repo peoples targets are private
So we need them in a git ignored folder

1. We need to scrub all our real targets from the repo, starting with all night plans

2. Set a path for /home/lordrick/Projects/night-planner/pvt_Nighplans on environmental variables and add it to git ignore

## Prompts
1. Identify all our real target files and their info

2. Make a plan to remove them from git and git history all branches and all commits

3. Setup the pvt_Nightplans path for our code to access

As usual, I will handle all the git commands

---

# Execution — Claude (Opus 5.5), 2026-11-09

No real target name or position is written in this file. Names and positions
are kept only in the git-ignored `pvt_Nighplans/_scrub/`.

## Prompt 1 — Inventory of real targets

**Tool:** [`scripts/scan_private_targets.py`](../scripts/scan_private_targets.py)
(run in `frb_env`). It

1. builds a catalogue of real targets from `pvt_Nighplans/`. Sources are every
   CSV name column (TNS, Pri/Sec names, candidate galaxies), every starlist,
   finder file names, and FRB/TNS/J-name tokens in any text, `.xlsx` or `.pdf`.
   It drops synthetic `SIM*` rows and flux standards (BD/Feige/HZ/…);
2. catalogues their **positions** as (RA, Dec) string pairs: decimal degrees
   truncated to 3 dp, plus sexagesimal `hh mm ss` / `hh:mm:ss`. A file counts
   as leaking a position when it holds both the RA and the Dec of one target,
   so a position is still caught after its name has been removed;
3. scans every tracked file at HEAD (text, office-zip XML, PDF via `pdftotext`)
   and **every blob in every commit on every branch** (36 commits).

Report (paths and counts only, safe to commit):
[`Logs/private_target_scan.md`](../Logs/private_target_scan.md).

**Totals:** 1650 real names and 817 real positions catalogued. 235 files at
HEAD leak them; 239 paths across history.

| Class | What | Real names / positions | Action |
|---|---|---|---|
| **A. Raw plan data** | `Night_plans/` (all 11 run dirs: CSVs, starlists, xlsx, finder PNG/JSON, plan_result.json) | up to 1523 names / 603 positions per file | **Remove from all history** |
| | `Keck-2026B-02_test1000/` (repo root) | 20 / 20 | **Remove from all history** |
| | `claude_prompts/night_plans/*.md` (3 run prompts) | up to 19 / 6 | **Remove from all history** |
| **B. Run-specific scripts** | 13 `scripts/{lick_2026b0*,keck_2026oct06_*,make_lick_2026b02_*,make_keck_2026oct06_*,build_lick_2026b02_night2_plan,check_deadtime_lick_2026b01}.py` | up to 14 / 7 | Pseudonymise + blank positions (or move private, see D2) |
| **C. Narrative records** | `Logs/2026/08–10/*.md` (15 files), `context/claudes_brain.md`, `scripts/document_pipeline_workflow.md`, `tests/test_data/TEST_RESULTS_SUMMARY.md`, `claude_prompts/development/user_comments_implementation.md` | up to 34 / 8 | Pseudonymise + blank positions |
| **D. Code / docs / tests** | `README.md`, `docs/{Shane_telescope_constraints,priority_comparison_astroscheduler,target_csv_guide}.md`, `backend/app.py`, `night_planner/lick_tub.py`, `scripts/{make_observing_report,target_visibility,make_keck_2026oct06_targetlist}.py`, `tests/{test_observing_log,test_priority_tiers,test_targets_io,test_backend}.py` | 1–9 names each; **`test_targets_io.py` and `test_backend.py` hold real host positions with the name stripped** | Pseudonymise; hand-fix the two tests (see step 2) |
| **History only** | `docs/priority_system.md` (old versions, 2 commits) | names | Pseudonymised by the same pass |
| Clean | `docs/*.pptx`, `docs/*.pdf`, `test_targs/`, `examples/`, `frontend/`, `Logs/log_summary.csv` | 0 | — |
| False positive | `tests/test_data/*.csv` (26 files): the synthetic generator's `FRB2026MMDDx` names happen to equal **2** real TNS names, with made-up positions | 2 / 0 | Leave (excluded from rules); optionally regenerate with `SIM` names |

Two scan bugs were fixed along the way. Flux standards spelled `bd284211`
(lower case) were counted as targets. And `cand_gal_names` cells hold Python
list strings, which merged several names into one.

## Prompt 2 — Plan to remove them from git and all history

**Tool:** `git filter-repo` (not installed yet:
`conda install -n frb_env -c conda-forge git-filter-repo`). One pass does two
things:
- `--invert-paths --paths-from-file claude_prompts/target_scrub_paths.txt`
  drops the class-A folders and the 13 moved scripts from every commit. That
  file is public (paths only), and the scan script reads the same file, so the
  two never drift apart.
- `--replace-text pvt_Nighplans/_scrub/replace_text.txt` rewrites the contents
  of every kept file in every commit. It replaces 1650 real names with stable
  codes (`TGT0001` …), blanks 12 exact positions, and applies 13 hand-made
  rules (`_scrub/extra_rules.txt`) that map old test fixtures holding real
  positions to the made-up values now in the tests.

All rule files are **private**. `pseudonyms.csv` is the only way back from a
code to a real name.

**Checked (2026-11-10):** `scan_private_targets.py --filter-out
pvt_Nighplans/_scrub --verify` applies the rules to all 373 versions of every
kept file in history, plus the new docs. It finds **0 names, 0 exact
positions, and 0 rounded positions**. The one remaining hit is a coincidence:
magnitude and S/N numbers in the Kast comparison CSV.

### Decisions (answered by LK, 2026-11-10)

- **D1. Names and positions?** *"Yes TNS names are public but we need not to
  show plans to everyone, scrub both as long as we are keeping our copy in
  pvt."* → Both are scrubbed. This includes the two real names that the
  synthetic fixtures had reused: one of them is a real Lick-2026B-01 target
  discussed in the kept docs. The fixtures get the same codes everywhere, so
  the tests are unaffected.
- **D2. Move the run scripts?** *"Move them, I have already copied the files
  to pvt_Nightplans, not sure what you mean by this, elaborate."*
  → **What it means:** copying `Night_plans/` covered the plan *data*. The
  run-specific *scripts* live in `scripts/` and were not copied. "Move" =
  copy them into the private dir **and** remove them from every commit.
  **Finding:** 4 of the 17 run-named scripts are not one-offs; they are the
  planner engine and must stay:
  `keck_2026oct06_calculations.py` (`cli.py calc`, `adapters.py`, 5 tests),
  `lick_2026b02_calculations.py` and `lick_2026b02_night2_calculations.py`
  (`kast_calculations.py`, tests), and `lick_2026b01_calculations.py`
  (`tests/test_data/run_all_tests.py`). They stay public with names replaced
  by codes. Renaming them to run-neutral names is a separate refactor.
  The other **13 were copied** (byte-identical) to
  `pvt_Nighplans/{Lick-2026B-01,Lick-2026B-02,Keck-2026B-02}/scripts/` and
  listed in `target_scrub_paths.txt`. Nothing kept imports them. Also copied
  into the private dir: `claude_prompts/night_plans/*.md` →
  `pvt_Nighplans/_prompts/`, and `Keck-2026B-02_test1000/`. **Not deleted from
  `scripts/`:** Claude Code's safety check blocks `rm` here; `git rm` them in
  step 0.
- **D3. Rescue the docs?** *"Yes"* → `docs/Lick-2026B-01_HOWTO_night_plan_creation.md`
  and `docs/Lick-2026B-01_CORRECTIONS_SUMMARY.md` were cleaned with the same
  rules (`--apply-to`), and the Dec column of the one RA+Dec table is
  withheld. Each has a provenance note. `docs/data/kast_exposure_model_comparison{,_sn10}.csv`
  hold magnitudes only. Links were updated in `README.md`, `docs/README.md`,
  `docs/Shane_telescope_constraints.md`, `etc.py`,
  `compare_kast_exposure_models.py`, `adapters.py` and
  `lick_2026b02_calculations.py`.
- **D4. GitHub?** *"delete and recreate"* → steps 5–6 below.

### Steps (LK/JXP run every git command)

```bash
# 0. LK, in ~/Projects/night-planner on develop -------------------------------
#    (Claude has done all non-git prep: tests use made-up positions, docs
#     rescued, links fixed, private copies made; 145 tests pass.)
git rm scripts/check_deadtime_lick_2026b01.py \
       scripts/build_lick_2026b02_night2_plan.py scripts/build_lick_2026b02_night_plan.py \
       scripts/lick_2026b02_extras.py scripts/lick_2026b02_finalize_starlists.py \
       scripts/lick_2026b02_nonfrb_finders.py scripts/lick_2026b02_sep15_revision.py \
       scripts/make_lick_2026b02_night2_starlist.py scripts/make_lick_2026b02_nonfrb_starlist.py \
       scripts/make_lick_2026b02_starlist.py scripts/keck_2026oct06_filler_search.py \
       scripts/keck_2026oct06_rejection_analysis.py scripts/make_keck_2026oct06_targetlist.py
git add -A        # .gitignore now hides pvt_Nighplans/ and Night_plans/
git status        # check: no pvt_Nighplans/ paths staged
git commit -m "Target scrub prep: private plans dir, rescued docs, fake test coords"
git push origin develop
#    Optional: merge develop into main first, so main also carries .gitignore.

# 1. Freeze, and record what deleting the repo will lose ------------------------
#    Tell everyone: no pushes, no PR merges until step 6.
#    JXP: write down the forks (Insights -> Forks), collaborators/teams,
#    branch protection, Pages, secrets, webhooks, description/topics.
#    Save any issue/PR discussion worth keeping.

# 2. Backup. Keep it PRIVATE and outside any repo; delete when satisfied.
git clone --mirror git@github.com:Sea-Meets-the-Stars/night-planner.git \
    ~/backups/night-planner-PRE-SCRUB.git

# 3. Rewrite a fresh mirror -----------------------------------------------------
conda install -n frb_env -c conda-forge git-filter-repo
git clone --mirror git@github.com:Sea-Meets-the-Stars/night-planner.git /tmp/np-scrub.git
cd /tmp/np-scrub.git
git filter-repo \
    --invert-paths \
    --paths-from-file ~/Projects/night-planner/claude_prompts/target_scrub_paths.txt \
    --replace-text   ~/Projects/night-planner/pvt_Nighplans/_scrub/replace_text.txt

# 4. Verify before anything leaves the machine ---------------------------------
git clone /tmp/np-scrub.git /tmp/np-verify && cd /tmp/np-verify
git log --all --name-only --format= | grep -c '^Night_plans/'      # expect 0
cp -r ~/Projects/night-planner/pvt_Nighplans .                       # git-ignored
conda run -n frb_env python scripts/scan_private_targets.py --out /tmp/scan_after.md
#   expect "Files at HEAD mentioning them: 0" and "Paths in history ...: 0"
conda run -n frb_env python -m pytest -q -m "not network"

# 5. JXP (admin): delete and re-create on GitHub -------------------------------
#    Settings -> Danger zone -> Delete this repository.
#    New repository: Sea-Meets-the-Stars/night-planner, public, EMPTY
#    (no README, licence or .gitignore).
cd /tmp/np-scrub.git
git remote add origin git@github.com:Sea-Meets-the-Stars/night-planner.git  # filter-repo removed it
git push origin 'refs/heads/*'     # all branches; NOT --mirror (skips refs/pull/*)
git push origin 'refs/tags/*'      # none today; harmless
#    Then set the default branch, re-add collaborators, branch protection,
#    Pages and secrets. Consider not re-pushing the stale branches
#    keck-2026oct02 / Lick-2026oct12.

# 6. Everyone re-clones. An old clone that pushes would bring the history back.
mv ~/Projects/night-planner ~/Projects/night-planner.OLD
git clone git@github.com:Sea-Meets-the-Stars/night-planner.git ~/Projects/night-planner
mv ~/Projects/night-planner.OLD/pvt_Nighplans ~/Projects/night-planner/
#    Carry over any other untracked files you need, then delete .OLD.
```

Commit messages contain no real names (checked), so `--replace-message` is not
needed.

**Deleting the repo** removes the PR refs (#1–#4) and the old commits served
by URL in one go, with no Support ticket. **Forks are the exception.** When a
public repo is deleted, its forks survive with the full old history, and the
old commits may stay reachable through the fork network. Check the forks in
step 1 and ask their owners to delete them. For reference:
[GitHub: Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

### Alternative (prompt 4): fresh repo, no history

LK asked whether it is easier to delete this repo and start a new one, with
every collaborator deleting their local copy. **Yes: simpler and safer**, if
losing the 36-commit history on GitHub is acceptable. The full history is
still kept in the private backup from step 2.

- Only one tree needs checking, not 373 historical blobs, and `git
  filter-repo` is not needed.
- The scrub itself does not get smaller. 61 kept files at HEAD still hold
  real names (logs, README, brain, docs, the 4 engine scripts and the test
  fixtures), so the same `replace_text.txt` rules are applied to the snapshot.
- Forks still survive deletion; step 1 (check and delete forks) still applies.
- PRs #1–#4 and any issues are lost either way (D4).
- `develop` already contains all of `main`, `Lick-2026oct12` and
  `keck-2026oct02`, so a snapshot of `develop` loses no code.

Steps, replacing 3–6 above (1 and 2 still apply):

```bash
# F1. Claude (no git state changes): export develop to a plain directory
git archive develop | tar -x -C ../night-planner-public
#     remove every path in claude_prompts/target_scrub_paths.txt from it,
#     apply pvt_Nighplans/_scrub/replace_text.txt (--apply-to), rerun the scan
#     on the directory (expect 0 names, 0 exact, 0 rounded), run the tests there.
# F2. LK: review the diff against develop, then in ../night-planner-public:
git init -b main && git add -A && git commit -m "Initial public release"
#     (check `git status` first: nothing from pvt_Nighplans/ or Night_plans/)
# F3. JXP: delete the old repo, create an EMPTY one (same name is fine), then
git remote add origin git@github.com:Sea-Meets-the-Stars/night-planner.git
git push -u origin main          # optionally also create and push develop
#     restore collaborators, protection, Pages, secrets.
# F4. Everyone: save unpushed work as files (the old and new histories are
#     unrelated, so old branches cannot be merged), move pvt_Nighplans/ out,
#     delete the old clone, clone the new repo, move pvt_Nighplans/ back.
```

### F1 done (prompt 5): `~/Projects/quick_night_planner`

LK: "Don't worry about the commit history for now, Make the code on a
separate directory `/home/lordrick/Projects/quick_night_planner`".

```bash
python scripts/build_public_snapshot.py --dest ../quick_night_planner           # build
python scripts/build_public_snapshot.py --dest ../quick_night_planner --update  # refresh
python scripts/build_public_snapshot.py --dest ../quick_night_planner --audit-only
```

- 218 files: every tracked file except `target_scrub_paths.txt`, with
  `replace_text.txt` applied (about 485 replacements in 59 files). It holds no `.git`.
- Audit: 0 real names, 0 exact positions. The 4 rounded-position flags are
  false positives (a Kast S/N table, a sun-time table, a Dec/TUB table, an
  altitude limit). Hits in `test_targs/` and `tests/test_data/` are synthetic;
  the one row carrying a real target's code is 125 deg from that target.
- Tests in the copy: 144 passed, 1 skipped (the `.gitignore` check, which
  needs a git checkout). Run them with `PYTHONPATH=<copy>`, because `frb_env`
  has the old repo installed in editable mode.
- Found while building it, and fixed in **this** repo too (re-run
  `--update` after any further change here):
  - one real position in hours remained in `tests/test_targets_io.py` (2
    spots) and `tests/test_backend.py`; it is now made up;
  - `test_observing_log` passed a real name to the report script; it now
    reads it from the private `Keck-2026B-02/report_extra.txt`;
  - my own notes (brain, 2026-11-10 log) and the scanner's docstring quoted
    a rounded real position as an example. They are rewritten; note the brain
    version was already pushed to `origin/develop` in `3332d46`.
  - The rounded-position tolerance is now 0.1 deg (0.2 deg for RA in hours).
- Run scripts that used real names (`FORCED_FIRST_TNS`, repeat lists, the
  Keck mask list) now carry codes, so they import and test fine but cannot
  re-run those exact nights. Their real versions stay here and in the
  private directory.

Next (LK/JXP): review the copy (e.g. `diff -r` against this repo), then F2–F4.
After moving, set `NIGHT_PLANNER_PLANS` to the new private directory and
`pip install -e` the new copy in `frb_env`.

### Who can do which step

The repo belongs to the `Sea-Meets-the-Stars` org. "Admin" below means an org
owner or a repo admin (probably JXP). These are GitHub's general permission
levels; your org's settings may tighten them.

| Step | Who |
|---|---|
| 0: `git rm`, commit, push develop | LK (write access) |
| 1: freeze; record forks and settings | JXP (admin, for settings) |
| 2–4: backup mirror, `filter-repo`, verify | Anyone with read access (all local) |
| 5: delete and re-create the repo, push, restore settings | Admin; the org may limit deletion to org owners |
| 6: re-clone | Every collaborator, on every machine |
| Deleting a fork | That fork's owner |

**Assume exposure.** The repo was public, so anyone may already have cloned
it. The rewrite only stops further exposure.

**Prevention** (done in prompt 3): plans default to a git-ignored directory, a
test guards the `.gitignore`, and `scan_private_targets.py` (with `--coarse`
and `--verify`) can be rerun at any time. Optional: a pre-commit hook that
runs the scan on staged files.

I could not check visibility, forks or PR refs from here: `gh` is not
authenticated, and the SSH remote needs an interactive key.

## Prompt 3 — `pvt_Nighplans` path for the code

- `pvt_Nighplans/` was already a full copy of `Night_plans/`
  (`diff -rq`: identical).
- [`night_planner/paths.py`](../night_planner/paths.py): `plans_dir()` now
  returns `NIGHT_PLANNER_PLANS` when set, else **`<repo>/pvt_Nighplans`**
  (new `PRIVATE_PLANS_DIR`). Before this it fell back to the tracked
  `Night_plans/`. Every user of `plans_dir()`/`plan_dir()` follows: CLI,
  backend `PLANS_ROOT`, `_safe_dir`, `/api/plans`.
- **Env var set** for the conda env:
  `conda env config vars set NIGHT_PLANNER_PLANS=/home/lordrick/Projects/night-planner/pvt_Nighplans -n frb_env`.
  It takes effect on the next `conda activate frb_env`. LK/JXP on other
  machines do the same with their own path. Without it the default still
  lands in the private directory.
- [`.gitignore`](../.gitignore): `pvt_Nighplans/` **and** `Night_plans/` (safety
  net for old commands and docs that still say `--output-dir Night_plans/…`).
  Note that ignoring does not untrack the files; step 2 above removes them.
- Tests: `tests/test_observing_log.py` and `tests/test_backend.py` now read the
  real Keck plan through `plan_dir()`, so they run locally and skip elsewhere.
  `tests/test_paths.py` asserts the new default and has a new test,
  `test_private_plan_directories_are_git_ignored`.
- Small follow-ons: the `backend/app.py` comments and docstrings, the
  `scripts/check_portability.py` skip list, the frontend output-dir
  placeholder (`pvt_Nighplans/…`; `_safe_dir` would reject `Night_plans/…`),
  and the env-var tables in `README.md` and `INSTALL.md`.
- **Tests:** `145 passed, 1 deselected` in `frb_env` (offline IERS). With
  `NIGHT_PLANNER_PLANS=/nonexistent` the six real-plan tests skip cleanly.

Not yet done (left for the decisions above): the many README/docs mentions of
`Night_plans/<run>/…` as example output paths, and the hard-coded
`Night_plans/...` defaults inside the run-specific scripts.

## Logs

- 2026-11-09T20:00Z — Claude: ran prompts 1–3. Wrote and debugged
  `scripts/scan_private_targets.py` (inventory, history scan, filter-repo rule
  generator); generated private rules in `pvt_Nighplans/_scrub/`; checked that
  they clean every surviving file; wrote the plan above; switched the plans
  default to `pvt_Nighplans`, updated `.gitignore`, set the `frb_env` env var,
  and updated tests and docs. No git state was modified.
- 2026-11-09T20:23Z — Claude: asked which steps only the owner can do. Added
  the "Who can do which step" table to the plan.
- 2026-11-10T01:42Z — Claude: Lordrick fetched `origin/main` (PR #4,
  `keck-2026oct02`, now merged). Reran the scan: no new leaks, rules
  unchanged; PR refs are now #1–#4. Making the repo private is ruled out, so
  the next step is step 0 (decisions + test fix + rescue docs).
- 2026-11-10T01:49Z — Claude: read LK's D1–D4 answers. Moving the scripts
  showed that 4 run-named scripts are the engine, so they stay with codes
  instead of names; the 13 one-offs plus the run prompts and test1000 were
  copied to pvt (the safety check blocked `rm`, so `git rm` is left to LK).
  Moved the removal list into `target_scrub_paths.txt`. Added to the scan
  script: rules from every historical blob, `extra_rules.txt`, `--apply-to`,
  `--coarse` and `--verify`. The rounded-position check found real positions
  in `test_targets_io.py` (3 spots) and in a HOWTO table; all fixed.
  Rescued the D3 docs and fixed links. Rewrote steps 0–6 for delete and
  re-create. Verify: 0/0/0. Tests: 145 passed.
- 2026-11-10T17:07Z — Claude: LK asked whether deleting the repo and starting
  a new one is easier. Answer: yes. Checked that step 0 is done (the 13
  scripts are no longer tracked) and that `develop` contains all other
  branches. The HEAD scan still finds real names in 61 kept files, so the same
  rules must be applied to the snapshot. Added "Alternative (prompt 4)" with
  steps F1–F4.
- 2026-11-10T18:05Z — Claude: built the history-free copy in
  `~/Projects/quick_night_planner` with the new `build_public_snapshot.py`.
  The audit and the tests in the copy found a real position in hours left in
  two tests, a real name in a test, and real rounded positions I had written
  as examples in my notes and a docstring. All fixed here and in the copy;
  tolerance raised. Copy: 0 names, 0 exact; 144 tests pass. Here: 145 pass.
