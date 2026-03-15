from __future__ import annotations

import logging
from typing import Any, Mapping

from homeassistant.components.persistent_notification import async_create as async_create_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, DOWNLOAD_URL_BASE, EXPORT_PROFILE_DETAILS
from .export_logic import async_export_context, build_effective_options

_LOGGER = logging.getLogger(__name__)


def get_runtime_data(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    """Return mutable runtime data for a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    return domain_data.setdefault(entry_id, {"last_export": None})


def get_entry_update_signal(entry_id: str) -> str:
    """Return the dispatcher signal used by entry entities."""
    return f"{DOMAIN}_{entry_id}_updated"


async def async_execute_export(
    hass: HomeAssistant,
    entry: ConfigEntry,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute an export and update runtime state."""
    options = build_effective_options(entry.options, overrides)

    try:
        result = await async_export_context(hass, options)
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("Export failed")
        raise HomeAssistantError(f"Context export failed: {err}") from err

    result_data = result.as_response()
    result_data["public_download_url"] = result_data.get("download_url")
    result_data["download_url"] = get_entry_download_url(entry.entry_id)
    runtime_data = get_runtime_data(hass, entry.entry_id)
    runtime_data["last_export"] = result_data
    async_dispatcher_send(hass, get_entry_update_signal(entry.entry_id))

    if options.create_notification:
        async_create_notification(
            hass,
            _build_export_notification_message(result_data),
            title="HA Context Exporter",
            notification_id=f"{DOMAIN}_{entry.entry_id}",
        )

    return result_data


async def async_show_last_download_link(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Expose the latest download link in a persistent notification."""
    last_export = get_runtime_data(hass, entry.entry_id).get("last_export")
    if not isinstance(last_export, dict) or not last_export.get("download_url"):
        raise HomeAssistantError(
            "No downloadable export is available yet. Export to a directory under /config/www first."
        )

    async_create_notification(
        hass,
        _build_download_notification_message(last_export),
        title="HA Context Exporter",
        notification_id=f"{DOMAIN}_{entry.entry_id}_download",
    )


def _build_export_notification_message(result: Mapping[str, Any]) -> str:
    profile = str(result.get("profile", "unknown"))
    profile_details = EXPORT_PROFILE_DETAILS.get(profile, "")
    message = (
        f"Export created: **{result.get('filename', 'unknown')}**\n\n"
        f"Profile: `{profile}`\n"
        f"Details: {profile_details}\n"
        f"Files: `{result.get('file_count', 0)}`\n"
        f"Size: `{result.get('bytes_written', 0)}` bytes\n"
        f"Path: `{result.get('absolute_path', 'n/a')}`\n"
    )
    if result.get("download_url"):
        message += (
            f"\n[Download latest export]({result['download_url']})\n\n"
            f"Direct URL: `{result['download_url']}`\n"
        )
    else:
        message += (
            "\nNo direct download URL is available. Configure `output_dir` inside `/config/www/...` "
            "to expose the ZIP through Home Assistant.\n"
        )
    return message


def _build_download_notification_message(result: Mapping[str, Any]) -> str:
    return (
        f"Latest export: **{result.get('filename', 'unknown')}**\n\n"
        f"[Download the ZIP]({result['download_url']})\n\n"
        f"Path: `{result.get('absolute_path', 'n/a')}`\n"
        f"Profile: `{result.get('profile', 'unknown')}`\n"
    )


def get_entry_download_url(entry_id: str) -> str:
    """Build the authenticated download URL for a config entry."""
    return f"{DOWNLOAD_URL_BASE}/{entry_id}"