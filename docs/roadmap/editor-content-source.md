# One content source: the editor and the server share `content_sets/`

**Decided 2026-09-18.** The world editor reads and writes the same files the
game server loads. There is no mirror, no export step, and no second copy of the
world to keep in step.

## Why

The editor used to read and write `mud-world-editor/data/` — its own tree, with
`res://data/...` hard-coded in `DatabaseManager.gd`, `RegionManager.gd`,
`WorldManager.gd`, and `Main.gd`. The only path between the two worlds was
`toolkit/editor_export_shim.py`, one way, editor → server.

That held together while the editor was mostly a *viewer*. Once it became the
authoring front-end — districts, connections, the Content Library, magic groups,
the Gems tab — the two trees stopped agreeing:

| | canonical | editor mirror |
|---|---|---|
| regions | 25 | 25 |
| quests | 24 | 24 |
| magic | 23 | 23 |
| weapons | 23 | **1** |
| villagers | 21 | **1** |
| junk | 36 | **1** |

The editor was missing 164 item ids and 52 NPC ids, had 10 gems the canonical
set did not, and had no `crafting/`, `dialogue/`, `knowledge/`, `player/` or
`world/` at all. A designer opening the Content Library saw one villager where
the game has twenty-one. Regions, quests and magic were only in step because
those were the files the recent pushes happened to touch.

### What the mirror actually held, once it was examined

"Stale copy" turned out to be three different stories, and only one of them was
a copy:

- **Items and NPCs: stubs.** One entry per file for weapons, armour, junk,
  consumables, treasure, villagers and hostiles. They had always been stubs —
  the commit that looked like it rewrote them (`67400cd`) only removed a trailing
  newline. Canonical is the whole world; nothing to merge.
- **Magic: the old schema.** Canonical spells use `effects: [{type, value}]`;
  the mirror still had the legacy flat `effect_type`/`effect_value` pairs. The
  mirror was *behind*, not ahead.
- **Gems and town districts: genuinely newer.** The Gems tab work
  (`abd3175`) added an intrinsic `rarity` to 28 gems plus ten gems that existed
  nowhere else — and `GemGenerator` reads exactly that field, falling back to
  guessing from `value` for legacy templates. So every gem in play was being
  generated off the fallback path while the authoring sat unread. The districts
  work (five districts with kind, shape, seed and membership) was the same story:
  `world.get_district` reads `properties.districts[*].members` for the room title
  and the room → district → region atmosphere chain, and canonical town still had
  the legacy block (one district, four rooms).

Those two were recovered before the mirror was retired, by
`toolkit/merge_editor_gems.py` and `toolkit/port_town_districts.py` — both
additive, and both leaving editorial changes (28 gem renames and re-prices, 38
rewritten town room descriptions) alone and reported instead.

## The rule

**Canonical content is what the game reads. Editor state is how the editor
remembers it looks. They are different files, in one tree.**

```
content_sets/fantasy_frontier/
  data/                     the game's content, exactly as the server loads it
    items/ npcs/ magic/ regions/ quests/ campaigns/ combat/ dialogue/ crafting/ …
    collections.json discoveries.json titles.json
  rules/ruleset.json        the game's rules (was data/ruleset.json in the mirror)
  editor/                   editor-only state; the server never reads this
    world_layout.json       world map placement
    magic_groups.json       magic library grouping
    templates/              editor room templates
    regions/<id>.editor.json   _editor_pos, _editor_exit_layout
    quest_layout.json       per-quest stage positions
```

The editor resolves its content-set root in this order, and shows the resolved
path in the window title so it is never ambiguous:

1. `--data-root <path>` on the command line (a content-set root, or a `data`
   directory; either is accepted).
2. `user://editor_settings.json` → `{"content_set_root": "..."}`.
3. `<project>/../content_sets/fantasy_frontier` — the checkout layout.
4. `<project>/data` — a standalone copy, if someone has one.

## Why a sidecar rather than `_editor_*` keys in the content

`_editor_pos` and `_editor_exit_layout` are layout bookkeeping. `RegionManager`
already documents the rule the project had been keeping by hand:

> Content-set-authored rooms (content_sets/fantasy_frontier/data/regions/*)
> carry no `_editor_pos` — it is purely editor layout metadata, never written by
> the game server.

Putting them back into the shipped files would reverse that: every region diff
would carry editor drags, a hand-editor would have to know to preserve keys the
game ignores, and "unknown key" checks could never be added to the content
validator. The sidecar keeps the contract clean and is invisible to the rest of
the pipeline.

The split happens at exactly two chokepoints — load and save — so the ~20 call
sites that read and write `_editor_*` on the in-memory dictionary are unchanged:
`load` merges the sidecar in, `save` lifts it back out and writes the canonical
file clean.

## Migration

The mirror's editor-only state was lifted once into `editor/` — layout for 12
regions and 193 rooms, the world map layout, magic groups, templates — by
`toolkit/migrate_editor_state.py`, and the two families holding newer authoring
were merged forward by `toolkit/merge_editor_gems.py` and
`toolkit/port_town_districts.py`.

The tree itself is now `mud-world-editor/legacy-mirror/`, read by nothing, kept
only because `regions/town.json` and `regions/dynamic_themes.json` remain a fork
whose resolution is an editorial decision (38 rewritten room descriptions, 8
rooms the canonical file has and the mirror does not). Its `README.md` says what
was recovered, what is left, and how to compare the two files. `toolkit/editor_export_shim.py`
stops being a sync step and becomes what it is good at: validating and reporting
a migration for anyone who still has an old mirror.

## Guardrails

- No editor script may hard-code a `res://data/...` **content** path. `res://`
  stays for scripts, scenes and themes; content comes from the resolver. A test
  enforces this, so the mirror cannot quietly come back.
- The retired mirror must not be the editor's fallback directory: `DataRoot`'s
  `<project>/data` candidate is checked, and a test asserts that
  `<project>/data` does not exist while `<project>/legacy-mirror` explains
  itself.
- Canonical region and quest files must contain no `_editor_*` keys. A test
  enforces that, so a save path that forgets the split is caught.
- The server's loader and the content validator must not walk `editor/`; a test
  asserts it.
- `mud-world-editor/tests/content_source_check.gd` runs headlessly and proves the
  real thing: the resolver lands on the content set, `town.json` loads through
  it with all 46 rooms positioned from the sidecar, the on-disk file carries no
  editor keys, and a split/merge round trip leaves the author's layout exactly as
  it found it.

