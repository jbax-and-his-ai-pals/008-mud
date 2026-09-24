# Editor coverage ledger

**What this is.** One row per declaration a content set can carry, recording what the
engine reads, what refuses a bad value, what the editor writes, what proves it, and
which batch closes the gap. This is the instrument
[game-authoring-roadmap.md](game-authoring-roadmap.md) §4/M2 and
[chunks-of-work.md](chunks-of-work.md) §6C–6D say to work from. It is not a new plan:
the order is chunks §6, the gates are the roadmap's M0–M5, and the evidence rules are
[editor-readiness.md](editor-readiness.md) §"How future updates should record coverage".

**Why a ledger instead of a percentage.** "12 of 21 content areas are CRUD" measured
*panels*. A panel that shows a field, a draft that flattens it, and a form whose file
the engine refuses are three different states, and only the last is authoring. The
columns below keep them apart, so a menu entry cannot be read as coverage.

## How to read a row

| Column | Means |
|---|---|
| **Declaration** | What an author writes, and where it lives. |
| **Engine reader** | The code that consumes the value at runtime (`file:line`). "no runtime reader" means the engine validates it and then ignores it. |
| **Validator** | What refuses a bad value, and where. `none` is a finding. |
| **Editor writer** | The panel/dialog that writes it, or `absent` / `read-only`. |
| **Status** | See the ladder below. |
| **Evidence** | The test that would notice a regression. `none` is a finding. |
| **Batch** | Which batch in [chunks §6](chunks-of-work.md) closes the gap. |

**Status ladder** — a row's status is the highest rung it satisfies, and a promotion
needs the named evidence, never a new dialog:

| Status | Requirement |
|---|---|
| **absent** | Nothing in the editor reads or writes it; hand-editing JSON is the only path. |
| **read-only** | The editor shows it and cannot write it. Unsupported values must survive untouched, which is honest but is not coverage. |
| **prototype** | A form writes it, but coverage is partial or a named defect remains. |
| **validated writer** | The save path stages the candidate and the engine refuses it on error (not merely a Validate button the author may forget). |
| **journey-proven** | A test boots a server and plays the authored result, asserting an outcome. |

**Basis.** HEAD `4e4355e` (2026-09-22), plus the current uncommitted opening,
external-root, coordinated-capability, weather and retreat slices and the 2026-09-22
reference-preflight/post-save engine-verdict hardening recorded in §I.6. Readers and validators were read out of
`server/engine/**` and `toolkit/**`; writers out of `mud-world-editor/scripts/**`;
evidence from the three gates:
`run_tests.py --suite all` (4596 singles + 280 batch + 3 current),
`run_content_checks.py` (29 steps), `run_editor_checks.py` (38 checks). Rows whose claim
drives a decision were re-checked by hand; the rest are a systematic read and say so.

**Paths.** `content_set.py` = `server/engine/server/content_set.py`; `registry.py` =
`server/engine/contracts/registry.py`; editor files are basenames under
`mud-world-editor/scripts/`; tests are basenames under `server/tests/singles/` or
`mud-world-editor/tests/`.

**The reference set.** M2 requires `fantasy_frontier` to become fully authorable, so
"used by fantasy?" is recorded where it changes priority: 24 regions / ~283 rooms,
266 item templates across 10 families, 84 NPCs, 45 recipes, 26 quests, 9 dialogue
graphs, 7 spell files, 16 titles, 3 collections, 5 discoveries, 6 backgrounds, 13
knowledge topics, 7 hazardous rooms, 0 `work` declarations, 2 campaigns.

---

## A. Project & experience

| Declaration | Engine reader | Validator | Editor writer | Status | Evidence | Batch |
|---|---|---|---|---|---|---|
| Manifest identity (`id`, `title`, `version`, schema/API range) | `world.py:103` (id); `title`/`version` values have no reader | `content_set.py:2900-2935` | `ContentSetScaffold.gd:231` (creation) + `ManifestEditorDialog.gd` (title, after creation) | validated writer | `content_set_scaffold_smoke.gd`, `manifest_editing_smoke.gd` | 6B |
| Manifest `paths` (content_root, ruleset, presentation, feature_profile, opening) | `content_set.py:2937-3001`; `headless_server.py:189-190` | `content_set.py:2942-2990`; `configuration_save.py` refuses a draft that moves them | creation only; the manifest dialog shows them and does not edit them | read-only | `content_set_scaffold_smoke.gd` | 6B |
| Manifest `capabilities` | `content_set.py:94-106` → `world.py:55,106,114,124` | `content_set.py:3003-3025`; manifest and changed explicit `ruleset.systems` entries are staged and validated together | creation + `ManifestEditorDialog.gd` (checkboxes) | validated writer | `manifest_editing_smoke.gd`, `test_configuration_save.py` | 6B |
| Manifest `start` | `world.py:230-231`; `definition_loader.py:201-220`; `persistence.py:267-268` | `content_set.py:3027-3061` — an unplaceable start room is refused by the staged verdict | creation + `ManifestEditorDialog.gd` | validated writer | `manifest_editing_smoke.gd` | 6B |
| `opening/*.json` | `headless/session.py:264-286` (heading, intro, objectives) | `content_set.py:2966-2975, 3040-3045` — scenario match; `OpeningDraft.gd` also guards non-empty prose/objectives and unique action ids | `OpeningEditorDialog.gd` from Manifest | validated writer | `opening_editing_smoke.gd` | 6B |
| `presentation/*.json` (theme pack, ui strings, accessibility) | `theme_pack`: `HeadlessServer.presentation_payload` → `hello` (both transports) → client `ThemeController.apply_content_set_theme` (a player's own `theme use` wins). `display_name`, `presentation_id`, `accessibility` have **no runtime reader** yet | `content_set.py::_validate_presentation` — known keys, a pack *id* not a path, boolean flags; `test_client_theme_packs.py` requires every shipped set's pack to be one the client ships | `PresentationDialog.gd` from the Manifest editor (pack picker over `client/themes`), saved through `configuration_save.py` | validated writer (`theme_pack`); declared-only (the rest) | `presentation_editing_smoke.gd`, `test_content_set_validator.py::TestPresentationFile`, `test_client_theme_packs.py`, transport `hello` snapshots | 6B |
| Feature profile (`data/profiles/*.profile.json`) | `feature_profile.py:53-59` via `headless_server.py:189-190` | `content_set.py:2963-2965` (object-ness only) | absent | absent | `feature_profile.py` | 6B |

**Notes.** Three of four sets named a `theme_pack` (`modern_neutral`) that does not
exist and fantasy_frontier named a file path; nothing reported either because nothing
read the field. It is read now (2026-09-23), and the four sets name real packs
(`fantasy_classic`, `default`, `default`, `scifi_frontier`). A manifest cannot be
edited after creation, so every row here is "rewrite the file by hand" except at
scaffold time.

## B. World

| Declaration | Engine reader | Validator | Editor writer | Status | Evidence | Batch |
|---|---|---|---|---|---|---|
| Region envelope (id, name, description, `properties`, rooms) | `definition_loader.py:159-176`; `region.py:50-69` | `content_set.py:719-747`; `reference_integrity_validator.py:107-121` | `RegionInspector.gd` + `Main.gd:794-835`; delete: `Main._confirm_delete_region` refuses the manifest start region, links from other regions (listed) and unsaved work, then deletes under a checkpoint and the engine verdict (refusal puts the file back) | validated writer | `content_round_trip_smoke.gd`, `content_source_check.gd`, `region_and_district_delete_smoke.gd`, `save_engine_verdict_smoke.gd` | 6B |
| Rooms (identity, prose, `_editor_pos`) | `room.py:10-30` | `content_set.py:761-803` | `ActionHandler.gd:66-92` (create), `:130-155` (delete), `RegionManager.gd:109-124` (save) | validated writer | `editor_session_safety_smoke.gd`, `save_engine_verdict_smoke.gd` (region saves roll back on refusal) | 6B |
| Exits / connections (direction, reciprocity, lock, hidden) | `room.py:10-30`; `world.py:397-449` | `content_set.py:761-803`; reachability `:818-851`; `reference_integrity_validator.py:131-142` | `ActionHandler.gd:29-64`; `RoomConnectionsPanel.gd` | validated writer | `connection_editing_smoke.gd`, `reciprocal_label_smoke.gd`, `save_engine_verdict_smoke.gd` (region saves roll back on refusal) | 6B |
| Room `properties` — scalars | `room.py` `ROOM_PROPERTY_KINDS` names every key the engine reads (atmosphere through `World.get_env_property`, `safe_zone` through `World.is_location_safe` -- which ignored the room until 2026-09-23 -- weather, hazards, `locked_by`, exits); `ROOM_EDITOR_PROPERTY_KINDS` the editor's map keys; the ruleset's custody section names two more | `content_set.py::_validate_room_property_keys`: a key nothing reads is a warning; a read key of the wrong type, a bad `temperature` or a `locked_by` naming no item is an error | `RoomPropertiesPanel.gd` via `PropertyTagRow.gd`, which now names keys nothing reads under the tags; the quick-add menus no longer offer `music` (read by nothing); vocabulary parity-checked | validated writer — fantasy_frontier's 15 `indoors` rooms (and 2 regions) counted as outdoors and now say `outdoors: false`; 3 `underwater` keys with no reader were removed. Region and district properties are checked the same way (`region.py` REGION_/DISTRICT_PROPERTY_KINDS, `_validate_region_property_keys`; Region/District inspectors name unread keys and no longer offer `weather`, which a region or district never reads); two regions' unread `spawn_templates`/`spawn_level_range` notes were removed | `room_property_vocabulary_smoke.gd`, `schema_parity_smoke.gd`, `nested_property_survival_smoke.gd`, `test_room_property_vocabulary.py`, `test_safe_room_logic.py`, `test_content_set_validator.py` | 6B |
| Room `properties` — nested (`hidden_exits`, `exit_requirements`, `env_interactions`; `time_descriptions` is the atmosphere row below) | `items/interactive.py:56-63`; `world.py:397-416, 548-570`; `room.py:69-100`, fired from `magic/effects.py:51` | `hidden_exits` destinations (`content_set.py:789-801`); `content_set.py::_validate_room_passage_properties` — requirement types and fields, directions the room really has, key items, reactions aimed at a real requirement or hazard, declared damage types | `RoomPassagesPanel.gd` (pickers over the room's own exits, requirements and declared damage types) | validated writer | `room_passages_authoring_smoke.gd` (ends with the engine validator), `save_engine_verdict_smoke.gd` (a refused lock type is rolled back), `test_content_set_validator.py::TestRoomPassageProperties`, `nested_property_survival_smoke.gd` | 6C |
| Room atmosphere and time descriptions (`env_properties`: dark/outdoors/windows/noise/smell/temperature; `time_descriptions`: dawn/day/dusk/night) | `room.py:21,30,127-132,141-142,190-199`; `weather_manager.py:50` | `content_set.py` authored-world gate — closed keys/types, ignored-key warning | `RoomEnvironmentPanel.gd` controlled atmosphere and optional time-description fields | validated writer | `save_engine_verdict_smoke.gd`, `room_environment_authoring_smoke.gd`, `test_content_set_validator.py` | 6C |
| Room hazards (`properties.hazard_type`, `hazard_damage`, `hazard_tick_interval`, `weather_hazard_multipliers`) | `world/environment.py:59-106` | `content_set.py:431-587` — only when `data/combat/elements.json` exists; coverage only if the ruleset opts in | `RoomEnvironmentPanel.gd` picks declared hazards and offers contextual numeric/weather overrides | validated writer | `save_engine_verdict_smoke.gd`, `room_environment_authoring_smoke.gd`, `content_set_runtime.py` (hazard damage), `environment_reader.py` | 6D |
| Room `initial_npcs` (+ placement `overrides`) | `definition_loader.py:247-278` (runtime whitelist); `npcs/ai/movement.py::perform_patrol` | `content_set.py` validates supported types and names ignored keys; `_validate_patrol_routes` checks the effective route (template or placement) in the home region: every point a room there and walkable by visible exits, the start index in range, a patrol NPC with points, points only on a patrol NPC; `properties_override` by the template's property rules (`_npc_property_errors`) | `RoomContentPanel.gd` guided placement overrides (name, stats/pools, behaviour from `NPCVocabulary`) a patrol route editor (points from the region's rooms, reorder, start point, back to the template route), and behaviour tuning per placement (Override boxes over the template's values; other keys listed and removable, never rewritten) | validated writer | `npc_patrol_route_smoke.gd`, `room_item_placement_smoke.gd`, `test_content_set_validator.py` | 6C |
| Room `items` (`quantity` + `properties_override`) | `definition_loader.py:230-247`; `item_factory.py::create_item_from_template` (overrides flattened into constructor fields, the rest become properties) | `content_set.py::_item_placement_override_issues`: an override keeps the type of what it replaces (constructor fields typed from each class's defaults, other keys from the template's value), no class/family change, `key_id`/`contains` references resolve; a key the template lacks is a warning; `reference_integrity_validator.py` | `RoomContentPanel.gd` guided placement overrides (name/description; container state; resource charges/respawn) plus every other override edited by its type (checkbox/number/text; arrays and objects shown), removable, and any scalar template property addable | validated writer | `room_item_placement_smoke.gd`, `test_definition_loader_full.py`, `test_content_set_validator.py` | 6C |
| Districts (`properties.districts`) | `world.py:786-827` | `content_set.py:590-677`; policy `:315-344` | `ActionHandler.gd:316-443` (incl. undoable `delete_district`, which keeps the rooms and clears their `_district_id`); `DistrictInspector.gd:62-84` | validated writer (colour is display-only) | `districts.py`, `district_pinch_smoke.gd`, `region_and_district_delete_smoke.gd` | 6B |
| Region `spawner` (weights, toggles, level_range) | `spawner.py:104-171`; `region.py:68` | `content_set.py:412-428` (`level_range`); `content_set.py::_validate_region_spawners` — creatures, weights, toggles, unknown keys | `SpawnerInspector.gd:22-151` | validated writer | `region_policy_validator.py` (partly), `save_engine_verdict_smoke.gd` (region saves roll back on refusal) | 6C |
| Region `properties.level_band` | `region.py:20-41`; `spawner.py:143` | `content_set.py:375-428` (policy-gated) | creation-time only; rendered non-editable (`RegionInspector.gd:220`) | read-only | `p7_region_bands.py` | 6C |
| Region `properties.biome` / `region_type` | **no runtime reader** | `content_set.py:347-372` | creation-time / scalar tag | read-only | `region_policy_validator.py` | 6D |
| `properties.weather_profile` | `weather_manager.py:55,65` | `content_set.py:1131-1166` | `RegionInspector.gd` picker sourced from declared ruleset profiles; an already-missing value remains visible | validated writer | `configuration_dialog_smoke.gd`, `save_engine_verdict_smoke.gd` (region saves roll back on refusal) | 6D |
| `editor/world_layout.json` | Godot only (`WorldManager.gd:11-53`) | correctly unvalidated | implicit (drag nodes; acknowledgement state) | prototype | `content_source_check.gd` | — |

**Notes.** The nested-property family is the one place where the editor is *safely*
read-only: `PropertyTagRow.build_nested_row` shows the object and never writes it, and
`nested_property_survival_smoke.gd` pins that for rooms, multi-room selection and items.
Note also that `world_effects` does not exist as a region field — world-effect policy
lives in the feature profile — so a row for it would be invented; what exists instead is
`data/world/field_interactions.json` (family G).

## C. Characters & social

| Declaration | Engine reader | Validator | Editor writer | Status | Evidence | Batch |
|---|---|---|---|---|---|---|
| NPC envelope (name, description, level, health/mana, `stats`, attack/defense) | `definition_loader.py:108-157`; `npc_factory.py:77-149` | `content_set.py:_validate_npc_template_runtime_shapes` checks authored primitive bounds; the stat dictionary remains contract-owned | `NPCInspector.gd:46-122` | validated writer | `npc_stat_vocabulary_smoke.gd`; `test_content_set_validator.py`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6D |
| NPC `faction` | `npc_factory.py:141`; `world/factions.py:155-176` | `content_set.py:883-926` — **warning only**; unknown faction silently becomes a bystander | `NPCInspector.gd` faction picker: the engine's five plus this set's `ruleset.factions.extra`/`overrides`, each labelled with its resolved disposition; an already-authored but undeclared value is shown, not dropped | prototype — an undeclared faction warns by design: it loads as a bystander (`test_faction_dispositions.py`) | `npc_faction_behavior_smoke.gd`; `schema_parity_smoke.gd` checks `NPCVocabulary.gd` against the engine | 6D |
| NPC `behavior_type` | `npc_factory.py:142`; `ai/dispatcher.py` | `content_set.py:909-915` — warning only; unknown value means the NPC never acts | `NPCInspector.gd` behavior picker, from `NPCVocabulary.BEHAVIOR_TYPES` | prototype — warns by design: the set still loads and runs (`test_npc_behavior_vocabulary.py`) | `npc_faction_behavior_smoke.gd`; `schema_parity_smoke.gd` | 6D |
| NPC `friendly` | `npc_factory.py:81` (overridden by `factions.is_hostile`) | `content_set.py:_validate_npc_template_runtime_shapes` boolean | `NPCInspector.gd` checkbox | validated writer | `npc_faction_behavior_smoke.gd`; `test_content_set_validator.py`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6D |
| NPC `dialog` (flat keyword dict) | `npc_factory.py:156-157`; `npc.py:85-86,124-125` | `template_placeholder_validator.py:97-134` (braces only) | `NPCInspector.gd` topic/reply rows; renaming a topic is a key rebuild, refused on a collision | validated writer | `hostile_dialog_no_leftover_placeholders.py`; `npc_dialog_topics_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6D |
| NPC `properties.dialogue` (graph binding) | `dialogue/manager.py:243-250` | `content_set.py:1522-1540`; orphans `:1545-1549` | `NPCInspector.gd` graph picker, offering only graphs this set has; an already-bound but missing graph is shown, not dropped | validated writer | `p5_dialogue.py` (engine side); `npc_dialogue_binding_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6D |
| Vendor stock (`properties.sells_items`, `sell_rate_multiplier`, `tariff`) | `mercantile.py:81-122, 370` | `content_set.py::_validate_npc_trade_and_loot` — stock items, price multipliers, relationship gates, `sell_rate_multiplier`, `tariff` campaign | `NPCInspector.gd`: a rate control plus a plain item picker per sold item (price multiplier, friendship floor); `tariff` remains absent (a region/world policy, not per-NPC) | validated writer | `vendor_order_references.py` (orbital orders); `npc_vendor_stock_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6D |
| Vendor `properties.buy_orders` | `mercantile.py:135-155, 211-232` | `content_set.py:_validate_vendor_orders` | `NPCInspector.gd`: one card per order (id, `ReferenceEditor` for what it wants, quantity, reward, repeatable/crafted-only); id rename refused on a collision | validated writer | `vendor_buy_order_relationship_gate.py`; `npc_vendor_stock_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6D |
| Gift preferences (`preferred_item_ids`, `preferred_gift_tags`, disliked…) | `use_give.py:19-51` | `content_set.py::_validate_npc_trade_and_loot` — known keys (a misspelt one was never read), string lists, real item ids | `NPCInspector.gd`: item pickers for the two id lists, text rows for the three open-vocabulary tag/category lists; nothing written by opening, an emptied list erases its key | validated writer | `relationship_gifts.py`; `npc_gift_preferences_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6D |
| `schedule`, `properties.work_location`, `can_unlock_chests`, `sells_houses` | `npc_factory.py:60-73,161`; `ai/schedules.py:143` | `content_set.py:_validate_npc_template_runtime_shapes` checks direct template schedule entries, real work locations, and flags | `NPCInspector.gd`: `work_location`/`can_unlock_chests`/`sells_houses` fields. `schedule` itself remains generated per `ruleset.npc_schedules`, rather than being a per-NPC raw field | validated writer | `npc_schedules_full.py` (engine side); `npc_behavior_tuning_smoke.gd`; `test_content_set_validator.py`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6D |
| `loot_table` | `npc_factory.py:159-240`; `npc.py:160-174` | `content_set.py::_validate_npc_trade_and_loot` — real items (or `is_chest`), chance 0–1, ordered integer quantities (a reversed one raised in `randint`) | `NPCInspector.gd` — an item picker per drop (renames the entry's key; refuses a collision rather than merging two drops); no longer writes `loot_table: {}` merely by being opened | validated writer | `content_round_trip_smoke.gd`, `npc_loot_table_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6D |
| Behaviour tuning (`aggression`, `flee_threshold`, `respawn_cooldown`, `wander_chance`, `move_cooldown`, `spell_cast_chance`) | `npc_factory.py:204-240`; `ai/movement.py:101-105` | `content_set.py:_validate_npc_template_runtime_shapes` bounds each control; `-1` remains the explicit no-respawn sentinel | `NPCInspector.gd` numeric fields, defaults shown match the engine's own | validated writer | `npc_behavior_tuning_smoke.gd`; `test_content_set_validator.py`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6D |
| `usable_spells`, `initial_inventory`, `patrol_points` | `npc_factory.py:159-240` | `content_set.py:_validate_npc_template_runtime_shapes` checks ability/item references, quantities, and patrol shape | `NPCInspector.gd`: a spell picker, an item-picker+quantity list, and a room-id text list respectively | validated writer | `guard_patrol_content.py`; `npc_behavior_tuning_smoke.gd`; `test_content_set_validator.py`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6D |
| Ruleset `factions.extra` / `overrides` | `world/factions.py:48-118, 228-277` | `content_set.py:854-880` | `RulesetEditorDialog.gd:129-147` — `extra` (id + disposition) only | validated writer | `configuration_dialog_smoke.gd`, `test_configuration_save.py` (staged engine verdict) | 6D |

**Notes.** This was the largest single block of `absent` rows, and it is the block a
player notices first. As of 2026-09-22, every row above is prototype except the
`schedule` role config (a ruleset/config-editor surface, deliberately not folded into
the per-NPC template) and `friendly`'s combat-side override. The engine reads and
validates most of these shapes; only the editor was missing.
`ReferenceEditor.gd:10-13` documents "a vendor's buy order" as a shape the
editor knows about, which makes the absence read as a bug rather than a decision.

## D. Items & generation

| Declaration | Engine reader | Validator | Editor writer | Status | Evidence | Batch |
|---|---|---|---|---|---|---|
| Item envelope (`name`, `type`, `weight`, `value`, `stackable`, `equip_slot`) | `definition_loader.py:51-106` (skips a template without `name`/`type`); `item_factory.py:142-298` | `content_set.py::_validate_item_envelopes`: an object with a non-empty `name` and a `type`, resolving (family first, then `type`) to a class `ITEM_CLASS_MAP` builds; `description`/`weight`/`value`/`stackable` typed; duplicate ids warned. `data_integrity_validator.py` still warns too | `ItemInspector.gd:34-78`; its type list is parity-checked against `ITEM_CLASS_MAP` | validated writer — a missing name or type was only a warning while the loader dropped the template. Extra top-level keys are kept as properties (`test_item_factory_full.py`) | `item_authoring_smoke.gd`, `save_engine_verdict_smoke.gd` (a blank name and an unbuildable type are refused and the file put back), `schema_parity_smoke.gd`, `test_content_set_validator.py` | 6C |
| Item `properties.resistances` (`{damage_type: float}`) | `contracts/equipment.py::armor_resistances`; schema `contracts/registry.py:129` | `content_set.py::_validate_item_resistances_and_sets` — numeric values, keys among `combat/elements.json`'s damage types | `ItemInspector.gd`: a picker (this set's own `data/combat/elements.json` damage types) + value per row; switching a row's type is a key rebuild, refused on a collision | validated writer | `item_resistances_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6C |
| Item `properties` — other nested objects (`substitute_resource_ids`, …) | `item_factory.py:205-259` | `content_set.py:2775-2875` (a named subset only) | read-only row (`ItemInspector.gd:386-399`) | read-only | `nested_property_survival_smoke.gd` | 6C |
| `properties.salvage_output` | `crafting_manager.py:401-464` | `content_set.py:2065-2170` | `ItemInspector.gd:93-162` via `ReferenceEditor.gd:52-120` | journey-proven | `item_authoring_smoke.gd` + playability `salvage` | 6C |
| `item_family`, `generation_profile`, rarity bands | `registry.py:285-305`; `instance_generator.py:98-118, 199-323` | `content_set.py:1986-2011, 2602-2630` | `ItemInspector.gd:175-345` (catalog-driven pickers) | validated writer | `contract_authoring_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6C |
| Affixes (`data/items/affixes.json`) | `affix_data.py:23-35`; `loot_generator.py:34-77` | `content_set.py::_validate_affixes` — required `allowed_types` of engine classes, keys the generator reads per library, prefix modifiers, effect-name placeholders | `AffixInspector.gd`, loaded/saved by `DatabaseManager._load_affixes`/`_save_affixes` | validated writer | `affix_and_set_authoring_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6C |
| Item sets (`data/items/sets.json`) | `set_manager.py:19-46` | `reference_integrity_validator.py:267-345` (members); `content_set.py::_validate_item_resistances_and_sets` — known keys, whole-number thresholds, `stat_mod` bonuses with numeric modifiers | `ItemSetInspector.gd`, loaded/saved by `DatabaseManager._load_item_sets`/`_save_item_sets` | validated writer | `affix_and_set_authoring_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6C |
| Containers (`contains`, `capacity`, `locked`, `key_id`, `is_open`) | `container.py:26-38, 339-351`; `item_factory.py:230-232` | `content_set.py:_validate_container_templates` — references, quantities, and basic state | `ItemInspector.gd` guided Container section; a room placement can locally set open/locked state | validated writer | `item_authoring_smoke.gd`, `room_item_placement_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6C |
| Resource nodes (`resource_item_id`, `yield_table`, `substitute_resource_ids`, `charges`, `respawn_days`, `weather_blocked_by`) | `resource_node.py:16-30, 85-277`; `commands/gathering.py:68-74` | `content_set.py:2173-2231` — yield references and grades | `ItemInspector.gd` primary yield, tool, charges, respawn, alternate yields; a room placement can locally set charges/respawn | validated writer | `item_authoring_smoke.gd`, `room_item_placement_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6C |
| `data/regions/dynamic_themes.json` (generation templates) | `region_generator.py:22-33, 68-70`; used by `quest_generation/generator.py::_instantiate_quest_logic` and the `genregion` debug command | `content_set.py::_validate_dynamic_themes` — known keys, non-empty lists (an empty one raised in `random.choice`), every `{placeholder}` backed by a word list and none in the never-formatted `room_names`/`description`, real spawner creatures, and every theme a quest's `procedural_regions` or the ruleset's `default_procedural_theme` names | `ThemeInspector.gd` under a "Region Themes" library category, including the shared word lists | validated writer | `region_theme_authoring_smoke.gd` (ends with the engine validator), `test_content_set_validator.py::TestDynamicThemes`, `content_round_trip_smoke.gd` | 6C |

**Notes.** Generation is the family where the engine is most configurable and the editor
least: families, profiles, rarity bands and salvage are authorable, and — since
2026-09-21 — so are the two item-directory contracts that were excluded outright
(affixes, item sets), node yields and container contents (both now prototype above),
and `resistances` (2026-09-22). What remains unauthorable is the rest of the nested
item-property table (`substitute_resource_ids` and any other object/array-valued
property nothing else declares) — still read-only, by design, until each gets its own
control the way `resistances` and salvage did rather than a second generic guess.

**The affix/set history is worth keeping in view.** They were excluded from load
because an old editor save rewrote `affixes.json` from the *items* cache and deleted
its string-valued keys (`generated_effect_name_pattern`,
`generated_description_suffix`). That was the right workaround and the wrong
destination: they are now loaded as themselves, kept out of the items cache, and the
string keys are pinned by a test that would fail if a save dropped them again. Their
bytes also had to be normalised into `SaveIO`'s form (4-space, LF, whole floats as
ints) — the round-trip gate found that immediately, which is what it is for.

## E. Crafting, gathering & work

| Declaration | Engine reader | Validator | Editor writer | Status | Evidence | Batch |
|---|---|---|---|---|---|---|
| Recipes (result, quantity, station, difficulty, quality tiers, familiarity) | `crafting_manager.py:32`; `crafting/recipe.py:63` | `content_set.py:2664-2772`; strict reader `recipe_reader_is_strict.py` | `RecipeInspector.gd:44-421` | journey-proven | `recipe_authoring_smoke.gd` + playability crafts 1 recipe/set; `m2_route_journeys_smoke.gd` (editor edit -> engine-checked save -> `edited_route_check.py` play, shipped vs edited) (an edited yield: gather, craft 3, use) | 6C |
| Stations (an item with `crafting_station_type`) | `crafting_manager.py` station lookup | `content_set.py:_validate_crafting_station_references` | recipe station picker lists authored station types; the item's own `crafting_station_type` property stays free text (a new station type has to be nameable) but now offers every type already in use via a suggestion button, the same scan the recipe picker does | validated writer | `recipe_authoring_smoke.gd` + `test_container_template_validation.py`; `item_station_type_suggestion_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6C |
| `crafting.salvage_rules.by_family` / `default_item_id` | `crafting_manager.py:424-464` | `content_set.py:2065-2152` | Ruleset dialog: fallback picker plus family/reference/rate rows; preserves comments and legacy class rules | validated writer | `configuration_dialog_smoke.gd`, `test_configuration_save.py` (staged engine verdict) | 6C |
| Contract `work` declarations | `contracts/work.py:59-101, 253-397`; `commands/work.py:23` | schema `registry.py:169-196`; semantic `work.py:181-222` — **`declaration_issues()` has no engine caller, only tests** | `ContractEditorDialog.gd:44, 219-235` (Work tab) | validated writer | `configuration_dialog_smoke.gd` | 6C |
| Work-job runtime (durations, spoil, deadlines) | `contracts/work.py:230-397`; `player/persistence.py` | runtime | — | journey-proven (engine side) | `sci_fi_proving_slice.py` (orbital only), `work_jobs.py` (synthetic) | 6C |
| `skills.stat_bonuses` | `skill_system.py:43-49` | `content_set.py:_validate_skills_rules` (shape) | `RulesetEditorDialog.gd`: skill id, stat (free text -- ruleset is where a stat is declared in the first place) and per-point rows | validated writer | `skill_audit.py` (warnings only); `ruleset_skill_bonuses_smoke.gd`, `test_configuration_save.py` (staged engine verdict) | 6C |
| Gathering tool requirement (`properties.tool_required`) | `resource_node.py:106` | `content_set.py:_validate_resource_node_yields` | **Correction, 2026-09-22: this was already authored** — `ItemInspector.gd`'s "Tool type" field (added alongside the rest of the resource-node section before this ledger's last full pass). No separate "route" or "tags" concept exists anywhere in the engine; that half of this row's description does not correspond to any real declaration | validated writer | `fantasy_gathering_route.py`; `item_authoring_smoke.gd`, `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6C |

**Notes.** `work` is declared by **orbital_salvage only**; fantasy declares none, so the
newest engine primitive has one shipped proof and the reference set cannot exercise it
until 6C authors one. That is the two-theme rule failing in the direction nobody checks:
the *engine* has a second consumer, the *reference content* does not.

## F. Combat & abilities

| Declaration | Engine reader | Validator | Editor writer | Status | Evidence | Batch |
|---|---|---|---|---|---|---|
| Damage channels (`valid_damage_types`, `default_damage_type`) | `config_combat.py:139-158` | `content_set.py:441-526` | `CombatVocabularyDialog.gd:22-23` | validated writer | `configuration_dialog_smoke.gd` | 6D |
| Hazards (`hazards.<id>`: channel, flavor, damage, tick) | `world/environment.py:45-106` | `content_set.py:441-526`; `reference_integrity_validator.py:752-808` | `CombatVocabularyDialog.gd:47-85` | validated writer | `configuration_dialog_smoke.gd`, `environment_reader.py` | 6D |
| `elemental_opposites`, `flavor_text` | read only through `elements.json` consumers | **unchecked by the engine** | not shown | absent | none | 6D |
| Authored abilities (`data/abilities/`, else `data/magic/`) | `spell_registry.py` (each ability built on its own; `_` keys skipped); `spell.py`; `magic/effects.py::apply_spell_effect` | `content_set.py::_validate_abilities` (constructor fields, target types, every effect type's own keys and payload, damage types, minion summons, message placeholders); `ability_load_check.py` | `MagicInspector.gd`: per-type effect cards (DoT name/tick/type, applied-effect name/kind/duration/modifiers, cleanse tags, summon creature/duration/cap), all five targets, all six messages; vocabulary parity-checked | journey-proven — the "legacy" keys were per-effect keys the engine reads, now authored. `max_summons` was read by nothing and is now enforced (the oldest summon is dismissed). Contract `abilities.target_type` still uses its own list (`ally`/`room`/`area`), which the cast path does not resolve | `ability_effect_authoring_smoke.gd`, `schema_parity_smoke.gd`, `test_ability_vocabulary.py`, `test_content_set_validator.py`, `test_summon_cap_enforcement.py`, `m2_route_journeys_smoke.gd` (editor edit -> engine-checked save -> `edited_route_check.py` play, shipped vs edited) (an edited damage value kills a cave bear the shipped one cannot) | 6D |
| Contract `resources` | `contracts/resources.py:69-160` | `registry.py:98-108, 376-387` | `ContractEditorDialog.gd` (Resources tab) | validated writer | `configuration_dialog_smoke.gd` | 6C |
| Contract `stats` (roles, order, short) | `contracts/stats.py:65-192`; `world.py:173-181` | `registry.py:215-222, 393-422` | `ContractEditorDialog.gd` (Stats tab) | validated writer | `npc_stat_vocabulary_smoke.gd` | 6C |
| Contract `attack_profiles` | `contracts/equipment.py:55-115` | `registry.py:110-123` | `ContractEditorDialog.gd` (tab) | validated writer — but `cooldown`, `resource_cost`, `tags` are **read by nothing** | `contract_field_audit.py` | 6C |
| Contract `defense_profiles` | `contracts/equipment.py:120-154` | `registry.py:125-132` | `ContractEditorDialog.gd` (tab) | validated writer — `tags` unread | `contract_field_audit.py` | 6C |
| Contract `effect_packets` | **none — `registry.effect_packet()` has zero call sites** | `registry.py:145-158` | `ContractEditorDialog.gd` (tab) | validated writer for a dead section | `contract_field_audit.py:153-167` | 6C (engine decision) |
| Contract `abilities` | `contracts/equipment.py:159-207` | `registry.py:134-143` | `ContractEditorDialog.gd` (tab) | validated writer — `effect_packet` unread | `contract_field_audit.py` | 6C |
| Ruleset `combat.retreat` | `world.py:361-369` | `content_set.py::_validate_simple_ruleset_sections` (`combat`) — string skill, non-negative numeric difficulties (a quoted one raised mid-fight) | typed skill and difficulty controls in `RulesetEditorDialog.gd` | validated writer | `configuration_dialog_smoke.gd`, `test_configuration_save.py` (staged engine verdict) | 6D |
| Ruleset `combat.additional_blocked_command_names`, `additional_combat_message_tokens` | `command_execution.py:373`; `status_payloads.py:650` | **none** | absent | absent | none | 6D |

## G. Progression & flows

| Declaration | Engine reader | Validator | Editor writer | Status | Evidence | Batch |
|---|---|---|---|---|---|---|
| Backgrounds (`data/player/backgrounds.json`) | `core/backgrounds.py:100-102`; `game_manager.py:144` | `content_set.py:2394-2490` | `BackgroundInspector.gd:35-410` — **8 fantasy stat names hard-coded** (`:18`) | journey-proven | `background_authoring_smoke.gd`, `p4_progression.py` | 6D |
| Ruleset `advancement` (`curve`, `grants`) | `core/advancement.py:269-368` | `content_set.py:2682-2772` checks the curve, grant IDs, known ledger kinds, and item matchers | `RulesetEditorDialog.gd`: curve controls plus grant cards for kinds, XP, message, and all engine-read match filters; unowned row metadata is preserved | validated writer | `configuration_dialog_smoke.gd`; `p4_progression.py`, `test_configuration_save.py` (staged engine verdict) | 6D |
| `data/advancement.json` (alternate config) | merged first (`advancement.py:275-289`), the ruleset section replacing it key by key | `content_set.py::_validate_advancement_content` — the same checks as the ruleset section, plus a warning for each key the ruleset overrides | none by design — Ruleset › Advancement is the authoring surface; no shipped set uses this file | validated (read-only) | `test_content_set_validator.py::TestAlternateAdvancementFile` | 6D |
| Quests (`data/quests/quests.json`) | `core/quests/loader.py:22-72` | `content_set.py:1714-1940` (this file only); `reference_integrity_validator.py:172-231`; `_validate_quest_rewards` (types, references, the quantity the engine indexes directly) | `QuestInspector.gd:40-137`; `QuestObjectiveEditor.gd:40-257`; rewards (xp, gold, item and relationship rows) added 2026-09-23 -- they had no control | journey-proven | `quest_inspector_smoke.gd`, `p6_new_objective_types_journey.py`, `m2_route_journeys_smoke.gd` (editor edit -> engine-checked save -> `edited_route_check.py` play, shipped vs edited) (edited rewards and closing line paid and shown on turn-in) | 6D |
| `quests/instances.json` (instance seeds) | `quests/loader.py:22-72`; `quest_generation/generator.py::generate_instance_quest`; `world/instance_manager.py::instantiate_quest_region` | `content_set.py::_validate_instance_quests` — `type`/`clear_region` objective, target/giver/completion NPCs, entry regions, room and target-count ranges, room-name pool, ids shared with `quests.json` | `InstanceQuestInspector.gd` under its own "Instance Quests" library category (previously opened in `QuestInspector`, which wrote `stages: []` on open) | validated writer — the generated quest is proven end to end, not yet through an editor journey | `instance_quest_authoring_smoke.gd`, `test_content_set_validator.py::TestInstanceQuests`, `test_instance_quest_authored_fields.py` | 6D |
| Ruleset `quest_generation` (boards, naming, interests, text templates) | `quests/manager.py:24-43, 213-287`; `quest_generation/generator.py:57, 113-126` | `content_set.py::_validate_ruleset_references` — every key: board rooms, delivery item, notices, turn-in phrases, NPC-interest keys against real templates, and `str.format` placeholders (the `instance_quest` patterns crash on an unknown one) | `QuestGenerationSection.gd` inside `RulesetEditorDialog.gd`; `RulesetDraft.gd::_validate_quest_generation` rechecks free-typed patterns | validated writer — no journey authors a notice through the editor | `ruleset_quest_generation_smoke.gd`, `test_content_set_validator.py::TestQuestGenerationPolicy`, `p6_new_objective_types_journey.py` (board locations) | 6D |
| Campaigns (`data/campaigns/*.json`) | `campaign_manager.py:21-34` | `content_set.py::_validate_campaigns` — required keys, node types the manager acts on (QUEST, END), quests, outcomes, triggers a quest reports, shadowed transitions, targets, chance, unread `conditions`, an END reachable from the start; `reference_integrity_validator.py:233-261` (ids) | `CampaignInspector.gd`: envelope plus the node graph as cards — rename (updates targets and the start), type, quest, outcome, ordered transitions (trigger, target, chance, narrative; reorder, add, remove). Types and triggers are parity-checked against `campaign_models.py` | validated writer | `campaign_authoring_smoke.gd`, `campaign_graph_authoring_smoke.gd` (ends with the engine validator), `test_content_set_validator.py::TestCampaigns`, `test_campaign_vocabulary.py`, `schema_parity_smoke.gd` | 6D |
| Dialogue graphs (`data/dialogue/*.json`) | `dialogue/manager.py:199-210, 240-253` | `content_set.py:1483-1653, 1675-1711` | `DialogueInspector.gd:54-262` | journey-proven — **one gap: presentation variants on a node's `text` are flattened** (`:646-651`, `:218-229`) | `dialogue_authoring_smoke.gd`, `p5_dialogue.py` | 6D |
| Titles (`data/titles.json`, `_guilds`) | `core/titles.py:75-83` | `content_set.py:2492-2534` | `TitleInspector.gd:40-347` | validated writer — no runtime journey confers an authored title | `title_authoring_smoke.gd`, `skill_audit.py` | 6D |
| Collections (`data/collections.json`) | `core/collection_manager.py:20-34` | `content_set.py:1259-1296` | `CollectionInspector.gd:23-135` | journey-proven | `collection_authoring_smoke.gd`, playability examine/get | 6D |
| Discoveries (`data/discoveries.json`) | `core/discovery_manager.py:27` | `content_set.py:1299-1334` | `DiscoveryInspector.gd:26-131` | journey-proven | `p7_sunken_lake.py` fires an authored discovery, `m2_route_journeys_smoke.gd` (editor edit -> engine-checked save -> `edited_route_check.py` play, shipped vs edited) (a renamed discovery is announced; its grant pays -- it never had, 2026-09-23 fix) | 6D |
| Knowledge topics (`data/knowledge/topics.json`) | `knowledge_manager.py:31-57, 302` | `content_set.py::_validate_knowledge_topics` (new) checks shape, `__common_topics__` self-references, and every response's condition/effect keys | `KnowledgeInspector.gd`: display name, keywords, and per-response text/priority/conditions/effects. Conditions are this system's own vocabulary (region_id/faction/template_id/knowledge_state/campaign_state/campaign_outcome/quest_state), copied from `knowledge_manager.py`'s constants and checked by `schema_parity_smoke.gd`, with `test_knowledge_condition_vocabulary.py` tying those constants to the words `_check_conditions` compares; effects reuse `DialogueSchema.gd`'s vocabulary exactly | validated writer | `knowledge_authoring_smoke.gd` (round-trips fantasy_frontier's real 14 topics); `test_content_set_validator.py`; `schema_parity_smoke.gd`; `test_knowledge_condition_vocabulary.py`; `save_engine_verdict_smoke.gd` (library saves roll back on refusal) | 6D |
| Field interactions (`data/world/field_interactions.json`) | `headless/field_fx.py:60-116, 207-263` via `headless_server.py:213` | `content_set.py::_validate_field_interactions` — known keys, polarity vocabulary, 0–1 coefficients, lower-case field ids, no self-suppression; undeclared fields warn | `FieldInteractionsDialog.gd` (Explorer › Ambient Fields…) over `FieldInteractionsDraft.gd`; saves through `configuration_save.py`, which may now create this one optional file | validated writer | `field_interactions_authoring_smoke.gd`, `test_content_set_validator.py::TestFieldInteractions`, `test_configuration_save.py` | 6D/6E |

## H. World & system policy — the ruleset

One row per section of `content_sets/fantasy_frontier/rules/ruleset.json` (21 top-level
keys). "Editor" is what `RulesetEditorDialog`/`RulesetDraft` can write today; everything
else in the file is preserved byte-for-byte and cannot be authored.

| Section | Engine reader | Validated by | Editor writes | Status | Batch |
|---|---|---|---|---|---|
| ~~`ruleset_id`~~, ~~`world_mode`~~ | removed 2026-09-23: read by nothing (the world mode is the server's feature profile `world.mode`) | `content_set.py::_refuse_retired_ruleset_keys` refuses both | no (the dialog's fields are gone) | retired | 6D |
| `progression_model` | `content_set.py:108-110`; `world.py:128` | `content_set.py:108-118` | yes (free text) | validated writer | 6D |
| `world.regions` (policy flags, `biomes`, `region_types`) | `world.py:797-798` | `content_set.py:236-343` | yes (3 checkboxes + 2 lists) | validated writer | 6C |
| `weather` (`profiles`, `descriptions`) | `weather_manager.py:27-67`; `information.py:185` | `content_set.py::_validate_weather_shapes` checks `descriptions` and each profile's `map`/`travel_notes` are string maps, alongside the existing profile-reference check; **`chances` is read by the engine and remains absent here** | `RulesetEditorDialog.gd`: description rows plus one card per profile (id, map rows, travel-note rows); an authored empty `map`/`travel_notes` round-trips as empty rather than being dropped | validated writer | `configuration_dialog_smoke.gd`; `ruleset_weather_smoke.gd`; `test_content_set_validator.py`, `test_configuration_save.py` (staged engine verdict) | 6D |
| `systems` | `content_set.py:80-124` | `content_set.py:80-124` (manifest mismatch = error) | 8 toggles | validated writer | 6B |
| `combat.retreat` | `world.py:361-369` | `content_set.py::_validate_simple_ruleset_sections` (`combat`) | typed skill and difficulty controls in `RulesetEditorDialog.gd` | validated writer | `configuration_dialog_smoke.gd`, `test_configuration_save.py` (staged engine verdict) | 6D |
| `locksmithing` | `world.py:540`; `items/lockpick.py:67` | `content_set.py::_validate_simple_ruleset_sections` — string skill; warns when no `skills.stat_bonuses` rule backs it | yes — World Rules (`WorldRulesSection.gd`) | validated writer | 6D |
| `crime` (+ `custody`) | `core/crime_manager.py:26-211`; `commands/jail.py:36-47` | `content_set.py::_validate_crime_and_debug_rules` — known keys, real numbers (the reader turns anything else into 0), boolean `enabled`, and while enabled a skill, reputation key and a `room_property` some room carries | yes — Crime (`CrimeSection.gd`); the jail-room check runs in the staged save | validated writer | 6D |
| `player_defaults` | `world.py:135-146`; `player/core.py:72`; `definition_loader.py::grant_starting_inventory` | `content_set.py::_validate_simple_ruleset_sections` — real items with integer quantities (a string quantity stopped character creation), real default spells | yes — World Rules (`WorldRulesSection.gd`) | validated writer | 6D |
| `quest_generation` | `quests/manager.py`; `generator.py` | `content_set.py::_validate_ruleset_references` (all keys) | yes | validated writer | 6D |
| `crafting.salvage_rules` | `crafting_manager.py:424-464` | `content_set.py:2083-2129` | fallback picker plus family/reference/rate rows (see the Crafting table) | validated writer (this row said absent after the form shipped; corrected 2026-09-24) | 6C |
| `social` (`tiers`, `gift_values`, `gift_tag_values`) | `social/relationships.py:28-70`; `use_give.py::_gift_affinity`; `mercantile.py:64` | `content_set.py::_validate_social_rules` | `SocialSection.gd` (Ruleset dialog: tier rows, the seven gift categories showing engine defaults, gift-tag rows; writes only changes) | journey-proven | 6D |
| `economy.currency_name` | `world.py:155-157` | `content_set.py::_validate_simple_ruleset_sections` | yes — World Rules (`WorldRulesSection.gd`) | validated writer | 6D |
| `advancement` | `core/advancement.py:269-368` | `content_set.py:2682-2772` | curve plus grant cards (kinds, XP, message, and engine-read match filters) (a save kept only the first grant card until 2026-09-23: cards were matched by a node name Godot uniquifies) | journey-proven | 6D |
| `loot` (`take_hint`, `chest_materials`, `currency_item_id`, `ambient_pools`) | `utils/utils.py:431-434`; `chest_loot_generator.py:87-126`; `npc.py:184-235` | `content_set.py::_validate_loot_settings` (unknown keys, hint placeholders, chests that are Containers, a real currency) and `_validate_ambient_loot_references` | `LootSection.gd` (Ruleset dialog: hint with an off switch, currency picker, ordered chest list, ambient pool cards with selectors and weighted drops) | validated writer | 6C |
| `skills.stat_bonuses` | `skill_system.py:43-49` | `content_set.py:_validate_skills_rules` | skill id, stat and per-point rows in `RulesetEditorDialog.gd` | validated writer | 6C |
| `factions` (not declared by fantasy) | `world/factions.py:48-118` | `content_set.py:854-880` | `extra` only | validated writer | 6D |
| `status` (orbital only) | `world.py:178` fallback; `contracts/stats.py:175` primary | `content_set.py::_validate_simple_ruleset_sections` — unique non-empty `stats` | `status.stats` only | validated writer | 6C |
| `npc_naming` | `npc_factory.py:61-73` | `content_set.py::_validate_simple_ruleset_sections` — `random_name_pattern` placeholders (an unknown one raised at spawn); repeated names warn (fantasy listed 18 twice; deduplicated) | yes — World Rules (`WorldRulesSection.gd`) | validated writer | 6D |
| `calendar` | `time_manager.py:23-52` | `content_set.py::_validate_simple_ruleset_sections` — name lists the reader would silently replace, start time range | yes — World Rules (`WorldRulesSection.gd`) | validated writer | 6D |
| `spawning` | `spawner.py:87,95` | `content_set.py::_validate_simple_ruleset_sections` — warns on a keyword matching no room (fantasy: `temple`, `home`) | yes — World Rules (`WorldRulesSection.gd`) | validated writer | 6D |
| `elites` | `npcs/elite.py:13-46` | `content_set.py::_validate_simple_ruleset_sections` — chance/multiplier ranges, `name_pattern` placeholders (an unknown one raised at spawn) | yes — World Rules (`WorldRulesSection.gd`) | validated writer | 6D |
| `npc_schedules` | `ai/schedules.py:58-173` | `content_set.py:_validate_npc_schedule_rules` validates roles, category keywords, slot ordering/references, canonical hours, and the one dispatcher-supported override | `RulesetEditorDialog.gd`: excluded names, room-name categories, role/template matching, ordered location slots, and daily activities. It preserves unknown setting-specific data on touched rows | validated writer | `test_content_set_validator.py`; `configuration_dialog_smoke.gd`, `test_configuration_save.py` (staged engine verdict) | 6D |
| `debug` | `commands/debug_crafting.py:62`, … | `content_set.py::_validate_crime_and_debug_rules` — known keys; gear, station and spell references resolve | no | absent (validated) | 6D |

**Notes.** The editor can write 20 of the 21 top-level keys: one scalar
(`progression_model`), `systems` (8 toggles),
`world.regions` (3 flags + 2 lists), `status` (`stats` only), `factions` (`extra` only),
`combat` (`retreat` only), `crafting` (`salvage_rules` only), the seven World Rules sections, `crime`,
`weather` (`descriptions` and `profiles` only, not `chances`),
plus structured `npc_schedules`, `advancement`, `skills.stat_bonuses` and
`quest_generation` sections. `test_configuration_dialog_coverage.py` holds the exact
set and fails on any `RulesetDraft` setter it cannot map. Seven small
sections (`locksmithing`, `player_defaults`, `economy`, `npc_naming`, `calendar`,
`spawning`, `elites`) have a validator and a form, the Ruleset editor's World Rules
section (`ruleset_world_rules_smoke.gd`). `crime` and `debug`
have validators too, so every top-level ruleset section is now checked by something.

### H.2 The three configuration dialogs, field by field (6A exit evidence)

M0's "exhaustive field/default coverage" gate is measurable, so it is measured rather
than asserted. `server/tests/singles/test_configuration_dialog_coverage.py` (11 tests)
scans the dialog sources and compares them with the engine's schemas; the allowlists in
that test *are* the record, so a field that stops being authorable fails the suite by
name, and a field that becomes authorable fails until the record is updated. The check
was falsified by removing one `_field(...)` line from a builder — it failed naming
`('defense_profiles', 'material')`.

| Dialog | Engine schema | Authorable | Not authorable (recorded, with reason) |
|---|---|---|---|
| `ContractEditorDialog` | `CONTRACT_SCHEMAS`: 8 sections, **69 fields** | 67 | `item_families.description`, `item_families.debug_only` — both read by nothing (§I.5), preserved as authored |
| `ContractEditorDialog` (file level) | `TOP_LEVEL_FIELDS` | `stats` page (`order`, `short`, `roles`) — validated by `registry._ingest_stats` | `schema_version` (engine-owned), file-level `label`/`description` (unread, preserved) |
| `RulesetEditorDialog` | 21 top-level keys | **20** (`crime`, `social`, `loot`, the seven World Rules sections, `progression_model`, `systems` ×8, `world.regions` ×5, `factions.extra`, `status.stats`, `combat.retreat`, `crafting.salvage_rules`, `skills.stat_bonuses`, `npc_schedules`, `advancement`, `weather` descriptions/profiles, `quest_generation`) | `debug` (developer tooling), byte-for-byte preserved |
| `CombatVocabularyDialog` | `combat/elements.json` | `valid_damage_types`, `default_damage_type`, and every hazard field the shipped file uses (`channel`, `damage`, `flavor`, `tick_interval`) | `elemental_opposites`, `flavor_text` |

**What this says about 6A.** The contract and combat-vocabulary dialogs are close to
field-complete against the schema, which is better than the §F rows imply — their
remaining gaps are validation scope and journeys, not missing controls. The ruleset
dialog is the one that is genuinely partial (7 of 23 keys), and the test records two
facts worth keeping: `ruleset_id` and `world_mode` were writable but read by nothing
(§I.5; both removed 2026-09-23), and `factions` is writable although **no shipped set declares it**, so the
"Custom Factions" panel has no example to copy from.

---

## I. Cross-cutting

### I.1 The validation surface

15 canonical checks, 29 gate steps (`content_check_steps.py:122-213`). The editor's
Validate button runs engine, references, templates, abilities, stale, json, numbers,
contracts, skills, neutrality and **playability for the open set** (`editor_validate.py:83-255`);
the remaining scopes are shown to the author with their reason (`editor_coverage()`
`:309-324`). Two checks deliberately cannot fail: `skill_audit` returns 0 whatever it
finds, and `genre_coupling_audit.py` has no runner. `content_neutrality_validator.py` has
no test module anywhere, so the neutrality gate has never been shown to fail.

### I.2 Lifecycle, switching and recovery

Safe and tested: switching writes both kinds of work, clears per-set state, and refuses
an unknown root (`content_set_switch_smoke.gd`); configuration saves stage the file,
compare SHA-256, run the engine verdict and keep a `.bak`
(`configuration-editing-safety.md`); the four-set byte round trip is green
(`content_round_trip_smoke.gd`); **a set can now be renamed or removed from the
chooser** (`ContentSetAdmin.gd`), inside the sets root only and only with the name
typed, and a rename moves the directory and the manifest `id` together
(`content_set_lifecycle_smoke.gd`). **Registered external roots are now supported**
without scanning or mutating their parents (`DataRoot.gd`,
`external_content_set_roots_smoke.gd`): registration is an exact manifest-bearing
folder stored alongside the active-root preference, and forgetting it never deletes
its files. Editing `paths` after creation remains deliberately unavailable.

**Multi-file saves have a checkpoint now** (2026-09-21). `SaveCheckpoint` copies the
set's `data/` tree before `Main._save_everything` writes anything and restores it if a
write fails, so "the previous coherent set" is a fact rather than a hope; restore
replaces the tree (a file the failed save created is removed, a truncated one comes
back), refuses a checkpoint from another set, and prunes to the newest three. Since
2026-09-22 (`a151633`) content-library and region saves also take the engine's verdict:
`Main._save_everything` writes, runs the content-set validator, and on refusal restores
the checkpoint while the edits stay open and dirty. That is the same guarantee as the
configuration dialogs' staged save, reached by rollback rather than staging. It went
unproven until `save_engine_verdict_smoke.gd` (2026-09-23), which drives the real editor
scene: a refused region edit and a refused library edit each leave disk byte-identical
and the work dirty, and the test fails in 10 places with the verdict disabled.

**Manifest capability changes now coordinate their matching explicit ruleset system
declarations** (2026-09-22). `configuration_transaction.py` validates the pair in one
staged set, writes per-file backups before either replacement, and restores the first
file if the second write fails. The manifest dialog tells the author that disabling a
capability retains related content as inactive; it does not delete recipes, items or
NPCs. `test_configuration_save.py` covers successful coordinated save, staged refusal
and a forced second-write rollback; `manifest_editing_smoke.gd` drives the actual UI.

**Change foundations, precisely** (verified for 6B's spec in `chunks-of-work.md` §6B;
updated 2026-09-21 as the first piece landed):

- **The reverse index exists now.** `toolkit/reference_index.py` answers "what names
  this id" over the gate's six families, sharing `REFERENCE_FAMILIES` and
  `reference_tables()` with the validator rather than re-deriving them. It reports
  its own coverage, so an id with no referrers reads as "nothing in the indexed
  families names this" and never as "unused". The editor runs it from the delete
  confirmation (`ReferenceIndex.gd`, `Main._confirm_delete_db_entry`).
- **Renaming an entry now asks, then repairs what it can reach** (2026-09-21).
  `DatabaseManager.rename_entry` (`:593-613`) still only moves the cache key, but the
  inspector no longer calls it directly: `Main._on_request_entry_rename` lists the
  index's referrers, repairs them through `DatabaseManager.patch_reference` (library
  caches) and `RegionManager.patch_reference` (region files — spawner weights, locked
  doors, release destinations), and names any that fail rather than leaving them for
  the next validation to find. Region patches go in memory when the region is open,
  and read-patch-write otherwise; an unparseable file is refused, not rewritten.
- **Deleting an entry shows its referrers first** (2026-09-21) and still checks
  nothing else: `delete_entry` (`:647-656`) removes it and returns the removed value
  so the delete can be undone.
- **One repair path exists and it is exits-only.** `RegionManager.gd:247-289` rewrites
  `region:room` exits in other region files after a room rename (text-scan, parse, patch,
  verified write, errors collected). Content references to a room — an NPC schedule, a
  title's guild `place`, a quest's `spawn_on_entry.room_id` — are not repaired, and
  none of them are indexed yet either.

The rest of 6B — multi-file staging with recovery, and the project-lifecycle half —
is unchanged, and the ledger's job is to keep it visible while 6C/6D add more rename
and delete paths.

### I.3 Vocabulary parity

Parity-checked through `engine_vocabulary_dump.py` + `schema_parity_smoke.gd`: condition
kinds (both directions), effect keys, objective types, effect shape hints, direction
reciprocals, manifest shape. Still unchecked copies, each a drift risk:
`ContractEditorDialog.gd:8-10` (`ITEM_CLASSES`, `RESOURCE_KINDS`, `STAT_ROLES`),
`ItemInspector.gd` class and equip-slot lists, `BackgroundInspector.gd:18` (eight stat
names), `NPCInspector.gd` attribute fallbacks, the `COMMON_PROPS` tables,
`ContractCatalog`'s fallbacks, `EngineValidator`'s source list, `ReferenceEditor`'s
target kinds.

### I.4 Read by the engine, validated by nothing

Room `env_properties` and `properties.locked_by`;
`spawner` toggles and weights; NPC `loot_table` and gift preferences; containers; affixes; and
the presentation file's descriptive fields. Each is a value a content author can write, the engine will act
on, and no gate will refuse. Room time descriptions plus the NPC template envelope
(`friendly`, stats/level, direct schedule, patrol, inventory and behaviour tuning) now
have runtime-shape validation; the remaining rows are the actual validator debt.

### I.5 Dead declarations and disagreements

Parsed and read by nothing: contract `effect_packets` (whole section),
`attack_profiles.cooldown`/`.resource_cost`/`tags`, `work[].tags`,
`work.declaration_issues()`, `manifest.title`/`version`, `presentation_path`,
`region.properties.biome`/`region_type` (ruleset `ruleset_id`/`world_mode` removed 2026-09-23).

Validators that disagree about the same fact (engine vs toolkit): `behavior_type`
vocabulary (toolkit invents three names, omits `follower`); vendor stock
(`sells_items` vs `buy_orders`); `damage_type` (toolkit rejects unknown channels, engine
only checks hazard channels); `spawner.monster_types`/`npc_types` ids (toolkit errors,
engine never resolves); item `name`/`type` (warning in the gate, fatal in playability -- the engine validator now refuses both, 2026-09-23);
`normalize_content_numbers.py` lists `defense` as both int and float, and `FLOAT_FIELDS`
is never read. Every one is a Track I finding with a citation, not an editor gap — but
each makes the editor's "no issues" less meaningful than it looks.

### I.6 Fixed while building this ledger

**A red suite at HEAD.** `test_content_check_steps.py::test_the_editor_names_what_it_did_not_run`
still asserted that `playability` appears in `not_run`, which stopped being true when the
editor began booting the open set. The suite was red at `93b7b9a` on that one assertion;
it now asserts both halves — `playability` ran, and `playability_other_sets` is declared.

**A new check, because two of these rows are mechanical.**
`server/tests/singles/test_configuration_dialog_coverage.py` (11 tests) compares the three
configuration dialogs with the schemas they write and fails in both directions when the
record drifts (see §H.2). It was falsified before being trusted: removing one
`_field(...)` line from `ContractEditorDialog.gd` fails it by name, and the file was
restored byte-for-byte afterwards.

---

## J. What this means for the batches

| Batch | Rows it closes | The one thing that must not be skipped |
|---|---|---|
| 6A (active) | cross-cutting: M0 hardening, visual/error layout, async validation | Field-level coverage is not a retest of the three dialogs; M0's gate is "an unrelated edit preserves every untouched typed field", which the ledger's `prototype` rows still fail. |
| 6B | A (all), B (region delete, level band, districts), H `systems` | The dependency index has to exist before the destructive controls do — a used identifier must not be deletable unnoticed. |
| 6C | D (affixes, sets, containers, node yields), E (stations, salvage rules, skills, `work` in fantasy), F (contract sections), I `crafting`/`loot` | Every row here is a *generation* input: an author tunes a distribution, so the proof is seeded samples, not a saved file. |
| 6D | C (all eleven absent rows), F (combat policy, elements leftovers), G (advancement, campaigns, knowledge topics, titles/collections/discoveries), H (the eleven unvalidated sections) | Eleven ruleset sections need a Track B validator before they get a form; the honest interim is read-only with the reason on screen. |
| 6E | the second consumer for each 6C/6D primitive | `work` currently has one shipped proof (orbital) and none in the reference set. |
| 6F/6G | migration and release-candidate rows | Nothing in this ledger is evidence for either; they start from M4's rehearsals. |

**The five rows that most change what an author can do**, in order: NPC
faction/behaviour/dialogue-binding (C), the ruleset sections that gate systems (H),
`knowledge/topics.json` and campaigns (G), item affixes/sets/containers (D), and room
hazard placement (B). Four of the five are `absent` rather than partial, which is why
they are cheap to start and expensive to fake.

## How to update this ledger

1. Change a row only with the evidence its new status requires; a dialog is not
   evidence for `validated writer` and a saved file is not evidence for
   `journey-proven`.
2. When a batch lands, add its test name to **Evidence** and move **Batch** to the next
   one that touches the row; do not delete a row because a surface was removed — say
   what replaced it or that nothing did.
3. Re-check a claim by running its named check, not by reading the editor: the gate and
   the editor share one check list, so `run_content_checks.py --help` and
   `toolkit/content_check_steps.py` are the authority on what "validated" covers.
4. Cite `file:line` when adding a reader, validator or writer; a row without one is a
   claim, not evidence.
