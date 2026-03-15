from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import HAContextExporterBaseEntity
from .runtime import async_execute_export, async_show_last_download_link, get_runtime_data


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up button entities for a config entry."""
    async_add_entities(
        [
            HAContextExporterRunExportButton(entry),
            HAContextExporterDownloadButton(entry),
        ]
    )


class HAContextExporterRunExportButton(HAContextExporterBaseEntity, ButtonEntity):
    """Button entity that triggers a new export."""

    _attr_name = "Export context"
    _attr_icon = "mdi:archive-arrow-down-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "run_export")

    async def async_press(self) -> None:
        """Trigger a new export using the current config entry options."""
        await async_execute_export(self.hass, self._entry)


class HAContextExporterDownloadButton(HAContextExporterBaseEntity, ButtonEntity):
    """Button entity that exposes the latest download link in the UI."""

    _attr_name = "Download latest export"
    _attr_icon = "mdi:file-download-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "download_latest_export")

    @property
    def available(self) -> bool:
        if self.hass is None:
            return False
        last_export = get_runtime_data(self.hass, self._entry.entry_id).get("last_export")
        return isinstance(last_export, dict) and bool(last_export.get("download_url"))

    async def async_press(self) -> None:
        """Show the latest download link in a persistent notification."""
        await async_show_last_download_link(self.hass, self._entry)