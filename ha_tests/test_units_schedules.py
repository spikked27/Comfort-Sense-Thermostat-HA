"""Real HA coverage for integration visibility, unit conversion, migration and schedules."""

import pytest

from homeassistant.config_entries import SOURCE_USER

from homeassistant.loader import async_get_integration_descriptions

from homeassistant.helpers.entity_component import DATA_INSTANCES

from homeassistant.setup import async_setup_component

from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from datetime import datetime, timezone



DOMAIN="comfort_sense"





def room():

    return {"id":"study","name":"Study","temperature_sensors":["sensor.study"],

            "occupancy_sensors":[],"target":21.111111111111,"tuning_mode":"manual","kp":0.2,"ki":0.000035,"kd":0}





async def test_entry_is_listed_as_integration_not_helper(hass):

    descriptions=await async_get_integration_descriptions(hass)

    assert DOMAIN in descriptions["custom"]["integration"]

    assert DOMAIN not in descriptions["custom"]["helper"]





async def test_single_thermostat_target_displays_and_accepts_fahrenheit(hass):

    hass.config.units=US_CUSTOMARY_SYSTEM

    hass.states.async_set("switch.heat","off")

    hass.states.async_set("sensor.study","68",{"unit_of_measurement":"°F"})

    entry=MockConfigEntry(domain=DOMAIN,version=3,data={"name":"Test heat","heater":"switch.heat","shadow":True,"comfort_temperature":(70-32)/1.8,"rooms":[room()]})

    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)

    await hass.async_block_till_done()

    eid="climate.test_heat_thermostat"

    assert hass.states.get(eid).attributes["temperature"]==pytest.approx(70)

    assert hass.states.get("number.test_heat_study_comfort_target") is None

    await hass.services.async_call("climate","set_temperature",{"entity_id":eid,"temperature":72},blocking=True)

    assert hass.data[DOMAIN][entry.entry_id].comfort_temperature==pytest.approx((72-32)/1.8)





async def test_fahrenheit_setup_stores_celsius_and_has_no_room_schedule_fields(hass):

    hass.config.units=US_CUSTOMARY_SYSTEM

    hass.states.async_set("switch.heat","off")

    hass.states.async_set("sensor.study","68",{"unit_of_measurement":"°F"})

    result=await hass.config_entries.flow.async_init(DOMAIN,context={"source":SOURCE_USER})

    result=await hass.config_entries.flow.async_configure(result["flow_id"],{

        "name":"Fahrenheit","heater":"switch.heat","shadow":True,

        "away_temperature":65,"boost_temperature":72,"sleep_temperature":65,"max_temperature":82.4})

    result=await hass.config_entries.flow.async_configure(result["flow_id"],{"action":"add"})

    fields={str(key) for key in result["data_schema"].schema}

    assert not any(key.startswith("morning_") for key in fields)

    r=room();r.pop("id");r["tuning_mode"]="auto"

    result=await hass.config_entries.flow.async_configure(result["flow_id"],r)

    result=await hass.config_entries.flow.async_configure(result["flow_id"],{"action":"finish"})

    result=await hass.config_entries.flow.async_configure(result["flow_id"],{})

    assert result["type"]=="create_entry"

    assert "target" not in fields

    assert result["data"]["away_temperature"]==pytest.approx((65-32)/1.8)

    await hass.async_block_till_done()





async def test_v1_migration_preserves_entry_and_old_schedule(hass):

    hass.states.async_set("switch.heat","off")

    hass.states.async_set("sensor.study","20",{"unit_of_measurement":"°C"})

    old={**room(),"morning_enabled":True,"morning_time":"07:00","morning_target":22,

         "morning_duration":60,"morning_days":[0,1,2,3,4]}

    entry=MockConfigEntry(domain=DOMAIN,version=1,data={"heater":"switch.heat","rooms":[old],"shadow":True})

    entry.add_to_hass(hass)

    eid=entry.entry_id

    assert await hass.config_entries.async_setup(eid)

    assert entry.entry_id==eid and entry.version==3

    assert entry.data["rooms"][0]["target"]==old["target"]

    assert "morning_time" not in entry.data["rooms"][0]

    assert entry.data["schedules"][0]["source"]=="study"

    assert entry.data["schedules"][0]["weekly"]["monday"][0]["from"]=="07:00"

    await hass.async_block_till_done()





async def test_native_schedule_preheats_and_restores_after_block(hass,freezer):

    freezer.move_to("2026-10-11 06:30:00+00:00")

    await hass.config.async_set_time_zone("UTC")

    assert await async_setup_component(hass,"schedule",{"schedule":{"morning":{

        "name":"Morning","sunday":[{"from":"07:00:00","to":"09:00:00",

            "data":{"temperature":70,"source":"Study"}}]}}})

    await hass.async_block_till_done()

    hass.states.async_set("switch.heat","off")

    hass.states.async_set("sensor.study","18",{"unit_of_measurement":"°C"})

    binding={"id":"morning","name":"Morning","entity_id":"schedule.morning","source":"Average",

        "target":23,"preheat":True,"priority":0,"data_temperature_unit":"°F"}

    r=room();r["target"]=19

    entry=MockConfigEntry(domain=DOMAIN,version=2,data={"heater":"switch.heat","rooms":[r],"shadow":True,"comfort_temperature":19,"schedules":[binding]})

    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)

    await hass.async_block_till_done()

    runtime=hass.data[DOMAIN][entry.entry_id]

    await runtime.change(mode="heat")

    assert runtime.reason=="Schedule preheat"

    assert runtime.room_data["study"]["target"]==pytest.approx((70-32)/1.8)

    assert runtime.schedule_status["morning"]=="Connected"

    freezer.move_to("2026-10-11 09:05:00+00:00")

    async_fire_time_changed(hass,datetime(2026,10,11,9,5,tzinfo=timezone.utc))

    await hass.async_block_till_done()

    await runtime.tick()

    assert runtime.room_data["study"]["target"]==19

    assert runtime.reason=="Room control"

    # YAML Schedule helpers own a future timer and are not config entries, so

    # remove this test-only helper explicitly before HA's timer-leak audit.

    await hass.data[DATA_INSTANCES]["schedule"].async_remove_entity("schedule.morning")

    await hass.async_block_till_done()





async def test_scheduling_is_a_separate_unit_aware_options_section(hass):

    hass.config.units=US_CUSTOMARY_SYSTEM

    hass.states.async_set("switch.heat","off")

    hass.states.async_set("sensor.study","68",{"unit_of_measurement":"°F"})

    hass.states.async_set("schedule.weekdays","off")

    entry=MockConfigEntry(domain=DOMAIN,version=2,data={"heater":"switch.heat","rooms":[room()],"shadow":True})

    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)

    flow=await hass.config_entries.options.async_init(entry.entry_id)

    assert "schedules" in flow["menu_options"]

    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"schedules"})

    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"action":"settings"})

    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"max_preheat_minutes":240,"fallback_heat_rate":0.9})

    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"action":"add"})

    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{

        "name":"Weekdays","entity_id":"schedule.weekdays","source":"Average","target":70,

        "preheat":True,"priority":1,"data_temperature_unit":"°F"})

    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"action":"finish"})

    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{})

    assert flow["type"]=="create_entry"

    assert entry.options["schedules"][0]["target"]==pytest.approx((70-32)/1.8)

    assert entry.options["fallback_heat_rate"]==pytest.approx(0.5)

    assert not any(key.startswith("morning_") for key in entry.options["rooms"][0])

    await hass.async_block_till_done()

