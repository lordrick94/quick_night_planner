#!/usr/bin/env python3
"""Stop hook: append authoritative per-prompt usage to Logs/log_summary.csv.

Reads the Claude Code Stop-hook JSON on stdin (which carries `transcript_path`),
parses the session transcript, and records one CSV row for the just-completed
user turn: UT time (prompt-received), tokens used, model, and estimated CO2.

Token/CO2 conventions are defined in Logs/logging.md. In particular:
  tokens_used = sum over the turn's (non-sidechain) assistant API calls of
                (input_tokens + cache_creation_input_tokens + output_tokens).
  Cache-read tokens are excluded (cached context carries negligible marginal
  compute and would otherwise dominate the count).
  CO2 (g) = tokens/1000 * 0.076   (0.20 Wh/1k tokens * 0.38 gCO2/Wh)

The hook must never disrupt the session: any error is swallowed and it exits 0.
"""

import csv
import json
import sys
from pathlib import Path

CO2_G_PER_1K_TOKENS = 0.076  # 0.20 Wh/1k * 0.38 gCO2/Wh; see Logs/logging.md
CSV_HEADER = ["ut_time", "tokens_used", "model", "co2_grams_estimate"]

# Project root is two levels above this file: .claude/hooks/log_usage.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT_ROOT / "Logs" / "log_summary.csv"


def is_user_prompt(rec):
    """True if a 'user' record is a real human prompt.

    Excludes tool results, sidechain (subagent) turns, and meta messages such
    as skill outputs and slash-command stdout (which arrive as user records
    with isMeta=True).
    """
    if rec.get("type") != "user":
        return False
    if rec.get("isMeta") or rec.get("isSidechain"):
        return False
    content = rec.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        types = [b.get("type") for b in content if isinstance(b, dict)]
        return "text" in types and "tool_result" not in types
    return False


def normalize_ts(ts):
    """Trim an ISO timestamp like 2026-07-03T12:31:11.217Z to whole seconds."""
    if not ts:
        return ""
    ts = ts.replace("Z", "")
    if "." in ts:
        ts = ts.split(".", 1)[0]
    return ts + "Z"


def main():
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    transcript_path = data.get("transcript_path")
    if not transcript_path or not Path(transcript_path).exists():
        return

    recs = []
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Index of the last real user prompt.
    last_user_idx = None
    for i, rec in enumerate(recs):
        if is_user_prompt(rec):
            last_user_idx = i
    if last_user_idx is None:
        return

    ut_time = normalize_ts(recs[last_user_idx].get("timestamp"))

    tokens = 0
    model = ""
    for rec in recs[last_user_idx + 1:]:
        if rec.get("type") != "assistant" or rec.get("isSidechain"):
            continue
        msg = rec.get("message", {})
        usage = msg.get("usage", {}) or {}
        tokens += (
            usage.get("input_tokens", 0)
            + usage.get("cache_creation_input_tokens", 0)
            + usage.get("output_tokens", 0)
        )
        if msg.get("model"):
            model = msg["model"]

    if tokens == 0 and not model:
        return  # nothing attributable to this turn

    co2 = round(tokens / 1000 * CO2_G_PER_1K_TOKENS, 2)

    # Avoid duplicate rows if Stop fires again for the same turn (clear/resume).
    if CSV_PATH.exists():
        try:
            last_line = ""
            with open(CSV_PATH, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        last_line = line
            if last_line.split(",", 1)[0] == ut_time:
                return
        except OSError:
            pass

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if write_header:
            writer.writerow(CSV_HEADER)
        writer.writerow([ut_time, tokens, model, co2])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never disrupt the session
    sys.exit(0)
