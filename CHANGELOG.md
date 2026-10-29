# Changelog

## 0.7.1a1

- Keep the console navigation and save bar inside the viewport when HA's custom-panel container has no definite height.
- Correct the empty Sleep-room label to "Use thermostat source" in both editors; existing selection behavior is unchanged.
- Add a browser regression for the actual HA container layout. No household configuration is migrated or changed.

## 0.7.0a1

- Bundle a themed administrator console in HA's sidebar and integration configuration page.
- Add an overview of active rooms, effective target, heat demand, relay feedback and setup blockers.
- Edit rooms with searchable typed entity pickers and live sensor readings; automatic tuning stays the default.
- Configure native Schedule-helper bindings and phone alarms in a separate visual scheduling section.
- Show connected external Scheduler schedules and explain timed Boost behavior.
- Validate reviewed drafts atomically, reject stale edits and require confirmed relay availability before enabling active control.
- Preserve original branding, room IDs, compatible learning and manual-entity preferences.
- Expose outdoor temperature and the learned heat-loss feedforward status/coefficient in thermostat attributes.
- Add real HA console, authorization, unit-conversion and browser/mobile regression coverage.

## 0.6.1a1

- Defer saved PID compensation validation while startup entities are unavailable or stale.
- Preserve the original cache timestamp across additional restarts; total age remains capped at 15 minutes.
- Require all relevant cached room inputs and configured outdoor/Auto occupancy sources before comparing control context.
- Reject HA restored placeholders as confirmed relay or temperature feedback.
- Preserve immediate Off/protection/source-change resets and minimum-off furnace protection.

## 0.6.0a1

- Preserve maintenance PID compensation on target increases; shed positive bias after larger setbacks.
- Recover bounded integral compensation only through brief restarts with matching source, equipment, gains and fresh temperature context.
- Keep Off, protection cutoffs, stale data and changed room/group selection as reset boundaries.
- Add on-demand anonymized PID diagnostics and concise demand limiting/restart-memory status attributes.
- Add whole-runtime multi-day thermal simulations for occupancy groups, schedules, Away, weather and restart behavior.

## 0.5.3a1

- Persist Heat/Off selections immediately and restore them after restart or integration reload.
- Resume only user intent; discard old relay pulses and wait a fresh minimum-off interval after observed Off.
- Confirm a still-on relay is Off before resuming; unavailable sensors, warm-room limits and Shadow remain authoritative.
- New/legacy installations without a saved mode start Off; changing the relay or Shadow mode also requires re-enabling Heat.
- Document timing protections under Configure → Advanced → Relay timing and safety.

## 0.5.2a1

- Accept wake-up alarms only inside a configurable local-time window, default 03:00–12:00.
- Ignore Samsung Clock bedtime/Sleep mode events outside that window, including restored holds.
- Add an Advanced wake-up window editor without adding fields to ordinary morning setup.
- Explain ignored alarms in Control status and Ready by diagnostics.
- Preserve valid wake-up holds across the end of the allowed window; native schedules and early preheat remain independent.

## 0.5.1a1

- Add Temperature Preset Comfort to the device Configuration controls.
- Group all four preset temperature controls under the Temperature Preset name prefix.
- Synchronize Comfort with the thermostat dial and persist edits without interrupting active presets or schedules.
- Preserve existing Away/Sleep/Boost entity IDs on upgrade.

## 0.5.0a1

- Default new room and Average controllers to automatic validated PID tuning; preserve explicit existing choices.
- Hide manual PID number entities by default while retaining Advanced editing and service access.
- Replace separate room warm/cold controls with one overall Room protection buffer.
- Add earliest-home-phone alarm deadlines, owner associations, cancellation, persisted holds and one morning session per local day.
- Share native schedule preheating, safety, Away/Boost priority and learned models with morning alarms.
- Latch preheating through arrival and maintain targets until the hold/block ends.
- Add Ready by and Estimated heating start sensors and bounded learned arrival corrections.

## 0.4.0a1

- Auto groups similarly occupied rooms using configurable relative tolerance, default 30%.
- Control the equal-room group temperature with a dedicated PID and reset history on membership changes.
- Add per-room warm/cold buffers; warm cutoff overrides cold recovery when shared-zone goals conflict.
- Add live Configuration entities for reaction, grouping, buffers, tuning and preset temperatures.
- Persist entity settings without unloading the active thermostat or resetting occupancy timing.
- Convert Fahrenheit buffers as differences, not absolute temperatures.


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
