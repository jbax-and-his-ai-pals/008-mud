# Data Fixtures

This folder contains immutable test fixtures for server/client validation.

## Validation status — and why it used to say otherwise

Until 2026-09-19 the line below this section read *"`data_integrity_validator`
and `reference_integrity_validator` both pass with zero errors."* **That was
never true, and nothing could have noticed.** Measured on all three trees:

| Fixture tree | Files | `data_integrity_validator` | `reference_integrity_validator` |
|---|---|---|---|
| `fantasy_editor_migrated_latest` | 72 | 0 errors | **60 errors** |
| `…__refresh_1777883376` | 36 | 0 errors | **51 errors** |
| `…__refresh_1777927964` | 36 | 0 errors | **37 errors** |

The gate could not have noticed because `run_content_checks.py` read
`LATEST_REFRESH.json`, found an absolute path recorded on another machine
(`C:\python\old\restart\...`), and **skipped all three fixture steps on every
machine but that one**. That skip is now a resolver, so the recorded path is
reinterpreted against this checkout and the steps run — which is how the errors
above became visible.

**The errors are expected, and they are not fixture defects.** These are partial
editor exports: 36–72 files against the full set's hundreds. They reference
`item_amethyst`, `slime`, `town:blacksmith` and 57 more — all of which exist in
`content_sets/fantasy_frontier/data` and none of which are in the export. A
partial slice of a content set cannot satisfy whole-set reference integrity, so
`reference_integrity_validator` is the wrong instrument for these trees.

**So the choice was taken as:** the gate runs `data_integrity_validator` and
`stale_reference_audit` on these trees — both pass cleanly and both are meaningful
for a partial export — and does **not** run `reference_integrity_validator`, which
is the wrong instrument for a partial slice. If the fixture is ever regenerated as
a complete set, that third step should be restored; the comment in
`run_content_checks.py` says where.

## `fantasy_editor_migrated_latest`

- Source: `content_sets/fantasy_frontier/data` (the same tree the editor edits)
- Pipeline: `toolkit/editor_export_shim.py` with latest-format hydration from `content_sets/fantasy_frontier/data`
- Validation status: `data_integrity_validator` passes with zero errors;
  `reference_integrity_validator` reports 60 errors, because this is a partial
  export. See the section above before treating either number as a defect.

Regenerate command:

```powershell
python toolkit/editor_export_shim.py --source content_sets/fantasy_frontier/data --target tmp/editor_export_migrate_latest/content_data --report tmp/editor_export_migrate_latest/report.json --latest-root content_sets/fantasy_frontier/data --strict
```

Preferred refresh command (handles locked/read-only destination paths and writes `LATEST_REFRESH.json`):

```powershell
python toolkit/fixture_refresh.py --source content_sets/fantasy_frontier/data --latest-root content_sets/fantasy_frontier/data --fixture-root server/data_fixtures --fixture-name fantasy_editor_migrated_latest
```
