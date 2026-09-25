# À faire (demande du 26/09/2026)

Jules's request of 2026-09-26, only partly done:

**Done (coach/metrics/session.py)**
- Moving detection is now `max(speed, gap_speed) > 0.8 m/s`. The old rule, `speed > 1.2`, counted steep hikes and walked recoveries as stops.
  Example: the Sentein hike went from 56 to 202 min moving.
- New metrics:
  - `descent_m`, `climb_rate` (m/h of climb), `effort_pace` (grade-adjusted pace);
  - `splits` (per km: pace, effort_pace, up, down, grade, hr);
  - `grade_bins` (time share and speed by slope class).
- All sessions re-analyzed with `uv run coach analyze --force`.

**Still to do**
1. app/views/sessions.py:
   - trail/hike view (sport 102/104/204 or ≥15 m D+/km), with a grid showing D+, D-, moving vs total time, real pace, effort pace, km-effort (km + D+/100), climb rate;
   - combined chart: altitude area plus pace and effort pace (or speed for hikes);
   - km splits table, and pace/speed by slope chart;
   - the view still uses `speed > 1.2` at lines 123 and 173: align it with the new rule.
2. Audit incoherent KPIs across pages. Hike speed was absurd (16 km/h) because of the moving bug; look for others.
3. Library: walk and jog recovery are treated the same. `workouts.summary()` ignores `walk` (always 415 s/km), and the card doesn't show the recovery. Use about 720 s/km when walked, and display the recovery.
4. Sleep, "répartition moche" (app/views/recovery.py):
   - per night: replace the 4 phase metrics and the stacked bar with a bullet chart (value vs reference band);
   - stats: replace the 5-colour stacked bars with duration bars (night + naps, 7-day mean) and a separate chart of phase %.
5. Run pytest and AppTest on all pages, update the Aide tab and the README, commit and push to `claude/strava-auto-coach-sjx418`.

