"""Real HA short-restart bias persistence and compact on-demand diagnostics."""
import json
import pytest
from homeassistant.util import dt as dt_util
from custom_components.comfort_sense.diagnostics import async_get_config_entry_diagnostics
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN="comfort_sense"


async def setup(hass,freezer):
    freezer.move_to("2026-10-28T10:00:00+00:00")
    hass.states.async_set("switch.private_heater","off")
    hass.states.async_set("sensor.private_room","20",{"unit_of_measurement":"°C"})
    entry=MockConfigEntry(domain=DOMAIN,version=4,data={"name":"Private thermostat","heater":"switch.private_heater",
        "rooms":[{"id":"private_room_id","name":"Private bedroom","temperature_sensors":["sensor.private_room"],"occupancy_sensors":[]}]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime=hass.data[DOMAIN][entry.entry_id]
    await runtime.change(mode="heat",source="Average")
    runtime.pids["_average"].integral=0.3
    freezer.tick(30)
    await runtime.tick()
    return entry,runtime


async def test_short_reload_recovers_bias_and_keeps_fresh_relay_timer(hass,freezer):
    entry,runtime=await setup(hass,freezer)
    before=runtime.pids["_average"].integral
    freezer.tick(60)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    restored=hass.data[DOMAIN][entry.entry_id]
    assert "Restored" in restored.memory_restore_status
    assert restored.pids["_average"].integral==pytest.approx(before,abs=0.002)
    assert restored.pids["_average"].derivative==0
    assert not restored.proposed
    assert restored.relay.changed==dt_util.utcnow().timestamp()


async def test_long_restart_or_explicit_off_cannot_recover_compensation(hass,freezer):
    entry,runtime=await setup(hass,freezer)
    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.tick(901)
    # Updated sensor reports isolate the outage-age gate from freshness.
    hass.states.async_set("sensor.private_room","20.01",{"unit_of_measurement":"°C"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    restored=hass.data[DOMAIN][entry.entry_id]
    assert "Restored" not in restored.memory_restore_status
    assert restored.pids["_average"].integral<0.01
    await restored.change(mode="off")
    assert restored.saved()["pid_memory"] is None
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].mode=="off"


async def test_diagnostics_explain_pid_without_exporting_entity_ids_or_room_names(hass,freezer):
    entry,runtime=await setup(hass,freezer)
    report=await async_get_config_entry_diagnostics(hass,entry)
    serialized=json.dumps(report)
    for value in ("private_room_id","Private bedroom","Private thermostat","switch.private_heater","sensor.private_room",entry.entry_id):
        assert value not in serialized
    assert report["control"]["controller"]=="average"
    assert report["control"]["terms"]["integral"]>0
    assert report["control"]["limiting_condition"]=="Minimum off time"
    assert report["timing"]["min_off_seconds"]==300
    assert report["restart_memory"]["maximum_age_seconds"]==900
