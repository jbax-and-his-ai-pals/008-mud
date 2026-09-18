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

### 1. Contract registry and validation

- Define versioned schemas for item families, generation profiles, attack and
  defense profiles, abilities, recipes, and effect packets.
- Extend content-set validation to reject unsupported profile fields,
  impossible capability combinations, and unresolvable references.
- Teach the editor to render controls from the same schema. It may offer
  family-specific polish, but cannot invent unvalidated fields.

### 2. Combat and ability seam

- Normalize existing weapon, armour, and spell code behind attack/defense/
  ability adapters without changing Fantasy Frontier outcomes.
- Make damage types, costs, cooldowns, and targeting authored vocabulary.
- Add a minimal sci-fi device ability and kinetic weapon/vest through the new
  interfaces.

### 3. Generic generated-instance pipeline

- Extract tier/distribution and instance serialization from `GemGenerator`.
- Move gem, equipment-affix, crafting-quality, and future component rolls to
  profiles backed by the same resolver.
- Keep compatibility fields during migration (`material_quality_score`, for
  example), then retire aliases only after save migration coverage exists.

### 4. Crafting and economy seam

- Make recipes ask for material/family/capability contracts, not fantasy item
  IDs except where an authored quest deliberately requires an exact relic.
- Preserve provenance and resolved instance quality through crafting, salvage,
  trade, appraisal, and quests.

### 5. Sci-fi proving slice

- Create a deliberately small content set: one room loop, one NPC, one
  kinetic attack source, one protective gear item, one charge/heat ability,
  one generated component family, and one fabrication recipe.
- It must omit Fantasy magic, mana, spell schools, gems, and fantasy enemy
  vocabulary.
- Add an end-to-end smoke journey and contract snapshots alongside the
  existing Fantasy Frontier coverage.

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

## Non-goals

- Do not build a second large game or a generalized scripting language.
- Do not make every conceivable property configurable.
- Do not delete working Fantasy Frontier behavior before its adapter has
  equivalent characterization coverage.
