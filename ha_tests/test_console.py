"""Console permissions, input validation, conflict protection and real HA reloads."""
from copy import deepcopy
import pytest
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.comfort_sense.panel import checked_config, snapshot, current_config

DOMAIN="comfort_sense"


async def setup(hass):
    hass.states.async_set("switch.heat","off")
    hass.states.async_set("sensor.room","20",{"device_class":"temperature","unit_of_measurement":"°C"})
    hass.states.async_set("sensor.outside","7",{"device_class":"temperature","unit_of_measurement":"°C"})
    entry=MockConfigEntry(domain=DOMAIN,version=4,data={"name":"Console thermostat","heater":"switch.heat",
        "outdoor_sensor":"sensor.outside","rooms":[{"id":"room","name":"Bedroom","temperature_sensors":["sensor.room"],"occupancy_sensors":[]}]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_panel_assets_and_admin_snapshot(hass,hass_client,hass_ws_client):
    entry=await setup(hass)
    client=await hass_client()
    for path,kind in (("/comfort_sense_static/comfort-sense.js","javascript"),("/comfort_sense_static/icon.png","image/png")):
        response=await client.get(path)
        assert response.status==200
        assert kind in response.content_type
        assert len(await response.read())>1000
    ws=await hass_ws_client(hass)
    await ws.send_json({"id":1,"type":"comfort_sense/console"})
    response=await ws.receive_json()
    assert response["success"]
    data=response["result"]
    assert data["entries"][0]["entry_id"]==entry.entry_id
    assert data["entries"][0]["config"]["rooms"][0]["name"]=="Bedroom"
    assert any(x["title"]=="Observation only" for x in data["entries"][0]["issues"])
    assert not any(e["entity_id"].startswith("sensor.console_thermostat") for e in data["entities"])
    await ws.send_json({"id":2,"type":"get_panels"})
    panels=(await ws.receive_json())["result"]
    assert panels["comfort-sense"]["require_admin"]


async def test_console_rejects_non_admin_reads_and_writes(hass,hass_ws_client,hass_read_only_user):
    entry=await setup(hass)
    ws=await hass_ws_client(hass,hass_read_only_user)
    for number,payload in enumerate(({"type":"comfort_sense/console"},
        {"type":"comfort_sense/save","entry_id":entry.entry_id,"revision":"x","unit":"°C","config":{}}),1):
        await ws.send_json({"id":number,**payload})
        result=await ws.receive_json()
        assert not result["success"]
        assert result["error"]["code"]=="unauthorized"


async def test_fahrenheit_save_survives_reload_and_conflicts_are_rejected(hass,hass_ws_client):
    hass.config.units=US_CUSTOMARY_SYSTEM
    entry=await setup(hass)
    row=snapshot(hass)["entries"][0]
    assert row["config"]["comfort_temperature"]==pytest.approx(69.8)
    row["config"].update(comfort_temperature=70,room_buffer=3.6,min_on_seconds=360)
    ws=await hass_ws_client(hass)
    message={"id":1,"type":"comfort_sense/save","entry_id":entry.entry_id,"revision":row["revision"],"unit":"°F","config":row["config"]}
    await ws.send_json(message)
    assert (await ws.receive_json())["success"]
    await hass.async_block_till_done()
    runtime=hass.data[DOMAIN][entry.entry_id]
    assert runtime.comfort_temperature==pytest.approx((70-32)/1.8)
    assert runtime.config["room_buffer"]==pytest.approx(2)
    assert runtime.config["min_on_seconds"]==360
    assert runtime.mode=="off"
    attributes=hass.states.get("climate.console_thermostat_thermostat").attributes
    assert attributes["outdoor_temperature"]==7
    assert attributes["outdoor_temperature_unit"]=="°C"
    assert attributes["outdoor_compensation"]["coefficient"] is None
    assert attributes["outdoor_compensation"]["status"]=="Waiting for accepted model"
    await ws.send_json({**message,"id":2})
    response=await ws.receive_json()
    assert response["error"]["code"]=="conflict"


async def test_console_validation_preserves_offline_inputs_and_rejects_bad_edits(hass):
    entry=await setup(hass)
    base=snapshot(hass)["entries"][0]["config"]
    hass.states.async_set("sensor.room","unavailable")
    assert checked_config(hass,entry,base,"°C")["rooms"][0]["temperature_sensors"]==["sensor.room"]
    for patch in ({"pwm_seconds":120},{"shadow":False},{"room_buffer":None},{"heater":"light.other"}):
        with pytest.raises((ValueError,TypeError)):
            checked_config(hass,entry,{**base,**patch},"°C")
    hass.states.async_set("sensor.not_temperature","100",{"unit_of_measurement":"W"})
    bad=deepcopy(base);bad["rooms"][0]["temperature_sensors"]=["sensor.not_temperature"]
    with pytest.raises(ValueError,match="temperature sensor"):
        checked_config(hass,entry,bad,"°C")
    bad=deepcopy(base);bad["rooms"][0]["temperature_sensors"]=["sensor.console_thermostat_bedroom_temperature"]
    with pytest.raises(ValueError,match="original room"):
        checked_config(hass,entry,bad,"°C")
    other=MockConfigEntry(domain=DOMAIN,version=4,data={**entry.data,"heater":"switch.other"})
    other.add_to_hass(hass)
    with pytest.raises(ValueError,match="already belongs"):
        checked_config(hass,entry,{**base,"heater":"switch.other"},"°C")


async def test_shadow_to_active_requires_acknowledgment_and_available_relay(hass):
    entry=await setup(hass)
    config=snapshot(hass)["entries"][0]["config"]
    config["shadow"]=False
    with pytest.raises(ValueError,match="Confirm"):
        checked_config(hass,entry,config,"°C")
    assert checked_config(hass,entry,config,"°C",True)["shadow"] is False
    hass.states.async_set("switch.heat","unavailable")
    with pytest.raises(ValueError,match="confirmed"):
        checked_config(hass,entry,config,"°C",True)


async def test_rooms_and_schedule_validation_is_atomic(hass,hass_ws_client):
    entry=await setup(hass)
    row=snapshot(hass)["entries"][0]
    before=current_config(hass,entry)
    row["config"]["rooms"][0]["temperature_sensors"]=[]
    ws=await hass_ws_client(hass)
    await ws.send_json({"id":1,"type":"comfort_sense/save","entry_id":entry.entry_id,
        "revision":row["revision"],"unit":"°C","config":row["config"]})
    response=await ws.receive_json()
    assert response["error"]["code"]=="invalid_config"
    assert current_config(hass,entry)==before
