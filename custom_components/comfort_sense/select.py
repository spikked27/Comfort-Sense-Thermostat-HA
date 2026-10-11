"""Automatic, average, or manually pinned room source."""
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import ServiceValidationError
from .const import DOMAIN
from .entity import ComfortSenseEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([RoomSource(hass.data[DOMAIN][entry.entry_id])])


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
