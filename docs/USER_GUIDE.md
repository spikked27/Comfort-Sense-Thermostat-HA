# Using Comfort Sense Thermostat

[← Overview](../README.md) · [Installation](GETTING_STARTED.md)

## Choose which rooms matter

| Temperature source | Behavior |
|---|---|
| **Auto** | Equally averages rooms within the grouping tolerance of the occupancy leader. Zero tolerance follows one winner. Little meaningful occupancy falls back to Average. |
| **Average** | Controls the equal-room mean through Average's own PID. A room with three sensors has the same weight as a room with one. |
| **A room name** | Pins that room. Losing all its valid temperature readings suppresses heating instead of silently choosing another room. |

Each room uses the median of its valid sensors. Stale or unavailable readings are
excluded. All rooms still receive heat together because there is one shared relay.

## Temperature and presets

The main dial sets **one comfort target** and returns to Comfort. It stays the same as Auto changes rooms or you select a room or Average. The **Active room** sensor shows the actual room being followed, even when the selector says Auto. Temperature fields follow HA's Celsius/Fahrenheit preference.

Choose reaction on the thermostat **device page → Configuration → Occupancy reaction time** (also available in the options flow):

| Reaction | Occupancy window | Typical sustained room-change buffer |
|---|---|---|
| Fast | 10 minutes | About 5 minutes |
| Medium (default) | 30 minutes | About 15 minutes |
| Slow | 60 minutes | About 30 minutes |

These are moving averages, not fixed timers. Intermittent motion changes the crossover time. Room occupancy sensors expose the percentage of each window occupied. No history is restored after restart; the window builds from fresh observations.

| Preset | What happens |
|---|---|
| **Comfort** | The thermostat setpoint and your selected source. |
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
**Configure → Advanced → Average PID tuning**.

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

**Heat demand is 0–100% requested furnace on-time**, not measured furnace power. At a 20-minute PWM cycle, 25% requests about 5 minutes On and 15 minutes Off; 50% requests about 10 minutes On. Minimum On/Off times and safety checks can alter the timing. Small requests accumulate over several cycles into a minimum-length pulse. The entity exposes `cycle_minutes` and `nominal_on_minutes`, plus proposed/observed relay state. Nominal time is not a countdown or a guaranteed pulse length.
Shadow proposals can differ from the relay controlled by the old thermostat and
do not prove how the house will respond after switching controllers.

## Common questions

**Will it eliminate overshoot?** PID guards and coast prediction limit avoidable
overshoot. Sun, stored heat, weather and imperfect models can still warm a room
after the relay switches off.

**Can two rooms reach different targets independently?** Shared heating warms them
together. Ordinary control uses one setpoint; schedules can temporarily prioritize a room. Independent zones need their own hardware.

**Does it need internet?** Control and learning are local. HACS uses GitHub for
installation and updates.

**Why did a restart stop heating?** Versions through 0.5.2 deliberately started Off. Version 0.5.3 saves Heat/Off immediately and restores it after restart or reload. Older versions did not save this choice, so select Heat once after the first upgrade. New installs, invalid saved modes, and changes to the heating relay or Shadow mode start Off. No old output pulse is restored: the controller confirms the relay is Off and waits its full minimum-off time before heating. Missing inputs and room protections still prevent output.

**Where is learning data?** A bounded buffer is kept in HA `.storage`. It can reveal
household heating patterns; do not attach it to a public issue.

[Native weekly scheduling, block overrides and priority →](SCHEDULING.md)

## Occupancy groups and room protection

On the device page, open **Configuration** to change grouping tolerance, reaction time, the overall Room protection buffer, tuning choices, optional manual gains and preset temperatures. Changes persist immediately without restarting the controller. [Behavior and buffer examples](ROOM_PROTECTION.md).

Automatic PID tuning is the default. Manual gain entities are hidden by default; the Advanced/room Manual forms remain available. See [phone-alarm morning comfort](SCHEDULING.md#phone-alarm-morning-comfort) for ready-by heating.

Preset temperatures are grouped under **Temperature Preset Away**, **Temperature Preset Boost**, **Temperature Preset Comfort** and **Temperature Preset Sleep** on the device Configuration page. Comfort edits the saved normal thermostat target; it stays synchronized with the dial. Editing Comfort during Away, Sleep, Boost or a schedule does not interrupt that active mode or plan. Existing preset entity IDs stay unchanged on upgrade.

## Furnace timing protections

Open **Settings → Devices & services → Comfort Sense → Configure → Advanced → Relay timing and safety**. **Minimum relay on time** and **Minimum relay off time** default to **300 seconds (5 minutes)**; **Slow PWM period** defaults to **1200 seconds (20 minutes)**. Small heat requests accumulate into minimum-length pulses. Off, warm-room protection and absolute safety limits can terminate a run early.

The separate **Room protection buffer** is on the thermostat **device page → Configuration**; it sets the warm/cold temperature boundaries for all rooms. Timing settings remain in Advanced to keep the ordinary Configuration list short.

## Understanding PID demand

Raising the target now keeps the same room/controller's maintenance compensation. A larger setback clears positive accumulated bias. Brief restarts can restore bounded compensation only if fresh readings and the selected room/group, target, equipment and gains still match; Off and safety/protection resets win. See [control details](CONTROL.md#setpoint-memory-and-short-restarts).

Use **Download diagnostics** on the integration menu for P/I/D/outdoor contribution details. **Heat demand** attributes show the current limiting condition and restart-memory result without adding more everyday controls.
