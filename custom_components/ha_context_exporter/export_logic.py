from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
import zipfile

from homeassistant.core import HomeAssistant

from .const import (
    ALLOWED_TEXT_EXTENSIONS,
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
    CORE_DIRS,
    CORE_FILES,
    DASHBOARD_STORAGE_PREFIXES,
    DEFAULT_OPTIONS,
    LOCATION_KEYWORDS,
    NETWORK_KEYWORDS,
    PROFILE_DEFAULTS,
    SENSITIVE_KEYWORDS,
    STORAGE_FILES,
)

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6_RE = re.compile(r"\b(?:[A-Fa-f0-9]{1,4}:){2,7}[A-Fa-f0-9]{1,4}\b")
URL_WITH_AUTH_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)([^\s:/@]+):([^@\s/]+)@")
URL_RE = re.compile(r"\bhttps?://[^\s'\"]+")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


@dataclass(slots=True)
class ExportOptions:
    export_profile: str
    output_dir: str
    filename_prefix: str
    include_packages: bool
    include_templates: bool
    include_blueprints: bool
    include_dashboards: bool
    include_storage: bool
    include_custom_components: bool
    include_logs: bool
    include_summary: bool
    redact_network: bool
    redact_urls: bool
    redact_location: bool
    create_notification: bool


@dataclass(slots=True)
class ExportResult:
    filename: str
    absolute_path: str
    download_url: str | None
    file_count: int
    excluded_count: int
    bytes_written: int
    profile: str
    created_at: str

    def as_response(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class _PreparedFile:
    source_path: Path
    archive_name: str
    kind: str


def build_effective_options(
    entry_options: Mapping[str, Any] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> ExportOptions:
    """Merge defaults, profile defaults, entry options and service overrides."""
    entry_data = dict(entry_options or {})
    service_data = dict(overrides or {})

    profile = service_data.get(
        CONF_EXPORT_PROFILE,
        entry_data.get(CONF_EXPORT_PROFILE, DEFAULT_OPTIONS[CONF_EXPORT_PROFILE]),
    )
    merged: dict[str, Any] = dict(DEFAULT_OPTIONS)
    merged.update(PROFILE_DEFAULTS.get(profile, PROFILE_DEFAULTS[DEFAULT_OPTIONS[CONF_EXPORT_PROFILE]]))
    merged.update(entry_data)
    merged.update(service_data)
    merged[CONF_EXPORT_PROFILE] = profile

    return ExportOptions(
        export_profile=str(merged[CONF_EXPORT_PROFILE]),
        output_dir=str(merged[CONF_OUTPUT_DIR]),
        filename_prefix=str(merged[CONF_FILENAME_PREFIX]),
        include_packages=bool(merged[CONF_INCLUDE_PACKAGES]),
        include_templates=bool(merged[CONF_INCLUDE_TEMPLATES]),
        include_blueprints=bool(merged[CONF_INCLUDE_BLUEPRINTS]),
        include_dashboards=bool(merged[CONF_INCLUDE_DASHBOARDS]),
        include_storage=bool(merged[CONF_INCLUDE_STORAGE]),
        include_custom_components=bool(merged[CONF_INCLUDE_CUSTOM_COMPONENTS]),
        include_logs=bool(merged[CONF_INCLUDE_LOGS]),
        include_summary=bool(merged[CONF_INCLUDE_SUMMARY]),
        redact_network=bool(merged[CONF_REDACT_NETWORK]),
        redact_urls=bool(merged[CONF_REDACT_URLS]),
        redact_location=bool(merged[CONF_REDACT_LOCATION]),
        create_notification=bool(merged[CONF_CREATE_NOTIFICATION]),
    )


async def async_export_context(hass: HomeAssistant, options: ExportOptions) -> ExportResult:
    """Run the blocking export in an executor."""
    return await hass.async_add_executor_job(_export_context_sync, hass.config.path(), options)


def _export_context_sync(config_dir_str: str, options: ExportOptions) -> ExportResult:
    config_dir = Path(config_dir_str).resolve()
    output_dir = _resolve_output_dir(config_dir, options.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    created_at = datetime.now(UTC)
    timestamp = created_at.strftime("%Y%m%d_%H%M%S")
    safe_prefix = _slugify(options.filename_prefix or "ha_context")
    filename = f"{safe_prefix}_{timestamp}.zip"
    zip_path = output_dir / filename

    prepared_files, excluded = _collect_files(config_dir, options)
    summary = _build_summary(config_dir, options, prepared_files, excluded)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if options.include_summary:
            archive.writestr("export_summary.json", json.dumps(summary, indent=2, ensure_ascii=False))
            archive.writestr("README_EXPORT.txt", _build_readme(summary))

        for prepared in prepared_files:
            _write_prepared_file(archive, prepared, options)

        archive.writestr(
            "excluded_items.json",
            json.dumps(excluded, indent=2, ensure_ascii=False),
        )

    public_root = (config_dir / "www").resolve()
    try:
        relative_to_public = zip_path.relative_to(public_root)
        download_url = f"/local/{relative_to_public.as_posix()}"
    except ValueError:
        download_url = None

    return ExportResult(
        filename=filename,
        absolute_path=str(zip_path),
        download_url=download_url,
        file_count=len(prepared_files) + (2 if options.include_summary else 0) + 1,
        excluded_count=len(excluded),
        bytes_written=zip_path.stat().st_size,
        profile=options.export_profile,
        created_at=created_at.isoformat(),
    )


def _resolve_output_dir(config_dir: Path, output_dir: str) -> Path:
    requested = Path(output_dir)
    target = (config_dir / requested).resolve() if not requested.is_absolute() else requested.resolve()
    try:
        target.relative_to(config_dir)
    except ValueError as err:
        raise ValueError("Output directory must stay inside the Home Assistant config directory") from err
    return target


def _collect_files(config_dir: Path, options: ExportOptions) -> tuple[list[_PreparedFile], list[dict[str, str]]]:
    files: list[_PreparedFile] = []
    excluded: list[dict[str, str]] = []

    for relative in CORE_FILES:
        _add_file(config_dir / relative, relative, files, excluded)

    if options.include_packages:
        _add_dir(config_dir / "packages", "packages", files, excluded)
    if options.include_templates:
        _add_dir(config_dir / "templates", "templates", files, excluded)
    if options.include_blueprints:
        _add_dir(config_dir / "blueprints", "blueprints", files, excluded)
    if options.include_custom_components:
        _add_dir(config_dir / "custom_components", "custom_components", files, excluded)
    if options.include_logs:
        _add_dir(config_dir / "logs", "logs", files, excluded)
        _add_file(config_dir / "home-assistant.log", "home-assistant.log", files, excluded)

    if options.include_storage:
        for relative in STORAGE_FILES:
            _add_file(config_dir / relative, relative, files, excluded)

        if options.include_dashboards:
            storage_dir = config_dir / ".storage"
            if storage_dir.exists():
                for child in storage_dir.iterdir():
                    if child.is_file() and any(child.name.startswith(prefix) for prefix in DASHBOARD_STORAGE_PREFIXES):
                        _add_file(child, f".storage/{child.name}", files, excluded)
            else:
                excluded.append({"path": ".storage", "reason": "missing"})

    if options.include_dashboards:
        _add_file(config_dir / "ui-lovelace.yaml", "ui-lovelace.yaml", files, excluded)
        _add_dir(config_dir / "dashboards", "dashboards", files, excluded)

    return _deduplicate(files), excluded


def _deduplicate(items: list[_PreparedFile]) -> list[_PreparedFile]:
    seen: set[str] = set()
    result: list[_PreparedFile] = []
    for item in items:
        if item.archive_name in seen:
            continue
        seen.add(item.archive_name)
        result.append(item)
    return result


def _add_file(source: Path, archive_name: str, files: list[_PreparedFile], excluded: list[dict[str, str]]) -> None:
    if not source.exists():
        excluded.append({"path": archive_name, "reason": "missing"})
        return
    if source.is_dir():
        excluded.append({"path": archive_name, "reason": "directory_not_expected"})
        return
    if source.name == "secrets.yaml":
        excluded.append({"path": archive_name, "reason": "always_excluded"})
        return
    if source.suffix.lower() and source.suffix.lower() not in ALLOWED_TEXT_EXTENSIONS and not source.name.startswith("core."):
        excluded.append({"path": archive_name, "reason": "unsupported_extension"})
        return

    kind = "json" if source.suffix.lower() == ".json" or source.parent.name == ".storage" else "text"
    files.append(_PreparedFile(source_path=source, archive_name=archive_name, kind=kind))


def _add_dir(source_dir: Path, archive_root: str, files: list[_PreparedFile], excluded: list[dict[str, str]]) -> None:
    if not source_dir.exists():
        excluded.append({"path": archive_root, "reason": "missing"})
        return
    if not source_dir.is_dir():
        excluded.append({"path": archive_root, "reason": "file_not_directory"})
        return

    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source_dir).as_posix()
        archive_name = f"{archive_root}/{relative}"

        if path.name == "secrets.yaml":
            excluded.append({"path": archive_name, "reason": "always_excluded"})
            continue
        if path.suffix.lower() not in ALLOWED_TEXT_EXTENSIONS and path.parent.name != ".storage":
            excluded.append({"path": archive_name, "reason": "unsupported_extension"})
            continue
        kind = "json" if path.suffix.lower() == ".json" or path.parent.name == ".storage" else "text"
        files.append(_PreparedFile(source_path=path, archive_name=archive_name, kind=kind))


def _write_prepared_file(archive: zipfile.ZipFile, prepared: _PreparedFile, options: ExportOptions) -> None:
    raw = prepared.source_path.read_text(encoding="utf-8", errors="replace")
    if prepared.kind == "json":
        cleaned = _sanitize_json_text(raw, options)
    else:
        cleaned = _sanitize_text(raw, options)
    archive.writestr(prepared.archive_name, cleaned)


def _sanitize_json_text(raw: str, options: ExportOptions) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _sanitize_text(raw, options)
    redacted = _redact_object(data, options)
    return json.dumps(redacted, indent=2, ensure_ascii=False, sort_keys=True)


def _redact_object(value: Any, options: ExportOptions, parent_key: str | None = None) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if _is_sensitive_key(key_lower):
                output[key] = "<redacted>"
            elif options.redact_network and _is_network_key(key_lower):
                output[key] = "<redacted-network>"
            elif options.redact_location and _is_location_key(key_lower):
                output[key] = "<redacted-location>"
            else:
                output[key] = _redact_object(item, options, key_lower)
        return output
    if isinstance(value, list):
        return [_redact_object(item, options, parent_key) for item in value]
    if isinstance(value, str):
        if parent_key and _is_sensitive_key(parent_key):
            return "<redacted>"
        if parent_key and options.redact_network and _is_network_key(parent_key):
            return "<redacted-network>"
        if parent_key and options.redact_location and _is_location_key(parent_key):
            return "<redacted-location>"
        return _sanitize_text(value, options)
    return value


def _sanitize_text(raw: str, options: ExportOptions) -> str:
    text = raw

    text = URL_WITH_AUTH_RE.sub(r"\1<redacted-user>:<redacted-pass>@", text)

    if options.redact_urls:
        text = URL_RE.sub("<redacted-url>", text)

    if options.redact_network:
        text = IPV4_RE.sub("<redacted-ip>", text)
        text = IPV6_RE.sub("<redacted-ipv6>", text)

    if options.redact_location:
        text = EMAIL_RE.sub("<redacted-email>", text)

    text = UUID_RE.sub("<redacted-uuid>", text)
    text = _redact_line_based_keys(text, options)
    return text


def _redact_line_based_keys(text: str, options: ExportOptions) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            lines.append(line)
            continue

        key_part, _sep, _value = line.partition(":")
        normalized = key_part.strip().strip("\"'").lower().replace(" ", "_")
        replacement: str | None = None

        if _is_sensitive_key(normalized):
            replacement = "<redacted>"
        elif options.redact_network and _is_network_key(normalized):
            replacement = "<redacted-network>"
        elif options.redact_location and _is_location_key(normalized):
            replacement = "<redacted-location>"

        if replacement is not None:
            lines.append(f"{key_part}: {replacement}")
        else:
            lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _is_sensitive_key(key: str) -> bool:
    return any(token in key for token in SENSITIVE_KEYWORDS)


def _is_network_key(key: str) -> bool:
    return any(token in key for token in NETWORK_KEYWORDS)


def _is_location_key(key: str) -> bool:
    return any(token in key for token in LOCATION_KEYWORDS)


def _build_summary(
    config_dir: Path,
    options: ExportOptions,
    prepared_files: list[_PreparedFile],
    excluded: list[dict[str, str]],
) -> dict[str, Any]:
    entity_registry = _load_storage_file(config_dir / ".storage/core.entity_registry")
    device_registry = _load_storage_file(config_dir / ".storage/core.device_registry")
    area_registry = _load_storage_file(config_dir / ".storage/core.area_registry")
    config_entries = _load_storage_file(config_dir / ".storage/core.config_entries")

    entities = entity_registry.get("data", {}).get("entities", []) if isinstance(entity_registry, dict) else []
    devices = device_registry.get("data", {}).get("devices", []) if isinstance(device_registry, dict) else []
    areas = area_registry.get("data", {}).get("areas", []) if isinstance(area_registry, dict) else []
    entries = config_entries.get("data", {}).get("entries", []) if isinstance(config_entries, dict) else []

    domains: dict[str, int] = {}
    helpers: dict[str, int] = {}
    helper_domains = {
        "input_boolean",
        "input_button",
        "input_datetime",
        "input_number",
        "input_select",
        "input_text",
        "counter",
        "timer",
        "schedule",
    }

    for entity in entities:
        entity_id = entity.get("entity_id")
        if not entity_id or "." not in entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        domains[domain] = domains.get(domain, 0) + 1
        if domain in helper_domains:
            helpers[domain] = helpers.get(domain, 0) + 1

    integrations: dict[str, int] = {}
    for entry in entries:
        domain = entry.get("domain", "unknown")
        integrations[domain] = integrations.get(domain, 0) + 1

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "profile": options.export_profile,
        "config_dir": str(config_dir),
        "included_files": len(prepared_files),
        "excluded_items": len(excluded),
        "top_entity_domains": dict(sorted(domains.items(), key=lambda item: (-item[1], item[0]))[:20]),
        "helpers": helpers,
        "counts": {
            "entities": len(entities),
            "devices": len(devices),
            "areas": len(areas),
            "integrations": len(entries),
            "automations": domains.get("automation", 0),
            "scripts": domains.get("script", 0),
            "sensors": domains.get("sensor", 0),
            "binary_sensors": domains.get("binary_sensor", 0),
        },
        "integration_domains": dict(sorted(integrations.items(), key=lambda item: (-item[1], item[0]))[:30]),
        "selected_options": asdict(options),
        "recommended_upload_files": [
            "export_summary.json",
            "configuration.yaml",
            "automations.yaml",
            ".storage/core.entity_registry",
            ".storage/core.device_registry",
            ".storage/core.config_entries",
        ],
    }


def _build_readme(summary: dict[str, Any]) -> str:
    counts = summary.get("counts", {})
    return (
        "HA Context Export\n"
        "=================\n\n"
        "This archive is designed to be uploaded to ChatGPT for Home Assistant context analysis.\n\n"
        f"Profile: {summary.get('profile')}\n"
        f"Entities: {counts.get('entities', 0)}\n"
        f"Devices: {counts.get('devices', 0)}\n"
        f"Areas: {counts.get('areas', 0)}\n"
        f"Integrations: {counts.get('integrations', 0)}\n\n"
        "Sensitive values have been masked based on the selected options.\n"
        "Always review the ZIP before sharing it outside your local environment.\n"
    )


def _load_storage_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")
    return cleaned or "ha_context"
