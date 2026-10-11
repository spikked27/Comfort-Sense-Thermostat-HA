"""Remove obsolete room targets: the thermostat owns one setpoint."""
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.exceptions import ServiceValidationError
from .const import DOMAIN
from .entity import ComfortSenseEntity
from .units import display_rate, native_rate


async def async_setup_entry(hass, entry, async_add_entities):
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain == "number" and entity.platform == "comfort_sense" and entity.unique_id.endswith("_target"):
            registry.async_remove(entity.entity_id)
    runtime=hass.data[DOMAIN][entry.entry_id]
    entities=[SettingNumber(runtime,"occupancy_margin","Occupancy grouping tolerance",0,100,1,"%")]
    for key,label in [("away_temperature","Away temperature"),("sleep_temperature","Sleep temperature"),("boost_temperature","Boost temperature")]:
        entities.append(SettingNumber(runtime,key,label,5,27,0.1,temperature=True))
    for key,low,high,step in [("kp",0,2,0.01),("ki",0,0.001,0.000001),("kd",0,3600,1)]:
        entities.append(SettingNumber(runtime,"average_"+key,"Average manual "+key.upper(),low,high,step))
    for room in runtime.rooms:
        for key,label in [("hot_buffer","Warm buffer"),("cold_buffer","Cold buffer")]:
            entities.append(SettingNumber(runtime,key,room["name"]+" "+label,0,10,0.1,room_id=room["id"],delta=True))
        for key,low,high,step in [("kp",0,2,0.01),("ki",0,0.001,0.000001),("kd",0,3600,1)]:
            entities.append(SettingNumber(runtime,key,room["name"]+" manual "+key.upper(),low,high,step,room_id=room["id"]))
    async_add_entities(entities)


class SettingNumber(ComfortSenseEntity, NumberEntity):
    _attr_entity_category=EntityCategory.CONFIG
    _attr_mode=NumberMode.BOX

    def __init__(self,runtime,key,label,low,high,step,unit=None,room_id=None,delta=False,temperature=False):
        self.key,self.room_id,self.delta,self.temperature=key,room_id,delta,temperature
        self.low,self.high=low,high
        super().__init__(runtime,f"config_{room_id+'_' if room_id else ''}{key}",label)
        self._attr_native_step=step
        self._attr_native_unit_of_measurement=unit
        if temperature:
            self._attr_device_class=NumberDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement=UnitOfTemperature.CELSIUS

    @property
    def unit(self):return str(self.runtime.hass.config.units.temperature_unit)

    @property
    def native_unit_of_measurement(self):
        return self.unit if self.delta else self._attr_native_unit_of_measurement

    @property
    def native_min_value(self):return display_rate(self.low,self.unit) if self.delta else self.low

    @property
    def native_max_value(self):
        high=min(self.high,self.runtime.config["max_temperature"]-0.1) if self.temperature else self.high
        return display_rate(high,self.unit) if self.delta else high

    @property
    def native_value(self):
        config=next(r for r in self.runtime.rooms if r["id"]==self.room_id) if self.room_id else self.runtime.config
        value=config[self.key]
        return display_rate(value,self.unit) if self.delta else value

    async def async_set_native_value(self,value):
        try:
            await self.runtime.configure({self.key:native_rate(value,self.unit) if self.delta else value},self.room_id)
        except (ValueError,TypeError) as err:
            raise ServiceValidationError(str(err)) from err
