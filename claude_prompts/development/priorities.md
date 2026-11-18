## Night planning and priorities
We have made an artifact explaining the night-planner decision for each target.
Find it, add a tab of how the decisions are done in /home/lordrick/Projects/misc_repos/AstroScheduler
And them make another tab comparing the two styles

## Logs
- 2026-11-14: Added the AstroScheduler and Side by side tabs to the Night Planner Decision Map (https://claude.ai/artifact/6ZnFg47ofPrqvFEWtawbSJ). Toy comparison in scripts/compare_scheduler_styles_toy.py, checked against the real solver by scripts/astroscheduler_toy_check.py. See Logs/2026/11/2026-11-14.md.
- 2026-11-15: Implemented the four AstroScheduler recommendations on the Lick/Kast path (retime/insert/partials, --previous-plan, schedule_before, site_limits.json + --limit) and remade Lick-2026B-04 as pvt_Nighplans/Lick-2026B-04_v2. See Logs/2026/11/2026-11-15.md.
- 2026-11-16: GUI controls for placement / pointing limits / previous plan, re-solves anchored on their own plan; Handbook and Decision Map artifacts updated. See Logs/2026/11/2026-11-16.md.
