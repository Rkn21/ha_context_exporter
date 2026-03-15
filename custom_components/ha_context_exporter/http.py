from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from secrets import compare_digest

from aiohttp import web
from aiohttp.hdrs import CONTENT_DISPOSITION, CONTENT_TYPE

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOWNLOAD_URL_BASE
from .runtime import get_runtime_data


class HAContextExporterDownloadView(HomeAssistantView):
    """Signed download endpoint for the latest generated export."""

    requires_auth = False
    url = f"{DOWNLOAD_URL_BASE}/{{entry_id}}/{{token}}/{{filename}}"
    name = "api:ha_context_exporter:download"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the download view."""
        self._hass = hass

    async def get(
        self,
        request: web.Request,
        entry_id: str,
        token: str,
        filename: str,
    ) -> web.StreamResponse:
        """Download the latest ZIP for a config entry."""
        hass = request.app[KEY_HASS]
        last_export = get_runtime_data(hass, entry_id).get("last_export")
        if not isinstance(last_export, dict):
            return web.Response(status=HTTPStatus.NOT_FOUND)

        absolute_path = last_export.get("absolute_path")
        expected_filename = last_export.get("filename")
        expected_token = last_export.get("download_token")
        if (
            not isinstance(absolute_path, str)
            or not isinstance(expected_filename, str)
            or not isinstance(expected_token, str)
        ):
            return web.Response(status=HTTPStatus.NOT_FOUND)
        if not compare_digest(token, expected_token) or filename != expected_filename:
            return web.Response(status=HTTPStatus.NOT_FOUND)

        export_path = Path(absolute_path)
        if not await hass.async_add_executor_job(export_path.is_file):
            return web.Response(status=HTTPStatus.NOT_FOUND)

        return web.FileResponse(
            path=export_path,
            headers={
                CONTENT_DISPOSITION: f'attachment; filename="{expected_filename}"',
                CONTENT_TYPE: "application/zip",
            },
        )