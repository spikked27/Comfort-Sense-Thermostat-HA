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
