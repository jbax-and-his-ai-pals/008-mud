# Save File Migration and Compatibility Policy

## Purpose

Save files belong to one content-set identity and are rejected when loaded by a
different game.

**This page was rewritten on 2026-09-19.** Its policy was right and its mechanisms
were invented: it described a `schema_version: "1.3"` string, a
`server/engine/server/save_migrations.py`, and a `persistence_migrations/` folder,
none of which have ever existed. Operators followed it and found none of it. What
follows is measured against the code, and the parts that are *policy we intend*
rather than *behaviour we have* are marked as such.

## What the engine does

### The format stamp

Every save written by `SaveManager.save` carries `save_format_version` at the top
level, as an **integer**:

```json
{ "save_format_version": 4, ... }
```

- Written by `save_manager.py` from `SAVE_FORMAT_VERSION` in
  `engine/world/save_format.py`; currently `4`.
- It is an integer, not a decimal string. Earlier revisions of this page said
  `"1.3"`, which no save has ever contained.
- A save with **no** stamp is read as `UNVERSIONED` (`0`), i.e. older than any
  version, and is migrated forward like any other old file. A stamp that is not a
  number is treated the same way — a corrupt stamp is not evidence of anything.

### What each version means

| Version | What changed |
|---|---|
| 1 | Saves were interchangeable between content sets; a save did not record which game it belonged to |
| 2 | A save records the content set it was written against (the migration itself is a no-op; the reader started checking) |
| 3 | The content set is written with a version as well as an id |
| 4 | Summoned NPCs stopped surviving a save, so the summon ledger is dropped rather than restored stale |

### Compatibility rules, as implemented

| Situation | Outcome |
|---|---|
| Same version | Loads |
| Older version | Migrated up before anything reads it; each applied step is logged |
| **Newer** version than the engine | **Refused** — `UnsupportedSaveVersion`. Not half-read |
| No stamp, or a non-numeric stamp | Treated as the oldest format and migrated forward |
| Different `content_set.id`, or same id with a different `content_set.version` | **Refused** — see below |

Migrations live in the `MIGRATIONS` table in `engine/world/save_format.py`, keyed
by version step, and each must be idempotent. There is no separate migrations
module and no per-release file to add.

### Content-set isolation (the actual guarantee)

This is the policy the document was always right about, and it is enforced:

`save_manager.py` compares the save's `content_set` block — `id` and `version` —
against the world being loaded into. If either differs, the load is **refused**
and the save is left untouched; a mismatch is never a partial load. Starting a new
save for a different game is the supported path, not migrating one across.

## Rollback policy

*Policy, not implemented behaviour — no part of this is automated today.*

If a release introduces a breaking save-format change:

1. Back up live world saves before deploying.
2. Ship a rollback path with the release. The engine has none: a version-4 save
   cannot be read by a version-3 build, by design.
3. Keep the previous engine binary available for 30 days post-release.
4. Test any live rollback against a clone of the production save first.

## Player data

Player saves (inventory, level, experience, location) are the most sensitive data:

- Player-data migrations must be **lossless** — no stat or item silently dropped.
- A save is not migrated across content sets; start a new save for the selected
  game. This part *is* enforced (above).
- Notifying players in-game after a migration is **not implemented**; migrations
  are logged server-side only.

## World state (SQLite)

**There is no schema versioning in `SqliteStore`, and this section previously
described one that does not exist.** `persistence/sqlite_store.py` creates its
tables with `CREATE TABLE IF NOT EXISTS` (`entities`, `sessions`, `world_cells`)
and has no `schema_version` table, no `PRAGMA user_version` check, and no
migration SQL. A shape change to those tables is a manual operation.

If versioned SQLite schema is wanted, it has to be built. Until then, treat the
SQLite store as unversioned and back it up before changing a table definition.

## Mod data

*Policy, not implemented behaviour.* Mods own their save-data schema and must:

- Namespace saved keys under their `plugin_id`.
- Provide a `migrate(old_version, data)` hook if they change data shapes. **No
  such hook is defined or called by the engine today** — a mod that changes its
  data shape currently has no supported way to migrate it.
- Not mutate core world/player data during migration.
