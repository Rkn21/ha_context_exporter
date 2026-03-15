from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME

from .const import (
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
    DEFAULT_FILENAME_PREFIX,
    DEFAULT_OPTIONS,
    DEFAULT_OUTPUT_DIR,
    DOMAIN,
    EXPORT_PROFILES,
)


class HAContextExporterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA Context Exporter."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id("singleton")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={},
                options={key: value for key, value in user_input.items() if key != CONF_NAME},
            )

        return self.async_show_form(step_id="user", data_schema=_build_user_schema({CONF_NAME: "Default"}))

    @staticmethod
    def async_get_options_flow(config_entry):
        return HAContextExporterOptionsFlow(config_entry)


class HAContextExporterOptionsFlow(config_entries.OptionsFlow):
    """Options flow for HA Context Exporter."""

    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_build_options_schema(current))


def _build_user_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Default")): str,
            vol.Required(
                CONF_EXPORT_PROFILE,
                default=defaults.get(CONF_EXPORT_PROFILE, DEFAULT_OPTIONS[CONF_EXPORT_PROFILE]),
            ): vol.In(EXPORT_PROFILES),
            vol.Required(
                CONF_OUTPUT_DIR,
                default=defaults.get(CONF_OUTPUT_DIR, DEFAULT_OUTPUT_DIR),
            ): str,
            vol.Required(
                CONF_FILENAME_PREFIX,
                default=defaults.get(CONF_FILENAME_PREFIX, DEFAULT_FILENAME_PREFIX),
            ): str,
            vol.Required(
                CONF_INCLUDE_PACKAGES,
                default=defaults.get(CONF_INCLUDE_PACKAGES, DEFAULT_OPTIONS[CONF_INCLUDE_PACKAGES]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_TEMPLATES,
                default=defaults.get(CONF_INCLUDE_TEMPLATES, DEFAULT_OPTIONS[CONF_INCLUDE_TEMPLATES]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_BLUEPRINTS,
                default=defaults.get(CONF_INCLUDE_BLUEPRINTS, DEFAULT_OPTIONS[CONF_INCLUDE_BLUEPRINTS]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_DASHBOARDS,
                default=defaults.get(CONF_INCLUDE_DASHBOARDS, DEFAULT_OPTIONS[CONF_INCLUDE_DASHBOARDS]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_STORAGE,
                default=defaults.get(CONF_INCLUDE_STORAGE, DEFAULT_OPTIONS[CONF_INCLUDE_STORAGE]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_CUSTOM_COMPONENTS,
                default=defaults.get(
                    CONF_INCLUDE_CUSTOM_COMPONENTS,
                    DEFAULT_OPTIONS[CONF_INCLUDE_CUSTOM_COMPONENTS],
                ),
            ): bool,
            vol.Required(
                CONF_INCLUDE_LOGS,
                default=defaults.get(CONF_INCLUDE_LOGS, DEFAULT_OPTIONS[CONF_INCLUDE_LOGS]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_SUMMARY,
                default=defaults.get(CONF_INCLUDE_SUMMARY, DEFAULT_OPTIONS[CONF_INCLUDE_SUMMARY]),
            ): bool,
            vol.Required(
                CONF_REDACT_NETWORK,
                default=defaults.get(CONF_REDACT_NETWORK, DEFAULT_OPTIONS[CONF_REDACT_NETWORK]),
            ): bool,
            vol.Required(
                CONF_REDACT_URLS,
                default=defaults.get(CONF_REDACT_URLS, DEFAULT_OPTIONS[CONF_REDACT_URLS]),
            ): bool,
            vol.Required(
                CONF_REDACT_LOCATION,
                default=defaults.get(CONF_REDACT_LOCATION, DEFAULT_OPTIONS[CONF_REDACT_LOCATION]),
            ): bool,
            vol.Required(
                CONF_PRIVACY_STRICT,
                default=defaults.get(CONF_PRIVACY_STRICT, DEFAULT_OPTIONS[CONF_PRIVACY_STRICT]),
            ): bool,
            vol.Required(
                CONF_CREATE_NOTIFICATION,
                default=defaults.get(
                    CONF_CREATE_NOTIFICATION,
                    DEFAULT_OPTIONS[CONF_CREATE_NOTIFICATION],
                ),
            ): bool,
        }
    )


def _build_options_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_EXPORT_PROFILE,
                default=defaults.get(CONF_EXPORT_PROFILE, DEFAULT_OPTIONS[CONF_EXPORT_PROFILE]),
            ): vol.In(EXPORT_PROFILES),
            vol.Required(
                CONF_OUTPUT_DIR,
                default=defaults.get(CONF_OUTPUT_DIR, DEFAULT_OUTPUT_DIR),
            ): str,
            vol.Required(
                CONF_FILENAME_PREFIX,
                default=defaults.get(CONF_FILENAME_PREFIX, DEFAULT_FILENAME_PREFIX),
            ): str,
            vol.Required(
                CONF_INCLUDE_PACKAGES,
                default=defaults.get(CONF_INCLUDE_PACKAGES, DEFAULT_OPTIONS[CONF_INCLUDE_PACKAGES]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_TEMPLATES,
                default=defaults.get(CONF_INCLUDE_TEMPLATES, DEFAULT_OPTIONS[CONF_INCLUDE_TEMPLATES]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_BLUEPRINTS,
                default=defaults.get(CONF_INCLUDE_BLUEPRINTS, DEFAULT_OPTIONS[CONF_INCLUDE_BLUEPRINTS]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_DASHBOARDS,
                default=defaults.get(CONF_INCLUDE_DASHBOARDS, DEFAULT_OPTIONS[CONF_INCLUDE_DASHBOARDS]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_STORAGE,
                default=defaults.get(CONF_INCLUDE_STORAGE, DEFAULT_OPTIONS[CONF_INCLUDE_STORAGE]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_CUSTOM_COMPONENTS,
                default=defaults.get(
                    CONF_INCLUDE_CUSTOM_COMPONENTS,
                    DEFAULT_OPTIONS[CONF_INCLUDE_CUSTOM_COMPONENTS],
                ),
            ): bool,
            vol.Required(
                CONF_INCLUDE_LOGS,
                default=defaults.get(CONF_INCLUDE_LOGS, DEFAULT_OPTIONS[CONF_INCLUDE_LOGS]),
            ): bool,
            vol.Required(
                CONF_INCLUDE_SUMMARY,
                default=defaults.get(CONF_INCLUDE_SUMMARY, DEFAULT_OPTIONS[CONF_INCLUDE_SUMMARY]),
            ): bool,
            vol.Required(
                CONF_REDACT_NETWORK,
                default=defaults.get(CONF_REDACT_NETWORK, DEFAULT_OPTIONS[CONF_REDACT_NETWORK]),
            ): bool,
            vol.Required(
                CONF_REDACT_URLS,
                default=defaults.get(CONF_REDACT_URLS, DEFAULT_OPTIONS[CONF_REDACT_URLS]),
            ): bool,
            vol.Required(
                CONF_REDACT_LOCATION,
                default=defaults.get(CONF_REDACT_LOCATION, DEFAULT_OPTIONS[CONF_REDACT_LOCATION]),
            ): bool,
            vol.Required(
                CONF_PRIVACY_STRICT,
                default=defaults.get(CONF_PRIVACY_STRICT, DEFAULT_OPTIONS[CONF_PRIVACY_STRICT]),
            ): bool,
            vol.Required(
                CONF_CREATE_NOTIFICATION,
                default=defaults.get(
                    CONF_CREATE_NOTIFICATION,
                    DEFAULT_OPTIONS[CONF_CREATE_NOTIFICATION],
                ),
            ): bool,
        }
    )
