"""Per-room comfort targets (native C, explicitly labelled)."""
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.exceptions import ServiceValidationError
from .const import DOMAIN
from .entity import ComfortSenseEntity


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RoomTarget(runtime, room) for room in runtime.rooms])


class RoomTarget(ComfortSenseEntity, NumberEntity):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_min_value = 5
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(self, runtime, room):
        self.room = room
        super().__init__(runtime, f"{room['id']}_target", f"{room['name']} comfort target")
        self._attr_native_max_value = min(27, runtime.config["max_temperature"]-0.1)

    @property
    def native_value(self): return self.runtime.targets.get(self.room["id"], self.room["target"])

    async def async_set_native_value(self, value):
        if not self.native_min_value <= value <= self.native_max_value:
            raise ServiceValidationError("Room target outside supported range")
        await self.runtime.change(targets={**self.runtime.targets, self.room["id"]: value})
