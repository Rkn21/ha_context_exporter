from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CONFIG_ENTRY_ID,
    CONF_CREATE_NOTIFICATION,
    CONF_EXPORT_PROFILE,
    CONF_FILENAME_PREFIX,
    CONF_INCLUDE_BLUEPRINTS,
    CONF_INCLUDE_CUSTOM_COMPONENTS,
    CONF_INCLUDE_DASHBOARDS,
    CONF_INCLUDE_LOGS,
    CONF_INCLUDE_PACKAGES,
    CONF_INCLUDE_STORAGE,
    CONF_INCLUDE_SUMMARY,
    CONF_INCLUDE_TEMPLATES,
    CONF_OUTPUT_DIR,
    CONF_PRIVACY_STRICT,
    CONF_REDACT_LOCATION,
    CONF_REDACT_NETWORK,
    CONF_REDACT_URLS,
    DOMAIN,
    EXPORT_PROFILES,
    PLATFORMS,
    SERVICE_EXPORT_CONTEXT,
)

if TYPE_CHECKING:
    from homeassistant.core import ServiceCall

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration domain and register services."""
    import voluptuous as vol

    from homeassistant.core import SupportsResponse
    from homeassistant.helpers import config_validation as cv

    from .http import HAContextExporterDownloadView
    from .runtime import async_execute_export

    hass.data.setdefault(DOMAIN, {})
    hass.http.register_view(HAContextExporterDownloadView(hass))

    export_service_schema = vol.Schema(
        {
            vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
            vol.Optional(CONF_EXPORT_PROFILE): vol.In(EXPORT_PROFILES),
            vol.Optional(CONF_OUTPUT_DIR): cv.string,
            vol.Optional(CONF_FILENAME_PREFIX): cv.string,
            vol.Optional(CONF_INCLUDE_PACKAGES): cv.boolean,
            vol.Optional(CONF_INCLUDE_TEMPLATES): cv.boolean,
            vol.Optional(CONF_INCLUDE_BLUEPRINTS): cv.boolean,
            vol.Optional(CONF_INCLUDE_DASHBOARDS): cv.boolean,
            vol.Optional(CONF_INCLUDE_STORAGE): cv.boolean,
            vol.Optional(CONF_INCLUDE_CUSTOM_COMPONENTS): cv.boolean,
            vol.Optional(CONF_INCLUDE_LOGS): cv.boolean,
            vol.Optional(CONF_INCLUDE_SUMMARY): cv.boolean,
            vol.Optional(CONF_REDACT_NETWORK): cv.boolean,
            vol.Optional(CONF_REDACT_URLS): cv.boolean,
            vol.Optional(CONF_REDACT_LOCATION): cv.boolean,
            vol.Optional(CONF_PRIVACY_STRICT): cv.boolean,
            vol.Optional(CONF_CREATE_NOTIFICATION): cv.boolean,
        }
    )

    async def async_handle_export_context(call: ServiceCall) -> dict[str, Any] | None:
        entry = _resolve_entry(hass, call.data.get(CONF_CONFIG_ENTRY_ID))
        result = await async_execute_export(hass, entry, call.data)
        return result if call.return_response else None

    if not hass.services.has_service(DOMAIN, SERVICE_EXPORT_CONTEXT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_EXPORT_CONTEXT,
            async_handle_export_context,
            schema=export_service_schema,
            supports_response=SupportsResponse.OPTIONAL,
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    from .runtime import get_runtime_data

    hass.data.setdefault(DOMAIN, {})
    get_runtime_data(hass, entry.entry_id)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry after options update."""
    await hass.config_entries.async_reload(entry.entry_id)


def _resolve_entry(hass: HomeAssistant, config_entry_id: str | None) -> ConfigEntry:
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.exceptions import ServiceValidationError

    if config_entry_id:
        entry = hass.config_entries.async_get_entry(config_entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError("Config entry not found for this integration")
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError("Selected config entry is not loaded")
        return entry

    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if not entries:
        raise ServiceValidationError("No loaded HA Context Exporter config entry found")
    if len(entries) > 1:
        raise ServiceValidationError(
            "Multiple entries found, provide config_entry_id in the service call"
        )
    return entries[0]
