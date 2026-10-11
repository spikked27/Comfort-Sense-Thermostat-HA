# Using Comfort Sense Thermostat

[← Overview](../README.md) · [Installation](GETTING_STARTED.md)

## Choose which rooms matter

| Temperature source | Behavior |
|---|---|
| **Auto** | Occupancy builds and fades gradually. The most-used rooms receive more priority. Little meaningful occupancy falls back to Average. |
| **Average** | Controls the equal-room mean through Average's own PID. A room with three sensors has the same weight as a room with one. |
| **A room name** | Pins that room. Losing all its valid temperature readings suppresses heating instead of silently choosing another room. |

Each room uses the median of its valid sensors. Stale or unavailable readings are
excluded. All rooms still receive heat together because there is one shared relay.

## Temperature and presets

The main dial updates every room's **comfort target** and returns to Comfort. Use
individual room target entities to change only one room. Setup and number fields
follow HA's Celsius or Fahrenheit preference, as does the climate card.

| Preset | What happens |
|---|---|
| **Comfort** | Room comfort targets and your selected source. |
| **Away** | The Away target and dedicated Average PID. Automatic Away follows confirmed absence after its delay. |
| **Sleep** | The Sleep target, optionally pinned to a sleeping room selected in system options. |
| **Boost** | The Boost target and Average PID for a bounded time, then a return to Comfort. |

Unknown home presence does not mean Away. Confirmed automatic Away takes priority
over Boost and morning schedules. Changing presets does not turn an Off thermostat
on; select Heat when required.

## Weekly schedules and morning comfort

Create a native **Schedule helper** in HA and draw weekly blocks in its time-grid
editor. Connect it through **Comfort Sense → Configure → Scheduling**, choosing a
room, Auto or Average, a scheduled target, and whether to warm up before the block.
Room and equipment configuration contain no scheduling fields.

Comfort Sense estimates how early to warm that room. A validated model uses heating
response, outdoor heat loss and delivery delay. Before learning is ready, it uses
your fallback warm-up rate. **Maximum morning preheat** bounds the lead time.

Morning rooms have priority while their plans are active. Sleep permits morning
warm-up; Away suppresses it. Manual Boost temporarily overrides the plan. Several
morning rooms use the largest scheduled demand, within relay and temperature limits.

The room's `schedule` diagnostic reports `lead_seconds`, `deadline`, `reachable` and
whether the estimate is `learned` or `fallback`. False reachability means the model
or allowed lead cannot support the requested arrival. True is still an estimate,
not a guarantee of hitting the target under every weather condition.

## Manual or automatic tuning

Choose independently in each room's settings. Average's gains and mode are in
**Equipment and Average PID**.

| Mode | Behavior |
|---|---|
| **Manual** | Your Kp/Ki/Kd values control that room or Average. Learning can improve morning planning, but does not replace your gains. |
| **Automatic validated tuning** | Uses the manual fallback until a model passes quality checks, then applies conservative learned PI gains. Automatic Kd is zero. |

Learning observes ordinary heating without deliberately forcing relay oscillations.
Poor fits are rejected. Diagnostics show mode, current and recommended gains,
model quality, and whether tuning is applied.

Average uses its learned tune only with complete valid-room membership. Missing
rooms temporarily use its manual fallback. A membership change clears derivative
history so a changed average is not mistaken for sudden cooling or warming.

Manual gains use normalized heating demand and Celsius. Read [gain units](CONTROL.md)
before copying another integration's values or making large adjustments.

## Read the status

| Status | Meaning |
|---|---|
| **Off** | Climate mode is Off. |
| **Room control** | Normal room or Average control. |
| **Away average** | Away uses its target and dedicated Average PID. |
| **Schedule preheat / Scheduled comfort** | A connected weekly schedule is warming up or holding a scheduled target. |
| **No valid temperatures** | All configured readings are missing or invalid. |
| **Selected room has no valid temperature** | The pinned room lost its input. |
| **Safety temperature limit** | A valid room sensor reached the configured maximum. |
| **Heater unavailable / Heater command failed** | Inspect relay connectivity and HA logs. |

Heat demand is a requested percentage, not measured furnace power. Slow relay
periods deliver that demand; small requests accumulate into useful pulses.
Shadow proposals can differ from the relay controlled by the old thermostat and
do not prove how the house will respond after switching controllers.

## Common questions

**Will it eliminate overshoot?** PID guards and coast prediction limit avoidable
overshoot. Sun, stored heat, weather and imperfect models can still warm a room
after the relay switches off.

**Can two rooms reach different targets independently?** Shared heating warms them
together. Targets guide priority; independent zones need their own hardware.

**Does it need internet?** Control and learning are local. HACS uses GitHub for
installation and updates.

**Why did a restart stop heating?** This alpha starts Off after restarts and options
reloads. Select Heat to resume.

**Where is learning data?** A bounded buffer is kept in HA `.storage`. It can reveal
household heating patterns; do not attach it to a public issue.

[Native weekly scheduling, block overrides and priority →](SCHEDULING.md)
