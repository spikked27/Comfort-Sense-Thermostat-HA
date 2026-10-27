"""Real HA setup, alarm flow, units, visibility and shared-plan arbitration."""
import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN="comfort_sense"


def room():
    return {"id":"bed","name":"Bedroom","temperature_sensors":["sensor.bed"],"occupancy_sensors":[]}


async def setup(hass,freezer):
    freezer.move_to("2026-10-27 09:30:00+00:00")
    await hass.config.async_set_time_zone("America/New_York")
    hass.config.units=US_CUSTOMARY_SYSTEM
    hass.states.async_set("switch.heat","off")
    hass.states.async_set("sensor.bed","64",{"unit_of_measurement":"°F"})
    hass.states.async_set("sensor.alarm","2026-10-27T06:00:00-04:00",{"device_class":"timestamp"})
    entry=MockConfigEntry(domain=DOMAIN,version=4,data={"name":"Test heat","heater":"switch.heat","rooms":[room()]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry,hass.data[DOMAIN][entry.entry_id]


async def test_defaults_hidden_manual_global_buffer_and_reveal_persists(hass,freezer):
    entry,runtime=await setup(hass,freezer)
    assert runtime.rooms[0]["tuning_mode"]==runtime.config["average_tuning_mode"]=="auto"
    registry=er.async_get(hass)
    manual=[e for e in er.async_entries_for_config_entry(registry,entry.entry_id)
            if e.unique_id.endswith(("_kp","_ki","_kd"))]
    assert len(manual)==6
    assert all(e.hidden_by==er.RegistryEntryHider.INTEGRATION and e.disabled_by is None for e in manual)
    assert hass.states.get("number.test_heat_room_protection_buffer").attributes["unit_of_measurement"]=="°F"
    assert hass.states.get("number.test_heat_bedroom_warm_buffer") is None
    registry.async_update_entity(manual[0].entity_id,hidden_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(manual[0].entity_id).hidden_by is None


async def test_morning_flow_fahrenheit_owner_preheat_and_hold(hass,freezer):
    entry,runtime=await setup(hass,freezer)
    flow=await hass.config_entries.options.async_init(entry.entry_id)
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"schedules"})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"action":"morning"})
    assert flow["step_id"]=="morning"
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{
        "morning_enabled":True,"alarm_sensors":["sensor.alarm"],"morning_target":68,
        "morning_source":"bed","morning_duration":60})
    assert flow["step_id"]=="schedules"
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"action":"alarm_owner"})
    hass.states.async_set("person.matt","home")
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"alarm_sensor":"sensor.alarm","person":"person.matt"})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"action":"finish"})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{})
    assert flow["type"]=="create_entry"
    await hass.async_block_till_done()
    runtime=hass.data[DOMAIN][entry.entry_id]
    assert runtime.config["morning_target"]==pytest.approx(20)
    await runtime.change(mode="heat")
    assert runtime.reason=="Schedule preheat"
    assert runtime.target_temperature==pytest.approx(20)
    assert hass.states.get("sensor.test_heat_ready_by").state=="2026-10-27T10:00:00+00:00"
    assert hass.states.get("sensor.test_heat_estimated_heating_start").state not in ("unknown","unavailable")
    freezer.move_to("2026-10-27 10:00:30+00:00")
    hass.states.async_set("sensor.alarm","2026-10-28T06:00:00-04:00",{"device_class":"timestamp"})
    await runtime.change(mode="heat")
    assert runtime.reason=="Scheduled comfort"
    assert runtime.target_temperature==pytest.approx(20)
    freezer.move_to("2026-10-27 11:00:30+00:00")
    await runtime.change(mode="heat")
    assert runtime.target_temperature==21


async def test_bad_alarm_input_shows_error_and_owner_away_excludes_phone(hass,freezer):
    entry,runtime=await setup(hass,freezer)
    flow=await hass.config_entries.options.async_init(entry.entry_id)
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"next_step_id":"schedules"})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{"action":"morning"})
    flow=await hass.config_entries.options.async_configure(flow["flow_id"],{
        "morning_enabled":True,"alarm_sensors":["sensor.bed"],"morning_target":68,
        "morning_source":"Average","morning_duration":60})
    assert flow["errors"]["base"]=="invalid_morning"
    runtime.config.update(morning_enabled=True,alarm_sensors=["sensor.alarm"],alarm_owners={"sensor.alarm":"person.matt"})
    hass.states.async_set("person.matt","not_home")
    await runtime.change(mode="heat")
    assert not runtime.schedule_plans


async def test_new_room_flow_defaults_automatic_without_manual_page(hass,freezer):
    await setup(hass,freezer)
    hass.states.async_set("switch.other","off")
    flow=await hass.config_entries.flow.async_init(DOMAIN,context={"source":SOURCE_USER})
    flow=await hass.config_entries.flow.async_configure(flow["flow_id"],{"name":"New","heater":"switch.other","shadow":True})
    flow=await hass.config_entries.flow.async_configure(flow["flow_id"],{"action":"add"})
    flow=await hass.config_entries.flow.async_configure(flow["flow_id"],{"name":"Bedroom","temperature_sensors":["sensor.bed"]})
    assert flow["step_id"]=="manage"
    flow=await hass.config_entries.flow.async_configure(flow["flow_id"],{"action":"finish"})
    flow=await hass.config_entries.flow.async_configure(flow["flow_id"],{})
    assert flow["data"]["rooms"][0]["tuning_mode"]=="auto"
    assert flow["data"]["average_tuning_mode"]=="auto"
    await hass.async_block_till_done()
