from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from aiohttp import web
from aiohttp.hdrs import CONTENT_DISPOSITION, CONTENT_TYPE

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOWNLOAD_URL_BASE
from .runtime import get_runtime_data


class HAContextExporterDownloadView(HomeAssistantView):
    """Authenticated download endpoint for the latest generated export."""

    url = f"{DOWNLOAD_URL_BASE}/{{entry_id}}"
    name = "api:ha_context_exporter:download"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the download view."""
        self._hass = hass

    async def get(self, request: web.Request, entry_id: str) -> web.StreamResponse:
        """Download the latest ZIP for a config entry."""
        hass = request.app[KEY_HASS]
        last_export = get_runtime_data(hass, entry_id).get("last_export")
        if not isinstance(last_export, dict):
            return web.Response(status=HTTPStatus.NOT_FOUND)

        absolute_path = last_export.get("absolute_path")
        filename = last_export.get("filename")
        if not isinstance(absolute_path, str) or not isinstance(filename, str):
            return web.Response(status=HTTPStatus.NOT_FOUND)

        export_path = Path(absolute_path)
        if not await hass.async_add_executor_job(export_path.is_file):
            return web.Response(status=HTTPStatus.NOT_FOUND)

        return web.FileResponse(
            path=export_path,
            headers={
                CONTENT_DISPOSITION: f'attachment; filename="{filename}"',
                CONTENT_TYPE: "application/zip",
            },
        )