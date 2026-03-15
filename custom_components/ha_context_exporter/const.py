from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "ha_context_exporter"
NAME: Final = "HA Context Exporter"
VERSION: Final = "0.1.0"

PLATFORMS: Final = (Platform.BUTTON, Platform.SENSOR)

SERVICE_EXPORT_CONTEXT: Final = "export_context"
DOWNLOAD_URL_BASE: Final = "/api/ha_context_exporter/download"

CONF_CONFIG_ENTRY_ID: Final = "config_entry_id"
CONF_EXPORT_PROFILE: Final = "export_profile"
CONF_OUTPUT_DIR: Final = "output_dir"
CONF_FILENAME_PREFIX: Final = "filename_prefix"
CONF_INCLUDE_PACKAGES: Final = "include_packages"
CONF_INCLUDE_TEMPLATES: Final = "include_templates"
CONF_INCLUDE_BLUEPRINTS: Final = "include_blueprints"
CONF_INCLUDE_DASHBOARDS: Final = "include_dashboards"
CONF_INCLUDE_STORAGE: Final = "include_storage"
CONF_INCLUDE_CUSTOM_COMPONENTS: Final = "include_custom_components"
CONF_INCLUDE_LOGS: Final = "include_logs"
CONF_INCLUDE_SUMMARY: Final = "include_summary"
CONF_REDACT_NETWORK: Final = "redact_network"
CONF_REDACT_URLS: Final = "redact_urls"
CONF_REDACT_LOCATION: Final = "redact_location"
CONF_PRIVACY_STRICT: Final = "privacy_strict"
CONF_CREATE_NOTIFICATION: Final = "create_notification"

EXPORT_PROFILE_COMPACT: Final = "compact"
EXPORT_PROFILE_STANDARD: Final = "standard"
EXPORT_PROFILE_EXTENDED: Final = "extended"

EXPORT_PROFILES: Final = {
    EXPORT_PROFILE_COMPACT: "Compact",
    EXPORT_PROFILE_STANDARD: "Standard",
    EXPORT_PROFILE_EXTENDED: "Extended",
}

EXPORT_PROFILE_DETAILS: Final = {
    EXPORT_PROFILE_COMPACT: "Core YAML files, templates, packages and essential registries.",
    EXPORT_PROFILE_STANDARD: "Compact profile plus dashboards and blueprints for broader troubleshooting context.",
    EXPORT_PROFILE_EXTENDED: "Standard profile plus full custom_components code for deep integration debugging; this profile is intentionally much noisier.",
}

DEFAULT_OUTPUT_DIR: Final = "www/ha_context_exports"
DEFAULT_FILENAME_PREFIX: Final = "ha_context"
DEFAULT_EXPORT_PROFILE: Final = EXPORT_PROFILE_STANDARD

DEFAULT_OPTIONS: Final = {
    CONF_EXPORT_PROFILE: DEFAULT_EXPORT_PROFILE,
    CONF_OUTPUT_DIR: DEFAULT_OUTPUT_DIR,
    CONF_FILENAME_PREFIX: DEFAULT_FILENAME_PREFIX,
    CONF_INCLUDE_PACKAGES: True,
    CONF_INCLUDE_TEMPLATES: True,
    CONF_INCLUDE_BLUEPRINTS: True,
    CONF_INCLUDE_DASHBOARDS: True,
    CONF_INCLUDE_STORAGE: True,
    CONF_INCLUDE_CUSTOM_COMPONENTS: False,
    CONF_INCLUDE_LOGS: False,
    CONF_INCLUDE_SUMMARY: True,
    CONF_REDACT_NETWORK: True,
    CONF_REDACT_URLS: False,
    CONF_REDACT_LOCATION: True,
    CONF_PRIVACY_STRICT: False,
    CONF_CREATE_NOTIFICATION: True,
}

PROFILE_DEFAULTS: Final = {
    EXPORT_PROFILE_COMPACT: {
        CONF_INCLUDE_PACKAGES: True,
        CONF_INCLUDE_TEMPLATES: True,
        CONF_INCLUDE_BLUEPRINTS: False,
        CONF_INCLUDE_DASHBOARDS: False,
        CONF_INCLUDE_STORAGE: True,
        CONF_INCLUDE_CUSTOM_COMPONENTS: False,
        CONF_INCLUDE_LOGS: False,
        CONF_INCLUDE_SUMMARY: True,
    },
    EXPORT_PROFILE_STANDARD: {
        CONF_INCLUDE_PACKAGES: True,
        CONF_INCLUDE_TEMPLATES: True,
        CONF_INCLUDE_BLUEPRINTS: True,
        CONF_INCLUDE_DASHBOARDS: True,
        CONF_INCLUDE_STORAGE: True,
        CONF_INCLUDE_CUSTOM_COMPONENTS: False,
        CONF_INCLUDE_LOGS: False,
        CONF_INCLUDE_SUMMARY: True,
    },
    EXPORT_PROFILE_EXTENDED: {
        CONF_INCLUDE_PACKAGES: True,
        CONF_INCLUDE_TEMPLATES: True,
        CONF_INCLUDE_BLUEPRINTS: True,
        CONF_INCLUDE_DASHBOARDS: True,
        CONF_INCLUDE_STORAGE: True,
        CONF_INCLUDE_CUSTOM_COMPONENTS: True,
        CONF_INCLUDE_LOGS: False,
        CONF_INCLUDE_SUMMARY: True,
    },
}

CORE_FILES: Final = [
    "configuration.yaml",
    "automations.yaml",
    "scripts.yaml",
    "scenes.yaml",
]

CORE_DIRS: Final = [
    "packages",
    "templates",
    "blueprints",
]

STORAGE_FILES: Final = [
    ".storage/core.entity_registry",
    ".storage/core.device_registry",
    ".storage/core.area_registry",
    ".storage/core.config_entries",
]

DASHBOARD_STORAGE_PREFIXES: Final = [
    "lovelace",
]

OPTION_KEYS: Final = set(DEFAULT_OPTIONS)

SENSITIVE_KEYWORDS: Final = {
    "password",
    "passwd",
    "secret",
    "local_key",
    "token",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "cookie",
    "webhook_id",
    "psk",
    "ssid",
    "pin",
}

NETWORK_KEYWORDS: Final = {
    "host",
    "hostname",
    "ip",
    "ip_address",
    "mac",
    "mac_address",
    "internal_url",
    "external_url",
    "base_url",
    "broker",
}

LOCATION_KEYWORDS: Final = {
    "latitude",
    "longitude",
    "elevation",
    "address",
    "postal_code",
}

STRICT_PRIVACY_KEYWORDS: Final = {
    "area_id",
    "config_entry_id",
    "device_id",
    "entry_id",
    "unique_id",
}

ALLOWED_TEXT_EXTENSIONS: Final = {
    ".yaml",
    ".yml",
    ".json",
    ".py",
    ".md",
    ".txt",
    ".log",
    ".csv",
    ".js",
    ".ts",
    ".css",
    ".jinja",
    ".j2",
    ".xml",
    ".conf",
    ".ini",
}
