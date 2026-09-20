# Track E — Systems

## Assessment

**State.** Five systems are already two-theme and need nothing from this track: crime/custody
(`core/crime_manager.py`; fantasy + night_shift ship the whole section, down to `is_holding_room` and
`emergency_tool_item_id`), locksmithing, combat/retreat (three sets rename `combat.retreat.skill`), gathering
(`items/resource_node.py`, used by `node_herb_bed` and `node_salvage_bench`), and contracts
(`contracts/registry.py`, two sets ship `world_contracts.json`). What is unfinished is the layer that turns a
declaration into something a player can feel: systems with an engine producer and no content consumer, or a
content consumer and no honest reader.

**Strongest.** `social/relationships.py` — authored tiers, gift values, milestones, discount, advancement hook,
all total with a documented fallback (`:6-14`). `commands/mercantile.py` composes it correctly: buy orders pay
relationship and milestones (`:326-331`) and every vendor price reads the tier discount (`:62-64`).
`core/crime_manager.py` is the model for the rest: its entire vocabulary comes out of a ruleset section
(`_section` `:25-29`; `room_property` `:116`, `release_destination_property` `:211`,
`emergency_tool_item_id` `:146`), which is why night_shift got the system by renaming a skill and a property.

**Weakest.** `world/room.py` expresses the environment three ways and reads it consistently by none.
`apply_hazards` (`:111-141`) reads a hardcoded `hazard_type` and multiplies by weather (`:131`);
`apply_elemental_interaction` (`:66-109`) can suppress a hazard or clear an exit for a duration, is called from
exactly one place (`magic/effects.py:51`), and is gated on a room property `elemental_interactions` that **no
content set authors** (zero hits across `content_sets/**/*.json`); `World.get_env_property`
(`world/world.py:783-816`) already resolves room → district → region for `dark`, `outdoors`, noise and
temperature, and no hazard uses it. `commands/gathering.py:37` is the same failure in miniature: `plant` finds
its station by the English string `"garden plot"`, then one line later uses the structural signal it should
have found it by (`get_property("plantable_crops", [])`, `:41`).

**Surprises.** (1) **A permanently false condition kind.** `conditions.py:137` publishes `time_of_day` from
`data.get("period", data.get("time_of_day"))`; the only writer of that dict, `time_manager.py:119-129`, keys it
`"time_period"`. So `{"kind": "time_of_day"}` compares `"" != wanted` and fails closed in every set — the kind
has worked in no build, and no content uses it, so nothing noticed. ROADMAP's "all sixteen kinds work
unchanged" is false for this one. (2) **The clock ignores its own declaration.** Day length (`86400`,
`time_manager.py:79`), the five period names (`:107-117`) and the four seasons (`:122`) are engine literals, so
`items/resource_node.py:200-202` re-derives a day as `// 86400` instead of asking `TimeManager`;
`room.time_descriptions` defaults to four keys (`room.py:21`) against five emitted periods, surviving on a
`morning/afternoon → "day"` fallback (`:149-150`), and no set authors it. (3) **A set cannot decline weather.**
`weather_manager.py:28-35` treats an empty `weather.chances` as falsy and installs `DEFAULT_WEATHER_CHANCES`
(`:12-17`, rain/storm/snow); the `weather` command carries no capability gate (`information.py:158`) and
`is_outdoors` defaults to `True` (`:170`) — which is why orbital's `dock_ring`, authored `"outdoors": false`,
is told it can "hear sounds indicating clear conditions outside" a station under "a hard black sky".
(4) `_guilds` is loaded (`core/titles.py:96-121`) and reduced to one field: `place`. `guild_id` is carried onto
`Title` (`:131`) and read by nothing, so the docstring's "named group with entry conditions" (`:16-18`) is a
name and a room pointer; `active_title` is read only by `titles.py` and persistence.

**Verdict on `skill_audit.py`'s findings.** The engine-hardcoded `"crafting"` should become a real declaration
(E3). The two-skill gate should stay a warning: it appears in exactly two sets and is the *same* block
(`ruleset.crime.custody.concealed_tool_requirements`, fantasy's stealth+lockpicking and night_shift's
awareness+security) — one judgement call twice, so the ledger's "revisit at five" stands. `diplomacy` being
undeclared (`quest_bandit_lieutenant.stages[0].objective.skill`) is a content/validator finding, not a system.
One audit premise is wrong and should be corrected before it bites: `skill_audit.py:243-245` classifies a room
exit's `skill_name` as "rolls and grants nothing", but `world.py:402` calls `practice_check`, which trains.

## Proposed roadmap

### E1. The clock becomes a system every surface reads

**What.** One published clock vocabulary, read by schedules, conditions and the `time`/`weather` surfaces; the
surfaces stop inventing state a set never declared. Readers only — calendar *shape* is the handoff.
**Composes.** `TimeManager.time_data`/`current_time_period`; the `calendar` ruleset section (names and
`start_time` are already authored and read); `conditions` `time_of_day`/`season` kinds; the `weather`
`descriptions`/`profiles`/`chances` ruleset sections; `npc_schedules` (`npcs/ai/schedules.py:53-70`,
hour-keyed, already no-ops when absent); `system_providers.on_time_period_change:9-33`; command capability
gating (`command_system.py:205-208`); presentation mode.
**Second theme.** `modern_capsule`: five rooms, two `stationary` NPCs, `progression_model: "none"`, no combat,
economy, skills or quests — a slice whose only possible content is a world changing on its own. `night_shift`,
a game named after a shift, declares no `calendar` and no `npc_schedules` either.
**Why now.** Two one-line defects block it, and every other item here publishes state through the clock.
**Depends on.** Nothing. (Vocabulary → Handoffs.)
**Lane note.** Lands in `core/`, `commands/`, `player/`, `ui/`. The room-prose fold-in needs
`world/description_generator.py` (D's half of `world/`) — handoff, not this item.
**Scope.** Medium.
**Done when.** A dialogue choice gated on `{"kind": "time_of_day", "value": "night"}` is invisible at midday
and shown at night (H-falsified both ways); a set with no `weather.chances` reports no weather and has no
`weather` command; modern_capsule's NPCs move on an authored schedule.
**Risk.** Making a dead kind live opens gates content has authored blind; the fix must ship with a
falsification. Changing calendar *shape* would reinterpret existing saves.

### E2. Environment: one declaration, resolved once

**What.** A reader in E's lane that composes the existing resolution chain, the mechanical hazard properties,
weather and the declared damage channel into damage, prose and mitigation — replacing three parallel
expressions of "this room is dangerous".
**Composes.** `World.get_env_property` (`world.py:783-816`) and `room.env_properties` **read, not edited**;
`hazard_type`/`hazard_damage`/`hazard_tick_interval`/`weather_hazard_multipliers` and the `active_env_effects`
record shape (`room.py:25-63,111-141`); `hazards.mapping`/`flavor` from the set's `combat/elements.json`
(`config_combat.py:108-109`); the damage site in `player/` plus
`contracts/equipment.damage_channel` (`:108`) and `armor_resistances` (`:136`, already merging an item's
`resistances` with its profile's); `magic/effects.py:51`; family capabilities; presentation mode.
**Second theme.** `orbital_salvage` has already declared the seat empty —
`data/combat/elements.json:15-18` `"hazards": {"mapping": {}, "flavor": {}}` — with four rooms authored
`"outdoors": false`, four damage channels including `thermal`, and `content_set.py:480-484` erroring on a
declared-but-unused hazard, so empty is currently the only legal way to say "not yet". Fantasy has seven hazard
rooms and nothing that answers them (`regions/caves.json:229`, `mountains.json:185`, `sunscorch_road.json:51`,
`swamp.json:180`, `obsidian_trial.json:74`, `ruins.json:120`, `coastal_path.json:45`).
**Why now.** Cheapest second consumer in the repo, and it exercises the contract layer rather than a ruleset.
**Depends on.** Nothing for the loop; "how long may you stay" is the duration handoff.
**Lane note.** Retiring `room.apply_hazards`/`apply_elemental_interaction` is D's edit; land the new reader
first and let D delete the old one rather than shadowing it forever.
**Scope.** Medium.
**Done when.** A room's authored environment both damages through its declared channel and appears in
player-mode prose in the set's own words; armour with the matching `resistances` measurably reduces it; a spell
matching an authored interaction suppresses it for the declared duration and it returns; the seven fantasy
hazard rooms behave identically.
**Risk.** Hazard prose is the last place mechanics leak to players (P1); the mitigation loop will expose that
no set authors armour resistances — that is F's authoring, not a code fix.

### E3. Skill checks: one authored name, one training path

**What.** Every skill a set can rename rolls and trains through one path; the engine-hardcoded `"crafting"`
becomes a declared name, and a set that declares none is a reported state rather than a silent level-0 roll.
**Composes.** `SkillSystem.practice_check`/`attempt_check`/`grant_xp`; the per-system `skill` field the engine
already reads for `locksmithing` and `combat.retreat` (read by the engine at `world.py:360-365`); the ruleset
section it belongs to; `Recipe` properties; `skill_audit.py` (Track I) as the referee.
**Second theme.** `night_shift` already renames two skills; `orbital_salvage` runs `crafting` with **no**
`skills` section, so `craft` there rolls a name its own set never declared — the audit says so verbatim.
**Why now.** One read of an existing section at three call sites (`crafting_manager.py:316,320,382`), and it
removes the only engine-declared skill in the shipped sets.
**Depends on.** Nothing. **Scope.** Small.
**Done when.** A set naming its crafting skill in the ruleset sees `craft` train that name and `skill_audit`
reports no `engine:` site for it; fantasy's difficulty and output are unchanged.
**Risk.** `crafting_manager` uses `attempt_check` plus a hand-written consolation `grant_xp(…, 2)` on failure;
routing it through `practice_check` changes failure XP — keep the rename and the balance change separate.

### E4. The social graph: declared rather than accidental

**What.** Relationships become a system a set opts into and labels itself, and the conversation record behind
topics becomes visible to the one evaluator. Today the second theme is running by accident.
**Composes.** `social/relationships.py`; `ruleset_section("social")` (`:17-22`); `player.npc_relationships` and
`relationship_milestones_completed`; `content_capability=` gating (`command_system.py:205-208`);
`give`/`relationship`/`relationships` (`commands/interaction/use_give.py`); `mercantile.py:62-64,326-331`;
`ConversationHistory` (`has_discussed:41`, `is_revealed:45`, persisted at `player/persistence.py:84,266`) and
`knowledge_manager.py:122,124`; `engine/naming.py`, the shared resolver (`:35` of `dialogue/manager.py` is one
of seven users).
**Second theme.** Already live and undeclared: `orbital_salvage`'s `foreman_ivo` carries two repeatable
`buy_orders` whose fulfilment pays relationship and milestones through `mercantile.py:326-331` while the set
declares no `social` section and no `social` capability — so it renders fantasy's default tier names
(`relationships.py:8-13`) and stacks a 15% discount on a station's prices. `night_shift`'s `dana` is the same
story.
**Why now.** The convention is being violated silently; declaring it is what makes the second theme real — and
relationships are the only system `modern_capsule` (two friendly NPCs, dialogue, nothing else) could show.
**Depends on.** The `discussed`/`revealed` condition kinds (Handoffs).
**Scope.** Medium.
**Done when.** A set with no `social` section shows no bond surface and no tier names; orbital and night_shift
author their own labels and the vendor price moves for exactly the tier they declared; `resolve_topic_id`
(`knowledge_manager.py:59-78`) is a thin call into `engine/naming.py`, with the prefix-match test
(`test_knowledge_manager_conditions.py:58`) honestly re-derived rather than loosened.
**Risk.** Gating a live behaviour removes prices' discounts in two sets — gate and authored sections must be
one change. P3 removed fuzzy matching on purpose; porting the topic matcher must not reintroduce it.

### E5. Conferred identity: `_guilds` becomes a group with entry conditions

**What.** The group a title is conferred by becomes readable: entry conditions evaluated on read (no new stored
state, no save-format change), folded into the title's own condition, with a refusal that names the group.
**Composes.** `core/titles.py` (`_guilds` load `:96-121`, `Title.guild_id` `:131`, `full_condition` `:63-69`,
`sync` `:156-181`); `engine.conditions.evaluate`, already the one evaluator for titles, dialogue and quests;
the `title` condition kind reading `earned_titles` (`conditions.py:307`); `commands/advancement.py`;
`content_set.py:2015-2027`, which already validates that a guild's `place` names a real room.
**Second theme.** `orbital_salvage`'s `crew.json` is already a named group (a foreman and a drone) with no
titles file; `night_shift`'s `staff.json` likewise. Either ships one `titles.json` with a guild whose condition
is a skill or relationship threshold — same evaluator, no new concept.
**Why now.** The only declared construct in the repo whose mechanical half is entirely absent.
**Depends on.** Nothing. **Scope.** Small.
**Done when.** A player who does not meet a guild's condition cannot wear a title it confers and is told why; a
player who does can; losing the condition revokes the worn title, as `sync` already does.
**Risk.** Tempting to make titles grant stats — that contradicts the deliberate inertness (`titles.py:10-11`).

## Handoffs

1. **Calendar vocabulary** (B). Extend the existing `calendar` section — which already declares `day_names`,
   `month_names`, `start_time` — with seconds per game day, period ids with hour edges, and the season list
   (or none). Today `86400`, the five period names and the four seasons are engine literals
   (`time_manager.py:79,107-117,122`) and day length is config (`config_game.py:24`). E1 consumes it
   contract-first.
2. **`work`/timers, with two consumers already waiting** (B). `items/resource_node.py:200-242` is the engine's
   only calendar duration and should consume the primitive instead of being one — `respawn_days` plus
   `depleted_day` plus the partial-recovery fixpoint is the primitive, written once, inside an item class. A
   *deadline* shape (contracts — the work-tracks doc's own Track E example) and E2's "how long may you stay"
   want the same two fields plus an authored lateness/expiry outcome. Neither is proposed as an item because
   neither primitive is declared yet.
3. **`discussed`/`revealed` condition kinds** (B). Two predicates over `ConversationHistory`
   (`conversation_history.py:41,45`) in the one evaluator, so authors stop hand-rolling a flag per line
   (ROADMAP P5's own open item). `engine/conditions.py` sits in no lane in `work-tracks.md`; it needs an owner.
4. **A periodic-effect shape** (B, only if K wants it): housing upkeep and restocking are periodic, not
   durational. Nothing above needs it.

## Explicitly not proposing

- **Rent/upkeep from housing.** Needs the periodic primitive; the ledger already parks it. `housing_manager.py`
  is otherwise complete, and its missing half is authoring.
- **A flow/power-grid system for orbital.** Ledger refusal; it wants a general flow concept on the resource
  contract, which is B's call.
- **Titles granting stats or access.** `titles.py:10-11` makes inertness the design.
- **Any per-theme special case** — a modern_capsule conversation engine, an orbital hazard module.
- **A heuristic for the two-skill gate.** Two sets, one identical block; the ledger's "revisit at five" stands.
- **`diplomacy` being undeclared** — content/validator finding (F/I), not a system.
- **`advancement.json` unused** (accepted ROADMAP item) and **`overcharge` declared twice** (contract
  `abilities` vs `data/abilities/overcharge.json`) — D/I territory.
- **`world.py:404`'s player-mode leak** (`(Requires {skill} {difficulty}+)` prints a skill id and threshold to
  players, contradicting P1) — D's file: reported, not proposed.
- **Making night_shift's combat meaningful** (one hostile, empty `loot_table`, zero weapons or armour) — F.

## Risks

- **Every second theme above is content work.** My items remove the engine-side reason a declaration would do
  nothing; if F does not author them, the systems stay single-theme with better plumbing.
- **A gate is a removal.** E1 (weather off) and E4 (bond surface off) delete live behaviour in sets that never
  opted in; each needs both authored declarations in the same change plus H coverage of the un-declared case.
- **Fixing `time_of_day` opens gates that have been dead forever** — that is the point, but it must land with a
  falsification rather than as a one-line fix.
- **`skill_audit`'s `ATTEMPTS` premise is wrong** (`:243-245` vs `world.py:402`). No set ships a `skill_name`
  exit today, so its `only_attempted` warning is a false positive waiting for the first one.
- **Calendar shape touches saves**: day/month lengths derive the date from `game_time`
  (`time_manager.py:97-105`), so shape stays a handoff and E1 changes readers only.

## Unknowns

- Which declaration wins for `overcharge` — I did not read `magic/spell_registry.py`.
- Whether any test covers the `time_of_day` kind; I found no content using it and did not grep `server/tests/**`.
- Whether `room.time_descriptions` was ever meant to be authored, given four default keys against five periods.
- Whether night_shift's combat is meant to be fightable at all — content intent, not visible in files.
- Whether housing interiors and their storage survive save/load (C's path; not exercised).
- Whether the P1 player-mode assertions cover the weather/hazard surfaces, including `room.py:139`'s
  engine-authored fallback string.
