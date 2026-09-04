# Theme Toolkit Quickstart

This toolkit validates and exports client theme packs for the Godot shell.

## Commands

Run from repo root:

```powershell
python toolkit/pack_tool.py validate client/themes
python toolkit/pack_tool.py validate toolkit/starter_packs
python toolkit/pack_tool.py export client/themes/fantasy_classic.json --out dist/packs
python toolkit/data_integrity_validator.py server/data
python toolkit/reference_integrity_validator.py server/data
python toolkit/mod_manifest_validator.py --roots server/mods mods
python toolkit/content_set_validator.py content_sets/fantasy_frontier
python toolkit/editor_export_shim.py --source mud-world-editor/data --target tmp/editor_export_shim/server_data --report tmp/editor_export_shim/report.json
python toolkit/fixture_refresh.py --source mud-world-editor/data --latest-root server/data --fixture-root server/data_fixtures --fixture-name fantasy_editor_migrated_latest
python toolkit/stale_reference_audit.py server/data --output tmp/stale_audit_server_data.txt
```

Optional strict validation:

```powershell
python toolkit/pack_tool.py validate toolkit/starter_packs --strict
python toolkit/data_integrity_validator.py server/data --strict-templates

# Single gate command (recommended for CI/local preflight)
powershell -ExecutionPolicy Bypass -File run_content_checks.ps1
```

`--strict` requires every key present in the reference pack (`client/themes/default.json`).

## Pack Shape

Required:
- `theme_id` (string)
- `display_name` (string)
- `pack_spec_version` (string; currently `"1"`)
- `runtime_api_min` (string dotted version, for example `"1.0"`)
- `runtime_api_max` (string dotted version, for example `"1.0"`)

Optional object sections:
- `ui_strings`
- `lexicon`
- `style_tokens`
- `icon_tokens`

Unknown keys are warned and ignored by the current client.

Compatibility notes:
- Default validation requires compatibility fields and checks runtime API range.
- Use `--runtime-api <version>` to validate packs against a different runtime target.
- Use `--allow-missing-compat` only for migration/backfill workflows.

## Starter Packs

See:
- `toolkit/starter_packs/cyberpunk_district.json`
- `toolkit/starter_packs/post_apoc_settlement.json`

Use these as copy-and-rename templates for new themes.
