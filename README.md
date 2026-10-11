# Comfort Sense Thermostat

Room-aware adaptive heating for Home Assistant. **0.1.0a1 — experimental alpha.**

One integration replaces a switching temperature template, an occupancy history
sensor chain, and a separate PID thermostat. It controls one heating relay for a
shared heating zone. Configure everything from **Settings → Devices & services**.

- Add rooms and choose one or more temperature and binary occupancy sensors in each.
- Occupancy builds over minutes and decays gradually. Room demand changes smoothly.
- Each room has its own PID controller, with independently selectable **Manual** or
  **Automatic validated tuning**. Manual Kp/Ki/Kd remain editable in either mode;
  they provide fallback settings while automatic mode collects adequate data.
- **Average has its own PID controller and thermal model**, with independent gains
  and tuning mode. It controls the equal-room average in Away, Boost, manual Average,
  and Auto when no room has meaningful occupancy. It does not average PID outputs.
- Away can follow a person, tracker, binary home sensor, or home-zone person count,
  after a configurable delay. Unknown presence never means confirmed absence.
- Boost raises the target for a bounded duration. Morning schedules specify room,
  weekdays, target temperature, arrival time, and how long to maintain comfort.
- Passive models learn heating response, outdoor heat loss, and delivery delay from
  normal operation. No oscillating relay autotune experiment is required.
- Anti-windup, filtered derivative on each measured temperature, coast prediction,
  minimum on/off times, and low-demand pulse accumulation limit avoidable overshoot.
- Diagnostics show actual versus proposed relay state, room weights, excluded
  sensors, applied/recommended gains, model quality, and deadline feasibility.

## Installation

Repository: [Comfort Sense Thermostat](https://github.com/spikked27/Comfort-Sense-Thermostat-HA). Install from the alpha source or a tagged release:

1. Add its URL in HACS → Custom repositories → Integration, install, and restart HA.
   Alternatively copy `custom_components/comfort_sense` into `/config/custom_components`.
2. Add **Comfort Sense Thermostat** in Devices & services. Choose your heating switch. Leave
   **Shadow mode** enabled while evaluating behavior alongside the existing controller.
3. Choose an outdoor temperature sensor to enable passive thermal identification.
   Outdoor measurements are optional for manual PID operation.
4. Add rooms and their sensors. Set comfort and morning temperatures, schedule days,
   and PID mode/gains separately for each room. Average gains are in system settings.
5. Review the entry. The thermostat initially starts Off. Select Heat to compute
   demands in shadow mode; shadow mode never calls the heater switch.
6. After reviewing diagnostics, disable the existing relay controller and its
   controlling automations. Turn shadow mode off in Comfort Sense Thermostat options, then select
   Heat again. Options reloads and HA restarts start Off in this alpha.

Use Home Assistant **2026.10 or newer**. Standalone algorithm tests use Python 3.12+;
Home Assistant's own Python version requirements also apply to live installation.

## Daily controls

The climate entity offers Heat/Off and Comfort/Away/Sleep/Boost presets. The main
temperature dial sets all room comfort targets and returns to Comfort. Individual
room number entities adjust a room's comfort target. The source select offers Auto,
Average, and each room. Sleep can pin a room, selected in system options.

Setup and number fields use **Celsius**, explicitly labelled. Climate and temperature
sensor display conversion follows HA settings. Fahrenheit and Kelvin input sensors
are converted to Celsius before control; missing unit metadata is rejected.

Morning schedules run in HA's local timezone. Sleep allows morning warm-up; Away
suppresses it, and manual Boost temporarily overrides schedules. Scheduled rooms
have priority over occupancy until their morning hold expires. Unreachable targets
are reported and lead time is capped; the schedule cannot guarantee an exact arrival
temperature under changing weather, insufficient heat output, or conflicting rooms.

With one shared relay, all rooms receive heat together. This integration cannot
independently control incompatible room targets without additional zone hardware.

## Tuning and learning

Manual mode honors that controller's user-supplied gains. Automatic mode collects
normal heater observations and only adopts a model after training and held-out
prediction gates pass. Models also support warm-up scheduling in Manual mode.

Normalized duty is 0–1 and the internal temperature unit is Celsius:

| Setting | Units |
|---|---|
| Kp | duty / °C |
| Ki | duty / (°C · second) |
| Kd | duty · second / °C |

The shipped manual defaults are conservative starting points, **not a universal
tune**. All gains are selectable. Automatically identified first-order models use
conservative SIMC-style PI recommendations; their derivative gain is zero. Manual
mode supports a nonzero Kd and filters measurement derivatives over ten minutes.

Never directly copy Smart Thermostat's percentage-based Fahrenheit gains. When its
output is 0–100 and its input is Fahrenheit, multiply Kp, Ki and Kd by **0.018** to
express equivalent normalized Celsius gains. This converts units; it does not make
the original tune suitable for this controller.

See [control design](docs/CONTROL.md), [migration](docs/MIGRATION.md),
[testing and release](docs/TESTING.md), and [contributing](CONTRIBUTING.md).

## Current verification status

The local deterministic and mocked-boundary suite passes. Real Home Assistant
integration tests are supplied for Linux CI and have **not yet run in this Windows
workspace**. No live heating control was deployed or changed during development.
Field performance, noise tolerance, and release compatibility remain to be verified.

Household archives, credentials, and private audit reports are outside this project.
The integration keeps a bounded local learning buffer in HA `.storage`; treat it
as private household data. MIT licensed, with original control implementation.
