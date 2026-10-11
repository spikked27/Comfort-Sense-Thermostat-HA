"""Native climate control and preset actions."""
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import UnitOfTemperature
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from .const import DOMAIN
from .entity import ComfortSenseEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ComfortSenseClimate(hass.data[DOMAIN][entry.entry_id])])


class ComfortSenseClimate(ComfortSenseEntity, ClimateEntity):
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = ["comfort", "away", "sleep", "boost"]
    _attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
                                | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 5.0
    _attr_target_temperature_step = 0.1
    _attr_precision = 0.1

    def __init__(self, runtime):
        super().__init__(runtime, "climate", "Thermostat")

    @property
    def hvac_mode(self): return HVACMode(self.runtime.mode)

    @property
    def hvac_action(self):
        if self.runtime.mode == "off": return HVACAction.OFF
        if self.runtime.config["shadow"] or self.runtime.actual is None: return None
        return HVACAction.HEATING if self.runtime.actual else HVACAction.IDLE

    @property
    def preset_mode(self): return self.runtime.preset

    @property
    def current_temperature(self): return self.runtime.current_temperature

    @property
    def native_current_temperature(self): return self.runtime.current_temperature

    @property
    def target_temperature(self): return self.runtime.target_temperature

    @property
    def native_target_temperature(self): return self.runtime.target_temperature

    @property
    def max_temp(self): return min(27.0, self.runtime.config["max_temperature"] - 0.1)

    @property
    def extra_state_attributes(self):
        r = self.runtime
        return {"shadow_mode": r.config["shadow"], "control_reason": r.reason,
                "requested_duty_percent": round(r.duty*100, 1), "proposed_relay_on": r.proposed,
                "observed_relay_on": r.actual, "rooms": r.room_data,
                "schedules": r.schedule_plans,"schedule_status":r.schedule_status,
                "controller_temperature_unit":"°C",
                "boost_until": dt_util.utc_from_timestamp(r.boost_until).isoformat() if r.preset == "boost" else None}

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode not in self.hvac_modes:
            raise ServiceValidationError("Only heat and off are supported")
        await self.runtime.change(mode=str(hvac_mode))

    async def async_turn_on(self): await self.runtime.change(mode="heat")

    async def async_turn_off(self): await self.runtime.change(mode="off")

    async def async_set_preset_mode(self, preset_mode):
        if preset_mode not in self.preset_modes:
            raise ServiceValidationError("Unknown preset")
        until = dt_util.utcnow().timestamp() + self.runtime.config["boost_minutes"]*60 if preset_mode == "boost" else 0
        await self.runtime.change(preset=preset_mode, boost_until=until)

    async def async_set_temperature(self, **kwargs):
        temperature = kwargs.get("temperature")
        if temperature is None or not self.min_temp <= temperature <= self.max_temp:
            raise ServiceValidationError("Target outside supported range")
        # Main dial changes comfort targets for all rooms; individual number entities refine them.
        targets = {r["id"]: temperature for r in self.runtime.rooms}
        await self.runtime.change(targets=targets, preset="comfort", boost_until=0)
