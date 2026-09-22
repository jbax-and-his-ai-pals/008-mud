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

**Basis.** HEAD `f08146d` (2026-09-22), plus the 2026-09-22 reference-preflight and
post-save engine-verdict hardening recorded in §I.6. Readers and validators were read out of
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
| Manifest `capabilities` | `content_set.py:94-106` → `world.py:55,106,114,124` | `content_set.py:3003-3025`; the staged verdict refuses a capability that contradicts `ruleset.systems` | creation + `ManifestEditorDialog.gd` (checkboxes) | validated writer | `manifest_editing_smoke.gd`, `test_configuration_save.py` | 6B |
| Manifest `start` | `world.py:230-231`; `definition_loader.py:201-220`; `persistence.py:267-268` | `content_set.py:3027-3061` — an unplaceable start room is refused by the staged verdict | creation + `ManifestEditorDialog.gd` | validated writer | `manifest_editing_smoke.gd` | 6B |
| `opening/*.json` | `headless/session.py:264-286` (heading, intro, objectives) | `content_set.py:2966-2975, 3040-3045` — `scenario_id` match only | absent (scaffold copies the folder) | absent | `character_creation_and_opening_guidance.py` (engine side) | 6B |
| `presentation/*.json` (theme pack, ui strings, accessibility) | **none server-side** — `content_set.py:165, 3129` assign and never read | `pack_tool.py` validates `client/themes`, not the set's declared pack | absent (copied by the scaffold) | absent | `pack_tool_compatibility.py` (client side only) | 6B |
| Feature profile (`data/profiles/*.profile.json`) | `feature_profile.py:53-59` via `headless_server.py:189-190` | `content_set.py:2963-2965` (object-ness only) | absent | absent | `feature_profile.py` | 6B |

**Notes.** Three of four sets name a `theme_pack` (`modern_neutral`) that does not
exist, which nothing reports because nothing reads the field. A manifest cannot be
edited after creation, so every row here is "rewrite the file by hand" except at
scaffold time.

## B. World

| Declaration | Engine reader | Validator | Editor writer | Status | Evidence | Batch |
|---|---|---|---|---|---|---|
| Region envelope (id, name, description, `properties`, rooms) | `definition_loader.py:159-176`; `region.py:50-69` | `content_set.py:719-747`; `reference_integrity_validator.py:107-121` | `RegionInspector.gd` + `Main.gd:794-835` | prototype (no delete-region control) | `content_round_trip_smoke.gd`, `content_source_check.gd` | 6B |
| Rooms (identity, prose, `_editor_pos`) | `room.py:10-30` | `content_set.py:761-803` | `ActionHandler.gd:66-92` (create), `:130-155` (delete), `RegionManager.gd:109-124` (save) | prototype | `editor_session_safety_smoke.gd` | 6B |
| Exits / connections (direction, reciprocity, lock, hidden) | `room.py:10-30`; `world.py:397-449` | `content_set.py:761-803`; reachability `:818-851`; `reference_integrity_validator.py:131-142` | `ActionHandler.gd:29-64`; `RoomConnectionsPanel.gd` | prototype | `connection_editing_smoke.gd`, `reciprocal_label_smoke.gd` | 6B |
| Room `properties` — scalars | `world.py:440` (`locked_by`); `room.py:129-132` (`time_descriptions`) | only `hidden_exits` (`content_set.py:789-801`) and `entered_by_system` (`:837-840`) | `RoomPropertiesPanel.gd:53-125` via `PropertyTagRow.gd:40-45` | prototype | `nested_property_survival_smoke.gd` | 6B |
| Room `properties` — nested (`hidden_exits`, `exit_requirements`, `env_interactions`, `time_descriptions`) | `items/interactive.py:56-63`; `world.py:397-416`; `room.py:69-100` | `hidden_exits` only (`content_set.py:789-801`, `:1675-1711`) | read-only row (`PropertyTagRow.gd:152-185`) | read-only | `nested_property_survival_smoke.gd` | 6C |
| Room atmosphere and time descriptions (`env_properties`: dark/outdoors/windows/noise/smell/temperature; `time_descriptions`: dawn/day/dusk/night) | `room.py:21,30,127-132,141-142,190-199`; `weather_manager.py:50` | `content_set.py` authored-world gate — closed keys/types, ignored-key warning | `RoomEnvironmentPanel.gd` controlled atmosphere and optional time-description fields | prototype | `room_environment_authoring_smoke.gd`, `test_content_set_validator.py` | 6C |
| Room hazards (`properties.hazard_type`, `hazard_damage`, `hazard_tick_interval`, `weather_hazard_multipliers`) | `world/environment.py:59-106` | `content_set.py:431-587` — only when `data/combat/elements.json` exists; coverage only if the ruleset opts in | `RoomEnvironmentPanel.gd` picks declared hazards and offers contextual numeric/weather overrides | prototype | `room_environment_authoring_smoke.gd`, `content_set_runtime.py` (hazard damage), `environment_reader.py` | 6D |
| Room `initial_npcs` (+ placement `overrides`) | `definition_loader.py:247-278` (runtime whitelist) | `content_set.py:805-839` validates supported types and names ignored keys | `RoomContentPanel.gd` guided placement overrides (name, stats/pools, behaviour) | prototype — patrol routes and `properties_override` are preserved, not yet structured | `room_item_placement_smoke.gd`, `test_content_set_validator.py` | 6C |
| Room `items` (`quantity` + `properties_override`) | `definition_loader.py:230-247`; `world.py:624` | `content_set.py:812-824`; `reference_integrity_validator.py:143-156` | `RoomContentPanel.gd` guided placement overrides (name/description; container state; resource charges/respawn) | prototype — extension-owned override keys are safely preserved but not authored | `room_item_placement_smoke.gd`, `test_definition_loader_full.py`, `test_content_set_validator.py` | 6C |
| Districts (`properties.districts`) | `world.py:786-827` | `content_set.py:590-677`; policy `:315-344` | `ActionHandler.gd:316-443`; `DistrictInspector.gd:62-84` | prototype (no delete; colour is display-only) | `districts.py`, `district_pinch_smoke.gd` | 6B |
| Region `spawner` (weights, toggles, level_range) | `spawner.py:104-171`; `region.py:68` | `content_set.py:412-428` — `level_range` only | `SpawnerInspector.gd:22-151` | prototype | `region_policy_validator.py` (partly) | 6C |
| Region `properties.level_band` | `region.py:20-41`; `spawner.py:143` | `content_set.py:375-428` (policy-gated) | creation-time only; rendered non-editable (`RegionInspector.gd:220`) | read-only | `p7_region_bands.py` | 6C |
| Region `properties.biome` / `region_type` | **no runtime reader** | `content_set.py:347-372` | creation-time / scalar tag | read-only | `region_policy_validator.py` | 6D |
| `properties.weather_profile` | `weather_manager.py:55,65` | `content_set.py:1131-1166` | free-form scalar tag | read-only | none | 6D |
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
| NPC envelope (name, description, level, health/mana, `stats`, attack/defense) | `definition_loader.py:108-157`; `npc_factory.py:77-149` | loader requires `name` only (`definition_loader.py:141-143`) | `NPCInspector.gd:46-122` | prototype | `npc_stat_vocabulary_smoke.gd` | 6D |
| NPC `faction` | `npc_factory.py:141`; `world/factions.py:155-176` | `content_set.py:883-926` — **warning only**; unknown faction silently becomes a bystander | `NPCInspector.gd` faction picker: the engine's five plus this set's `ruleset.factions.extra`/`overrides`, each labelled with its resolved disposition; an already-authored but undeclared value is shown, not dropped | prototype | `npc_faction_behavior_smoke.gd`; `schema_parity_smoke.gd` checks `NPCVocabulary.gd` against the engine | 6D |
| NPC `behavior_type` | `npc_factory.py:142`; `ai/dispatcher.py` | `content_set.py:909-915` — warning only; unknown value means the NPC never acts | `NPCInspector.gd` behavior picker, from `NPCVocabulary.BEHAVIOR_TYPES` | prototype | `npc_faction_behavior_smoke.gd`; `schema_parity_smoke.gd` | 6D |
| NPC `friendly` | `npc_factory.py:81` (overridden by `factions.is_hostile`) | **none** | absent | absent | none | 6D |
| NPC `dialog` (flat keyword dict) | `npc_factory.py:156-157`; `npc.py:85-86,124-125` | `template_placeholder_validator.py:97-134` (braces only) | `NPCInspector.gd` topic/reply rows; renaming a topic is a key rebuild, refused on a collision | prototype | `hostile_dialog_no_leftover_placeholders.py`; `npc_dialog_topics_smoke.gd` | 6D |
| NPC `properties.dialogue` (graph binding) | `dialogue/manager.py:243-250` | `content_set.py:1522-1540`; orphans `:1545-1549` | `NPCInspector.gd` graph picker, offering only graphs this set has; an already-bound but missing graph is shown, not dropped | prototype | `p5_dialogue.py` (engine side); `npc_dialogue_binding_smoke.gd` | 6D |
| Vendor stock (`properties.sells_items`, `sell_rate_multiplier`, `tariff`) | `mercantile.py:81-122, 370` | ids only (`reference_integrity_validator.py:470-479`) | `NPCInspector.gd`: a rate control plus a plain item picker per sold item (price multiplier, friendship floor); `tariff` remains absent (a region/world policy, not per-NPC) | prototype | `vendor_order_references.py` (orbital orders); `npc_vendor_stock_smoke.gd` | 6D |
| Vendor `properties.buy_orders` | `mercantile.py:135-155, 211-232` | `content_set.py:_validate_vendor_orders` | `NPCInspector.gd`: one card per order (id, `ReferenceEditor` for what it wants, quantity, reward, repeatable/crafted-only); id rename refused on a collision | prototype | `vendor_buy_order_relationship_gate.py`; `npc_vendor_stock_smoke.gd` | 6D |
| Gift preferences (`preferred_item_ids`, `preferred_gift_tags`, disliked…) | `use_give.py:19-51` | ids only (`reference_integrity_validator.py:458-469`) | `NPCInspector.gd`: item pickers for the two id lists, text rows for the three open-vocabulary tag/category lists; nothing written by opening, an emptied list erases its key | prototype | `relationship_gifts.py`; `npc_gift_preferences_smoke.gd` | 6D |
| `schedule`, `properties.work_location`, `can_unlock_chests`, `sells_houses` | `npc_factory.py:60-73,161`; `ai/schedules.py:143` | **none** | absent | absent | `npc_schedules_full.py` (engine side) | 6D |
| `loot_table` | `npc_factory.py:159-240`; `npc.py:160-174` | **none** | `NPCInspector.gd` — an item picker per drop (renames the entry's key; refuses a collision rather than merging two drops); no longer writes `loot_table: {}` merely by being opened | prototype | `content_round_trip_smoke.gd`, `npc_loot_table_smoke.gd` | 6D |
| Behaviour tuning (`aggression`, `flee_threshold`, `respawn_cooldown`, `wander_chance`, `move_cooldown`, `spell_cast_chance`) | `npc_factory.py:204-240`; `ai/movement.py:101-105` | **none** | absent | absent | none | 6D |
| `usable_spells`, `initial_inventory`, `patrol_points` | `npc_factory.py:159-240` | spell ids only (`reference_integrity_validator.py:557-562`) | absent | absent | `guard_patrol_content.py` | 6D |
| Ruleset `factions.extra` / `overrides` | `world/factions.py:48-118, 228-277` | `content_set.py:854-880` | `RulesetEditorDialog.gd:129-147` — `extra` (id + disposition) only | prototype | `configuration_dialog_smoke.gd` | 6D |

**Notes.** This was the largest single block of `absent` rows, and it is the block a
player notices first. `faction`, `behavior_type`, `loot_table` and gift preferences are
now prototype (2026-09-22); still absent is the rest of it: an NPC created in the editor
still cannot be bound to a dialogue graph, cannot stock a shop, and cannot have a
schedule. The engine reads and validates most of these shapes; only the editor is
missing. `ReferenceEditor.gd:10-13` documents "a vendor's buy order" as a shape the
editor knows about, which makes the absence read as a bug rather than a decision.

## D. Items & generation

| Declaration | Engine reader | Validator | Editor writer | Status | Evidence | Batch |
|---|---|---|---|---|---|---|
| Item envelope (`name`, `type`, `weight`, `value`, `stackable`, `equip_slot`) | `definition_loader.py:51-106`; `item_factory.py:142-298` | loader `:92-94`; `data_integrity_validator.py:80-95` (warning only in the gate); `content_playability_check.py:329-339` (fatal) | `ItemInspector.gd:34-78` | prototype — **unknown top-level keys are silently dropped** (`item_factory.py:220`) | `item_authoring_smoke.gd` | 6C |
| Item `properties` — nested objects (`resistances`, `substitute_resource_ids`, …) | `item_factory.py:205-259` | `content_set.py:2775-2875` (a named subset only) | read-only row (`ItemInspector.gd:386-399`) | read-only | `nested_property_survival_smoke.gd` | 6C |
| `properties.salvage_output` | `crafting_manager.py:401-464` | `content_set.py:2065-2170` | `ItemInspector.gd:93-162` via `ReferenceEditor.gd:52-120` | journey-proven | `item_authoring_smoke.gd` + playability `salvage` | 6C |
| `item_family`, `generation_profile`, rarity bands | `registry.py:285-305`; `instance_generator.py:98-118, 199-323` | `content_set.py:1986-2011, 2602-2630` | `ItemInspector.gd:175-345` (catalog-driven pickers) | prototype (save path runs no validator) | `contract_authoring_smoke.gd` | 6C |
| Affixes (`data/items/affixes.json`) | `affix_data.py:23-35`; `loot_generator.py:34-77` | **none for structure** (`data_integrity_validator.py:82` exempts it) | `AffixInspector.gd`, loaded/saved by `DatabaseManager._load_affixes`/`_save_affixes` | prototype — authorable now, still no structural validator (Track B) | `affix_and_set_authoring_smoke.gd` | 6C |
| Item sets (`data/items/sets.json`) | `set_manager.py:19-46` | `reference_integrity_validator.py:267-345` (members) | `ItemSetInspector.gd`, loaded/saved by `DatabaseManager._load_item_sets`/`_save_item_sets` | prototype — authorable now; member ids are checked by the reference gate | `affix_and_set_authoring_smoke.gd` | 6C |
| Containers (`contains`, `capacity`, `locked`, `key_id`, `is_open`) | `container.py:26-38, 339-351`; `item_factory.py:230-232` | `content_set.py:_validate_container_templates` — references, quantities, and basic state | `ItemInspector.gd` guided Container section; a room placement can locally set open/locked state | prototype | `item_authoring_smoke.gd`, `room_item_placement_smoke.gd` | 6C |
| Resource nodes (`resource_item_id`, `yield_table`, `substitute_resource_ids`, `charges`, `respawn_days`, `weather_blocked_by`) | `resource_node.py:16-30, 85-277`; `commands/gathering.py:68-74` | `content_set.py:2173-2231` — yield references and grades | `ItemInspector.gd` primary yield, tool, charges, respawn, alternate yields; a room placement can locally set charges/respawn | prototype | `item_authoring_smoke.gd`, `room_item_placement_smoke.gd` | 6C |
| `data/regions/dynamic_themes.json` (generation templates) | `region_generator.py:22-33, 68-70` | **none** (deliberately out of scope) | editor-owned `editor/templates/` instead | absent | none | 6C |

**Notes.** Generation is the family where the engine is most configurable and the editor
least: families, profiles, rarity bands and salvage are authorable, and — since
2026-09-21 — so are the two item-directory contracts that were excluded outright
(affixes, item sets). What remains unauthorable is what an author tunes most: node
yields, container contents, and the nested item properties the item panel shows but
will not write.

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
| Recipes (result, quantity, station, difficulty, quality tiers, familiarity) | `crafting_manager.py:32`; `crafting/recipe.py:63` | `content_set.py:2664-2772`; strict reader `recipe_reader_is_strict.py` | `RecipeInspector.gd:44-421` | journey-proven | `recipe_authoring_smoke.gd` + playability crafts 1 recipe/set | 6C |
| Stations (an item with `crafting_station_type`) | `crafting_manager.py` station lookup | `content_set.py:_validate_crafting_station_references` | recipe station picker lists authored station types; station item property remains scalar | prototype | `recipe_authoring_smoke.gd` + `test_container_template_validation.py`; station-property picker follows with the nested property batch | 6C |
| `crafting.salvage_rules.by_family` / `default_item_id` | `crafting_manager.py:424-464` | `content_set.py:2065-2152` | Ruleset dialog: fallback picker plus family/reference/rate rows; preserves comments and legacy class rules | prototype | `configuration_dialog_smoke.gd` | 6C |
| Contract `work` declarations | `contracts/work.py:59-101, 253-397`; `commands/work.py:23` | schema `registry.py:169-196`; semantic `work.py:181-222` — **`declaration_issues()` has no engine caller, only tests** | `ContractEditorDialog.gd:44, 219-235` (Work tab) | validated writer | `configuration_dialog_smoke.gd` | 6C |
| Work-job runtime (durations, spoil, deadlines) | `contracts/work.py:230-397`; `player/persistence.py` | runtime | — | journey-proven (engine side) | `sci_fi_proving_slice.py` (orbital only), `work_jobs.py` (synthetic) | 6C |
| `skills.stat_bonuses` | `skill_system.py:43-49` | `content_set.py:1109-1129` (shape) | absent | absent | `skill_audit.py` (warnings only) | 6C |
| Gathering tool/route requirements (`required_tool`, tags) | `commands/gathering.py:68-74`; `resource_node.py` | `content_set.py:2173-2231` | absent | absent | `fantasy_gathering_route.py` | 6C |

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
| Authored abilities (`data/abilities/`, else `data/magic/`) | `spell_registry.py:14-75`; `spell.py:42` | `ability_load_check.py:40-95` (whole file inside one `try`) | `MagicInspector.gd:29-217` | prototype — legacy `effect_type`/`effect_data`/`dot_*` have no control | `ability_load_check.py`, playability casts | 6D |
| Contract `resources` | `contracts/resources.py:69-160` | `registry.py:98-108, 376-387` | `ContractEditorDialog.gd` (Resources tab) | validated writer | `configuration_dialog_smoke.gd` | 6C |
| Contract `stats` (roles, order, short) | `contracts/stats.py:65-192`; `world.py:173-181` | `registry.py:215-222, 393-422` | `ContractEditorDialog.gd` (Stats tab) | validated writer | `npc_stat_vocabulary_smoke.gd` | 6C |
| Contract `attack_profiles` | `contracts/equipment.py:55-115` | `registry.py:110-123` | `ContractEditorDialog.gd` (tab) | validated writer — but `cooldown`, `resource_cost`, `tags` are **read by nothing** | `contract_field_audit.py` | 6C |
| Contract `defense_profiles` | `contracts/equipment.py:120-154` | `registry.py:125-132` | `ContractEditorDialog.gd` (tab) | validated writer — `tags` unread | `contract_field_audit.py` | 6C |
| Contract `effect_packets` | **none — `registry.effect_packet()` has zero call sites** | `registry.py:145-158` | `ContractEditorDialog.gd` (tab) | validated writer for a dead section | `contract_field_audit.py:153-167` | 6C (engine decision) |
| Contract `abilities` | `contracts/equipment.py:159-207` | `registry.py:134-143` | `ContractEditorDialog.gd` (tab) | validated writer — `effect_packet` unread | `contract_field_audit.py` | 6C |
| Ruleset `combat.retreat` | `world.py:361-369` | **none** | absent | absent | `skill_audit.py` (skill name only) | 6D |
| Ruleset `combat.additional_blocked_command_names`, `additional_combat_message_tokens` | `command_execution.py:373`; `status_payloads.py:650` | **none** | absent | absent | none | 6D |

## G. Progression & flows

| Declaration | Engine reader | Validator | Editor writer | Status | Evidence | Batch |
|---|---|---|---|---|---|---|
| Backgrounds (`data/player/backgrounds.json`) | `core/backgrounds.py:100-102`; `game_manager.py:144` | `content_set.py:2394-2490` | `BackgroundInspector.gd:35-410` — **8 fantasy stat names hard-coded** (`:18`) | journey-proven | `background_authoring_smoke.gd`, `p4_progression.py` | 6D |
| Ruleset `advancement` (`curve`, `grants`) | `core/advancement.py:269-368` | `content_set.py:2234-2307` | absent | absent | `p4_progression.py` | 6D |
| `data/advancement.json` (alternate config) | merged first (`advancement.py:275-289`) | **none** | absent | absent | none | 6D |
| Quests (`data/quests/quests.json`) | `core/quests/loader.py:22-72` | `content_set.py:1714-1940` (this file only); `reference_integrity_validator.py:172-231` | `QuestInspector.gd:40-137`; `QuestObjectiveEditor.gd:40-257` | journey-proven | `quest_inspector_smoke.gd`, `p6_new_objective_types_journey.py` | 6D |
| `quests/instances.json` (instance seeds) | `quests/loader.py:22-72` | **none** (`content_set.py` reads `quests.json` only) | absent | absent | `quest_loader_is_not_abandoned.py` | 6D |
| Ruleset `quest_generation` (boards, naming, interests, text templates) | `quests/manager.py:24-43, 213-287`; `quest_generation/generator.py:57, 113-126` | `content_set.py:1171-1211` — `authored_board_templates` only | absent | absent | `p6_new_objective_types_journey.py` (board locations) | 6D |
| Campaigns (`data/campaigns/*.json`) | `campaign_manager.py:21-34` | `reference_integrity_validator.py:233-261` (ids) | **absent**: loaded (`DatabaseManager.gd:415-433`), never saved (`save_all` `:512-533`), no category | absent | `finite_adventure_runtime.py`, `portbridge_content.py` (engine side) | 6D |
| Dialogue graphs (`data/dialogue/*.json`) | `dialogue/manager.py:199-210, 240-253` | `content_set.py:1483-1653, 1675-1711` | `DialogueInspector.gd:54-262` | journey-proven — **one gap: presentation variants on a node's `text` are flattened** (`:646-651`, `:218-229`) | `dialogue_authoring_smoke.gd`, `p5_dialogue.py` | 6D |
| Titles (`data/titles.json`, `_guilds`) | `core/titles.py:75-83` | `content_set.py:2492-2534` | `TitleInspector.gd:40-347` | validated writer — no runtime journey confers an authored title | `title_authoring_smoke.gd`, `skill_audit.py` | 6D |
| Collections (`data/collections.json`) | `core/collection_manager.py:20-34` | `content_set.py:1259-1296` | `CollectionInspector.gd:23-135` | journey-proven | `collection_authoring_smoke.gd`, playability examine/get | 6D |
| Discoveries (`data/discoveries.json`) | `core/discovery_manager.py:27` | `content_set.py:1299-1334` | `DiscoveryInspector.gd:26-131` | journey-proven | `p7_sunken_lake.py` fires an authored discovery | 6D |
| Knowledge topics (`data/knowledge/topics.json`) | `knowledge_manager.py:31-57, 302` | **none anywhere** | absent | absent | `knowledge_discovery.py` (synthetic) | 6D |
| Field interactions (`data/world/field_interactions.json`) | `headless/field_fx.py:207-263` via `headless_server.py:213` | **none** | absent | absent | `sample_world_effects_provider` plugin only | 6D/6E |

## H. World & system policy — the ruleset

One row per section of `content_sets/fantasy_frontier/rules/ruleset.json` (23 top-level
keys). "Editor" is what `RulesetEditorDialog`/`RulesetDraft` can write today; everything
else in the file is preserved byte-for-byte and cannot be authored.

| Section | Engine reader | Validated by | Editor writes | Status | Batch |
|---|---|---|---|---|---|
| `ruleset_id` | **no reader** | none | yes (free text) | prototype (a value nothing reads) | 6D |
| `world_mode` | **no reader** (world mode comes from the feature profile) | none | yes (free text) | prototype (same) | 6D |
| `progression_model` | `content_set.py:108-110`; `world.py:128` | `content_set.py:108-118` | yes (free text) | prototype | 6D |
| `world.regions` (policy flags, `biomes`, `region_types`) | `world.py:797-798` | `content_set.py:236-343` | yes (3 checkboxes + 2 lists) | validated writer | 6C |
| `weather` (`profiles`, `descriptions`) | `weather_manager.py:27-67`; `information.py:185` | `content_set.py:1138-1166` — profile names only; **`chances` is read by the engine and absent here** | no | absent | 6D |
| `systems` | `content_set.py:80-124` | `content_set.py:80-124` (manifest mismatch = error) | 8 toggles | validated writer | 6B |
| `combat` | `world.py:361-369` | none | no | absent | 6D |
| `locksmithing` | `world.py:540`; `items/lockpick.py:67` | none | no | absent | 6D |
| `crime` (+ `custody`) | `core/crime_manager.py:26-211`; `commands/jail.py:36-47` | none | no | absent | 6D |
| `player_defaults` | `world.py:135-146`; `player/core.py:72` | none | no | absent | 6D |
| `quest_generation` | `quests/manager.py`; `generator.py` | `authored_board_templates` only | no | absent | 6D |
| `crafting.salvage_rules` | `crafting_manager.py:424-464` | `content_set.py:2083-2129` | no | absent | 6C |
| `social` (`tiers`, `gift_values`, `gift_tag_values`) | `social/relationships.py:28-70`; `mercantile.py:64` | `content_set.py:959-1093` | no | absent | 6D |
| `economy.currency_name` | `world.py:155-157` | none | no | absent | 6D |
| `advancement` | `core/advancement.py:269-368` | `content_set.py:2244-2307` | no | absent | 6D |
| `loot` (`take_hint`, `chest_materials`, `currency_item_id`, `ambient_pools`) | `utils/utils.py:431-434`; `chest_loot_generator.py:87-126`; `npc.py:184-235` | `content_set.py:1216-1256` — `ambient_pools` only | no | absent | 6C |
| `skills.stat_bonuses` | `skill_system.py:43-49` | `content_set.py:1109-1129` | no | absent | 6C |
| `factions` (not declared by fantasy) | `world/factions.py:48-118` | `content_set.py:854-880` | `extra` only | prototype | 6D |
| `status` (orbital only) | `world.py:178` fallback; `contracts/stats.py:175` primary | none | `status.stats` only | prototype | 6C |
| `npc_naming` | `npc_factory.py:61-73` | none | no | absent | 6D |
| `calendar` | `time_manager.py:23-52` | none | no | absent | 6D |
| `spawning` | `spawner.py:87,95` | none | no | absent | 6D |
| `elites` | `npcs/elite.py:13-46` | none — the only test patches `ruleset_section` and never reads the shipped section | no | absent | 6D |
| `npc_schedules` | `ai/schedules.py:58-173` | none | no | absent | 6D |
| `debug` | `commands/debug_crafting.py:62`, … | none | no | absent | 6D |

**Notes.** The editor can write 7 of the 23 top-level keys, and five of those are a
single field: three scalars (`ruleset_id`, `world_mode`, `progression_model`), `systems`
(8 toggles), `world.regions` (3 flags + 2 lists), `status` (`stats` only) and `factions`
(`extra` only). Eleven
sections are validated by nothing at all: `combat`, `locksmithing`, `crime`,
`player_defaults`, `economy`, `npc_naming`, `calendar`, `spawning`, `elites`,
`npc_schedules`, `debug`. Under the standing rule — a section gets a form only when a
validator can refuse a bad value — those eleven stay read-only until Track B supplies the
check, and the ledger is where that debt is visible rather than implied.

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
| `RulesetEditorDialog` | 23 top-level keys | **7** (`ruleset_id`, `world_mode`, `progression_model`, `systems` ×8, `world.regions` ×5, `factions.extra`, `status.stats`) | the other 16 keys, byte-for-byte preserved |
| `CombatVocabularyDialog` | `combat/elements.json` | `valid_damage_types`, `default_damage_type`, and every hazard field the shipped file uses (`channel`, `damage`, `flavor`, `tick_interval`) | `elemental_opposites`, `flavor_text` |

**What this says about 6A.** The contract and combat-vocabulary dialogs are close to
field-complete against the schema, which is better than the §F rows imply — their
remaining gaps are validation scope and journeys, not missing controls. The ruleset
dialog is the one that is genuinely partial (7 of 23 keys), and the test records two
facts worth keeping: `ruleset_id` and `world_mode` are writable but read by nothing
(§I.5), and `factions` is writable although **no shipped set declares it**, so the
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
(`content_set_lifecycle_smoke.gd`). Still missing: external content-set roots and
editing `paths` after creation.

**Multi-file saves have a checkpoint now** (2026-09-21). `SaveCheckpoint` copies the
set's `data/` tree before `Main._save_everything` writes anything and restores it if a
write fails, so "the previous coherent set" is a fact rather than a hope; restore
replaces the tree (a file the failed save created is removed, a truncated one comes
back), refuses a checkpoint from another set, and prunes to the newest three. The
content-library and region saves still run no engine verdict on save
(`DatabaseManager.gd:512-533`, `RegionManager.gd:109-124`) — what changed is that a
failure no longer leaves the set half-written.

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

Room `env_properties` and `properties.exit_requirements`/`env_interactions`/
`time_descriptions`/`locked_by`; `spawner` toggles and weights; NPC `friendly`, `stats`,
`level`, `loot_table`, `schedule`, `patrol_points`, `initial_inventory`, the behaviour
tuning block, gift preferences; containers; affixes; `knowledge/topics.json`;
`field_interactions.json`; `dynamic_themes.json`; `presentation/*.json`. Each is a value
a content author can write, the engine will act on, and no gate will refuse.

### I.5 Dead declarations and disagreements

Parsed and read by nothing: contract `effect_packets` (whole section),
`attack_profiles.cooldown`/`.resource_cost`/`tags`, `work[].tags`,
`work.declaration_issues()`, `manifest.title`/`version`, `presentation_path`,
`region.properties.biome`/`region_type`, ruleset `ruleset_id`/`world_mode`.

Validators that disagree about the same fact (engine vs toolkit): `behavior_type`
vocabulary (toolkit invents three names, omits `follower`); vendor stock
(`sells_items` vs `buy_orders`); `damage_type` (toolkit rejects unknown channels, engine
only checks hazard channels); `spawner.monster_types`/`npc_types` ids (toolkit errors,
engine never resolves); item `name`/`type` (warning in the gate, fatal in playability);
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
