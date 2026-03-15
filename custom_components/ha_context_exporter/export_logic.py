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
LINE_KEY_VALUE_RE = re.compile(r'^(\s*(?:-\s*)?["\']?[A-Za-z0-9_. -]+["\']?)(\s*:\s*)(.*)$')
NORMALIZE_KEY_RE = re.compile(r"[^a-z0-9]+")

HELPER_DOMAINS = {
    "counter",
    "input_boolean",
    "input_button",
    "input_datetime",
    "input_number",
    "input_select",
    "input_text",
    "schedule",
    "timer",
}

LINE_BASED_REDACTION_EXTENSIONS = {
    ".yaml",
    ".yml",
    ".conf",
    ".ini",
    ".txt",
    ".log",
}


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
    generated_files = _build_generated_files(config_dir, options, prepared_files, excluded)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for archive_name, content in generated_files.items():
            archive.writestr(archive_name, content)

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
        file_count=len(prepared_files) + len(generated_files) + 1,
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
    suffix = source.suffix.lower()
    is_storage_file = source.parent.name == ".storage"
    if suffix and suffix not in ALLOWED_TEXT_EXTENSIONS and not is_storage_file:
        excluded.append({"path": archive_name, "reason": "unsupported_extension"})
        return
    if not suffix and not is_storage_file and not source.name.startswith("core."):
        excluded.append({"path": archive_name, "reason": "unsupported_extension"})
        return

    kind = "json" if suffix == ".json" or is_storage_file else "text"
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
        cleaned = _sanitize_text(raw, options, prepared.source_path.suffix.lower())
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


def _sanitize_text(raw: str, options: ExportOptions, file_extension: str | None = None) -> str:
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
    if file_extension in LINE_BASED_REDACTION_EXTENSIONS:
        text = _redact_line_based_keys(text, options)
    return text


def _redact_line_based_keys(text: str, options: ExportOptions) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            lines.append(line)
            continue

        match = LINE_KEY_VALUE_RE.match(line)
        if match is None:
            lines.append(line)
            continue

        key_part, separator, _value = match.groups()
        normalized = key_part.strip().strip("\"'").lower().replace(" ", "_")
        replacement: str | None = None

        if _is_sensitive_key(normalized):
            replacement = "<redacted>"
        elif options.redact_network and _is_network_key(normalized):
            replacement = "<redacted-network>"
        elif options.redact_location and _is_location_key(normalized):
            replacement = "<redacted-location>"

        if replacement is not None:
            lines.append(f"{key_part}{separator}{replacement}")
        else:
            lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _is_sensitive_key(key: str) -> bool:
    return _matches_keyword(key, SENSITIVE_KEYWORDS)


def _is_network_key(key: str) -> bool:
    return _matches_keyword(key, NETWORK_KEYWORDS)


def _is_location_key(key: str) -> bool:
    return _matches_keyword(key, LOCATION_KEYWORDS)


def _matches_keyword(key: str, keywords: set[str]) -> bool:
    normalized = _normalize_key(key)
    if not normalized:
        return False
    if normalized in keywords:
        return True
    segments = {segment for segment in normalized.split("_") if segment}
    return any(keyword in segments for keyword in keywords if "_" not in keyword)


def _normalize_key(key: str) -> str:
    return NORMALIZE_KEY_RE.sub("_", key.strip().lower()).strip("_")


def _build_summary(
    config_dir: Path,
    options: ExportOptions,
    prepared_files: list[_PreparedFile],
    excluded: list[dict[str, str]],
    registry_context: dict[str, Any],
    helper_summary: dict[str, Any],
    entity_snapshot: dict[str, Any],
    custom_components_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    entities = registry_context["entities"]
    devices = registry_context["devices"]
    areas = registry_context["areas"]
    entries = registry_context["entries"]

    domains: dict[str, int] = {}
    helpers: dict[str, int] = {}

    for entity in entities:
        entity_id = entity.get("entity_id")
        if not entity_id or "." not in entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        domains[domain] = domains.get(domain, 0) + 1
        if domain in HELPER_DOMAINS:
            helpers[domain] = helpers.get(domain, 0) + 1

    integrations: dict[str, int] = {}
    for entry in entries:
        domain = entry.get("domain", "unknown")
        integrations[domain] = integrations.get(domain, 0) + 1

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "profile": options.export_profile,
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
        "helper_count": helper_summary.get("helper_count", 0),
        "entity_snapshot_count": entity_snapshot.get("entity_count", 0),
        "selected_options": asdict(options),
        "generated_files": [
            "export_summary.json",
            "README_EXPORT.txt",
            "helpers_summary.json",
            "entity_snapshot.json",
        ],
        "recommended_upload_files": [
            "export_summary.json",
            "helpers_summary.json",
            "entity_snapshot.json",
            "configuration.yaml",
            "automations.yaml",
            ".storage/core.entity_registry",
            ".storage/core.device_registry",
            ".storage/core.config_entries",
        ],
    }
    if custom_components_summary is not None:
        summary["custom_components"] = {
            "component_count": custom_components_summary.get("component_count", 0),
            "total_files": custom_components_summary.get("total_files", 0),
        }
        summary["generated_files"].append("custom_components_summary.json")
    return summary


def _build_generated_files(
    config_dir: Path,
    options: ExportOptions,
    prepared_files: list[_PreparedFile],
    excluded: list[dict[str, str]],
) -> dict[str, str]:
    if not options.include_summary:
        return {}

    registry_context = _load_registry_context(config_dir)
    entity_snapshot = _build_entity_snapshot(registry_context)
    helper_summary = _build_helper_summary(config_dir, registry_context)
    custom_components_summary = _build_custom_components_summary(config_dir)
    summary = _build_summary(
        config_dir,
        options,
        prepared_files,
        excluded,
        registry_context,
        helper_summary,
        entity_snapshot,
        custom_components_summary,
    )

    generated = {
        "export_summary.json": json.dumps(_redact_object(summary, options), indent=2, ensure_ascii=False),
        "README_EXPORT.txt": _build_readme(summary),
        "helpers_summary.json": json.dumps(
            _redact_object(helper_summary, options),
            indent=2,
            ensure_ascii=False,
        ),
        "entity_snapshot.json": json.dumps(
            _redact_object(entity_snapshot, options),
            indent=2,
            ensure_ascii=False,
        ),
    }
    if custom_components_summary is not None:
        generated["custom_components_summary.json"] = json.dumps(
            _redact_object(custom_components_summary, options),
            indent=2,
            ensure_ascii=False,
        )
    return generated


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
        "Generated helper and entity snapshots are included for faster analysis.\n"
        "The standard profile is usually the best balance for sharing; extended is intentionally much noisier.\n\n"
        "Sensitive values have been masked based on the selected options.\n"
        "Always review the ZIP before sharing it outside your local environment.\n"
    )


def _load_registry_context(config_dir: Path) -> dict[str, Any]:
    entity_registry = _load_storage_file(config_dir / ".storage/core.entity_registry")
    device_registry = _load_storage_file(config_dir / ".storage/core.device_registry")
    area_registry = _load_storage_file(config_dir / ".storage/core.area_registry")
    config_entries = _load_storage_file(config_dir / ".storage/core.config_entries")

    entities = entity_registry.get("data", {}).get("entities", []) if isinstance(entity_registry, dict) else []
    devices = device_registry.get("data", {}).get("devices", []) if isinstance(device_registry, dict) else []
    areas = area_registry.get("data", {}).get("areas", []) if isinstance(area_registry, dict) else []
    entries = config_entries.get("data", {}).get("entries", []) if isinstance(config_entries, dict) else []

    return {
        "entities": entities,
        "devices": devices,
        "areas": areas,
        "entries": entries,
        "devices_by_id": {str(device.get("id")): device for device in devices if device.get("id")},
        "areas_by_id": {str(area.get("area_id")): area for area in areas if area.get("area_id")},
        "entries_by_id": {str(entry.get("entry_id")): entry for entry in entries if entry.get("entry_id")},
    }


def _build_entity_snapshot(registry_context: dict[str, Any]) -> dict[str, Any]:
    devices_by_id = registry_context["devices_by_id"]
    areas_by_id = registry_context["areas_by_id"]
    entries_by_id = registry_context["entries_by_id"]
    entities: list[dict[str, Any]] = []

    for entity in sorted(registry_context["entities"], key=lambda item: str(item.get("entity_id", ""))):
        entity_id = entity.get("entity_id")
        if not entity_id or "." not in entity_id:
            continue

        domain = entity_id.split(".", 1)[0]
        device = devices_by_id.get(str(entity.get("device_id")))
        area = areas_by_id.get(str(entity.get("area_id")))
        if area is None and device is not None:
            area = areas_by_id.get(str(device.get("area_id")))

        config_entry = entries_by_id.get(str(entity.get("config_entry_id")))
        if config_entry is None and device is not None:
            for entry_id in device.get("config_entries", []):
                config_entry = entries_by_id.get(str(entry_id))
                if config_entry is not None:
                    break

        entities.append(
            _compact_dict(
                {
                    "entity_id": entity_id,
                    "domain": domain,
                    "name": _first_non_empty(entity.get("name"), entity.get("original_name")),
                    "device_class": _first_non_empty(
                        entity.get("device_class"),
                        entity.get("original_device_class"),
                    ),
                    "state_class": _first_non_empty(
                        entity.get("state_class"),
                        entity.get("original_state_class"),
                    ),
                    "unit_of_measurement": _first_non_empty(
                        entity.get("unit_of_measurement"),
                        entity.get("original_unit_of_measurement"),
                    ),
                    "entity_category": entity.get("entity_category"),
                    "disabled_by": entity.get("disabled_by"),
                    "hidden_by": entity.get("hidden_by"),
                    "area": _first_non_empty(area.get("name") if area else None, area.get("area_id") if area else None),
                    "device": _first_non_empty(
                        device.get("name_by_user") if device else None,
                        device.get("name") if device else None,
                    ),
                    "integration": _first_non_empty(
                        config_entry.get("domain") if config_entry else None,
                        entity.get("platform"),
                    ),
                    "integration_title": config_entry.get("title") if config_entry else None,
                }
            )
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "entity_count": len(entities),
        "entities": entities,
    }


def _build_helper_summary(config_dir: Path, registry_context: dict[str, Any]) -> dict[str, Any]:
    helper_details = _load_helper_definitions(config_dir)
    devices_by_id = registry_context["devices_by_id"]
    areas_by_id = registry_context["areas_by_id"]
    entries_by_id = registry_context["entries_by_id"]
    helpers: list[dict[str, Any]] = []
    by_domain: dict[str, int] = {}

    for entity in sorted(registry_context["entities"], key=lambda item: str(item.get("entity_id", ""))):
        entity_id = entity.get("entity_id")
        if not entity_id or "." not in entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        if domain not in HELPER_DOMAINS:
            continue

        by_domain[domain] = by_domain.get(domain, 0) + 1
        details = helper_details.get(entity_id, {})
        device = devices_by_id.get(str(entity.get("device_id")))
        area = areas_by_id.get(str(entity.get("area_id")))
        if area is None and device is not None:
            area = areas_by_id.get(str(device.get("area_id")))

        config_entry = entries_by_id.get(str(entity.get("config_entry_id")))
        if config_entry is None and device is not None:
            for entry_id in device.get("config_entries", []):
                config_entry = entries_by_id.get(str(entry_id))
                if config_entry is not None:
                    break

        helpers.append(
            _compact_dict(
                {
                    "entity_id": entity_id,
                    "domain": domain,
                    "name": _first_non_empty(entity.get("name"), entity.get("original_name"), details.get("name")),
                    "area": _first_non_empty(area.get("name") if area else None, area.get("area_id") if area else None),
                    "device": _first_non_empty(
                        device.get("name_by_user") if device else None,
                        device.get("name") if device else None,
                    ),
                    "integration": _first_non_empty(
                        config_entry.get("domain") if config_entry else None,
                        entity.get("platform"),
                    ),
                    **details,
                }
            )
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "helper_count": len(helpers),
        "by_domain": dict(sorted(by_domain.items())),
        "helpers": helpers,
    }


def _load_helper_definitions(config_dir: Path) -> dict[str, dict[str, Any]]:
    helper_details: dict[str, dict[str, Any]] = {}
    storage_dir = config_dir / ".storage"

    for domain in sorted(HELPER_DOMAINS):
        raw_items = _extract_storage_items(_load_storage_file(storage_dir / domain), domain)
        for item in raw_items:
            entity_id = _resolve_helper_entity_id(domain, item)
            if not entity_id:
                continue
            helper_details[entity_id] = _compact_dict(
                {
                    "name": item.get("name"),
                    "icon": item.get("icon"),
                    "initial": item.get("initial"),
                    "restore": item.get("restore"),
                    "editable": item.get("editable"),
                    "min": _first_non_empty(item.get("min"), item.get("minimum")),
                    "max": _first_non_empty(item.get("max"), item.get("maximum")),
                    "step": item.get("step"),
                    "mode": item.get("mode"),
                    "options": item.get("options"),
                    "unit_of_measurement": _first_non_empty(
                        item.get("unit_of_measurement"),
                        item.get("unit"),
                    ),
                    "has_date": item.get("has_date"),
                    "has_time": item.get("has_time"),
                    "pattern": item.get("pattern"),
                    "duration": item.get("duration"),
                }
            )

    return helper_details


def _extract_storage_items(data: dict[str, Any], domain: str) -> list[dict[str, Any]]:
    candidates: list[Any] = []
    containers = [data]
    data_section = data.get("data") if isinstance(data, dict) else None
    if isinstance(data_section, dict):
        containers.append(data_section)

    for container in containers:
        if isinstance(container, list):
            candidates.append(container)
            continue
        if not isinstance(container, dict):
            continue
        for key in ("items", "entries", domain, "helpers"):
            value = container.get(key)
            if isinstance(value, list):
                candidates.append(value)

    for candidate in candidates:
        if candidate and all(isinstance(item, dict) for item in candidate):
            return candidate
    return []


def _resolve_helper_entity_id(domain: str, item: dict[str, Any]) -> str | None:
    entity_id = item.get("entity_id")
    if isinstance(entity_id, str) and entity_id:
        return entity_id

    object_id = _first_non_empty(item.get("id"), item.get("object_id"), item.get("slug"), item.get("name"))
    if not object_id:
        return None
    return f"{domain}.{_slugify(str(object_id)).lower()}"


def _build_custom_components_summary(config_dir: Path) -> dict[str, Any] | None:
    root = config_dir / "custom_components"
    if not root.exists() or not root.is_dir():
        return None

    components: list[dict[str, Any]] = []
    total_files = 0
    for manifest_path in sorted(root.glob("*/manifest.json")):
        component_dir = manifest_path.parent
        manifest = _load_storage_file(manifest_path)
        file_count = sum(1 for path in component_dir.rglob("*") if path.is_file())
        total_files += file_count
        components.append(
            _compact_dict(
                {
                    "domain": component_dir.name,
                    "name": manifest.get("name"),
                    "version": manifest.get("version"),
                    "documentation": manifest.get("documentation"),
                    "issue_tracker": manifest.get("issue_tracker"),
                    "requirements": manifest.get("requirements"),
                    "dependencies": manifest.get("dependencies"),
                    "codeowners": manifest.get("codeowners"),
                    "file_count": file_count,
                }
            )
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "component_count": len(components),
        "total_files": total_files,
        "components": components,
    }


def _compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item is not None and item != "" and item != [] and item != {}
    }


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value:
            continue
        return value
    return None


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
