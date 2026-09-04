# Data Fixtures

This folder contains immutable test fixtures for server/client validation.

## `fantasy_editor_migrated_latest`

- Source: `mud-world-editor/data`
- Pipeline: `toolkit/editor_export_shim.py` with latest-format hydration from `server/data`
- Validation status: `data_integrity_validator` and `reference_integrity_validator` both pass with zero errors.

Regenerate command:

```powershell
python toolkit/editor_export_shim.py --source mud-world-editor/data --target tmp/editor_export_migrate_latest/server_data --report tmp/editor_export_migrate_latest/report.json --latest-root server/data --strict
```

Preferred refresh command (handles locked/read-only destination paths and writes `LATEST_REFRESH.json`):

```powershell
python toolkit/fixture_refresh.py --source mud-world-editor/data --latest-root server/data --fixture-root server/data_fixtures --fixture-name fantasy_editor_migrated_latest
```
