"""Administrator console: validated config editing and live readiness feedback."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import voluptuous as vol
from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, area_registry as ar

from .const import DEFAULTS, DOMAIN
from .settings import validate
from .units import display_temperature, native_temperature, display_rate, native_rate

URL="/comfort_sense_static"
TEMPERATURES=("comfort_temperature","away_temperature","sleep_temperature","boost_temperature","morning_target","max_temperature")
RATES=("room_buffer","fallback_heat_rate")


def revision(config):
    return hashlib.sha256(json.dumps(config,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def current_config(hass,entry):
    runtime=hass.data.get(DOMAIN,{}).get(entry.entry_id)
    config=deepcopy(validate({**entry.data,**entry.options}))
    if runtime:
        config["comfort_temperature"]=runtime.comfort_temperature
    return config


def converted(config,unit,to_display):
    result=deepcopy(config)
    temp=display_temperature if to_display else native_temperature
    rate=display_rate if to_display else native_rate
    for key in TEMPERATURES:result[key]=temp(result[key],unit)
    for key in RATES:result[key]=rate(result[key],unit)
    for binding in result["schedules"]:binding["target"]=temp(binding["target"],unit)
    return result


def entity_fields(config):
    yield config["heater"],"switch"
    if config["outdoor_sensor"]:yield config["outdoor_sensor"],"temperature"
    if config["home_sensor"]:yield config["home_sensor"],"presence"
    for room in config["rooms"]:
        for eid in room["temperature_sensors"]:yield eid,"temperature"
        for eid in room.get("occupancy_sensors",[]):yield eid,"binary_sensor"
    for eid in config["alarm_sensors"]:yield eid,"timestamp"
    for eid in config["alarm_owners"].values():yield eid,"person"
    for binding in config["schedules"]:
        if binding.get("entity_id"):yield binding["entity_id"],"schedule"


def checked_config(hass,entry,shown,unit,acknowledge=False):
    """Validate everything before updating this integration's config entry."""
    old=current_config(hass,entry)
    if set(shown)-set(old)-set(DEFAULTS)-{"heater","rooms"}:
        raise ValueError("Unknown configuration field")
    candidate=validate(converted(shown,unit,False))
    if not isinstance(candidate["shadow"],bool) or not isinstance(candidate["name"],str) or not candidate["name"].strip():
        raise ValueError("Enter a thermostat name and control mode")
    candidate["name"]=candidate["name"].strip()
    for room in candidate["rooms"]:
        if not isinstance(room["id"],str) or not room["id"] or not isinstance(room["name"],str) or not room["name"].strip():
            raise ValueError("Each room needs a name")
        room["name"]=room["name"].strip()
        for key in ("temperature_sensors","occupancy_sensors"):
            if not isinstance(room.get(key,[]),list) or any(not isinstance(e,str) for e in room.get(key,[])):
                raise ValueError("Select room sensors from the list")
    # Trimming names must not introduce duplicate names.
    candidate=validate(candidate)
    for binding in candidate["schedules"]:
        if not isinstance(binding["preheat"],bool):raise ValueError("Choose whether to preheat for each schedule")
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id!=entry.entry_id and {**other.data,**other.options}.get("heater")==candidate["heater"]:
            raise ValueError("That heater already belongs to another Comfort Sense thermostat")
    if not candidate["shadow"] and (old["shadow"] or old["heater"]!=candidate["heater"]) and not acknowledge:
        raise ValueError("Confirm other controllers of this relay are stopped before enabling active control")
    old_entities=set(entity_fields(old))
    registry=er.async_get(hass)
    for eid,kind in entity_fields(candidate):
        domain=eid.split(".",1)[0]
        domains={"sensor"} if kind in ("temperature","timestamp") else {"binary_sensor","person","device_tracker","zone"} if kind=="presence" else {kind}
        if domain not in domains:raise ValueError(f"Invalid {kind} entity: {eid}")
        registered=registry.async_get(eid)
        if registered and registered.platform==DOMAIN and kind=="temperature":
            raise ValueError("Select the original room temperature sensor, not a Comfort Sense calculated sensor")
        state=hass.states.get(eid)
        if (eid,kind) in old_entities:continue  # existing offline hardware can be kept
        if not state:raise ValueError(f"Entity not found: {eid}")
        attrs=state.attributes
        if kind=="temperature" and attrs.get("device_class")!="temperature" and attrs.get("unit_of_measurement") not in ("°C","°F","K"):
            raise ValueError(f"Select a temperature sensor: {eid}")
        if kind=="timestamp" and attrs.get("device_class")!="timestamp":
            raise ValueError(f"Select a next-alarm timestamp sensor: {eid}")
    if not candidate["shadow"] and (old["shadow"] or old["heater"]!=candidate["heater"]):
        state=hass.states.get(candidate["heater"])
        if not state or state.state not in ("on","off") or state.attributes.get("restored"):
            raise ValueError("The heater must report a confirmed on/off state before active control is enabled")
    return candidate


def snapshot(hass):
    unit=str(hass.config.units.temperature_unit)
    registry=er.async_get(hass)
    entries=[]
    for entry in hass.config_entries.async_entries(DOMAIN):
        config=current_config(hass,entry)
        runtime=hass.data.get(DOMAIN,{}).get(entry.entry_id)
        registered=er.async_entries_for_config_entry(registry,entry.entry_id)
        climate=next((e.entity_id for e in registered if e.domain=="climate"),None)
        issues=[]
        def issue(level,title,detail,tab):issues.append(dict(level=level,title=title,detail=detail,tab=tab))
        heater=hass.states.get(config["heater"])
        if not heater or heater.state not in ("on","off") or heater.attributes.get("restored"):
            issue("error","Heater disconnected","Heating control and learning are waiting for relay feedback.","equipment")
        if config["shadow"]:issue("info","Observation only","Shadow mode is on. Comfort Sense does not switch the heater.","equipment")
        if not config["outdoor_sensor"]:issue("warning","Add outdoor temperature","Needed for learning heat loss and room warm-up times.","equipment")
        elif not runtime or runtime.outdoor is None:issue("warning","Outdoor reading unavailable","Thermal learning is waiting for a valid outdoor temperature.","equipment")
        if not runtime:issue("error","Thermostat not loaded","Check this integration on the Devices & services page.","equipment")
        rooms=[]
        for room in config["rooms"]:
            data=runtime.room_data.get(room["id"],{}) if runtime else {}
            temperature=data.get("temperature")
            if temperature is None:issue("error",f"{room['name']}: no temperature","Check the selected sensors before heating can follow this room.","rooms")
            if data.get("occupancy_unavailable"):issue("warning",f"{room['name']}: occupancy unavailable","Room selection may fall back to the average.","rooms")
            rooms.append({"id":room["id"],"temperature":display_temperature(temperature,unit) if temperature is not None else None,
                "occupancy":round(data.get("occupancy",0)*100),"active":data.get("weight",0)>0,
                "learning":data.get("tuning_status","Waiting for observations"),"learned":bool(data.get("model")),
                "excluded":data.get("excluded_sensors",[])})
        external=[]
        for state in hass.states.async_all("switch"):
            if climate and climate in state.attributes.get("entities",[]) and "timeslots" in state.attributes and state.state=="on":
                external.append({"name":state.name,"entity_id":state.entity_id,"days":state.attributes.get("weekdays",[]),"timeslots":state.attributes.get("timeslots",[])})
        if external:issue("warning","External schedules connected",f"{len(external)} Scheduler schedules also change this thermostat. Review preset timing and boost duration.","schedules")
        entries.append({"entry_id":entry.entry_id,"revision":revision(config),"name":config["name"],"config":converted(config,unit,True),
            "climate_entity":climate,"issues":issues,"rooms":rooms,"external_schedules":external,
            "live":{"mode":runtime.mode if runtime else "off","preset":runtime.preset if runtime else "comfort",
                "source":runtime.active_source if runtime else "Unavailable","reason":runtime.reason if runtime else "Not loaded",
                "temperature":display_temperature(runtime.current_temperature,unit) if runtime and runtime.current_temperature is not None else None,
                "target":display_temperature(runtime.target_temperature,unit) if runtime and runtime.target_temperature is not None else None,
                "demand":round(runtime.duty*100,1) if runtime else 0,"observed":runtime.actual if runtime else None,
                "outdoor":display_temperature(runtime.outdoor,unit) if runtime and runtime.outdoor is not None else None,
                "outdoor_compensation":runtime.outdoor_compensation() if runtime else {},
                "proposed":runtime.proposed if runtime else False,"morning":runtime.morning.status if runtime else "Not loaded",
                "plans":deepcopy(runtime.schedule_plans) if runtime else [],"average_learning":runtime.learning_status.get("_average","Waiting for observations") if runtime else "Not loaded"}})
    catalog=[]
    for state in hass.states.async_all():
        if state.domain not in ("sensor","binary_sensor","person","device_tracker","zone","schedule","switch"):continue
        entity=registry.async_get(state.entity_id)
        if entity and entity.platform==DOMAIN:continue
        catalog.append({"entity_id":state.entity_id,"name":state.name,"state":state.state,
            "unit":state.attributes.get("unit_of_measurement",""),"device_class":state.attributes.get("device_class"),
            "area_id":entity.area_id if entity else None})
    return {"unit":unit,"entries":entries,"entities":catalog,
        "areas":[{"id":a.id,"name":a.name} for a in ar.async_get(hass).areas.values()]}


@websocket_api.websocket_command({vol.Required("type"):"comfort_sense/console"})
@websocket_api.require_admin
@callback
def ws_console(hass,connection,msg):
    connection.send_result(msg["id"],snapshot(hass))


@websocket_api.websocket_command({vol.Required("type"):"comfort_sense/save",vol.Required("entry_id"):str,
    vol.Required("revision"):str,vol.Required("unit"):vol.In(["°C","°F"]),vol.Required("config"):dict,
    vol.Optional("acknowledge_active",default=False):bool})
@websocket_api.require_admin
@callback
def ws_save(hass,connection,msg):
    entry=hass.config_entries.async_get_entry(msg["entry_id"])
    if not entry or entry.domain!=DOMAIN:
        connection.send_error(msg["id"],"not_found","Thermostat not found")
        return
    try:
        if revision(current_config(hass,entry))!=msg["revision"] or msg["unit"]!=str(hass.config.units.temperature_unit):
            connection.send_error(msg["id"],"conflict","Settings changed elsewhere. Reload the latest settings before saving.")
            return
        candidate=checked_config(hass,entry,msg["config"],msg["unit"],msg["acknowledge_active"])
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError) as err:
        connection.send_error(msg["id"],"invalid_config",str(err))
        return
    runtime=hass.data.get(DOMAIN,{}).get(entry.entry_id)
    if runtime and candidate["comfort_temperature"]!=runtime.comfort_temperature:
        runtime.comfort_temperature=candidate["comfort_temperature"]
        runtime.save_later()
    hass.config_entries.async_update_entry(entry,title=candidate["name"],options=candidate)
    connection.send_result(msg["id"],{"saved":True})


async def async_setup_panel(hass):
    path=Path(__file__).parent
    await hass.http.async_register_static_paths([StaticPathConfig(URL+"/icon.png",str(path/"brand/icon@2x.png"),True),
        StaticPathConfig(URL,str(path/"frontend"),False)])
    version=json.loads(await hass.async_add_executor_job((path/"manifest.json").read_text))["version"]
    await panel_custom.async_register_panel(hass,frontend_url_path="comfort-sense",webcomponent_name="comfort-sense-panel",
        sidebar_title="Comfort Sense",sidebar_icon="mdi:home-thermometer-outline",require_admin=True,
        config_panel_domain=DOMAIN,module_url=f"{URL}/comfort-sense.js?v={version}")
    websocket_api.async_register_command(hass,ws_console)
    websocket_api.async_register_command(hass,ws_save)
