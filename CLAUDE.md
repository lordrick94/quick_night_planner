# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Project Overview

**night-planner** teaches Claude how to generate a night plan for a modern,
professional telescope. Claude learns from a pair of professional astronomers
(J. Xavier Prochaska and a colleague) who have been planning observing nights for
many years. A further goal is a webpage dashboard — hosted on GitHub — that
monitors all of the author's Claude-assisted projects.

## Git

- **The author (JXP) performs all git commands.** Claude must not run `git add`,
  `git commit`, `git push`, or any other state-modifying git operation. Read-only
  commands (`git status`, `git log`, `git diff`) are fine when needed to understand
  the repo.

## Calculations

- **If you do any calculation, generate it as a Python script and write it to
  disk** so the author can add it to the repository. Do not compute results only
  inline (in your head, a one-off shell one-liner, or a scratch REPL). Committing
  the logic to a reusable, reviewable `.py` file keeps every result reproducible
  and version-controllable.

## Logging

This project uses **the same logging approach as the ClimateIntelligence
repository**. The full spec — daily narrative log format, `log_summary.csv`
conventions, token accounting, and the CO2 formula — lives in
[`Logs/logging.md`](Logs/logging.md). Read it if in doubt.

**Claude must log every prompt related to this project.** Responsibilities are
split between Claude and an automatic hook:

### 1. Daily narrative log — written by Claude (every prompt)

After responding to each user prompt, append an entry to the day's log file:

- **Path:** `Logs/YYYY/MM/YYYY-MM-DD.md` (UTC date); create `YYYY/MM/` if missing.
- **File heading (once per day):** `# Logging for YYYY-MM-DD`.
- **One section per user prompt** (not per tool call) containing:
  - **UT time** the prompt was received (`date -u +"%Y-%m-%dT%H:%M:%SZ"`).
  - **Prompt:** the *verbatim user text only* (no IDE/system-reminder context).
  - **Model**, and **Tokens/CO2** — note the authoritative values live in
    `log_summary.csv`; any inline figures are estimates.
  - A **prose narrative** of the work: the thinking, decisions, mistakes, and
    successes — not just what changed.

### 2. Summary table — written automatically by a hook (do NOT write by hand)

`Logs/log_summary.csv` is appended by a `Stop` hook
([`.claude/hooks/log_usage.py`](.claude/hooks/log_usage.py)) after every turn,
recording the authoritative `ut_time, tokens_used, model, co2_grams_estimate`.
**Claude must not append rows to `log_summary.csv` itself.** If the hook is
inactive (e.g. just installed and needing `/hooks` or a restart to load), note
that in the daily log rather than hand-writing rows.

## Claude's brain

- **Save what you are learning to [`context/claudes_brain.md`](context/claudes_brain.md)
  as you go.** Record durable knowledge about night planning, the telescope, the
  author's preferences, and how this repository is organized — the things a fresh
  session would want to know. Maintain a **version history** at the bottom of that
  file, adding a dated entry each time you update it.

## Coding conventions

See the *Coding* section of [`Logs/logging.md`](Logs/logging.md): Python; methods
not classes; imports at top; docstrings describing inputs/outputs; matplotlib /
seaborn / Bokeh for plots; and `"Created by JXP and Claude"` at the top of each
file and docstring.
