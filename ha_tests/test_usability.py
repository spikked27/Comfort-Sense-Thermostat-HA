"""Exercise the complete short setup, advanced options and dashboard entities."""
import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN="comfort_sense"


def room():
    return {"id":"study","name":"Study","temperature_sensors":["sensor.study"],"occupancy_sensors":["binary_sensor.study"],"target":21,"tuning_mode":"manual","kp":0.2,"ki":0.000035,"kd":0}


async def test_short_setup_and_manual_gains_are_separate(hass):
    hass.states.async_set("switch.heat","off")
    # Temperature helpers can omit a unit until their first startup reading.
    hass.states.async_set("sensor.study","unknown",{"device_class":"temperature"})
    flow=await hass.config_entries.flow.async_init(DOMAIN,context={"source":SOURCE_USER})
    assert {str(k) for k in flow["data_schema"].schema}=={"name","heater","outdoor_sensor","home_sensor","shadow","reaction_time"}
    flow=await hass.config_entries.flow.async_configure(flow["flow_id"],{"name":"Simple","heater":"switch.heat","shadow":True,"reaction_time":"medium"})
    flow=await hass.config_entries.flow.async_configure(flow["flow_id"],{"action":"add"})
    assert {str(k) for k in flow["data_schema"].schema}=={"name","temperature_sensors","occupancy_sensors","tuning_mode"}
    flow=await hass.config_entries.flow.async_configure(flow["flow_id"],{"name":"Study","temperature_sensors":["sensor.study"],"tuning_mode":"manual"})
    assert flow["step_id"]=="room_gains"
    flow=await hass.config_entries.flow.async_configure(flow["flow_id"],{"kp":0.3,"ki":0.00002,"kd":0})
    flow=await hass.config_entries.flow.async_configure(flow["flow_id"],{"action":"finish"})
    flow=await hass.config_entries.flow.async_configure(flow["flow_id"],{})
    assert flow["type"]=="create_entry"
    assert flow["data"]["rooms"][0]["kp"]==0.3
    await hass.async_block_till_done()


async def test_advanced_average_pid_and_invalid_relay_cycle(hass):
    hass.states.async_set("switch.heat","off")
    hass.states.async_set("sensor.study","20",{"unit_of_measurement":"°C"})
    entry=MockConfigEntry(domain=DOMAIN,version=3,data={"heater":"switch.heat","shadow":True,"rooms":[room()]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    flow=await hass.config_entries.options.async_init(entry.entry_id)
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"advanced"})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"average_pid"})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"average_tuning_mode":"manual"})
    assert flow["step_id"]=="average_gains"
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"average_kp":0.45,"average_ki":0.00002,"average_kd":0})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"relay"})
    bad={"pwm_seconds":120,"min_on_seconds":300,"min_off_seconds":300,"sensor_timeout_minutes":180,"max_temperature":28}
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],bad)
    assert flow["errors"]["base"]=="invalid_cycle"
    bad["pwm_seconds"]=1200
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],bad)
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"init"})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"review"})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{})
    assert flow["type"]=="create_entry"
    assert entry.options["average_kp"]==0.45
    await hass.async_block_till_done()


async def test_active_room_occupancy_and_duty_entities(hass):
    hass.states.async_set("switch.heat","off")
    hass.states.async_set("sensor.study","20",{"unit_of_measurement":"°C"})
    hass.states.async_set("binary_sensor.study","on")
    entry=MockConfigEntry(domain=DOMAIN,version=3,data={"name":"Test heat","heater":"switch.heat","shadow":True,"rooms":[room()]})
    entry.add_to_hass(hass)
    registry=er.async_get(hass)
    old=registry.async_get_or_create("number",DOMAIN,entry.entry_id+"_study_target",config_entry=entry,suggested_object_id="old_target")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(old.entity_id) is None
    runtime=hass.data[DOMAIN][entry.entry_id]
    runtime.occupancy["study"].moving_average(True,1800)
    await runtime.change(mode="heat")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_heat_active_room").state=="Study"
    assert float(hass.states.get("sensor.test_heat_study_occupancy").state)>95
    demand=hass.states.get("sensor.test_heat_heat_demand")
    assert demand.attributes["cycle_minutes"]==20
    assert demand.attributes["nominal_on_minutes"]==pytest.approx(float(demand.state)/100*20,abs=0.02)


async def test_fahrenheit_presets_are_configured_separately(hass):
    hass.config.units=US_CUSTOMARY_SYSTEM
    hass.states.async_set("switch.heat","off")
    hass.states.async_set("sensor.study","68",{"unit_of_measurement":"°F"})
    entry=MockConfigEntry(domain=DOMAIN,version=3,data={"heater":"switch.heat","shadow":True,"rooms":[room()]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    flow=await hass.config_entries.options.async_init(entry.entry_id)
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"advanced"})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"presets"})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"away_temperature":65,"sleep_temperature":65,"boost_temperature":72,"boost_minutes":60,"away_delay_minutes":20,"sleep_room":""})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"init"})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"review"})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{})
    assert entry.options["away_temperature"]==pytest.approx((65-32)/1.8)
    assert entry.options["boost_temperature"]==pytest.approx((72-32)/1.8)
    await hass.async_block_till_done()
