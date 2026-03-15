from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import EXPORT_PROFILE_DETAILS
from .entity import HAContextExporterBaseEntity
from .runtime import get_runtime_data


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensor entities for a config entry."""
    async_add_entities([HAContextExporterLastExportSensor(entry)])


class HAContextExporterLastExportSensor(HAContextExporterBaseEntity, SensorEntity):
    """Sensor exposing metadata for the latest export."""

    _attr_name = "Last export"
    _attr_icon = "mdi:archive-clock-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "last_export")

    @property
    def native_value(self) -> datetime | None:
        last_export = self._last_export
        created_at = last_export.get("created_at") if last_export else None
        if not created_at:
            return None
        return datetime.fromisoformat(created_at)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        last_export = self._last_export
        if not last_export:
            return None

        profile = str(last_export.get("profile", "unknown"))
        return {
            "filename": last_export.get("filename"),
            "absolute_path": last_export.get("absolute_path"),
            "download_url": last_export.get("download_url"),
            "public_download_url": last_export.get("public_download_url"),
            "has_signed_download_url": bool(last_export.get("download_url")),
            "file_count": last_export.get("file_count"),
            "excluded_count": last_export.get("excluded_count"),
            "bytes_written": last_export.get("bytes_written"),
            "profile": profile,
            "profile_details": EXPORT_PROFILE_DETAILS.get(profile),
        }

    @property
    def _last_export(self) -> dict[str, Any] | None:
        if self.hass is None:
            return None
        last_export = get_runtime_data(self.hass, self._entry.entry_id).get("last_export")
        return last_export if isinstance(last_export, dict) else None