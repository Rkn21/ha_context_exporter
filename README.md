# HA Context Exporter

Custom integration for Home Assistant, installable through HACS, that builds a **sanitized ZIP export** of your HA configuration for troubleshooting, support, or LLM analysis.

## Features

- UI-configurable through **Settings > Devices & Services**
- Direct UI controls through Home Assistant entities:
  - an **Export context** button to generate a new ZIP
  - a **Download latest export** button to surface the latest download link in the UI
  - a **Last export** diagnostic sensor with file, size and profile metadata
- Manual export through the `ha_context_exporter.export_context` action
- Sensible export presets: `compact`, `standard`, `extended`
- Redaction of common secrets, including Tuya Local `local_key`, URLs with credentials, IP addresses, hostnames, and location-like data
- Optional `privacy_strict` mode to also mask persistent internal identifiers such as `device_id`, `area_id`, `entry_id`, and `unique_id`
- Writes the ZIP inside your Home Assistant `/config` directory
- Optional public download path when exporting inside `/config/www/...`
- Built-in summary files with counts plus helper definitions, entity snapshots, live values at export time, automation summaries, and custom component metadata
- Built-in summary files now also include a dedicated HACS inventory derived from HACS storage data when available
- Adds a root-level `file_index.json` so external tools can discover the archive structure without unpack heuristics

## What gets exported

Depending on options:

- `configuration.yaml`
- `automations.yaml`
- `scripts.yaml`
- `scenes.yaml`
- `packages/`
- `templates/`
- `blueprints/`
- dashboards (`ui-lovelace.yaml`, `dashboards/`, `.storage/lovelace*`)
- selected `.storage` files:
  - `core.entity_registry`
  - `core.device_registry`
  - `core.area_registry`
  - `core.config_entries`
- generated summaries:
  - `file_index.json`
  - `export_summary.json`
  - `helpers_summary.json`
  - `entity_snapshot.json`
  - `automation_summary.json`
  - `hacs_inventory.json`
  - `custom_components_summary.json`
- optionally `custom_components/`

The generated summaries now also include runtime information captured at the exact moment of export:

- current entity value/state
- current entity attributes
- available parameter names exposed by the entity
- selectable options such as `options`, `preset_modes`, `hvac_modes`, etc.
- range metadata such as `min`, `max`, `step`, `min_temp`, `max_temp`

When HACS is installed and its storage files are present, `hacs_inventory.json` adds a repository-level inventory with category, installed state, versions, source file, and related metadata extracted from `.storage/hacs*`.

To reduce stale data, generated summaries are now built from entities that are actually active at export time, and exported core registry files are pruned to avoid keeping obvious traces of deleted entities, devices, and areas.

The integration always excludes `secrets.yaml`.

## Installation with HACS

1. Push this repository to GitHub.
2. In HACS, open **Custom repositories**.
3. Add the repository URL.
4. Select **Integration**.
5. Install **HA Context Exporter**.
6. Restart Home Assistant.
7. Add the integration from **Settings > Devices & Services**.

## Usage

### From the UI

Configure the export profile and masking rules in the integration options.

After setup, the integration also exposes UI entities you can place on a dashboard or use from the integration page:

- `button.<entry_name>_export_context`
- `button.<entry_name>_download_latest_export`
- `sensor.<entry_name>_last_export`

The download button becomes available after the first export. Pressing it creates a persistent notification with a direct signed download link to the latest ZIP.

If `output_dir` points inside `/config/www/...`, the export result also keeps a secondary `public_download_url` that can be shared locally as `/local/...`.

### Export profiles

- `compact`: smallest useful export. Includes core YAML files, templates, packages and essential registry/storage files.
- `standard`: recommended default. Includes everything from `compact` plus dashboards and blueprints.
- `extended`: deepest troubleshooting profile. Includes everything from `standard` plus full `custom_components/` source code and is much noisier.

### From Developer Tools > Actions

Action:

```yaml
action: ha_context_exporter.export_context
```

Example with overrides:

```yaml
action: ha_context_exporter.export_context
data:
  export_profile: standard
  include_custom_components: false
  redact_network: true
  redact_urls: false
  privacy_strict: false
  output_dir: www/ha_context_exports
```

When `return_response` is enabled in the action tool, the service returns metadata such as:

- `filename`
- `download_url`
- `file_count`
- `bytes_written`

Additional local-only metadata may also be present for internal download handling. Signed URLs are meant for local use and are not exposed as sensor attributes.

## Important notes

- Review the ZIP before sharing it externally.
- The masking is intentionally conservative, but no automatic redaction is perfect.
- `standard` is usually the best profile for sharing; `extended` is mainly for custom integration debugging.

`entity_snapshot.json` is the main file to inspect if you want the real values present during export. `helpers_summary.json` also includes the current value and available options for helper entities when Home Assistant exposes them in state attributes.

## Suggested next improvements

- dedicated sidebar panel with one-click export
- optional inclusion/exclusion globs
- addon companion to upload directly to a temporary sharing endpoint
- richer summaries for automations and helper dependencies
