from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {
    "absolute_path",
    "download_url",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict:
    """Return diagnostics for a config entry."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    payload = {
        "title": entry.title,
        "options": dict(entry.options),
        "last_export": runtime.get("last_export"),
    }
    return async_redact_data(payload, TO_REDACT)
