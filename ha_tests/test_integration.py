"""Tests executed against real Home Assistant by Linux CI, separate from local fakes."""
import pytest
from homeassistant.config_entries import SOURCE_USER
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN="comfort_sense"


def room():
    return {"id":"study","name":"Study","temperature_sensors":["sensor.study"],
        "occupancy_sensors":["binary_sensor.study"],"target":21,"kp":0.2,"ki":0.000035,"kd":0,
        "tuning_mode":"manual"}


async def test_user_room_review_and_setup(hass):
    hass.states.async_set("switch.heat","off")
    hass.states.async_set("sensor.study","20",{"unit_of_measurement":"°C","device_class":"temperature"})
    result=await hass.config_entries.flow.async_init(DOMAIN,context={"source":SOURCE_USER})
    assert result["step_id"]=="system"
    result=await hass.config_entries.flow.async_configure(result["flow_id"],{
        "name":"Test heat","heater":"switch.heat","shadow":True})
    assert result["step_id"]=="manage"
    result=await hass.config_entries.flow.async_configure(result["flow_id"],{"action":"add"})
    assert result["step_id"]=="room"
    r=room();r.pop("id")
    result=await hass.config_entries.flow.async_configure(result["flow_id"],r)
    assert result["step_id"]=="manage"
    result=await hass.config_entries.flow.async_configure(result["flow_id"],{"action":"finish"})
    assert result["step_id"]=="review"
    result=await hass.config_entries.flow.async_configure(result["flow_id"],{})
    assert result["type"]=="create_entry"
    await hass.async_block_till_done()
    assert hass.states.get("climate.test_heat_thermostat") is not None


async def test_shadow_setup_unload_never_calls_switch(hass):
    calls=[]
    async def command(call): calls.append(call)
    hass.services.async_register("switch","turn_on",command)
    hass.services.async_register("switch","turn_off",command)
    hass.states.async_set("switch.heat","off")
    hass.states.async_set("sensor.study","20",{"unit_of_measurement":"°C"})
    entry=MockConfigEntry(domain=DOMAIN,data={"name":"Test heat","heater":"switch.heat","shadow":True,"rooms":[room()]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not calls


async def test_duplicate_heater_rejected(hass):
    hass.states.async_set("switch.heat","off")
    entry=MockConfigEntry(domain=DOMAIN,data={"heater":"switch.heat","rooms":[room()]})
    entry.add_to_hass(hass)
    flow=await hass.config_entries.flow.async_init(DOMAIN,context={"source":SOURCE_USER})
    result=await hass.config_entries.flow.async_configure(flow["flow_id"],{"name":"Duplicate","heater":"switch.heat","shadow":True})
    assert result["errors"]["base"]=="heater_already_configured"


async def test_invalid_room_rejected(hass):
    hass.states.async_set("switch.heat","off")
    flow=await hass.config_entries.flow.async_init(DOMAIN,context={"source":SOURCE_USER})
    flow=await hass.config_entries.flow.async_configure(flow["flow_id"],{"name":"Test","heater":"switch.heat","shadow":True})
    flow=await hass.config_entries.flow.async_configure(flow["flow_id"],{"action":"add"})
    r=room();r.pop("id");r["name"]="Average"
    result=await hass.config_entries.flow.async_configure(flow["flow_id"],r)
    assert result["errors"]["base"]=="invalid_room"


async def test_room_options_update_manual_fallback_without_changing_average(hass):
    hass.states.async_set("switch.heat","off")
    hass.states.async_set("sensor.study","20",{"unit_of_measurement":"°C"})
    entry=MockConfigEntry(domain=DOMAIN,data={"heater":"switch.heat","shadow":True,"rooms":[room()],"average_kp":0.55})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    result=await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"]=="init"
    result=await hass.config_entries.options.async_configure(result["flow_id"],{"next_step_id":"manage"})
    result=await hass.config_entries.options.async_configure(result["flow_id"],{"action":"edit:study"})
    update=room();update.pop("id")
    update.update(kp=0.35,tuning_mode="auto")
    result=await hass.config_entries.options.async_configure(result["flow_id"],update)
    result=await hass.config_entries.options.async_configure(result["flow_id"],{"action":"finish"})
    result=await hass.config_entries.options.async_configure(result["flow_id"],{})
    assert result["type"]=="create_entry"
    await hass.async_block_till_done()
    runtime=hass.data[DOMAIN][entry.entry_id]
    assert runtime.pids["study"].kp==0.35
    assert runtime.pids["_average"].kp==0.55
    assert runtime.rooms[0]["tuning_mode"]=="auto"


async def test_active_unload_requests_heater_off(hass):
    calls=[]
    async def command(call): calls.append(call.service)
    hass.services.async_register("switch","turn_on",command)
    hass.services.async_register("switch","turn_off",command)
    hass.states.async_set("switch.heat","off")
    hass.states.async_set("sensor.study","20",{"unit_of_measurement":"°C"})
    entry=MockConfigEntry(domain=DOMAIN,data={"heater":"switch.heat","shadow":False,"rooms":[room()]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert calls[-1]=="turn_off"
