"""Native setup: heating system, repeatable rooms, review; options support room edits."""
from copy import deepcopy
import uuid
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .const import DEFAULTS, DOMAIN
from .settings import validate


def entity(domains, multiple=False):
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domains, multiple=multiple))


def number(low, high, unit=None):
    config = {"min":low,"max":high,"step":"any","mode":"box"}
    if unit is not None:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(selector.NumberSelectorConfig(**config))


def system_schema(config):
    c = {**DEFAULTS, **config}
    fields = {
        vol.Required("name", default=c["name"]): str,
        vol.Required("heater", **({"default": c["heater"]} if c.get("heater") else {})): entity("switch"),
        vol.Optional("outdoor_sensor", **({"default": c["outdoor_sensor"]} if c["outdoor_sensor"] else {})): entity("sensor"),
        vol.Optional("home_sensor", **({"default": c["home_sensor"]} if c["home_sensor"] else {})): entity(["binary_sensor", "person", "device_tracker", "zone"]),
        vol.Required("shadow", default=c["shadow"]): bool,
        vol.Required("average_tuning_mode", default=c["average_tuning_mode"]):
            vol.In({"manual":"Manual average PID gains", "auto":"Automatic average tuning"}),
    }
    limits = {
        "away_temperature": (5,27,"°C"), "boost_temperature": (5,27,"°C"),
        "sleep_temperature": (5,27,"°C"), "max_temperature": (10,35,"°C"),
        "boost_minutes": (1,240,"min"), "away_delay_minutes": (0,180,"min"),
        "occupancy_rise_minutes": (1,60,"min"), "occupancy_decay_minutes": (1,180,"min"),
        "sensor_timeout_minutes": (5,1440,"min"), "min_on_seconds": (30,3600,"s"),
        "min_off_seconds": (30,3600,"s"), "pwm_seconds": (120,7200,"s"),
        "max_preheat_minutes": (15,480,"min"), "fallback_heat_rate": (0.1,5,"°C/h"),
        "average_kp": (0,2,None), "average_ki": (0,0.001,None), "average_kd": (0,3600,None),
    }
    for key, args in limits.items():
        fields[vol.Required(key, default=c[key])] = number(*args)
    if c.get("rooms"):
        fields[vol.Optional("sleep_room", default=c["sleep_room"])] = vol.In({"": "Average", **{r["id"]:r["name"] for r in c["rooms"]}})
    return vol.Schema(fields)


def room_schema(room=None):
    r = room or {}
    return vol.Schema({
        vol.Required("name", default=r.get("name", "")): str,
        vol.Required("temperature_sensors", default=r.get("temperature_sensors", [])): entity("sensor", True),
        vol.Optional("occupancy_sensors", default=r.get("occupancy_sensors", [])): entity("binary_sensor", True),
        vol.Required("target", default=r.get("target", 21.0)): number(5,27,"°C"),
        vol.Required("tuning_mode", default=r.get("tuning_mode", "manual")):
            vol.In({"manual":"Manual PID gains", "auto":"Automatic validated room tuning"}),
        vol.Required("kp", default=r.get("kp", 0.2)): number(0,2),
        vol.Required("ki", default=r.get("ki", 0.000035)): number(0,0.001),
        vol.Required("kd", default=r.get("kd", 0.0)): number(0,3600),
        vol.Required("morning_enabled", default=r.get("morning_enabled", False)): bool,
        vol.Required("morning_time", default=r.get("morning_time", "07:00")): str,
        vol.Required("morning_target", default=r.get("morning_target", 21.0)): number(5,27,"°C"),
        vol.Required("morning_duration", default=r.get("morning_duration", 60)): number(1,240,"min"),
        vol.Required("morning_days", default=[str(x) for x in r.get("morning_days", [0,1,2,3,4])]):
            selector.SelectSelector(selector.SelectSelectorConfig(multiple=True, options=[
                {"value":str(i), "label": day} for i,day in enumerate(["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"])])),
    })


class Editor:
    config: dict
    editing: str | None = None

    async def async_step_system(self, user_input=None):
        errors = {}
        if user_input is not None:
            candidate = {**self.config, **user_input}
            # Omitted optional fields are deliberate removals when editing.
            candidate["home_sensor"] = user_input.get("home_sensor", "")
            candidate["outdoor_sensor"] = user_input.get("outdoor_sensor", "")
            heater = candidate.get("heater")
            entries = self.hass.config_entries.async_entries(DOMAIN)
            current = getattr(getattr(self, "config_entry", None), "entry_id", None)
            if any(e.entry_id != current and {**e.data, **e.options}.get("heater") == heater for e in entries):
                errors["base"] = "heater_already_configured"
            elif not self.hass.states.get(heater):
                errors["base"] = "heater_missing"
            else:
                self.config = candidate
                return await self.async_step_manage()
        return self.async_show_form(step_id="system", data_schema=system_schema(self.config), errors=errors)

    async def async_step_manage(self, user_input=None):
        rooms = self.config.get("rooms", [])
        if user_input is not None:
            action = user_input["action"]
            if action == "add":
                self.editing = None
                return await self.async_step_room()
            if action == "system": return await self.async_step_system()
            if action == "finish": return await self.async_step_review()
            self.editing = action.split(":", 1)[1]
            if action.startswith("remove:"):
                self.config["rooms"] = [r for r in rooms if r["id"] != self.editing]
                if self.config.get("sleep_room") == self.editing:
                    self.config["sleep_room"] = ""
                return await self.async_step_manage()
            return await self.async_step_room()
        choices = {"add":"Add room", "system":"Heating system settings"}
        for r in rooms:
            choices[f"edit:{r['id']}"] = f"Edit {r['name']}"
            choices[f"remove:{r['id']}"] = f"Remove {r['name']}"
        if rooms: choices["finish"] = "Review and finish"
        return self.async_show_form(step_id="manage", data_schema=vol.Schema({vol.Required("action"): vol.In(choices)}))

    async def async_step_room(self, user_input=None):
        existing = next((r for r in self.config.get("rooms",[]) if r["id"] == self.editing), None)
        errors = {}
        if user_input is not None:
            try:
                room = {**user_input, "id": self.editing or uuid.uuid4().hex,
                        "name": user_input["name"].strip(),
                        "occupancy_sensors": user_input.get("occupancy_sensors", []),
                        "morning_days": [int(d) for d in user_input["morning_days"]]}
                rooms = [r for r in self.config.get("rooms",[]) if r["id"] != self.editing] + [room]
                if not room["name"]:
                    raise ValueError("Room name required")
                validate({**self.config, "rooms": rooms})
                for e in room["temperature_sensors"]:
                    state = self.hass.states.get(e)
                    if not state or state.attributes.get("unit_of_measurement") not in ("°C", "°F", "K"):
                        raise ValueError("Select temperature entities with a known unit")
                self.config["rooms"] = rooms
                return await self.async_step_manage()
            except (ValueError, TypeError, KeyError):
                errors["base"] = "invalid_room"
        return self.async_show_form(step_id="room", data_schema=room_schema(existing), errors=errors)

    async def async_step_review(self, user_input=None):
        try:
            checked = validate(self.config)
        except (ValueError, KeyError, TypeError):
            return self.async_show_form(step_id="review", data_schema=vol.Schema({}), errors={"base":"invalid_config"},
                description_placeholders={"summary":"Go back and correct settings or rooms."})
        summary = (f"{len(checked['rooms'])} rooms; heater {checked['heater']}; "
                   f"{'shadow observations only' if checked['shadow'] else 'ACTIVE RELAY CONTROL'}; "
                   f"{sum(r['tuning_mode'] == 'auto' for r in checked['rooms'])} rooms with automatic tuning. "
                   "Disable any other controller of this relay before enabling active control.")
        if user_input is not None:
            return self.finish(checked)
        return self.async_show_form(step_id="review", data_schema=vol.Schema({}), description_placeholders={"summary":summary})


class ComfortSenseConfigFlow(Editor, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self): self.config = {**DEFAULTS, "rooms": []}

    async def async_step_user(self, user_input=None): return await self.async_step_system(user_input)

    def finish(self, checked):
        return self.async_create_entry(title=checked["name"], data=checked)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry): return ComfortSenseOptionsFlow()


class ComfortSenseOptionsFlow(Editor, config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if not hasattr(self, "config"):
            self.config = deepcopy({**self.config_entry.data, **self.config_entry.options})
        return await self.async_step_manage(user_input)

    def finish(self, checked): return self.async_create_entry(title="", data=checked)
