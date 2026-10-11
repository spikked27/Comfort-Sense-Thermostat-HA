# Occupancy groups and room protection

Open the Comfort Sense **device page → Configuration** to adjust these settings.
Entity changes are saved immediately and take effect without unloading the
thermostat. The setup flow is still available for equipment, room sensors and
weekly schedule connections.

## Occupancy grouping

**Occupancy grouping tolerance** defaults to 30%. Auto finds the leading valid
room and includes other rooms within this relative difference:

`difference = 2 × (leader score − room score) / (leader score + room score)`

This is a relative difference, not percentage points. Scores of 60% and 50%
differ by about 18%, so they qualify together at a 30% tolerance. Scores of 60%
and 40% differ by 40%, so only the leading room qualifies. Every qualifying room
has equal weight. Zero tolerance selects one winner; ties retain the previous
winner. Little meaningful occupancy falls back to the whole-home Average.

Previously included rooms get a two-percentage-point exit allowance to avoid
rapid membership changes at the boundary. **Active room** lists every included
room, and the thermostat's current temperature is their mean. The setpoint stays
the same. Reaction time sets the moving occupancy window to 10, 30 or 60 minutes.

A group has one PID acting on its mean temperature, rather than an average of
clipped room demands. It uses conservative selected-room gains: the lowest P/I
and largest D. Room automatic/manual tuning remains independent. The group clears
its integral and derivative history when membership changes. Group preheat uses
the slowest selected room's learned arrival estimate when every model is ready;
otherwise it uses the fallback rate.

## Warm and cold buffers

Every room has separate **Warm buffer** and **Cold buffer** Configuration entities.
Both default to 2°C / 3.6°F, relative to the thermostat's active target, including
Away, Boost and scheduled targets. These settings apply to all configured rooms,
including rooms outside the occupancy group.

For a 70°F target and 4°F buffers:

| Condition | Action |
|---|---|
| Any room reaches 74°F | Pause heating and discard pending relay pulses. |
| Any room falls below 66°F | Its protective PID can raise the heat request. |
| A warm room and cold room conflict | The warm limit takes priority. |

Small hysteresis (up to 0.2°C / 0.36°F) prevents chatter. Cold recovery aims just
above the lower boundary, not at the full comfort setpoint. Set an individual
buffer to **0** to disable that side of protection for that room. The absolute
maximum temperature safeguard remains independent. Off stays Off; protection
does not activate an Off thermostat or send commands in Shadow mode.

Fahrenheit buffers are **temperature differences**: 4°F equals about 2.22°C.
There is no 32-degree offset. Preset target entities are absolute temperatures
and use normal HA conversion.

The heating zone shares one relay. It cannot cool a warm room while heating a
cold one, and stored heat can continue warming rooms after a cutoff. These are
control limits rather than a guarantee of exact room temperatures.

Control status reports **Warm room protection** or **Cold room protection** when
they govern output. `room_protection` attributes expose room names, boundaries,
availability and protective demand; diagnostic temperatures are internally °C.

## Other Configuration entities

Reaction time, room/Average tuning choices, manual PID gains, Away/Sleep/Boost
temperatures and occupancy grouping tolerance are categorized as Configuration.
Manual gains remain stored as fallbacks in Automatic mode; editing them does not
replace a validated automatic tune. Switching to Manual applies those gains.

Ordinary controls—thermostat temperature, Heat/Off, preset selection and temperature
source—remain in Controls. Readings and status remain sensors.
