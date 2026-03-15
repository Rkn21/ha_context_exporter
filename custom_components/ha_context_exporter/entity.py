from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NAME
from .runtime import get_entry_update_signal


class HAContextExporterBaseEntity(Entity):
    """Base entity shared by HA Context Exporter platforms."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, unique_suffix: str) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Home Assistant",
            model=NAME,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                get_entry_update_signal(self._entry.entry_id),
                self._async_handle_state_update,
            )
        )

    @callback
    def _async_handle_state_update(self) -> None:
        self.async_write_ha_state()