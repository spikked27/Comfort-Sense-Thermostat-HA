"""Shared entities update from runtime notifications."""
from homeassistant.helpers.entity import Entity
from .const import DOMAIN


class ComfortSenseEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, runtime, key, name):
        self.runtime = runtime
        self._attr_unique_id = f"{runtime.entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = {"identifiers": {(DOMAIN, runtime.entry.entry_id)},
                                  "name": runtime.config["name"], "manufacturer": "ComfortSense",
                                  "model": "Occupancy-aware PID thermostat"}

    async def async_added_to_hass(self):
        self.async_on_remove(self.runtime.subscribe(self.async_write_ha_state))
