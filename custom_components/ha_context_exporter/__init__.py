from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.persistent_notification import async_create as async_create_notification
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

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
    CONF_REDACT_LOCATION,
    CONF_REDACT_NETWORK,
    CONF_REDACT_URLS,
    DEFAULT_OPTIONS,
    DOMAIN,
    EXPORT_PROFILES,
    SERVICE_EXPORT_CONTEXT,
)
from .export_logic import async_export_context, build_effective_options

_LOGGER = logging.getLogger(__name__)

EXPORT_SERVICE_SCHEMA = vol.Schema(
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
        vol.Optional(CONF_CREATE_NOTIFICATION): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration domain and register services."""
    hass.data.setdefault(DOMAIN, {})

    async def async_handle_export_context(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data.get(CONF_CONFIG_ENTRY_ID))
        options = build_effective_options(entry.options, call.data)
        try:
            result = await async_export_context(hass, options)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Export failed")
            raise HomeAssistantError(f"Context export failed: {err}") from err

        runtime_data = hass.data[DOMAIN].setdefault(entry.entry_id, {})
        runtime_data["last_export"] = result.as_response()

        if options.create_notification:
            message = (
                f"Export created: **{result.filename}**\\n\\n"
                f"Path: `{result.absolute_path}`\\n"
            )
            if result.download_url:
                message += f"Download URL: `{result.download_url}`\\n"
            async_create_notification(
                hass,
                message,
                title="HA Context Exporter",
                notification_id=f"{DOMAIN}_{entry.entry_id}",
            )

        return result.as_response() if call.return_response else None

    if not hass.services.has_service(DOMAIN, SERVICE_EXPORT_CONTEXT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_EXPORT_CONTEXT,
            async_handle_export_context,
            schema=EXPORT_SERVICE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {"last_export": None})
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry after options update."""
    await hass.config_entries.async_reload(entry.entry_id)


def _resolve_entry(hass: HomeAssistant, config_entry_id: str | None) -> ConfigEntry:
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
