# HA Context Exporter

Custom integration for Home Assistant, installable through HACS, that builds a **sanitized ZIP export** of your HA configuration for troubleshooting, support, or LLM analysis.

## Features

- UI-configurable through **Settings > Devices & Services**
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
- Update `manifest.json` URLs and `codeowners` before publishing the repository.

## Suggested next improvements

- dedicated sidebar panel with one-click export
- optional inclusion/exclusion globs
- addon companion to upload directly to a temporary sharing endpoint
- richer summaries for automations and helper dependencies
