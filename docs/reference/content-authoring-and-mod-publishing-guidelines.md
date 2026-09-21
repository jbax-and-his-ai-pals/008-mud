# Content Authoring and Mod Publishing Guidelines

## Purpose

This document defines baseline quality and validation expectations for:

- data content inside content-set packages
- theme packs under `client/themes` and `toolkit/starter_packs`
- server mods under `server/mods` and `mods`

It is intended to keep community content stable across runtime updates and safe for distribution.

## 1. Authoring Rules (Data Content)

- Keep all content in UTF-8 JSON files.
- Prefer additive content changes over in-place mutation of shared IDs.
- Treat IDs as stable contracts once published.
- Avoid removing or renaming referenced IDs without migration notes.

Reference checks enforced by gate:

- JSON integrity: `toolkit/data_integrity_validator.py`
- Cross-file references: `toolkit/reference_integrity_validator.py`
- Content-set contract, vocabulary and playability: `run_content_checks.py`

### Closed engine vocabularies

Some words in a content set are the engine's, not yours. Every one of them is a
closed list: a value outside it does not raise, it *falls back*, and the fallback
is usually quieter than what you meant.

| Field | Where | What happens on an unknown value |
|---|---|---|
| `faction` | NPC templates | The NPC is a bystander: nobody's enemy, no attacks, no reputation. Declare your own in `ruleset.factions` (below). |
| `behavior_type` | NPC templates | The NPC has **no AI routine at all** and stands still forever. |
| `match.item_family` | `ruleset.advancement.grants` | The grant pays nothing. The gate warns and lists the families your items actually use. |
| `type` (conditions) | dialogue graphs, titles, quest availability | The condition fails closed and is reported. See `engine/conditions.py`. |
| `effects` keys | dialogue graphs, topic responses | Reported by the graph parser and refused by the gate. See `engine/dialogue/effects.py`. |
| `objective.type` (quests) | quest definitions | Refused by the gate. |
| `capabilities` (manifest) | `content_set.manifest.json` | Refused by the gate. The list is the engine's. |

`toolkit/engine_vocabulary_dump.py` prints the condition kinds, effect keys,
objective types and manifest vocabulary as one JSON object; the editor's schema
parity check compares its own copy against it, so the two cannot drift.

**`behavior_type`**, in full — the routine each value selects
(`engine/npcs/ai/dispatcher.py` dispatches through exactly this list):

| Value | The NPC... |
|---|---|
| `stationary` | stands where it is placed. The default. |
| `wanderer` | drifts between adjacent rooms on its own cooldown. |
| `aggressive` | wanders, and hunts whatever it considers an enemy. |
| `patrol` | walks a fixed loop of `patrol_points`. |
| `follower` | follows its `follow_target`. |
| `scheduled` | moves by the hour, per the set's `npc_schedules`. |
| `healer` | heals nearby allies, and otherwise wanders. |
| `minion` | is summoned: expires after `summon_duration`, obeys its owner. |

**Renaming your factions.** The engine ships five (`player`, `player_minion`,
`friendly`, `neutral`, `hostile`) and every system asks about them through one
reader. A set that wants its own names — or wants to restate what one of the five
means — declares them once in its ruleset, and display, targeting, conversation
gating, wandering, quest generation and kill-reputation all follow:

```json
"factions": {
  "extra": [
    { "id": "raiders", "disposition": "hostile" },
    { "id": "townsfolk", "disposition": "friendly" }
  ],
  "overrides": { "neutral": "friendly" }
}
```

`disposition` is one of `hostile`, `friendly`, `neutral`, `player`, and it
decides whether the faction fights the player, whether it can be talked to, and
what killing one does to reputation. Factions that share a disposition treat
each other the way that disposition treats itself: two hostile kinds ignore each
other, exactly as `hostile` always has.

**Narrowing an XP grant to an item.** `ruleset.advancement.grants[].match` takes
`item_family` (preferred — it is what your template declared), `item_tags`, or
`item_type`. `item_type` is the engine's Python class name: it exists for
compatibility, it cannot be renamed from content, and a retired class name
(`Gem`, `Junk`, `Treasure`) can never match, because an item built from one of
those families reports `Item`. The gate refuses the impossible ones and warns
about a family no item of yours uses.

### Required Practices

- Region exits must target valid room references.
- `initial_npcs[].template_id` must reference existing NPC templates.
- Item references (`item_id`, `item_template_id`) must resolve.
- Campaign `quest_template_id` and node transitions must resolve.

## 2. Theme Pack Compatibility Contract

Theme packs must include:

- `theme_id`
- `display_name`
- `pack_spec_version`
- `runtime_api_min`
- `runtime_api_max`

Validation entrypoint:

- `toolkit/pack_tool.py validate ...`

Compatibility policy:

- `pack_spec_version` must match supported pack spec major.
- runtime API must satisfy `runtime_api_min <= runtime_api <= runtime_api_max`.
- packs failing validation checks are not shippable.

## 3. Mod Manifest Compatibility Contract

Each mod must provide `manifest.json` with:

- `plugin_id`
- `name`
- `version`
- `manifest_schema_version`
- `engine_api_min`
- `engine_api_max`
- `capabilities` (array)

Allowed capabilities:

- `command_registration`
- `world_modification`
- `server_broadcast`
- `system_provider_registration`

Validation entrypoint:

- `toolkit/mod_manifest_validator.py --roots server/mods mods`

Runtime enforcement:

- Plugin load path validates manifest requirements and capability whitelist before executing `setup(api)`.

## 4. Publishing Workflow (Minimum)

1. Run `python run_content_checks.py` (from the repository root) — or, on Windows,
   `powershell -ExecutionPolicy Bypass -File run_content_checks.ps1`, which is a
   wrapper around the same entry point.
2. Resolve all `[ERROR]` findings.
3. Review `[WARN]` findings and either fix or document rationale.
4. Include release notes for:
   - new IDs introduced
   - removed/deprecated IDs
   - compatibility range changes
5. Tag content bundle version and manifest version consistently.

## 5. Compatibility and Deprecation Policy

- Stable IDs and contracts are required within a published content set.
- Breaking changes require:
  - explicit deprecation note
  - migration guidance
  - engine version range update in pack/mod manifests
- New runtime API versions should retain prior behavior where possible, and only tighten contracts with clear changelogs.
