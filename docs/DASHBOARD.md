# Thermostat dashboard

[Overview](../README.md) · [User guide](USER_GUIDE.md)

The thermostat has one target. The source selector chooses Auto, Average or a room;
**Active room** shows what Auto actually follows. Include both on your dashboard.
Room occupancy sensors report the percentage of the moving window occupied, so a
history graph explains why a room won. Medium uses 30 minutes of history.

This example uses built-in Home Assistant cards. Replace the example entity IDs
with those listed on your Comfort Sense device; names include your thermostat's
configured name. Add temperature and occupancy entities for every configured room.

```yaml
type: vertical-stack
cards:
  - type: thermostat
    entity: climate.comfortsense_thermostat
    name: Comfort Sense
  - type: entities
    title: Room and heating status
    show_header_toggle: false
    entities:
      - entity: select.comfortsense_temperature_source
        name: Follow
      - entity: sensor.comfortsense_active_room
        name: Currently following
      - entity: sensor.comfortsense_heat_demand
        name: Requested furnace on-time (%)
      - entity: sensor.comfortsense_control_status
        name: Control status
  - type: history-graph
    title: Thermostat temperature and target
    hours_to_show: 12
    entities:
      - climate.comfortsense_thermostat
  - type: history-graph
    title: Room temperatures
    hours_to_show: 12
    entities:
      - entity: sensor.comfortsense_living_room_temperature
        name: Living Room
      - entity: sensor.comfortsense_bedroom_temperature
        name: Bedroom
      - entity: sensor.comfortsense_average_temperature
        name: Average
  - type: history-graph
    title: Recent occupancy (%)
    hours_to_show: 12
    entities:
      - entity: sensor.comfortsense_living_room_occupancy
        name: Living Room
      - entity: sensor.comfortsense_bedroom_occupancy
        name: Bedroom
  - type: history-graph
    title: Active room history
    hours_to_show: 12
    entities:
      - sensor.comfortsense_active_room
```

Heat demand is requested on-time over the PWM cycle. With a 20-minute cycle, 25%
means about five minutes On. Its `nominal_on_minutes` attribute describes the
request; minimum run/off times and safety checks can change actual timing. Shadow
mode calculates proposals without operating the furnace. Use the physical relay's
history or an HA History Stats helper to show **actual** heating time.

Temperature values embedded in the climate's `rooms` diagnostic are internally
Celsius. Use the room temperature entities or the climate's displayed
`current_temperature` for dashboards; HA converts those to your preferred unit.

Older room-target number entities are removed in 0.3. Replace their cards with the
thermostat dial and Active room sensor.
