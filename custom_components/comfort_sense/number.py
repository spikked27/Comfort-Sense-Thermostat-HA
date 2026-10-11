"""Remove obsolete room targets: the thermostat owns one setpoint."""
from homeassistant.helpers import entity_registry as er


async def async_setup_entry(hass, entry, async_add_entities):
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain == "number" and entity.platform == "comfort_sense" and entity.unique_id.endswith("_target"):
            registry.async_remove(entity.entity_id)
