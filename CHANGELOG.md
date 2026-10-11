# Changelog

## 0.3.0a1

- One thermostat setpoint follows the winning room in Auto; remove obsolete room targets.
- Fast/Medium/Slow reaction uses 10/30/60-minute moving occupancy windows.
- Add Active room and per-room occupancy sensors for dashboard status/history.
- Reduce basic setup to six fields and room setup to four; move optional settings to Advanced.
- Show manual gains only when selected; simplify schedule connections.
- Expose heat-demand cycle length and nominal on-time for clearer diagnostics.
- Migrate existing entries and the saved main setpoint while preserving room IDs and learning.

## 0.2.0a1

- Show Comfort Sense in Integrations instead of classifying it as a Helper.
- Use HA's Celsius/Fahrenheit preference for setup targets and room number controls.
- Replace room-level morning fields with separate native Schedule-helper bindings.
- Read future weekly blocks for preheat, with per-block source/target overrides and priority.
- Migrate existing entries and enabled morning plans without changing room IDs or stored targets.
- Preserve learning observations across restart before a thermal model has been accepted.
- Add migration, Fahrenheit read/write, weekly schedule and HA integration-list tests.

## 0.1.0a1

Added a generated logo, bundled HA brand icons, a direct HACS installation button,
and user-facing installation and usage guides. Release packaging includes icons.

Initial experimental integration: configurable rooms and sensors, gradual occupancy
priority, per-room manual/automatic PID, independent Average PID and model, Away
and timed Boost, weekday room warm-up deadlines, passive slow-system identification,
relay guards, shadow observations, diagnostic entities, setup/options flow and tests.

39 core/runtime tests and six real HA integration tests pass in Linux CI.
Field commissioning and comfort-performance validation remain pending.
