# HA Context Exporter

Custom integration for Home Assistant, installable through HACS, that builds a **sanitized ZIP export** of your HA configuration for troubleshooting, support, or LLM analysis.

## Features

- UI-configurable through **Settings > Devices & Services**
- Direct UI controls through Home Assistant entities:
  - an **Export context** button to generate a new ZIP
  - a **Download latest export** button to surface the latest download link in the UI
  - a **Last export** diagnostic sensor with path, profile and URL metadata
- Manual export through the `ha_context_exporter.export_context` action
- Sensible export presets: `compact`, `standard`, `extended`
- Redaction of common secrets, tokens, URLs with credentials, IP addresses, hostnames, and location-like data
- Writes the ZIP inside your Home Assistant `/config` directory
- Optional public download path when exporting inside `/config/www/...`
- Built-in summary file with counts for entities, devices, helpers, and integrations

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
- optionally `custom_components/`

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

The download button becomes available after the first export. Pressing it creates a persistent notification with a direct authenticated download link to the latest ZIP.

If `output_dir` points inside `/config/www/...`, the export metadata also keeps a secondary `public_download_url` that can be shared locally as `/local/...`.

### Export profiles

- `compact`: smallest useful export. Includes core YAML files, templates, packages and essential registry/storage files.
- `standard`: recommended default. Includes everything from `compact` plus dashboards and blueprints.
- `extended`: deepest troubleshooting profile. Includes everything from `standard` plus `custom_components/`.

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
  output_dir: www/ha_context_exports
```

When `return_response` is enabled in the action tool, the service returns metadata such as:

- `absolute_path`
- `download_url`
- `file_count`
- `bytes_written`

## Important notes

- Review the ZIP before sharing it externally.
- The masking is intentionally conservative, but no automatic redaction is perfect.

## Suggested next improvements

- dedicated sidebar panel with one-click export
- optional inclusion/exclusion globs
- addon companion to upload directly to a temporary sharing endpoint
- richer summaries for automations and helper dependencies
