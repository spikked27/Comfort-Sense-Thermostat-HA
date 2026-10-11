"""Control and learning diagnostics, accessible to dashboards and automations."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfTemperature
from .const import AVERAGE, DOMAIN
from .entity import ComfortSenseEntity


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Status(runtime), Duty(runtime), *[RoomTemperature(runtime,r) for r in runtime.plants]])


class Status(ComfortSenseEntity, SensorEntity):
    def __init__(self, runtime): super().__init__(runtime, "status", "Control status")

    @property
    def native_value(self): return self.runtime.reason

    @property
    def extra_state_attributes(self):
        return {"shadow": self.runtime.config["shadow"], "learning": self.runtime.learning_status}


class Duty(ComfortSenseEntity, SensorEntity):
    _attr_native_unit_of_measurement = "%"

    def __init__(self, runtime): super().__init__(runtime, "duty", "Heat demand")

    @property
    def native_value(self): return round(self.runtime.duty*100, 1)


class RoomTemperature(ComfortSenseEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, runtime, room):
        self.room = room
        super().__init__(runtime, f"{room['id']}_temperature", f"{room['name']} temperature")

    @property
    def native_value(self): return self.runtime.room_data.get(self.room["id"], {}).get("temperature")

    @property
    def extra_state_attributes(self): return self.runtime.room_data.get(self.room["id"], {})
