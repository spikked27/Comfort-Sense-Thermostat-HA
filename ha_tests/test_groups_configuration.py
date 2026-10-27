"""Real HA checks for occupancy groups and live device Configuration controls."""
import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from homeassistant.util import dt as dt_util
from custom_components.comfort_sense.learning import ThermalModel
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN="comfort_sense"


async def setup(hass):
    hass.config.units=US_CUSTOMARY_SYSTEM
    hass.states.async_set("switch.heat","off")
    rooms=[]
    for rid,name,value in [("living","Living Room",68),("bed","Bedroom",72)]:
        hass.states.async_set("sensor."+rid,str(value),{"unit_of_measurement":"°F"})
        hass.states.async_set("binary_sensor."+rid,"on")
        rooms.append({"id":rid,"name":name,"temperature_sensors":["sensor."+rid],
            "occupancy_sensors":["binary_sensor."+rid],"tuning_mode":"manual","kp":0.2,"ki":0.000035,"kd":0})
    entry=MockConfigEntry(domain=DOMAIN,version=3,data={"name":"Test heat","heater":"switch.heat", "shadow":True,
        "rooms":rooms,"comfort_temperature":(70-32)/1.8})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry,hass.data[DOMAIN][entry.entry_id]


async def test_configuration_entities_live_persistence_units_and_no_unload(hass):
    entry,runtime=await setup(hass)
    await runtime.change(mode="heat")
    registry=er.async_get(hass)
    entities=er.async_entries_for_config_entry(registry,entry.entry_id)
    settings=[e for e in entities if "_config_" in e.unique_id]
    assert len(settings)==18
    assert all(e.entity_category==EntityCategory.CONFIG for e in settings)
    assert registry.async_get("select.test_heat_temperature_source").entity_category is None
    eid="number.test_heat_room_protection_buffer"
    assert hass.states.get(eid).attributes["unit_of_measurement"]=="°F"
    assert float(hass.states.get(eid).state)==pytest.approx(3.6)
    await hass.services.async_call("number","set_value",{"entity_id":eid,"value":4},blocking=True)
    await hass.services.async_call("number","set_value",{"entity_id":"number.test_heat_occupancy_grouping_tolerance","value":25},blocking=True)
    await hass.services.async_call("select","select_option",{"entity_id":"select.test_heat_occupancy_reaction_time","option":"Slow"},blocking=True)
    await hass.services.async_call("number","set_value",{"entity_id":"number.test_heat_away_temperature","value":65},blocking=True)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id] is runtime
    assert runtime.mode=="heat"
    assert runtime.config["room_buffer"]==pytest.approx(4/1.8)
    assert runtime.config["away_temperature"]==pytest.approx((65-32)/1.8)
    assert entry.options["occupancy_margin"]==25
    assert entry.options["reaction_time"]=="slow"
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    restored=hass.data[DOMAIN][entry.entry_id]
    assert restored.config["reaction_time"]=="slow"
    assert restored.config["room_buffer"]==pytest.approx(4/1.8)


async def test_group_mean_single_target_and_room_protection(hass):
    entry,runtime=await setup(hass)
    for value in runtime.occupancy.values():value.moving_average(True,1800)
    await runtime.change(mode="heat")
    await hass.async_block_till_done()
    climate=hass.states.get("climate.test_heat_thermostat")
    assert climate.attributes["current_temperature"]==pytest.approx(70)
    assert climate.attributes["temperature"]==pytest.approx(70)
    assert climate.attributes["active_room"]=="Living Room + Bedroom"
    assert runtime.group_data["active"]
    assert runtime.duty==pytest.approx(0,abs=1e-9)
    hass.states.async_set("sensor.bed","76",{"unit_of_measurement":"°F"})
    await runtime.change(mode="heat")
    assert runtime.guard_data["bed"]["hot"]
    assert runtime.duty==0
    assert runtime.reason=="Warm room protection: Bedroom"
    assert runtime.config["shadow"]


async def test_configuration_manual_gains_do_not_change_auto_model_selection(hass):
    entry,runtime=await setup(hass)
    await runtime.change(mode="heat")
    await hass.services.async_call("number","set_value",{"entity_id":"number.test_heat_living_room_manual_kp","value":0.4},blocking=True)
    model=ThermalModel(1.8,0.06,0.15,1800,0.1,0.9,dt_util.utcnow().timestamp(),800)
    runtime.models["living"]=model
    await hass.services.async_call("select","select_option",{"entity_id":"select.test_heat_living_room_pid_tuning","option":"Automatic"},blocking=True)
    await hass.async_block_till_done()
    assert runtime.rooms[0]["kp"]==0.4
    assert runtime.rooms[0]["tuning_mode"]=="auto"
    assert runtime.pids["living"].kp==model.gains()[0]
    await hass.services.async_call("number","set_value",{"entity_id":"number.test_heat_living_room_manual_kp","value":0.5},blocking=True)
    assert runtime.pids["living"].kp==model.gains()[0]
    await hass.services.async_call("select","select_option",{"entity_id":"select.test_heat_living_room_pid_tuning","option":"Manual"},blocking=True)
    assert runtime.pids["living"].kp==0.5
    assert runtime.mode=="heat"
