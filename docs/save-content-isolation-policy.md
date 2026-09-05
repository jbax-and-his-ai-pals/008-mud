# Save File Migration and Compatibility Policy

## Purpose

This document defines the policy for backward compatibility of player save files, world saves, and server state databases across game versions.

## Versioning Contracts

### Save File Schema Version

Every `world_save.json` and player save file carries a `schema_version` field at the top level:

```json
{ "schema_version": "1.3", ... }
```

- This field is written by the save system at every save point.
- Loaders must check this field before applying migration steps.

### Compatibility Guarantee

| From Version | To Version | Outcome        |
|--------------|------------|----------------|
| Same major   | Same major | Always loads   |
| Lower minor  | Higher     | Migrates up    |
| Higher minor | Lower      | Warning + best-effort |
| Different major | Any     | Blocked (explicit migration required) |

---

## Migration Steps (Per Release)

Each engine release must list **what it changes** in save schema and supply a migration hook:

```python
# server/engine/server/save_migrations.py
MIGRATIONS = {
    "1.0 -> 1.1": migrate_v1_0_to_v1_1,
    "1.1 -> 1.2": migrate_v1_1_to_v1_2,
}
```

Migrations are **idempotent** — running twice must produce the same result.

---

## Rollback Policy

If a release introduces a breaking save schema change:

1. Tag a backup of all live world saves before deploying.
2. Ship a rollback migration script alongside the release.
3. Keep the previous engine binary available for 30 days post-release.
4. Any live rollback must be tested on a clone of the production save first.

---

## Player Data

Player saves (inventory, level, experience, location) are treated as the most sensitive data:

- Player data migrations must be **lossless** — no stats or items silently dropped.
- If a migration would lose data (e.g. removed item type), it must log a warning and retain the raw data under `_legacy_data`.
- Players may be notified in-game on first login after a migration.

---

## World State (SQLite)

The `SqliteStore` persistence layer versions its schema via a `schema_version` table:

- On startup, the server compares the stored version to the expected version.
- If the stored version is older, it runs migration SQL before accepting connections.
- Migration SQL lives in `server/engine/server/persistence_migrations/`.

---

## Mod Data

Mods are responsible for their own save data compatibility. Mods must:

- Namespace all saved keys under their `plugin_id`.
- Provide a `migrate(old_version, data)` hook in their manifest if they change data shapes.
- Not mutate core world/player data during migration.
