"""ComfortSense occupancy-aware thermostat integration."""
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import entity_registry as er
from .const import DOMAIN, PLATFORMS
from .runtime import Runtime
from .scheduling import migrate_config
from .settings import validate


async def async_setup(hass,config):
    from .panel import async_setup_panel
    await async_setup_panel(hass)
    return True


async def async_migrate_entry(hass,entry):
    if entry.version>4:
        return False
    if entry.version==1:
        data=migrate_config({**entry.data,**entry.options})
        hass.config_entries.async_update_entry(entry,data=data,options={},version=2)
    if entry.version==2:
        data={**entry.data,**entry.options}
        data.setdefault("comfort_temperature",next((r.get("target",21) for r in data.get("rooms",[])),21))
        data.setdefault("reaction_time","medium")
        hass.config_entries.async_update_entry(entry,data=data,options={},version=3)
    if entry.version==3:
        data=migrate_config({**entry.data,**entry.options})
        registry=er.async_get(hass)
        for entity in er.async_entries_for_config_entry(registry,entry.entry_id):
            if entity.domain=="number" and entity.platform==DOMAIN and entity.unique_id.endswith(("_kp","_ki","_kd")) and entity.hidden_by is None:
                registry.async_update_entity(entity.entity_id,hidden_by=er.RegistryEntryHider.INTEGRATION)
        # Existing explicit manual choices and gains remain intact.
        hass.config_entries.async_update_entry(entry,data=data,options={},version=4)
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
    runtime=hass.data.get(DOMAIN,{}).get(entry.entry_id)
    if runtime and runtime.config==validate({**entry.data,**entry.options}):
        return  # configuration entities already applied these settings in place
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await hass.data[DOMAIN].pop(entry.entry_id).stop()
        return True
    return False
