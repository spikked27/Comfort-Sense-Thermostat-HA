# Moving from Smart Thermostat and room templates

Keep the existing installation operating while Comfort Sense Thermostat observes it in Shadow
mode. Choose physical room sensors and occupancy sensors directly, plus outdoor
temperature and an explicit home-presence source. Do not feed Comfort Sense Thermostat a
time-averaged sensor that switches between rooms.

Review each room's valid temperatures, excluded sensors, occupancy score, gains,
model recommendation, proposed demand, and morning-plan reachability. Check the
dedicated Average sensor and its separate tuning settings. Selecting Heat in Shadow
mode enables demand computation but does not command the relay.

Before switching controllers, disable the old Smart Thermostat platform and any
automation, script, or scheduler action that writes its settings or the heating
relay. Search for the old climate entity and relay in YAML, scripts, helpers and
UI automations. Preserve an export of those definitions to support rollback.

Create native Schedule helpers and connect them under the integration's separate
Scheduling section. Block starts are desired arrival times when preheat is enabled. Replace old
`climate.set_preset_mode` and temperature actions with the new climate entity.
Comfort Sense Thermostat has Comfort/Away/Sleep/Boost; map other legacy presets explicitly.
Historical occupancy helpers and room-switching/filter templates can be removed
once no remaining automations reference them.

Upgrades from Comfort Sense 0.1 preserve the existing entry and entity IDs. Old
enabled room morning settings become separate legacy schedule bindings; connect
native helpers to edit their times in HA's weekly grid. Existing stored Celsius
targets are preserved while forms and number controls use your HA unit preference.

After removing competing control, turn Shadow off in Comfort Sense Thermostat options and select
Heat. The first relay turn-on respects a full minimum-off period after startup.
The alpha starts Off on restart/reload; make enabling Heat an explicit commissioning
step. Never leave two active controllers writing the same relay.

For rollback, switch Comfort Sense Thermostat Off, restore Shadow mode or unload it, restore the
old controller, and re-enable its automations. Unloading active Comfort Sense Thermostat requests
relay Off; unloading Shadow mode sends no relay command.

The spring temperature archive is useful for planning fallback warm-up rates. It
cannot identify heater gain, causal delivery delay, or reliable PID gains without
actuator labels and outdoor data. Apartment history must remain a separate physical
environment; do not transfer its learned coefficients to a different home.

## Updating to 0.3

The existing entry migrates automatically. The saved thermostat target becomes one shared comfort setpoint (for older divergent room overrides, the first configured room supplies it). Room target number entities are removed. Room IDs, learning, tuning choices, schedule connections and Shadow mode are preserved. Medium reaction replaces the previous exponential weighting with a 30-minute moving occupancy window. Select Heat after restart.

## Updating to 0.5

Update through HACS and restart HA when convenient, then select Heat to resume.
New room and Average controllers default to Automatic PID; existing explicit
Manual selections and gains are preserved. Manual gain entities become hidden
once during migration; you can reveal them later without a reload hiding them again.

Review **Configuration → Room protection buffer**. The smallest enabled former
room warm/cold buffer becomes one symmetric limit for all rooms. If all previous
buffers were zero, relative protection stays disabled. Old per-room buffer entities
are removed; replace any dashboard or automation references with the overall buffer.

Native schedules keep working. To use alarms, open **Configure → Scheduling →
Morning comfort from phone alarms**. Enable it, select the phones' next-alarm
sensors and choose the target, room source and hold duration. Optionally associate
each phone with a person under Scheduling. No alarm sensors or persons are selected
automatically during upgrade. See [scheduling](SCHEDULING.md).
