# Cross-theme engine contracts

**Status:** proposed architecture and next active refactor track (2026-09-18).

## Why this exists

Fantasy Frontier demonstrated that a content set can suppress large systems such
as magic, crafting, quests, or combat. The next constraint is deeper: core
engine code must not know whether an attack is a sword swing, a fire spell, a
rifle shot, or a hostile environmental effect. Likewise, an item template must
not conflate its authored identity, its runtime capabilities, and a particular
generated instance.

The small sci-fi proving content set is intentional architecture work, not a
second production game. It will expose fantasy assumptions while the affected
systems are still small enough to change safely.

## Layering rule

```text
Engine kernel
  persistence · events · inventory · targeting · effects · validation
  combat resolution · crafting resolution · generated-instance resolution

Contracts and capability adapters
  attack source · defense source · ability · consumable · material · recipe
  item family · generation profile · progression/reputation hooks

Content set
  templates · ruleset choices · enabled capabilities · world · presentation
  Fantasy Frontier: spells, swords, armour, gems, potions
  Sci-fi proving set: devices, kinetic weapons, protective gear, components
```

Core code may query a declared capability or a normalized contract. It must not
branch on genre labels such as `spell`, `mana`, `sword`, `gem`, `orc`, or
`science_fiction`.

## Contract model

### Item template, family, and instance

An **item template** is authored, stable content: name, description, base
economics, capabilities, and a reference to a generation profile. An **item
family** is a contract such as `equipment`, `consumable`, `material`, or
`collectible_stone`; it is not a user-facing genre label. An **item instance**
is the persistent result a player owns.

```json
{
  "id": "rose_quartz",
  "type": "Gem",
  "item_family": "collectible_stone",
  "rarity": "common",
  "generation_profile": "cut_stone"
}
```

```json
{
  "template_id": "rose_quartz",
  "instance_id": "generated-unique-id",
  "rolls": {"quality": "fine", "size": "large"},
  "resolved": {"name": "Fine large rose quartz", "value": 83}
}
```

The template is content. The instance stores resolved rolls and enough derived
state to survive future balance changes and save/load. A generated item is
never merely a mutable shared template.

### Profiles and normalized distributions

Profiles declare only engine-supported attribute kinds, tier lists, bounds,
and weighting/bias parameters. The engine owns roll algorithms and value
formulas; content never executes arbitrary code.

Reusable dimensions include `quality`, `size`, `material`, `durability`,
`charge`, `stability`, `affixes`, and `condition`. A profile selects only the
dimensions relevant to its family. Bias may come from the template, source,
level band, recipe, encounter, or world state, but every roll remains bounded
and serializable.

The current `GemGenerator` is a provisional first family implementation. It
must be refactored into the shared instance pipeline rather than becoming the
pattern for one-off generators.

### Gameplay capabilities

| Contract | Engine responsibility | Fantasy implementation | Sci-fi proving implementation |
| --- | --- | --- | --- |
| `attack_source` | targeting, hit/crit, damage packets, costs | sword, bow, offensive spell | kinetic sidearm, shock baton, device discharge |
| `defense_source` | mitigation, resistance, block, durability | armour, shield, ward | vest, personal shield, environmental suit |
| `ability` | targets, costs, cooldowns, effects | spell school + mana | gadget/module + charge or heat |
| `recipe` | inputs, station/capability checks, outputs, quality contribution | smithing, alchemy, lapidary | fabrication, calibration, field assembly |
| `generated_item` | roll profile, resolved instance, appraisal/persistence | gem, affixed weapon, crafted quality | component, power cell, anomaly sample |

`magic` remains a theme-level implementation of `ability`; it is not a kernel
primitive. Likewise, fantasy elemental names remain authored damage/effect
vocabulary layered on top of generic damage packets and effect tags.

## Delivery plan

### 0. Freeze and map current assumptions

- Record every engine branch on a concrete item type, spell/mana field, or
  fantasy identifier.
- Classify each as a true engine primitive, a capability query, or content
  leakage.
- Add characterization tests before moving behavior.

**Done — the map (2026-09-18).** `toolkit/genre_coupling_audit.py` scans the
engine's string literals for genre vocabulary and reports them by file, function
and theme, distinguishing a *branch* (a comparison on the literal) from a *name*
(a field or a log line). Current state: 203 genre-word literals in the engine,
of which **49 are real branch sites** — 41 magic, 5 material (`Gem`), 3
weapon/armour. The rest are field names, docstrings, and message templates.

Concentration, which is what makes the work tractable:

| engine area | genre-word literals | dominant theme |
|---|---|---|
| `items/` | 41 | material 18, magic 18, weapon/armour 5 |
| `commands/` | 25 | magic |
| `player/` | 23 | magic |
| `server/headless/` | 20 | magic |
| `magic/` | 18 | magic |
| `core/`, `npcs/`, `dialogue/`, `world/` | 34 between them | magic, a little material |

Six coupling families, each with its disposition:

1. **Magic is an engine subsystem, not a content capability.** `engine/magic/`,
   `player/magic.py`, the `spell_power` stat, `mana`/`max_mana` on runtime
   state, the `spell_known` condition kind, `teach_spell` dialogue effect,
   `learn_spell` consumable effect, `random_spell_scroll` in the item factory,
   `retreating_for_mana` NPC behaviour, and `Mana:` in status output. A sci-fi
   content set that declares no magic still gets all of it.
   *Disposition: replace with contracts* — an **ability** contract and an
   authored **resource** (mana is one), with fantasy spells as one
   implementation. This is the single largest piece of P9 and the reason the
   registry comes first.
2. **Item `type` is doing two jobs.** `items/item_factory.py` maps `"Gem"`,
   `"Weapon"`, `"Armor"`, `"Consumable"` to Python classes, content templates
   say `"type": "Gem"`, and `GemGenerator.is_gem_template` /
   `chest_loot_generator` branch on that string.
   *Disposition: replace with contracts* — `item_family` (neutral: `equipment`,
   `consumable`, `material`, `collectible_stone`) plus a `generation_profile`
   reference, with the class map keyed on family.
3. **Consumable effects mix neutral and fantasy nouns** — `heal` and
   `learn_recipe` are theme-neutral, `mana_restore` and `learn_spell` are not.
   *Disposition: replace with contracts* — effect **packets** that name their own
   resource and payload, so the vocabulary lives in content.
4. **Progression names a fantasy activity.** `KIND_SPELL` in the advancement
   ledger and the ruleset's spell grants.
   *Disposition: capability* — the ledger already takes an authored kind; rename
   the magic-specific one to the ability vocabulary when (1) lands.
5. **Status and summary payloads assume mana.** `finite_adventure` emits
   `final_mana`/`max_mana`; the status builder prints `Mana:`.
   *Disposition: capability* — a payload should report the resources the content
   set declares, not a fixed pair.
6. **Already generic and worth keeping as the pattern:** `damage_type` and
   `effect_type` are authored vocabularies; `system_enabled(capability)` gates
   subsystems; `behavior_type` is an engine-owned closed set;
   `engine/conditions.py` reads content facts through one evaluator. These are
   what a contract looks like in this codebase.

Classification vocabulary used above, matching the layering rule: **kernel** =
genre-neutral machinery (inventory, persistence, resolution, validation);
**capability** = branching on a declared contract the engine owns, which may
stay; **content leak** = branching on a genre word, which the registry replaces.
The scanner's own heuristic calls 155 findings "leaks"; the 49 branch sites above
are the ones that matter, and the difference is exactly the manual classification
this step asked for.

Characterization coverage before behaviour moves: `test_gem_generator`,
`test_chest_loot_generator`, `test_weapon_item`, `test_player_combat`,
`test_spell_registry_full`, `test_ambient_loot_filters`,
`test_status_and_room_payload_builders`, plus the whole-content-set gates in
`run_content_checks.py`. What is missing is a test that pins *outcomes* (damage
dealt, value rolled) rather than shapes; add those as each seam moves.

### 1. Contract registry and validation

- Define versioned schemas for item families, generation profiles, attack and
  defense profiles, abilities, recipes, and effect packets.
- Extend content-set validation to reject unsupported profile fields,
  impossible capability combinations, and unresolvable references.
- Teach the editor to render controls from the same schema. It may offer
  family-specific polish, but cannot invent unvalidated fields.

**Done — the registry (2026-09-18).** `server/engine/contracts/`:

- `schema.py` — a small declarative schema language (`string`, `int`, `float`,
  `bool`, `enum`, `list_of`, `object`, `map`, with `required`, `min`/`max`,
  nesting and per-field labels). Deliberately strict: **unknown fields are
  errors**, a required field may not be blank, and a quoted `"3"` where an int
  belongs is refused. Errors carry a JSON-ish path, so a validator message can
  be pasted back into the file.
- `registry.py` — `ContractRegistry` loads `data/contracts/world_contracts.json`,
  validates every section against `CONTRACT_SCHEMAS`, then resolves references
  (a profile's family, a family's resource, an ability's packet and cost, a
  packet's resource). **Versioned and fail-closed**: a `schema_version` this
  engine does not implement is refused outright rather than best-effort read; a
  structurally broken section is not half-registered.
- Lookups the engine uses instead of branching: `item_class_for_family`,
  `family_has_capability`, `tiers(profile, kind)`, `resource`, `ability`,
  `effect_packet`. Two shared resolvers — `item_class_for_template` and
  `generation_profile_for_template` — exist so `ItemFactory` (which decides what
  to build) and `GemGenerator` (which decides what is worth rolling) cannot
  disagree.
- Neutral engine defaults (`DEFAULT_GENERATION_PROFILE`) so a content set that
  declares nothing still rolls sensibly: ranks and bands, no genre vocabulary.

**Content declares, loaded and live:** `content_sets/fantasy_frontier/data/contracts/world_contracts.json`
declares 5 item families (`equipment`, `consumable`, `material`, `curio`,
`collectible_stone`), 2 resources (`health`, `mana`), the `faceted_stone`
generation profile (the tables `GemGenerator` used to hardcode), 2 attack
profiles, 1 defense profile, 3 effect packets and 2 abilities.

**Wired, not aspirational:** `GemGenerator` reads its rarity/size/quality tiers
from the profile, `ItemFactory` resolves a template's class family-first, and
`_validate_contract_content` turns registry refusals into content errors — plus
two checks the registry cannot make about itself (a family's `item_class` must be
a class the engine has; a template naming an undefined family or profile is an
error). `tests/singles/test_contract_registry.py` (35 tests) covers the schema
language, version refusal, every reference rule, resolution precedence, the
content gates, and that authored tiers actually replace the built-in ones.

Two things this surfaced:

- The engine's band weights assumed **exactly five** tiers, so a content profile
  declaring two crashed `random.choices`. The five-band case is now preserved
  exactly and any other count samples the same curve, so a two-band profile
  means "ordinary or rare" instead of an exception.
- Godot's JSON parser returns numbers as floats, so the editor's contract reader
  rejected `"schema_version": 1` as "not an integer". Fixed to accept an
  integral float, which is what the parser actually hands you.

**Editor parity:** `mud-world-editor/scripts/data/ContractCatalog.gd` reads the
same file through `DataRoot`, checks `schema_version` against the version it
knows, and enumerates families and profiles for inspectors — so the options a
control offers are the ones content declares, and anything it writes is checked
by the engine's schema on the next content run. The headless check asserts it
resolves `collectible_stone` to `Gem` and `faceted_stone` exactly as the registry
does (26 assertions total).

**Still to do in this step:** recipes as contracts (a recipe asking for a
material *family* rather than fantasy item ids), and "impossible capability
combinations" — the rules for which capabilities may coexist are not written yet,
because they need the ability seam (step 2) to know what combinations mean.

### 2. Combat and ability seam

- Normalize existing weapon, armour, and spell code behind attack/defense/
  ability adapters without changing Fantasy Frontier outcomes.
- Make damage types, costs, cooldowns, and targeting authored vocabulary.
- Add a minimal sci-fi device ability and kinetic weapon/vest through the new
  interfaces.

**Done — one vertical slice (2026-09-18).** `engine/contracts/equipment.py` is
the seam, and its rule is the same everywhere: **contract first, authored
property second, engine default last**. A content set can move one item at a
time, and an item nobody has migrated behaves exactly as it did.

Wired read sites (each previously read a raw template property):

| what | was | now |
|---|---|---|
| weapon damage | `weapon.get_property("damage")` | `weapon_damage(world, weapon)` |
| weapon damage type | `weapon.get_property("weapon_damage_type")` | `weapon_damage_type(world, weapon)` |
| armour defense | `item.get_property("defense")` | `armor_defense(world, item)` |
| armour material | `body_item.get_property("armor_material")` | `armor_material(world, item)` |
| armour resistances | `item.get_property("resistances")` | `armor_resistances(world, item)` (profile overrides per key) |
| spell cost / cooldown / targeting / level | `spell.mana_cost` etc. | `ability_numbers(world, spell)` |

**The slice:** `item_iron_sword` → `attack_profiles.melee_blade` (damage 8,
slashing), `item_leather_tunic` → `defense_profiles.light_armour` (defense 2,
leather), `magic_missile` → `abilities.magic_missile` (mana 5, cooldown 3.0,
enemy, level 1). The values are copied verbatim from the templates, so this is a
relocation rather than a change.

`tests/singles/test_combat_contract_slice.py` (15 tests) asserts both halves:
**equivalence** against the numbers the templates still carry — so editing one
and not the other fails — and **that the contract is load-bearing**, by retuning
a profile and watching the sword, the armour and the cast change. It also pins
the two honest limits: a spell with no declared ability keeps its own numbers,
and an ability costing a resource other than mana is *not* silently charged as
mana (that is the resource seam, still unbuilt).

Two things this caught:

- `light_armour` carried a placeholder `resistances: {"physical": 0.1}` from
  when nothing read it. Wiring the seam would have quietly given every leather
  tunic 0.1% physical resistance it never had; the placeholder is gone, and the
  test asserting `{}` before and `{fire: 25}` after is what caught it.
- Families could not stay as first drafted. `equipment` (item_class `Weapon`)
  would have resolved every *armour* template in it to a Weapon, because
  resolution is family-first and a family names exactly one engine class. The
  shipped families are now class-aligned (`weapon`, `armor`, `curio`, …) and
  carry **capabilities** (`equippable`, `vendor_trash`, `generated_instance`),
  which is what the engine queries. The sweep script refuses to write unless all
  257 templates resolve to the class their legacy `type` already produced.

**Still to do in this step:** `DAMAGE_TYPE`/cooldown vocabularies are partly
engine-side still (`WEAPON_VS_ARMOR_MULTIPLIERS`, `VALID_DAMAGE_TYPES` in
`config_combat.py` — the *list* is content-loaded from `data/combat/elements.json`,
but the material-interaction table's words, `slashing`/`piercing`/`crushing`
against `cloth`/`leather`/`chain`/`plate`, are engine constants). A set whose
armour has a material outside that list multiplies by 1.0, which is safe but not
declared.

**The ability pool became content (2026-09-20).** This was the last thing
standing between the engine and a set with abilities but no magic: the pool an
ability spends was mana, by name, everywhere.

- **`engine/contracts/resources.py`** resolves the **ability resource**: the
  declared resource whose `kind` is `"ability"`, or a deliberate neutral
  fallback (`id: ability`, `label: Ability`) for a set that declares none. The
  resource's `label` and `short` are what players read; its `max_stat` drives how
  large the pool is and its `regeneration_stat` how fast it refills. Those last
  two fields were declared in the contract from the beginning and read by
  nothing — a declaration the engine ignores, which is the pattern this whole
  initiative exists to remove. The *curve* stays in `engine/config`, renamed
  `ABILITY_POOL_*` (the `PLAYER_MANA_*` names are aliases now): how much a pool
  holds per point of its driving stat is a rule, not a name.
- **`abilities` is its own capability.** `magic` now means "this set's abilities
  are spells" — a flavour — and implies `abilities` for sets written before the
  split. The ability commands, the pool's state, the loading of ability
  definitions and the debug refill gate on `abilities`.
- **The pool travels with its name.** The status payload carries
  `ability_resource: {id, label, short, current, max}` rather than a `mana` key,
  the client renders whatever it is told, and the status field is the neutral
  `ability_resource`. Messages ("Not enough charge (need 6, have 2)") and the
  level-up line are named by the contract.
- **`data/abilities/` is loaded like `data/magic/`**. The loader looks for the
  neutral directory first and falls back, so the first content set keeps the
  directory name it chose and a new set is not made to write "magic" on a folder
  of device abilities.
- **Two engine defaults that were content words went with it.** A resource node
  with no declared tool used to require a `pickaxe` (every shipped node declares
  its own tool, so nothing changed for them); a status line used to show
  `SPELL_POWER` and `MAGIC_RESIST` to every set with abilities, and a set may now
  declare `ruleset.status.stats` to say what it shows.
- The ability **command surface** is neutral: the command is `abilities`
  (`spells`, `spl` and `magic` remain aliases so a fantasy player keeps their
  muscle memory), the category is `Abilities`, and the wording is
  ability-neutral. What is *not* solved: help advertises those aliases, and
  alias vocabulary is not something content can currently hide. That is
  recorded below rather than papered over.

`tests/singles/test_combat_contract_slice.py` and the content checks pin the
equivalence: Fantasy Frontier's pool is still `50 + (intelligence - 10) * 5`,
still regenerates on wisdom, and the mana status payload is byte-identical.

### 3. Generic generated-instance pipeline

- Extract tier/distribution and instance serialization from `GemGenerator`.
- Move gem, equipment-affix, crafting-quality, and future component rolls to
  profiles backed by the same resolver.
- Keep compatibility fields during migration (`material_quality_score`, for
  example), then retire aliases only after save migration coverage exists.

**Started (2026-09-18).** The tier tables, the family resolution and the
"is this a template with instances" question are contract-driven now, and the
two genre branches *outside* the generator are gone:

- **Chest loot no longer rolls genre categories.** `_slot_categories(world)`
  derives what a chest may hold from declared capabilities — `currency` needs a
  coin item, `generated_instance` gives the rolled slot, `equippable` the gear
  slot, and the rest are curios — with the historic four-way split as the
  no-families fallback. A sci-fi set's chests hold its own things with no engine
  change.
- **Icons no longer branch on a class name.** Families declare `icon_style`, the
  factory stamps it on the instance, and the renderer draws by style with the
  class-name map kept as data (`LEGACY_STYLES`) for unmigrated items.
- **Every shipped template now declares its family** (247 of them; 257 checked),
  which is what makes the capability queries real rather than aspirational.

Two honest notes. First, catching this required a probe: after the category
rewrite chests briefly rolled *only* currency and curios, because no template
declared a family yet — the fix was the content sweep, not a fallback. Second,
**naming, value and persistence still lived in `GemGenerator`**: the generator
rolled and decorated instances itself, and the generic resolver that would let
any family produce instances did not exist yet.

**Built (2026-09-20).** The resolver exists: `engine/items/instance_generator.py`
rolls instances for *any* family whose contract says it rolls them, and
`gem_generator.py` is now a compatibility facade over it (same public names,
no logic). Naming, value and persistence came with it.

- **The property vocabulary is neutral, and a set may name its own.**
  `InstanceGenerator` writes `instance_source`, `instance_rarity`,
  `instance_size*`, `instance_quality*` and the cross-system `material_quality*`
  trio, and never the word "gem". The shipped profile declares
  `"property_prefix": "gem"`, which is why instances still carry `gem_size` and
  `gem_rarity` for pre-P9 readers, and a sci-fi component family declares
  `"property_prefix": "component"` and gets `component_size` instead. The engine
  writes the prefix without knowing what it means.
- **Naming is a content decision.** A profile may declare `name_template` over
  `{base}`, `{quality}`, `{size}`, `{rarity}` and `{profile}`. Bands a set does
  not use render empty and the gaps close up, so a "standard" size leaves no
  double space and an all-empty group leaves no `()`. An unknown token falls back
  to the default shape rather than raising mid-roll.
- **The `"type": "Gem"` fallback is retired, and its absence is checked.** This
  was the last genre word deciding behaviour: a template with no family rolled
  instances because of its class name. Content now says so through a family
  (`generated_instance` + a profile), and
  `test_editor_content_source.py::test_nothing_relies_on_the_retired_class_name_generation_fallback`
  fails if a shipped `type: Gem` template stops declaring one. The guardrail is
  a test rather than engine logic on purpose: the point is that the engine no
  longer knows the word. A set with un-migrated rolling templates now gets
  nothing rolled — loudly, via the check, instead of silently.
- **A latent roll crash was fixed on the way.** An ungraded template in a set
  whose rarity bands have their own names (a sci-fi set's `scrap` /
  `serviceable`) resolved to a band id that was not in the table, which produced
  zero total weight and made `random.choices` raise. An ungraded specimen now
  resolves to the *commonest declared* band, and the instance records the band
  the table actually resolved to rather than the name the lookup started from.

**The bug this step found, which is the reason completion gate 3 is worth
having.** A rolled instance is saved as an item *reference*: the template id plus
whatever differs from the template. Value, weight and stackability did not
differ, as far as the save was concerned — they were skipped as "core attributes"
— so a perfect ruby reloaded as an ordinary one: template value, and *stackable*,
which silently merged it with its neighbours on the next pickup. A crafted
quality tier's value multiplier reverted the same way. Fixed in
`utils._serialize_item_reference`, which now records a core attribute when it
differs from what the template produces (declared value, else the `Item`
default), so ordinary items gain no save noise and generated ones keep their
identity. `test_generated_instance_round_trip.py` covers the inventory half and
a real save file end to end; it failed on value, weight and stackable before the
fix.

Also outstanding, and deliberately: **recipes still name item ids, not
materials.** A recipe asking for "any material of grade ≥ fine" is a crafting
seam change (step 4), and half-building it here would leave two ways to match an
ingredient.

### 4. Crafting and economy seam

- Make recipes ask for material/family/capability contracts, not fantasy item
  IDs except where an authored quest deliberately requires an exact relic.
- Preserve provenance and resolved instance quality through crafting, salvage,
  trade, appraisal, and quests.

**Built (2026-09-21).** An ingredient is no longer an item id. It is a
*reference*, and there are three kinds:

```json
{"item_id": "item_iron_ingot", "quantity": 2}
{"item_family": "salvaged_part", "quantity": 2, "min_material_quality": 2}
{"capability": "crafting_material", "quantity": 1}
```

`item_id` wins when more than one is present, so every recipe written before
families existed resolves exactly as it did -- the migration is one recipe at a
time rather than a flag day. `min_material_quality` is the floor a member of a
family or a capability has to reach: the rule says *what kind of thing*, the
floor says *how good*. Each reference may also carry `alternatives`, which are
whole references of their own (`{"item_family": ...}` included) and each of
which may declare a `quality_penalty` -- the trade-off in a substitution, which
lands on that slot's material-grade contribution when it is the option actually
spent.

One matcher serves every call site. `CraftingManager._ingredient_matches` is
what counting, selecting, previewing, spending, the crafting command's
requirement list, the headless status payload and the editor all go through,
because a recipe that *looks* craftable and then fails to craft is worse than
one that says what it is missing. The validator resolves a family against the
content set's own contracts and a capability against the capabilities its
families declare, so a typo fails the build rather than reading as a recipe that
can never be made.

What this buys, concretely: `content_sets/orbital_salvage`'s fabrication recipe
asks for **two salvaged parts of grade 2 or better** instead of two named
components, and the salvage bench on the deck yields exactly that -- grade 2
serviceable parts, with a rarer clean-grade pull on the yield table. The recipe
reads the set's own family and the set's own grade, and neither the engine nor
the recipe knows the word "servo".

**Still not done here:** vendor orders still read `min_material_quality_score` on a
named item rather than on a family.

**Follow-up (2026-09-21): the same rule reached the other two places content asks
for an item.** `engine/items/references.py` is now the one implementation of the
question — `matches`, `describe`, `options`, `match_plan`, `count_matching`,
`matching_template_id` — and a recipe ingredient, a vendor's buy order and a
salvage rule are three call sites of it rather than three implementations.

*Vendor orders.* A `buy_orders` entry may name a family or a capability, so a
vendor who will take "two parts of grade 2 or better" no longer needs every part
in the set listed, and no longer needs editing when a new one is added. The older
`min_material_quality_score` spelling is still read (vendor orders used it
first); content should author `min_material_quality`. Two conditions ride
*alongside* the reference because neither is a kind of item: `crafted_only`, and
the grade floor — a recipe's floor lives inside the family rule it was written
beside, but an order writes it at the top level, including next to an exact
template, and a floor that only applied to some of the ways an order can be
written would be a trap. The refusal message names every requirement that
applies, because naming only one sends someone off to satisfy a requirement that
was never the only one.

*Salvage output.* `salvage_output` — on the template, or in
`crafting.salvage_rules` — is a reference too. Rules may now be keyed
`by_family`, which is what the engine class key was always a proxy for:
`fantasy_frontier`'s `"Weapon"`/`"Armor"` rules became `by_family.weapon` /
`by_family.armor`, so a weapon template with no family of its own no longer
silently joins a rule nobody meant it to. The class key is still read, because a
template that declares no family has no family key to be found under.

Nothing validated any of this before, so a typo'd key fell silently through to
the set's scrap default and a rule naming a missing template failed only when a
player tried it. `_validate_salvage_rules` and `_validate_item_salvage_outputs`
now cover the ruleset, the `by_family` keys (against the set's own contracts),
the item templates, and the `quantity_per_weight` rate.

**Two gaps this closed in the shipped content.** `orbital_salvage` enabled
`salvage` and declared no rule of any kind, so *every* attempt in the sci-fi set
returned "You cannot salvage the X" — the set's own salvage bench was gathering,
not salvage. It now strips parts, gear and unruled items into `item_scrap_alloy`
(the set's answer to "what is this station made of"), keyed by family. And its
foreman, who was already `is_vendor: true` in a content set with no `economy`
system, now trades: two buy orders by family and grade, in credits.

### 5. Sci-fi proving slice

- Create a deliberately small content set: one room loop, one NPC, one
  kinetic attack source, one protective gear item, one charge/heat ability,
  one generated component family, and one fabrication recipe.
- It must omit Fantasy magic, mana, spell schools, gems, and fantasy enemy
  vocabulary.
- Add an end-to-end smoke journey and contract snapshots alongside the
  existing Fantasy Frontier coverage.

**Built (2026-09-20): `content_sets/orbital_salvage`.** A dead salvage station
in four rooms -- dock ring, spine corridor, workshop, cargo hold -- with one
foreman, one hostile loading drone, a kinetic sidearm, an impact vest, a salvage
bench that rolls components, a fabrication recipe, and one ability that spends
**charge**. It declares `abilities` and not `magic`, and it says nothing about
spells, gems, mana or gold anywhere in its files.

Everything it needs is a declaration it makes itself:

| what | how the set says it |
|---|---|
| the ability pool | `resources: charge` (`kind: ability`, `max_stat: intelligence`, `short: CHG`) |
| the weapon | `attack_profiles.kinetic_round` (`damage_type: kinetic`, 7 damage, 1.8s) |
| the vest | `defense_profiles.impact_shell` (2 defense, `material: synthetic`) |
| the components | family `salvaged_part` with `generated_instance` + profile `salvage_grade`, `property_prefix: "component"`, bands named `scrap`/`serviceable`/`clean`, `micro`/`standard`/`bulk`, `worn`/`true` |
| the ability | `abilities.overcharge` (costs 6 charge, 6s cooldown, `effect_packets.discharge`) |
| the ability definition | `data/abilities/overcharge.json` -- the neutral directory the loader now prefers |
| the damage channels | `data/combat/elements.json` (`kinetic`, `thermal`, `electric`) |
| the status line | `ruleset.status.stats` -- no `SPELL_POWER` for a set that has none |

`tests/singles/test_sci_fi_proving_slice.py` (11 tests) walks the journey and
does two different jobs. It asserts the slice **works** -- creation grants the
set's own kit, gathering rolls `component_*` instances with the set's own band
names, the recipe consumes them into a patch kit, `cast overcharge` spends 6
charge and names the cost `6 CHG`, the weapon and vest resolve their declared
profiles -- and then it asserts **nothing leaks**, by scanning every line of
player-visible text from a scripted journey for the vocabulary the set never
declares (`mana`, `spell`, `gem`, `sword`, `gold`, `pickaxe`, ...). That second
half is the real proof: a fantasy word reaching a sci-fi player is the failure
this initiative exists to remove, and no mechanics test can see it. The scan
found three real leaks while being written -- `SPELL_POWER`/`MAGIC_RESIST` on the
status line, `Mana:` in the ability list, and a `pickaxe` requirement the set
never authored.

Nothing in the engine was special-cased for it. The only engine changes it
needed were the ones above, each of which was a content word standing in for a
declaration.

**Known and recorded, not hidden:**

- The `Spell` class, `spell_registry`, `known_spells`, `mana_cost` and
  `runtime_state.magic` remain the *internal* names of the ability machinery.
  They are storage and API names rather than branches, they never reach a player
  of the sci-fi set, and renaming them is a save-format migration rather than a
  contract change. **That migration now has somewhere to live:**
  `engine/world/save_format.py` owns `SAVE_FORMAT_VERSION` and a migration chain,
  a save from a newer build is refused rather than half-read, and this is the
  file to bump when those names move. See ROADMAP §"A save says what it is".
- The ability command advertises fantasy aliases (`spells`, `magic`) in `help`.
  Alias vocabulary is not content-declarable yet.
- An NPC caster (`npc.mana`, `npc.max_mana`, spell-casting AI) is still
  mana-shaped. No shipped NPC in the sci-fi set casts anything, so this is a
  gap in the proof rather than a lie in it.
- The crafting seam (step 4) is built end to end: recipe ingredients, vendor buy
  orders and salvage output all speak the same authored reference.

## Completion gates

This initiative is complete only when:

1. Fantasy and the sci-fi proof launch through one executable and one content
   loader with no genre branches in core paths.
2. Both use the same combat, ability, generated-instance, crafting, save/load,
   validation, and editor contracts.
3. A generated item round-trips through inventory/save/load with its resolved
   identity intact.
4. The content validator and editor reject the same invalid contracts.
5. Tests prove both reference sets without allowing content-ID exceptions in
   engine code.

**Where the gates stand:** 2 is met for combat, abilities, generated instances
and the whole crafting/economy seam. 3 is met and tested
(`test_generated_instance_round_trip.py`). 4 is met for the content validator on
both sets and for the editor's contract catalog; the editor's *authoring* surface
for the new contract fields (`name_template`, `property_prefix`) does not exist
yet. 5 is met for the engine kernel
(`toolkit/content_neutrality_validator.py` runs against both sets as a content
check) but not for content *ids* named in engine code that the sci-fi set does
not use. 1 is the honest remaining one, and what is left is spell-school
vocabulary (`spell_known`, `teach_spell`, `random_spell_scroll`) and NPC casting
(`retreating_for_mana`, `mana_restore`) — paths the sci-fi set does not exercise.
The crafting quality vocabulary that used to sit on this list is gone: ingredient
matching no longer reads a genre word, because there is nothing left in it for a
genre word to mean.

**A correction to how that progress was measured.** The "45 genre branch sites,
down from 49" figure above cannot be reproduced from anything in this repository:
`toolkit/genre_coupling_audit.py` is the only tool that measures coupling, and it
counts genre *string literals* (`ast.Constant`), not branch sites — identifiers
and attribute names are invisible to it, so renaming `Spell` or `mana_cost` would
move none of its numbers. Running it now reports **213 literals** (167
CONTENT_LEAK, 18 CAPABILITY, 28 KERNEL). Its classifier also over-counts for this
purpose: it flags `ui/icons.py` and the docstring in `contracts/__init__.py` that
states this initiative's own goal. Treat the literal count as a rough trend and
the per-file list as the actionable part; the crafting seam did not move either,
because the genre words it removed were identifiers.

## Non-goals

- Do not build a second large game or a generalized scripting language.
- Do not make every conceivable property configurable.
- Do not delete working Fantasy Frontier behavior before its adapter has
  equivalent characterization coverage.
