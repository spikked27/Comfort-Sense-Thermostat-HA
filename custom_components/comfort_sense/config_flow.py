"""Setup and independent options for equipment, rooms and native HA schedules."""
from copy import deepcopy
import uuid
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .const import DEFAULTS, DOMAIN
from .settings import validate
from .scheduling import migrate_config
from .units import display_temperature, native_temperature, display_rate, native_rate

TEMPERATURE_FIELDS=("comfort_temperature","away_temperature","boost_temperature","sleep_temperature","max_temperature")


def entity(domains, multiple=False):
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domains,multiple=multiple))


def number(low,high,unit=None):
    config={"min":low,"max":high,"step":"any","mode":"box"}
    if unit is not None:
        config["unit_of_measurement"]=unit
    return selector.NumberSelector(selector.NumberSelectorConfig(**config))


def temperature(low,high,unit):
    return number(round(display_temperature(low,unit),3),round(display_temperature(high,unit),3),unit)


def system_schema(config,unit="°C"):
    c={**DEFAULTS,**config}
    fields={
        vol.Required("name",default=c["name"]):str,
        vol.Required("heater",**({"default":c["heater"]} if c.get("heater") else {})):entity("switch"),
        vol.Optional("outdoor_sensor",**({"default":c["outdoor_sensor"]} if c["outdoor_sensor"] else {})):entity("sensor"),
        vol.Optional("home_sensor",**({"default":c["home_sensor"]} if c["home_sensor"] else {})):entity(["binary_sensor","person","device_tracker","zone"]),
        vol.Required("shadow",default=c["shadow"]):bool,
        vol.Required("reaction_time",default=c["reaction_time"]):vol.In({"fast":"Fast (10-minute history)","medium":"Medium (30-minute history)","slow":"Slow (60-minute history)"}),
    }
    return vol.Schema(fields)


def room_schema(room=None,unit="°C"):
    r=room or {}
    return vol.Schema({
        vol.Required("name",default=r.get("name","")):str,
        vol.Required("temperature_sensors",default=r.get("temperature_sensors",[])):entity("sensor",True),
        vol.Optional("occupancy_sensors",default=r.get("occupancy_sensors",[])):entity("binary_sensor",True),
        vol.Required("tuning_mode",default=r.get("tuning_mode","auto")):vol.In({"auto":"Automatic validated room tuning","manual":"Manual PID gains"}),
    })


def source_choices(config):
    return {"Auto":"Occupancy priority","Average":"Whole-home average",**{r["id"]:r["name"] for r in config.get("rooms",[])}}


def schedule_schema(config,binding=None,unit="°C"):
    b=binding or {}
    return vol.Schema({
        vol.Required("name",default=b.get("name","")):str,
        vol.Required("entity_id",**({"default":b["entity_id"]} if b.get("entity_id") else {})):entity("schedule"),
        vol.Required("source",default=b.get("source","Average")):vol.In(source_choices(config)),
        vol.Required("target",default=round(display_temperature(b.get("target",21),unit),3)):temperature(5,27,unit),
        vol.Required("preheat",default=b.get("preheat",True)):bool,
    })


class Editor:
    config:dict
    editing:str|None=None
    form_unit:str="°C"

    @property
    def unit(self):
        return str(self.hass.config.units.temperature_unit)

    @property
    def options_editor(self):
        return isinstance(self,config_entries.OptionsFlow)

    async def next_menu(self):
        return await self.async_step_init() if self.options_editor else await self.async_step_manage()

    async def async_step_system(self,user_input=None):
        errors={}
        if user_input is not None:
            values=dict(user_input)
            for key in TEMPERATURE_FIELDS:
                if key in values:
                    values[key]=native_temperature(values[key],self.form_unit)
            candidate={**self.config,**values}
            candidate["home_sensor"]=user_input.get("home_sensor","")
            candidate["outdoor_sensor"]=user_input.get("outdoor_sensor","")
            heater=candidate.get("heater")
            current=self.config_entry.entry_id if self.options_editor else None
            if any(e.entry_id!=current and {**e.data,**e.options}.get("heater")==heater for e in self.hass.config_entries.async_entries(DOMAIN)):
                errors["base"]="heater_already_configured"
            elif not self.hass.states.get(heater):
                errors["base"]="heater_missing"
            else:
                self.config=candidate
                return await self.next_menu()
        self.form_unit=self.unit
        return self.async_show_form(step_id="system",data_schema=system_schema(self.config,self.form_unit),
                                   errors=errors,description_placeholders={"temperature_unit":self.form_unit})

    async def async_step_manage(self,user_input=None):
        rooms=self.config.get("rooms",[])
        if user_input is not None:
            action=user_input["action"]
            if action=="add":
                self.editing=None
                return await self.async_step_room()
            if action=="back":return await self.async_step_init()
            if action=="finish":return await self.async_step_review()
            self.editing=action.split(":",1)[1]
            if action.startswith("remove:"):
                self.config["rooms"]=[r for r in rooms if r["id"]!=self.editing]
                if self.config.get("sleep_room")==self.editing:self.config["sleep_room"]=""
                return await self.async_step_manage()
            return await self.async_step_room()
        choices={"add":"Add room"}
        for r in rooms:
            choices[f"edit:{r['id']}"]=f"Edit {r['name']}"
            choices[f"remove:{r['id']}"]=f"Remove {r['name']}"
        if self.options_editor:choices["back"]="Back to configuration"
        if rooms:choices["finish"]="Review and save"
        return self.async_show_form(step_id="manage",data_schema=vol.Schema({vol.Required("action"):vol.In(choices)}))

    async def async_step_room(self,user_input=None):
        existing=next((r for r in self.config.get("rooms",[]) if r["id"]==self.editing),None)
        errors={}
        if user_input is not None:
            try:
                room={**(existing or {}),**user_input,"id":self.editing or uuid.uuid4().hex,
                      "name":user_input["name"].strip(),"occupancy_sensors":user_input.get("occupancy_sensors",[]),
                      "target":self.config["comfort_temperature"]}
                rooms=[r for r in self.config.get("rooms",[]) if r["id"]!=self.editing]+[room]
                if not room["name"]:raise ValueError("Room name required")
                validate({**self.config,"rooms":rooms})
                for e in room["temperature_sensors"]:
                    state=self.hass.states.get(e)
                    if not state or (state.attributes.get("unit_of_measurement") not in ("°C","°F","K") and state.attributes.get("device_class") != "temperature"):
                        raise ValueError("Select temperature sensors")
                self.config["rooms"]=rooms
                if room.get("tuning_mode","auto")=="manual":
                    self.editing=room["id"]
                    return await self.async_step_room_gains()
                return await self.async_step_manage()
            except (ValueError,TypeError,KeyError):
                errors["base"]="invalid_room"
        self.form_unit=self.unit
        shown={**(existing or {}),**(user_input or {})}
        return self.async_show_form(step_id="room",data_schema=room_schema(shown,self.form_unit),errors=errors,
                                   description_placeholders={"temperature_unit":self.form_unit})

    async def async_step_room_gains(self,user_input=None):
        room=next(r for r in self.config["rooms"] if r["id"]==self.editing)
        if user_input is not None:
            room.update(user_input)
            return await self.async_step_manage()
        return self.async_show_form(step_id="room_gains",data_schema=vol.Schema({
            vol.Required(k,default=room.get(k,d)):number(0,high)
            for k,d,high in [("kp",0.2,2),("ki",0.000035,0.001),("kd",0,3600)]
        }),description_placeholders={"room":room["name"]})

    async def async_step_advanced(self,user_input=None):
        return self.async_show_menu(step_id="advanced",menu_options=["presets","relay","average_pid","init"])

    async def async_step_presets(self,user_input=None):
        if user_input is not None:
            values=dict(user_input)
            for key in ("away_temperature","sleep_temperature","boost_temperature"):
                values[key]=native_temperature(values[key],self.form_unit)
            self.config.update(values)
            return await self.async_step_advanced()
        self.form_unit=self.unit
        fields={vol.Required(k,default=round(display_temperature(self.config[k],self.unit),3)):temperature(5,27,self.unit)
            for k in ("away_temperature","sleep_temperature","boost_temperature")}
        fields.update({vol.Required(k,default=self.config[k]):number(*args) for k,args in {
            "boost_minutes":(1,240,"min"),"away_delay_minutes":(0,180,"min")}.items()})
        fields[vol.Optional("sleep_room",default=self.config["sleep_room"])]=vol.In({"":"Use thermostat source",**{r["id"]:r["name"] for r in self.config["rooms"]}})
        return self.async_show_form(step_id="presets",data_schema=vol.Schema(fields),description_placeholders={"temperature_unit":self.unit})

    async def async_step_relay(self,user_input=None):
        errors={}
        if user_input is not None:
            values=dict(user_input)
            values["max_temperature"]=native_temperature(values["max_temperature"],self.form_unit)
            if values["pwm_seconds"] < values["min_on_seconds"]+values["min_off_seconds"]:
                errors["base"]="invalid_cycle"
            else:
                self.config.update(values)
                return await self.async_step_advanced()
        self.form_unit=self.unit
        fields={vol.Required(k,default=self.config[k]):number(*args) for k,args in {
            "sensor_timeout_minutes":(5,1440,"min"),"min_on_seconds":(30,3600,"s"),
            "min_off_seconds":(30,3600,"s"),"pwm_seconds":(120,7200,"s")}.items()}
        fields[vol.Required("max_temperature",default=round(display_temperature(self.config["max_temperature"],self.unit),3))]=temperature(10,35,self.unit)
        return self.async_show_form(step_id="relay",data_schema=vol.Schema(fields),errors=errors,description_placeholders={"temperature_unit":self.unit})

    async def async_step_average_pid(self,user_input=None):
        if user_input is not None:
            self.config.update(user_input)
            return await self.async_step_average_gains() if user_input["average_tuning_mode"]=="manual" else await self.async_step_advanced()
        return self.async_show_form(step_id="average_pid",data_schema=vol.Schema({
            vol.Required("average_tuning_mode",default=self.config["average_tuning_mode"]):vol.In({"manual":"Manual gains","auto":"Automatic validated tuning"})}))

    async def async_step_average_gains(self,user_input=None):
        if user_input is not None:
            self.config.update(user_input)
            return await self.async_step_advanced()
        return self.async_show_form(step_id="average_gains",data_schema=vol.Schema({
            vol.Required("average_"+k,default=self.config["average_"+k]):number(0,high)
            for k,high in [("kp",2),("ki",0.001),("kd",3600)]}))

    async def async_step_schedules(self,user_input=None):
        bindings=self.config.get("schedules",[])
        if user_input is not None:
            action=user_input["action"]
            if action=="add":
                self.editing=None
                return await self.async_step_schedule()
            if action=="settings":return await self.async_step_schedule_settings()
            if action=="morning":return await self.async_step_morning()
            if action=="alarm_window":return await self.async_step_alarm_window()
            if action=="alarm_owner":return await self.async_step_alarm_owner()
            if action=="back":return await self.next_menu()
            if action=="finish":return await self.async_step_review()
            self.editing=action.split(":",1)[1]
            if action.startswith("details:"):
                return await self.async_step_schedule_details()
            if action.startswith("remove:"):
                self.config["schedules"]=[s for s in bindings if s["id"]!=self.editing]
                return await self.async_step_schedules()
            return await self.async_step_schedule()
        choices={"add":"Connect a Schedule helper","morning":"Morning comfort from phone alarms",
                 "alarm_window":"Wake-up alarm time window (advanced)","settings":"Warm-up planning settings"}
        if self.config.get("alarm_sensors"):
            choices["alarm_owner"]="Associate an alarm with a person (optional)"
        for b in bindings:
            suffix=" (migrated)" if not b.get("entity_id") else ""
            choices[f"edit:{b['id']}"]=f"Edit {b['name']}{suffix}"
            choices[f"details:{b['id']}"]=f"Advanced settings for {b['name']}"
            choices[f"remove:{b['id']}"]=f"Remove {b['name']}"
        choices.update(back="Back to configuration",finish="Review and save")
        return self.async_show_form(step_id="schedules",data_schema=vol.Schema({vol.Required("action"):vol.In(choices)}))

    async def async_step_schedule(self,user_input=None):
        existing=next((s for s in self.config.get("schedules",[]) if s["id"]==self.editing),None)
        errors={}
        if user_input is not None:
            try:
                binding={"priority":0,"data_temperature_unit":self.unit,**(existing or {}),**user_input,"id":self.editing or uuid.uuid4().hex,"name":user_input["name"].strip(),
                         "target":native_temperature(user_input["target"],self.form_unit)}
                if not self.hass.states.get(binding["entity_id"]):raise ValueError("Schedule missing")
                bindings=[s for s in self.config.get("schedules",[]) if s["id"]!=self.editing]+[binding]
                validate({**self.config,"schedules":bindings})
                self.config["schedules"]=bindings
                return await self.async_step_schedules()
            except (ValueError,KeyError,TypeError):
                errors["base"]="invalid_schedule"
        self.form_unit=self.unit
        return self.async_show_form(step_id="schedule",data_schema=schedule_schema(self.config,existing,self.form_unit),
                                   errors=errors,description_placeholders={"temperature_unit":self.form_unit})

    async def async_step_schedule_details(self,user_input=None):
        binding=next(b for b in self.config["schedules"] if b["id"]==self.editing)
        if user_input is not None:
            binding.update(user_input)
            return await self.async_step_schedules()
        return self.async_show_form(step_id="schedule_details",data_schema=vol.Schema({
            vol.Required("priority",default=binding.get("priority",0)):number(0,100),
            vol.Required("data_temperature_unit",default=binding.get("data_temperature_unit",self.unit)):vol.In(["°C","°F"]),
        }))

    async def async_step_schedule_settings(self,user_input=None):
        if user_input is not None:
            self.config.update(max_preheat_minutes=user_input["max_preheat_minutes"],
                               fallback_heat_rate=native_rate(user_input["fallback_heat_rate"],self.form_unit))
            return await self.async_step_schedules()
        self.form_unit=self.unit
        return self.async_show_form(step_id="schedule_settings",data_schema=vol.Schema({
            vol.Required("max_preheat_minutes",default=self.config["max_preheat_minutes"]):number(15,480,"min"),
            vol.Required("fallback_heat_rate",default=display_rate(self.config["fallback_heat_rate"],self.form_unit)):
                number(display_rate(0.1,self.form_unit),display_rate(5,self.form_unit),self.form_unit+"/h"),
        }),description_placeholders={"temperature_unit":self.form_unit})

    async def async_step_morning(self,user_input=None):
        errors={}
        if user_input is not None:
            try:
                candidate={**self.config,**user_input,
                    "morning_target":native_temperature(user_input["morning_target"],self.form_unit)}
                candidate["alarm_owners"]={e:p for e,p in self.config["alarm_owners"].items() if e in candidate["alarm_sensors"]}
                validate(candidate)
                for eid in candidate["alarm_sensors"]:
                    state=self.hass.states.get(eid)
                    if state is None or state.attributes.get("device_class")!="timestamp":
                        raise ValueError("Select next-alarm timestamp sensors")
                self.config=candidate
                return await self.async_step_schedules()
            except (ValueError,TypeError,KeyError):
                errors["base"]="invalid_morning"
        self.form_unit=self.unit
        c={**self.config,**(user_input or {})}
        target=(user_input["morning_target"] if user_input else display_temperature(c["morning_target"],self.unit))
        return self.async_show_form(step_id="morning",data_schema=vol.Schema({
            vol.Required("morning_enabled",default=c["morning_enabled"]):bool,
            vol.Required("alarm_sensors",default=c["alarm_sensors"]):entity("sensor",True),
            vol.Required("morning_target",default=round(target,3)):temperature(5,27,self.unit),
            vol.Required("morning_source",default=c["morning_source"]):vol.In(source_choices(self.config)),
            vol.Required("morning_duration",default=c["morning_duration"]):number(1,240,"min"),
        }),errors=errors,description_placeholders={"temperature_unit":self.unit})

    async def async_step_alarm_window(self,user_input=None):
        errors={}
        if user_input is not None:
            try:
                candidate={**self.config,**user_input}
                validate(candidate)
                self.config=candidate
                return await self.async_step_schedules()
            except (ValueError,TypeError):
                errors["base"]="invalid_alarm_window"
        c={**self.config,**(user_input or {})}
        return self.async_show_form(step_id="alarm_window",data_schema=vol.Schema({
            vol.Required("alarm_window_start",default=c["alarm_window_start"]):selector.TimeSelector(),
            vol.Required("alarm_window_end",default=c["alarm_window_end"]):selector.TimeSelector(),
        }),errors=errors)

    async def async_step_alarm_owner(self,user_input=None):
        if user_input is not None:
            eid=user_input["alarm_sensor"]
            if eid in self.config["alarm_sensors"]:
                if user_input.get("person"):
                    self.config["alarm_owners"][eid]=user_input["person"]
                else:
                    self.config["alarm_owners"].pop(eid,None)
            return await self.async_step_schedules()
        return self.async_show_form(step_id="alarm_owner",data_schema=vol.Schema({
            vol.Required("alarm_sensor"):vol.In(self.config["alarm_sensors"]),
            vol.Optional("person"):entity("person"),
        }),description_placeholders={"owners":", ".join(f"{e}: {p}" for e,p in self.config["alarm_owners"].items()) or "None"})

    async def async_step_review(self,user_input=None):
        if user_input and user_input.get("action")=="back":return await self.next_menu()
        schema=vol.Schema({vol.Optional("action",default="save"):vol.In({"save":"Save configuration","back":"Back to configuration"})})
        try:
            checked=validate(self.config)
        except (ValueError,KeyError,TypeError):
            return self.async_show_form(step_id="review",data_schema=schema,errors={"base":"invalid_config"},
                description_placeholders={"summary":"Check system, room and schedule settings. Use Back to correct them."})
        summary=(f"{len(checked['rooms'])} rooms, {len(checked['schedules'])} schedules; "
                 f"{'shadow observations only' if checked['shadow'] else 'ACTIVE RELAY CONTROL'}. "
                 "Disable any other controller of this relay before enabling active control.")
        if user_input is not None:return self.finish(checked)
        return self.async_show_form(step_id="review",data_schema=schema,description_placeholders={"summary":summary})


class ComfortSenseConfigFlow(Editor,config_entries.ConfigFlow,domain=DOMAIN):
    VERSION=4

    def __init__(self):self.config=deepcopy({**DEFAULTS,"rooms":[]})

    async def async_step_user(self,user_input=None):return await self.async_step_system(user_input)

    def finish(self,checked):return self.async_create_entry(title=checked["name"],data=checked)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):return ComfortSenseOptionsFlow()


class ComfortSenseOptionsFlow(Editor,config_entries.OptionsFlow):
    async def async_step_init(self,user_input=None):
        if not hasattr(self,"config"):
            self.config={**deepcopy(DEFAULTS),**migrate_config({**self.config_entry.data,**self.config_entry.options})}
        return self.async_show_menu(step_id="init",menu_options=["system","manage","schedules","advanced","review"])

    def finish(self,checked):return self.async_create_entry(title="",data=checked)
