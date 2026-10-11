"""Automatic, average, or manually pinned room source."""
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN
from .entity import ComfortSenseEntity


async def async_setup_entry(hass, entry, async_add_entities):
    runtime=hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RoomSource(runtime),SettingSelect(runtime,"reaction_time","Occupancy reaction time",
        {"Fast":"fast","Medium":"medium","Slow":"slow"}),
        SettingSelect(runtime,"average_tuning_mode","Average PID tuning",{"Manual":"manual","Automatic":"auto"}),
        *[SettingSelect(runtime,"tuning_mode",room["name"]+" PID tuning",{"Manual":"manual","Automatic":"auto"},room["id"])
            for room in runtime.rooms]])


class SettingSelect(ComfortSenseEntity,SelectEntity):
    _attr_entity_category=EntityCategory.CONFIG

    def __init__(self,runtime,key,label,choices,room_id=None):
        self.key,self.choices,self.room_id=key,choices,room_id
        self._attr_options=list(choices)
        super().__init__(runtime,f"config_{room_id+'_' if room_id else ''}{key}",label)

    @property
    def current_option(self):
        config=next(r for r in self.runtime.rooms if r["id"]==self.room_id) if self.room_id else self.runtime.config
        return next(label for label,value in self.choices.items() if value==config[self.key])

    async def async_select_option(self,option):
        if option not in self.choices:raise ServiceValidationError("Unknown setting")
        await self.runtime.configure({self.key:self.choices[option]},self.room_id)


class RoomSource(ComfortSenseEntity, SelectEntity):
    def __init__(self, runtime):
        super().__init__(runtime, "source", "Temperature source")
        self.names = {r["name"]: r["id"] for r in runtime.rooms}
        self._attr_options = ["Auto", "Average", *self.names]

    @property
    def current_option(self):
        return next((name for name,rid in self.names.items() if rid == self.runtime.source), self.runtime.source)

    async def async_select_option(self, option):
        if option not in self.options:
            raise ServiceValidationError("Unknown source")
        await self.runtime.change(source=self.names.get(option, option))
