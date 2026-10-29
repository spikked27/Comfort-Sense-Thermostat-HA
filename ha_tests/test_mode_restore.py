"""Persist user HVAC intent across HA storage and real integration reloads."""
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN="comfort_sense"


async def setup(hass):
    hass.states.async_set("switch.heat","off")
    hass.states.async_set("sensor.room","20",{"unit_of_measurement":"°C"})
    entry=MockConfigEntry(domain=DOMAIN,version=4,data={"name":"Test heat","heater":"switch.heat",
        "rooms":[{"id":"room","name":"Room","temperature_sensors":["sensor.room"],"occupancy_sensors":[]}]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry,hass.data[DOMAIN][entry.entry_id]


async def test_reload_restores_heat_and_preset_without_restoring_relay_pulse(hass):
    entry,runtime=await setup(hass)
    assert runtime.mode=="off"
    await runtime.change(mode="heat",preset="sleep",source="room")
    saved=await Store(hass,1,f"{DOMAIN}.{entry.entry_id}").async_load()
    assert saved["mode"]=="heat"
    assert saved["control_signature"]==["switch.heat",True]
    runtime.relay.pulse_end=10**12
    runtime.relay.credit=1000
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    restored=hass.data[DOMAIN][entry.entry_id]
    assert restored.mode=="heat"
    assert restored.preset=="sleep"
    assert restored.source=="room"
    assert not restored.proposed
    assert restored.relay.pulse_end!=10**12
    assert hass.states.get("climate.test_heat_thermostat").state=="heat"


async def test_explicit_off_is_saved_immediately_and_survives_reload(hass):
    entry,runtime=await setup(hass)
    await runtime.change(mode="heat")
    await runtime.change(mode="off")
    saved=await Store(hass,1,f"{DOMAIN}.{entry.entry_id}").async_load()
    assert saved["mode"]=="off"
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].mode=="off"
    assert hass.states.get("climate.test_heat_thermostat").state=="off"
