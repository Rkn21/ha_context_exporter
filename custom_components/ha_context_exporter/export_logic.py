from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
import zipfile

from homeassistant.core import HomeAssistant, State

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
    CONF_PRIVACY_STRICT,
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
    STRICT_PRIVACY_KEYWORDS,
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
INTERNAL_ID_RE = re.compile(r"^[a-f0-9]{8,}$", re.IGNORECASE)

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

LIVE_PARAMETER_KEYS = {
    "device_class",
    "duration",
    "editable",
    "effect_list",
    "fan_modes",
    "has_date",
    "has_time",
    "hvac_modes",
    "max",
    "max_temp",
    "min",
    "min_temp",
    "mode",
    "options",
    "pattern",
    "precision",
    "preset_modes",
    "source_list",
    "sound_mode_list",
    "state_class",
    "step",
    "supported_features",
    "swing_horizontal_modes",
    "swing_modes",
    "target_temp_step",
    "unit_of_measurement",
}

LIVE_OPTION_KEYS = {
    "effect_list",
    "fan_modes",
    "hvac_modes",
    "options",
    "preset_modes",
    "source_list",
    "sound_mode_list",
    "swing_horizontal_modes",
    "swing_modes",
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
    privacy_strict: bool
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
        privacy_strict=bool(merged[CONF_PRIVACY_STRICT]),
        create_notification=bool(merged[CONF_CREATE_NOTIFICATION]),
    )


async def async_export_context(hass: HomeAssistant, options: ExportOptions) -> ExportResult:
    """Run the blocking export in an executor."""
    live_entity_states = _capture_live_entity_states(hass)
    return await hass.async_add_executor_job(
        _export_context_sync,
        hass.config.path(),
        options,
        live_entity_states,
    )


def _export_context_sync(
    config_dir_str: str,
    options: ExportOptions,
    live_entity_states: dict[str, dict[str, Any]],
) -> ExportResult:
    config_dir = Path(config_dir_str).resolve()
    output_dir = _resolve_output_dir(config_dir, options.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    created_at = datetime.now(UTC)
    timestamp = created_at.strftime("%Y%m%d_%H%M%S")
    safe_prefix = _slugify(options.filename_prefix or "ha_context")
    filename = f"{safe_prefix}_{timestamp}.zip"
    zip_path = output_dir / filename

    prepared_files, excluded = _collect_files(config_dir, options)
    generated_files = _build_generated_files(
        config_dir,
        options,
        prepared_files,
        excluded,
        live_entity_states,
    )

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

    _record_profile_exclusions(options, excluded)

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
        _add_optional_log_files(config_dir, files, excluded)

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
                _append_excluded(excluded, ".storage", "missing")

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
        _append_excluded(excluded, archive_name, "missing")
        return
    if source.is_dir():
        _append_excluded(excluded, archive_name, "directory_not_expected")
        return
    if source.name == "secrets.yaml":
        _append_excluded(excluded, archive_name, "always_excluded")
        return
    suffix = source.suffix.lower()
    is_storage_file = source.parent.name == ".storage"
    is_home_assistant_log = source.name.startswith("home-assistant.log")
    if suffix and suffix not in ALLOWED_TEXT_EXTENSIONS and not is_storage_file and not is_home_assistant_log:
        _append_excluded(excluded, archive_name, "unsupported_extension")
        return
    if not suffix and not is_storage_file and not source.name.startswith("core.") and not is_home_assistant_log:
        _append_excluded(excluded, archive_name, "unsupported_extension")
        return

    kind = "json" if suffix == ".json" or is_storage_file else "text"
    files.append(_PreparedFile(source_path=source, archive_name=archive_name, kind=kind))


def _add_dir(source_dir: Path, archive_root: str, files: list[_PreparedFile], excluded: list[dict[str, str]]) -> None:
    if not source_dir.exists():
        _append_excluded(excluded, archive_root, "missing")
        return
    if not source_dir.is_dir():
        _append_excluded(excluded, archive_root, "file_not_directory")
        return

    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source_dir).as_posix()
        archive_name = f"{archive_root}/{relative}"

        if path.name == "secrets.yaml":
            _append_excluded(excluded, archive_name, "always_excluded")
            continue
        if (
            path.suffix.lower() not in ALLOWED_TEXT_EXTENSIONS
            and path.parent.name != ".storage"
            and not path.name.startswith("home-assistant.log")
        ):
            _append_excluded(excluded, archive_name, "unsupported_extension")
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
            elif options.privacy_strict and _should_strict_redact_key(key_lower, item):
                output[key] = "<redacted-id>"
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
        if parent_key and options.privacy_strict and _should_strict_redact_key(parent_key, value):
            return "<redacted-id>"
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
        elif options.privacy_strict and _should_strict_redact_key(normalized, _value):
            replacement = "<redacted-id>"
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


def _should_strict_redact_key(key: str, value: Any) -> bool:
    normalized = _normalize_key(key)
    if normalized in STRICT_PRIVACY_KEYWORDS:
        return True
    if normalized == "id" and isinstance(value, str):
        return _looks_like_internal_id(value)
    return False


def _looks_like_internal_id(value: str) -> bool:
    candidate = value.strip().strip('"\'')
    return bool(INTERNAL_ID_RE.fullmatch(candidate))


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


def _capture_live_entity_states(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    return {
        state.entity_id: _build_live_state_snapshot(state)
        for state in hass.states.async_all()
        if state.entity_id and "." in state.entity_id
    }


def _build_live_state_snapshot(state: State) -> dict[str, Any]:
    attributes = dict(state.attributes)
    return _compact_dict(
        {
            "current_value": _make_json_compatible(state.state),
            "current_attributes": _make_json_compatible(_compact_dict(attributes)),
            "available_parameters": sorted(attributes),
            "available_options": _make_json_compatible(_extract_available_options(attributes)),
            "parameter_details": _make_json_compatible(_extract_parameter_details(attributes)),
            "last_changed": state.last_changed.isoformat(),
            "last_updated": state.last_updated.isoformat(),
        }
    )


def _extract_available_options(attributes: Mapping[str, Any]) -> dict[str, list[Any]]:
    options: dict[str, list[Any]] = {}
    for key in sorted(LIVE_OPTION_KEYS):
        value = attributes.get(key)
        if isinstance(value, list) and value:
            options[key] = value
    return options


def _extract_parameter_details(attributes: Mapping[str, Any]) -> dict[str, Any]:
    return _compact_dict(
        {
            key: attributes.get(key)
            for key in sorted(LIVE_PARAMETER_KEYS)
            if key in attributes
        }
    )


def _make_json_compatible(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _make_json_compatible(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_make_json_compatible(item) for item in value]
    return str(value)


def _build_summary(
    config_dir: Path,
    options: ExportOptions,
    prepared_files: list[_PreparedFile],
    excluded: list[dict[str, str]],
    registry_context: dict[str, Any],
    helper_summary: dict[str, Any],
    entity_snapshot: dict[str, Any],
    automation_summary: dict[str, Any],
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
        "automation_summary_count": automation_summary.get("automation_count", 0),
        "excluded_by_category": _summarize_exclusions(excluded),
        "selected_options": asdict(options),
        "generated_files": [
            "export_summary.json",
            "README_EXPORT.txt",
            "helpers_summary.json",
            "entity_snapshot.json",
            "automation_summary.json",
        ],
        "recommended_upload_files": [
            "export_summary.json",
            "helpers_summary.json",
            "entity_snapshot.json",
            "automation_summary.json",
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
    live_entity_states: dict[str, dict[str, Any]],
) -> dict[str, str]:
    if not options.include_summary:
        return {}

    registry_context = _load_registry_context(config_dir)
    entity_snapshot = _build_entity_snapshot(registry_context, live_entity_states)
    helper_summary = _build_helper_summary(config_dir, registry_context, live_entity_states)
    automation_summary = _build_automation_summary(config_dir, registry_context)
    custom_components_summary = _build_custom_components_summary(config_dir, options.include_custom_components)
    summary = _build_summary(
        config_dir,
        options,
        prepared_files,
        excluded,
        registry_context,
        helper_summary,
        entity_snapshot,
        automation_summary,
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
        "automation_summary.json": json.dumps(
            _redact_object(automation_summary, options),
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
        "This archive is designed to be uploaded to an AI assistant for Home Assistant context analysis.\n\n"
        f"Profile: {summary.get('profile')}\n"
        f"Entities: {counts.get('entities', 0)}\n"
        f"Devices: {counts.get('devices', 0)}\n"
        f"Areas: {counts.get('areas', 0)}\n"
        f"Integrations: {counts.get('integrations', 0)}\n\n"
        "Generated helper, entity and automation summaries are included for faster analysis.\n"
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


def _build_entity_snapshot(
    registry_context: dict[str, Any],
    live_entity_states: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    devices_by_id = registry_context["devices_by_id"]
    areas_by_id = registry_context["areas_by_id"]
    entries_by_id = registry_context["entries_by_id"]
    entities_by_id = {
        str(entity.get("entity_id")): entity
        for entity in registry_context["entities"]
        if entity.get("entity_id")
    }
    entities: list[dict[str, Any]] = []

    for entity_id in sorted(set(entities_by_id) | set(live_entity_states)):
        if not entity_id or "." not in entity_id:
            continue

        entity = entities_by_id.get(entity_id, {})
        live_state = live_entity_states.get(entity_id, {})
        live_attributes = live_state.get("current_attributes", {})

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
                    "name": _first_non_empty(
                        entity.get("name"),
                        entity.get("original_name"),
                        live_attributes.get("friendly_name") if isinstance(live_attributes, dict) else None,
                    ),
                    "device_class": _first_non_empty(
                        entity.get("device_class"),
                        entity.get("original_device_class"),
                        live_attributes.get("device_class") if isinstance(live_attributes, dict) else None,
                    ),
                    "state_class": _first_non_empty(
                        entity.get("state_class"),
                        entity.get("original_state_class"),
                        live_attributes.get("state_class") if isinstance(live_attributes, dict) else None,
                    ),
                    "unit_of_measurement": _first_non_empty(
                        entity.get("unit_of_measurement"),
                        entity.get("original_unit_of_measurement"),
                        live_attributes.get("unit_of_measurement") if isinstance(live_attributes, dict) else None,
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
                    **live_state,
                }
            )
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "entity_count": len(entities),
        "registered_entity_count": len(entities_by_id),
        "live_entity_count": len(live_entity_states),
        "entities": entities,
    }


def _build_helper_summary(
    config_dir: Path,
    registry_context: dict[str, Any],
    live_entity_states: dict[str, dict[str, Any]],
) -> dict[str, Any]:
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
        live_state = live_entity_states.get(entity_id, {})
        live_attributes = live_state.get("current_attributes", {})
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
                    "name": _first_non_empty(
                        entity.get("name"),
                        entity.get("original_name"),
                        details.get("name"),
                        live_attributes.get("friendly_name") if isinstance(live_attributes, dict) else None,
                    ),
                    "area": _first_non_empty(area.get("name") if area else None, area.get("area_id") if area else None),
                    "device": _first_non_empty(
                        device.get("name_by_user") if device else None,
                        device.get("name") if device else None,
                    ),
                    "integration": _first_non_empty(
                        config_entry.get("domain") if config_entry else None,
                        entity.get("platform"),
                    ),
                    **live_state,
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


def _build_automation_summary(config_dir: Path, registry_context: dict[str, Any]) -> dict[str, Any]:
    automations_path = config_dir / "automations.yaml"
    if not automations_path.exists():
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "automation_count": 0,
            "automations": [],
            "source": "missing",
        }

    raw = automations_path.read_text(encoding="utf-8", errors="replace")
    blocks = _split_top_level_yaml_list(raw)
    devices_by_id = registry_context["devices_by_id"]
    areas_by_id = registry_context["areas_by_id"]
    entities_by_id = {
        str(entity.get("entity_id")): entity
        for entity in registry_context["entities"]
        if entity.get("entity_id")
    }
    automations: list[dict[str, Any]] = []

    for index, block in enumerate(blocks, start=1):
        entity_ids = _extract_yaml_field_values(block, "entity_id")
        device_ids = _extract_yaml_field_values(block, "device_id")
        area_ids = _extract_yaml_field_values(block, "area_id")
        trigger_summary = _summarize_automation_section(
            block,
            section_keys=("trigger", "triggers"),
            summary_keys=("platform", "entity_id", "device_id", "event_type", "topic", "at"),
        )
        condition_summary = _summarize_automation_section(
            block,
            section_keys=("condition", "conditions"),
            summary_keys=("condition", "entity_id", "device_id", "state", "above", "below"),
        )
        action_summary = _summarize_automation_section(
            block,
            section_keys=("action", "actions"),
            summary_keys=("service", "action", "entity_id", "device_id", "scene", "delay"),
        )
        trigger_summary = _resolve_automation_section_references(
            trigger_summary,
            entities_by_id,
            devices_by_id,
            areas_by_id,
        )
        condition_summary = _resolve_automation_section_references(
            condition_summary,
            entities_by_id,
            devices_by_id,
            areas_by_id,
        )
        action_summary = _resolve_automation_section_references(
            action_summary,
            entities_by_id,
            devices_by_id,
            areas_by_id,
        )
        service_calls = _dedupe_strings(
            [
                *action_summary.get("service_calls", []),
                *_extract_yaml_field_values(block, "service"),
            ]
        )
        trigger_platforms = _dedupe_strings(
            [
                *trigger_summary.get("platforms", []),
                *_extract_yaml_field_values(block, "platform"),
            ]
        )
        resolved_entities = _dedupe_object_list(
            [
                _resolve_entity_reference(entity_id, entities_by_id, devices_by_id, areas_by_id)
                for entity_id in entity_ids
            ]
            + trigger_summary.get("referenced_entities", [])
            + condition_summary.get("referenced_entities", [])
            + action_summary.get("referenced_entities", [])
        )
        resolved_devices = _dedupe_object_list(
            [
                _resolve_device_reference(device_id, devices_by_id, areas_by_id)
                for device_id in device_ids
            ]
            + trigger_summary.get("referenced_devices", [])
            + condition_summary.get("referenced_devices", [])
            + action_summary.get("referenced_devices", [])
        )
        resolved_areas = _dedupe_object_list(
            [
                _resolve_area_reference(area_id, areas_by_id)
                for area_id in area_ids
            ]
            + trigger_summary.get("referenced_areas", [])
            + condition_summary.get("referenced_areas", [])
            + action_summary.get("referenced_areas", [])
        )

        automations.append(
            _compact_dict(
                {
                    "index": index,
                    "id": _extract_yaml_scalar(block, "id"),
                    "alias": _extract_yaml_scalar(block, "alias"),
                    "description": _extract_yaml_scalar(block, "description"),
                    "mode": _extract_yaml_scalar(block, "mode"),
                    "trigger_platforms": trigger_platforms,
                    "triggers": trigger_summary.get("entries", []),
                    "trigger_summary": _compact_dict(trigger_summary),
                    "conditions": condition_summary.get("entries", []),
                    "condition_summary": _compact_dict(condition_summary),
                    "actions": action_summary.get("entries", []),
                    "action_summary": _compact_dict(action_summary),
                    "service_calls": service_calls,
                    "referenced_entities": resolved_entities,
                    "referenced_devices": resolved_devices,
                    "referenced_areas": resolved_areas,
                }
            )
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "automation_count": len(automations),
        "automations": automations,
        "source": "automations.yaml",
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


def _build_custom_components_summary(config_dir: Path, code_exported: bool) -> dict[str, Any] | None:
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
        "code_exported": code_exported,
        "components": components,
    }


def _record_profile_exclusions(options: ExportOptions, excluded: list[dict[str, str]]) -> None:
    if not options.include_packages:
        _append_excluded(excluded, "packages", "disabled_by_profile")
    if not options.include_templates:
        _append_excluded(excluded, "templates", "disabled_by_profile")
    if not options.include_blueprints:
        _append_excluded(excluded, "blueprints", "disabled_by_profile")
    if not options.include_custom_components:
        _append_excluded(excluded, "custom_components", "disabled_by_profile")
    if not options.include_logs:
        _append_excluded(excluded, "logs", "disabled_by_profile")
    if not options.include_storage:
        _append_excluded(excluded, ".storage", "disabled_by_profile")
    if not options.include_dashboards:
        _append_excluded(excluded, "ui-lovelace.yaml", "disabled_by_profile")
        _append_excluded(excluded, "dashboards", "disabled_by_profile")
        _append_excluded(excluded, ".storage/lovelace*", "disabled_by_profile")


def _add_optional_log_files(
    config_dir: Path,
    files: list[_PreparedFile],
    excluded: list[dict[str, str]],
) -> None:
    candidates = [
        "home-assistant.log",
        "home-assistant.log.1",
        "home-assistant.log.fault",
    ]
    found_any = False
    for relative in candidates:
        source = config_dir / relative
        if source.exists() and source.is_file():
            _add_file(source, relative, files, excluded)
            found_any = True

    if not found_any:
        _append_excluded(excluded, "home-assistant.log*", "missing")


def _append_excluded(excluded: list[dict[str, str]], path: str, reason: str) -> None:
    excluded.append(
        {
            "path": path,
            "reason": reason,
            "category": _classify_exclusion_reason(reason),
        }
    )


def _classify_exclusion_reason(reason: str) -> str:
    if reason == "disabled_by_profile":
        return "excluded_by_profile"
    if reason == "always_excluded":
        return "excluded_for_safety"
    if reason == "unsupported_extension":
        return "unsupported"
    if reason == "missing":
        return "missing_expected"
    return "other"


def _summarize_exclusions(excluded: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in excluded:
        category = str(item.get("category", "other"))
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items()))


def _split_top_level_yaml_list(raw: str) -> list[str]:
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in raw.splitlines():
        if line.startswith("- "):
            if current:
                blocks.append(current)
            current = [line]
            continue
        if current:
            current.append(line)

    if current:
        blocks.append(current)

    return ["\n".join(block).strip() for block in blocks if any(part.strip() for part in block)]


def _summarize_automation_section(
    block: str,
    section_keys: tuple[str, ...],
    summary_keys: tuple[str, ...],
) -> dict[str, Any]:
    section_text = _extract_yaml_section(block, section_keys)
    if not section_text:
        return {}

    entity_ids = _extract_yaml_field_values(section_text, "entity_id")
    device_ids = _extract_yaml_field_values(section_text, "device_id")
    area_ids = _extract_yaml_field_values(section_text, "area_id")
    summary: dict[str, Any] = {
        "entries": _extract_yaml_section_entries(section_text, summary_keys),
    }
    if "platform" in summary_keys:
        summary["platforms"] = _extract_yaml_field_values(section_text, "platform")
    if "service" in summary_keys or "action" in summary_keys:
        summary["service_calls"] = _dedupe_strings(
            _extract_yaml_field_values(section_text, "service")
            + _extract_yaml_field_values(section_text, "action")
        )
    if entity_ids:
        summary["referenced_entities"] = [{"entity_id": entity_id} for entity_id in entity_ids]
    if device_ids:
        summary["referenced_devices"] = [{"device_id": device_id} for device_id in device_ids]
    if area_ids:
        summary["referenced_areas"] = [{"area_id": area_id} for area_id in area_ids]
    return summary


def _resolve_automation_section_references(
    summary: dict[str, Any],
    entities_by_id: dict[str, dict[str, Any]],
    devices_by_id: dict[str, dict[str, Any]],
    areas_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not summary:
        return {}

    resolved = dict(summary)
    resolved["referenced_entities"] = _dedupe_object_list(
        [
            _resolve_entity_reference(item.get("entity_id", ""), entities_by_id, devices_by_id, areas_by_id)
            for item in summary.get("referenced_entities", [])
            if item.get("entity_id")
        ]
    )
    resolved["referenced_devices"] = _dedupe_object_list(
        [
            _resolve_device_reference(item.get("device_id", ""), devices_by_id, areas_by_id)
            for item in summary.get("referenced_devices", [])
            if item.get("device_id")
        ]
    )
    resolved["referenced_areas"] = _dedupe_object_list(
        [
            _resolve_area_reference(item.get("area_id", ""), areas_by_id)
            for item in summary.get("referenced_areas", [])
            if item.get("area_id")
        ]
    )
    return _compact_dict(resolved)


def _extract_yaml_section(block: str, section_keys: tuple[str, ...]) -> str:
    lines = block.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        for key in section_keys:
            if not stripped.startswith(f"{key}:"):
                continue

            base_indent = len(line) - len(line.lstrip())
            section_lines = [line]
            for next_line in lines[index + 1 :]:
                if not next_line.strip():
                    section_lines.append(next_line)
                    continue
                indent = len(next_line) - len(next_line.lstrip())
                if indent <= base_indent:
                    break
                section_lines.append(next_line)
            return "\n".join(section_lines)
    return ""


def _extract_yaml_section_entries(section_text: str, summary_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    lines = section_text.splitlines()
    current: list[str] = []

    for line in lines[1:]:
        stripped = line.strip()
        if stripped.startswith("- ") and current:
            entries.append(_summarize_yaml_entry(current, summary_keys))
            current = [line]
            continue
        if stripped.startswith("- "):
            current = [line]
            continue
        if current:
            current.append(line)

    if current:
        entries.append(_summarize_yaml_entry(current, summary_keys))

    if not entries:
        entries.append(_summarize_yaml_entry(lines, summary_keys))
    return [entry for entry in entries if entry]


def _summarize_yaml_entry(lines: list[str], summary_keys: tuple[str, ...]) -> dict[str, Any]:
    block = "\n".join(lines)
    summary: dict[str, Any] = {}
    for key in summary_keys:
        values = _extract_yaml_field_values(block, key)
        if values:
            summary[key] = values[0] if len(values) == 1 else values
    return _compact_dict(summary)


def _extract_yaml_scalar(block: str, key: str) -> str | None:
    values = _extract_yaml_field_values(block, key, first_only=True)
    return values[0] if values else None


def _extract_yaml_field_values(block: str, key: str, first_only: bool = False) -> list[str]:
    pattern = re.compile(rf"^\s*-?\s*{re.escape(key)}\s*:\s*(.*)$")
    list_pattern = re.compile(r"^\s*-\s*(.+?)\s*$")
    lines = block.splitlines()
    values: list[str] = []
    index = 0

    while index < len(lines):
        match = pattern.match(lines[index])
        if match is None:
            index += 1
            continue

        raw_value = _strip_yaml_comment(match.group(1).strip())
        base_indent = len(lines[index]) - len(lines[index].lstrip())
        if raw_value:
            values.extend(_split_yaml_scalar_values(raw_value))
            if first_only and values:
                return values[:1]
            index += 1
            continue

        index += 1
        while index < len(lines):
            next_line = lines[index]
            if not next_line.strip():
                index += 1
                continue
            indent = len(next_line) - len(next_line.lstrip())
            if indent <= base_indent:
                break
            list_match = list_pattern.match(next_line)
            if list_match is not None:
                values.extend(_split_yaml_scalar_values(_strip_yaml_comment(list_match.group(1).strip())))
                if first_only and values:
                    return values[:1]
            index += 1

    return _dedupe_strings(values[:1] if first_only else values)


def _split_yaml_scalar_values(value: str) -> list[str]:
    candidate = value.strip()
    if not candidate:
        return []
    if candidate.startswith("[") and candidate.endswith("]"):
        parts = candidate[1:-1].split(",")
        return _dedupe_strings([_strip_yaml_quotes(part.strip()) for part in parts if part.strip()])
    return [_strip_yaml_quotes(candidate)]


def _strip_yaml_quotes(value: str) -> str:
    return value.strip().strip('"\'')


def _strip_yaml_comment(value: str) -> str:
    if " #" in value:
        value = value.split(" #", 1)[0]
    return value.strip()


def _resolve_entity_reference(
    entity_id: str,
    entities_by_id: dict[str, dict[str, Any]],
    devices_by_id: dict[str, dict[str, Any]],
    areas_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    entity = entities_by_id.get(entity_id, {})
    device = devices_by_id.get(str(entity.get("device_id"))) if entity else None
    area = areas_by_id.get(str(entity.get("area_id"))) if entity else None
    if area is None and device is not None:
        area = areas_by_id.get(str(device.get("area_id")))
    return _compact_dict(
        {
            "entity_id": entity_id,
            "name": _first_non_empty(entity.get("name"), entity.get("original_name"), entity_id),
            "device": _first_non_empty(
                device.get("name_by_user") if device else None,
                device.get("name") if device else None,
            ),
            "area": _first_non_empty(area.get("name") if area else None, area.get("area_id") if area else None),
        }
    )


def _resolve_device_reference(
    device_id: str,
    devices_by_id: dict[str, dict[str, Any]],
    areas_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    device = devices_by_id.get(device_id, {})
    area = areas_by_id.get(str(device.get("area_id"))) if device else None
    return _compact_dict(
        {
            "device_id": device_id,
            "name": _first_non_empty(device.get("name_by_user"), device.get("name")),
            "area": _first_non_empty(area.get("name") if area else None, area.get("area_id") if area else None),
        }
    )


def _resolve_area_reference(area_id: str, areas_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    area = areas_by_id.get(area_id, {})
    return _compact_dict(
        {
            "area_id": area_id,
            "name": _first_non_empty(area.get("name"), area.get("area_id")),
        }
    )


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _dedupe_object_list(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        compacted = _compact_dict(value)
        if not compacted:
            continue
        signature = json.dumps(compacted, sort_keys=True, ensure_ascii=False)
        if signature in seen:
            continue
        seen.add(signature)
        result.append(compacted)
    return result


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
