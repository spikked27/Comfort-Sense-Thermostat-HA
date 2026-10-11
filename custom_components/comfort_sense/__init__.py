"""ComfortSense occupancy-aware thermostat integration."""
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from .const import DOMAIN, PLATFORMS
from .runtime import Runtime
from .scheduling import migrate_config


async def async_migrate_entry(hass,entry):
    if entry.version>2:
        return False
    if entry.version==1:
        data=migrate_config({**entry.data,**entry.options})
        hass.config_entries.async_update_entry(entry,data=data,options={},version=2)
    return True


async def async_setup_entry(hass, entry):
    runtime = Runtime(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    await runtime.start()
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP,
        lambda event: hass.async_create_task(runtime.stop())))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(reload_entry))
    return True


async def reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await hass.data[DOMAIN].pop(entry.entry_id).stop()
        return True
    return False
