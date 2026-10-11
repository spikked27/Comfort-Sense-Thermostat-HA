"""Control and learning diagnostics, accessible to dashboards and automations."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfTemperature
from .const import AVERAGE, DOMAIN
from .entity import ComfortSenseEntity


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Status(runtime), Duty(runtime), ActiveRoom(runtime),
        *[RoomTemperature(runtime,r) for r in runtime.plants], *[RoomOccupancy(runtime,r) for r in runtime.rooms]])


class ActiveRoom(ComfortSenseEntity, SensorEntity):
    """Actual control source, independent of the user's Auto/room selection."""
    def __init__(self,runtime): super().__init__(runtime,"active_room","Active room")

    @property
    def native_value(self): return self.runtime.active_source

    @property
    def extra_state_attributes(self):
        return {"selection":self.runtime.source,"reaction_time":self.runtime.config["reaction_time"]}


class RoomOccupancy(ComfortSenseEntity, SensorEntity):
    _attr_native_unit_of_measurement = "%"

    def __init__(self,runtime,room):
        self.room=room
        super().__init__(runtime,f"{room['id']}_occupancy",f"{room['name']} occupancy")

    @property
    def native_value(self): return round(self.runtime.room_data.get(self.room["id"],{}).get("occupancy",0)*100,1)


class Status(ComfortSenseEntity, SensorEntity):
    def __init__(self, runtime): super().__init__(runtime, "status", "Control status")

    @property
    def native_value(self): return self.runtime.reason

    @property
    def extra_state_attributes(self):
        return {"shadow": self.runtime.config["shadow"], "learning": self.runtime.learning_status,
                "schedules":self.runtime.schedule_status}


class Duty(ComfortSenseEntity, SensorEntity):
    _attr_native_unit_of_measurement = "%"

    def __init__(self, runtime): super().__init__(runtime, "duty", "Heat demand")

    @property
    def native_value(self): return round(self.runtime.duty*100, 1)

    @property
    def extra_state_attributes(self):
        r=self.runtime
        return {"cycle_minutes":r.config["pwm_seconds"]/60,
                "nominal_on_minutes":round(r.duty*r.config["pwm_seconds"]/60,2),
                "minimum_on_minutes":r.config["min_on_seconds"]/60,
                "minimum_off_minutes":r.config["min_off_seconds"]/60,
                "proposed_relay_on":r.proposed,"observed_relay_on":r.actual,
                "shadow_mode":r.config["shadow"]}


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
