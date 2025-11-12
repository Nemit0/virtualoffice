# Simulation Time Model (Minute Ticks)

VDOS uses a minute-based tick model throughout the Simulation Engine.

- 1 tick = 1 minute of simulated time
- Day length = `hours_per_day * 60` ticks (default 8h → 480 ticks)
- Hour boundary = every 60 ticks
- Day boundary = every `hours_per_day * 60` ticks

Key behaviors:
- sim_time formatting: computed directly from minute ticks.
- Work windows: `work_hours` (e.g., `09:00-18:00`) map to minute offsets; planning triggers at the worker’s start minute.
- Hourly summaries: generated at `current_tick % 60 == 0`.
- Daily reports: generated at `current_tick % (hours_per_day*60) == 0`.
- Event cadence: event checks use minute ticks (e.g., 60 for ~1 hour into day, modulo 120 for every 2 hours).
- Scheduled comms: clock times in hourly plans (e.g., `Email at 10:30 ...`) execute on the corresponding minute tick.

Week math:
- current_day = `floor((current_tick-1) / (hours_per_day*60))`
- current_week = `floor(current_day/5) + 1`  (Mon–Fri work week)

Wall-clock pacing:
- The auto-tick interval and dashboard refresh control how quickly ticks are processed in real time. They don’t change the tick semantics.

