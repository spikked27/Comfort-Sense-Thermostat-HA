"""Preset configuration names, bidirectional Comfort updates and persistence."""
import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN="comfort_sense"


async def setup(hass):
    hass.config.units=US_CUSTOMARY_SYSTEM
    hass.states.async_set("switch.heat","off")
    hass.states.async_set("sensor.room","68",{"unit_of_measurement":"°F"})
    entry=MockConfigEntry(domain=DOMAIN,version=4,data={"name":"Test heat","heater":"switch.heat",
        "rooms":[{"id":"room","name":"Room","temperature_sensors":["sensor.room"],"occupancy_sensors":[]}]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry,hass.data[DOMAIN][entry.entry_id]


async def test_comfort_config_does_not_interrupt_away_and_tracks_dial_after_restart(hass):
    entry,runtime=await setup(hass)
    registry=er.async_get(hass)
    for preset in ("comfort","away","sleep","boost"):
        eid="number.test_heat_temperature_preset_"+preset
        entity=registry.async_get(eid)
        assert entity.entity_category==EntityCategory.CONFIG
        assert entity.original_name=="Temperature Preset "+preset.title()
    comfort="number.test_heat_temperature_preset_comfort"
    climate="climate.test_heat_thermostat"
    await runtime.change(mode="heat",preset="away")
    await hass.services.async_call("number","set_value",{"entity_id":comfort,"value":72},blocking=True)
    await hass.async_block_till_done()
    assert runtime.preset=="away"
    assert runtime.target_temperature==18
    assert runtime.comfort_temperature==pytest.approx((72-32)/1.8)
    assert float(hass.states.get(comfort).state)==pytest.approx(72)
    await hass.services.async_call("climate","set_preset_mode",{"entity_id":climate,"preset_mode":"comfort"},blocking=True)
    assert runtime.target_temperature==pytest.approx((72-32)/1.8)
    await hass.services.async_call("climate","set_temperature",{"entity_id":climate,"temperature":70},blocking=True)
    await hass.async_block_till_done()
    assert float(hass.states.get(comfort).state)==pytest.approx(70)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get(comfort).state)==pytest.approx(70)
    assert hass.data[DOMAIN][entry.entry_id].mode=="heat"


async def test_upgraded_preset_entity_ids_remain_stable(hass):
    registry=er.async_get(hass)
    # Seed an existing install's registry name and entity ID.
    entry=MockConfigEntry(domain=DOMAIN,version=4,data={"name":"Test heat","heater":"switch.heat",
        "rooms":[{"id":"room","name":"Room","temperature_sensors":["sensor.room"],"occupancy_sensors":[]}]})
    entry.add_to_hass(hass)
    previous=registry.async_get_or_create("number",DOMAIN,entry.entry_id+"_config_away_temperature",
        suggested_object_id="test_heat_away_temperature",config_entry=entry,original_name="Away temperature")
    hass.states.async_set("switch.heat","off")
    hass.states.async_set("sensor.room","20",{"unit_of_measurement":"°C"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(previous.entity_id).original_name=="Temperature Preset Away"
    assert hass.states.get(previous.entity_id) is not None
    assert registry.async_get("number.test_heat_temperature_preset_away") is None
