# Logging

> This logging approach is ported from the **ClimateIntelligence** repository so
> that night-planner logs work identically. The finalized conventions (CO2
> factors, token accounting, file layout) are reproduced below.

## Goals

We want to log all of the work that Claude does for this project. Not just the
code, but the thinking process, the decisions, the mistakes, the successes, etc.
And, the tokens used and an estimate of the CO2 emissions.

## Basics

### Log files

Claude logs the following every time it receives a prompt related to this project:

- The UT time
- The prompt
- The tokens used
- The model used
- An estimate of the CO2 emissions

Claude generates a unique log file for every calendar day. These appear in the
`Logs/` directory and its `YYYY/MM/` subdirectories (created if they do not
exist). The filename is `YYYY-MM-DD.md` and the file's heading is
`# Logging for YYYY-MM-DD`.

Each user prompt (not each tool call) gets one section containing the five
structured fields above plus a **prose narrative** of the work — the thinking,
decisions, mistakes, and successes. Log only the *verbatim user text* as the
prompt (do not include injected IDE/system-reminder context).

### Summary table

A summary table of every log entry lives in `Logs/log_summary.csv` with columns:

- `ut_time`
- `tokens_used`
- `model`
- `co2_grams_estimate`

**This file is written automatically by a `Stop` hook**
([`.claude/hooks/log_usage.py`](../.claude/hooks/log_usage.py)) after every turn,
which reads the session transcript and records the authoritative numbers. **Claude
must not append rows to `log_summary.csv` by hand** — that would duplicate the
hook's row. Token accounting (per the hook):
`tokens_used = Σ (input_tokens + cache_creation_input_tokens + output_tokens)`
over the turn's non-sidechain assistant API calls; cache-read tokens are excluded.

### CO2 emissions calculation

The per-prompt CO2 estimate uses a transparent, reproducible formula:

```
CO2 (grams) = (tokens / 1000) × energy_per_1k_tokens × grid_intensity
```

Factors (finalized 2026-07-03 in ClimateIntelligence):

| Factor | Value | Basis |
|--------|-------|-------|
| `energy_per_1k_tokens` | 0.20 Wh per 1,000 tokens | Combined input+output, large frontier model. Order-of-magnitude estimate. |
| `grid_intensity` | 0.38 gCO2 / Wh (≈ 380 gCO2 / kWh) | Anthropic data-center region (US-average, location-based). |

**Combined factor:** `0.20 Wh × 0.38 gCO2/Wh = 0.076 gCO2 per 1,000 tokens`.

**Worked example:** 16,000 tokens → `(16000 / 1000) × 0.20 × 0.38 = 1.22 g` ≈ **1.2 gCO2**.

If these factors are ever refined, regenerate them as a Python script written to
disk (per the CLAUDE.md calculation rule) so the result stays reproducible.

## Coding

Guidelines for any code written in this project:

- Use Python.
- Add inline comments to explain the effort.
- Reuse existing code when possible.
- Use methods, not classes.
- Use matplotlib, seaborn, or Bokeh for plotting.
- Place import statements at the top of the file.
- Include a description of inputs/outputs in the doc string of all methods.
- Add "Created by JXP and Claude" to the top of the file and each doc string.
