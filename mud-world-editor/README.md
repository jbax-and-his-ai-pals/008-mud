# MUD world editor

A Godot 4 editor for the content sets the game server loads. It edits the same
files the server reads — there is no export step and no mirror — so a change here
is a change to the game. See `docs/roadmap/editor-content-source.md` for how that
came to be, and `docs/roadmap/world-editor-evaluation.md` for what it can and
cannot do today.

## Running it

Open `project.godot` in Godot 4.7+ (or run the executable with `--path`). The
editor resolves which content set to edit in this order, first hit wins:

1. `--data-root <path>` on the command line (a content-set directory, or its
   `data/` subdirectory);
2. `user://editor_settings.json` → `{"content_set_root": "..."}`;
3. `<this project>/../content_sets/fantasy_frontier` (a checkout);
4. `<this project>/data` (a standalone copy).

The window title shows which world is open and how it was found, so the answer is
never a guess. There is no in-app switcher yet: to edit a different content set,
launch with `--data-root`:

```
godot --path mud-world-editor -- --data-root ../content_sets/orbital_salvage
```

## What it edits

| Surface | Content |
|---|---|
| Region graph | rooms, exits, districts, spawner settings, room properties, NPC and item placement, bulk generation, auto-arrange |
| Content Library | NPCs, items (with their contract family and roll tables), abilities (from `abilities/` or `magic/`), quests, recipes, **dialogue graphs**, room templates |
| Contracts | a read-only browser for what the set declares: families, roll tables, resources, attack/defense profiles, abilities, effect packets |
| World view | region positions and acknowledged validation warnings |
| Editor state | room positions, exit layout, quest stage positions, world layout and ability groups — all in `<content set>/editor/`, never in `data/` |

Each inspector is written against the engine's own schema, in one place, so the
labels and fields are the ones the runtime reads:

- **quests** — `scripts/data/QuestSchema.gd`: objective types with the fields the
  tracker and validator use, alternative routes, turn-in and completion dialogue,
  spawn entries.
- **recipes** — `engine/crafting/recipe.py`: ingredients, quality tiers,
  familiarity milestones, station, and difficulty as a switch (absent means
  "derive it", so a spin box would write 0 onto every recipe it touched).
- **dialogue** — `scripts/data/DialogueSchema.gd`: the condition kinds
  `engine/conditions.py` evaluates, and the effect keys
  `engine/dialogue/effects.py` applies, each with the shape it expects. Node
  targets are pickers over the graph's own nodes, and renaming a node repoints
  every reference to it.

Keys an inspector does not model are shown and preserved, never dropped.

**Open Content Set…** in the explorer switches between the content sets beside the
checkout: the world reloads and the choice is written to
`user://editor_settings.json`, so the next launch opens the same set. Sets are
listed as "Title   (id)". **Rename…** changes either: the title is the display
name and always safe to change; the id is also the folder name and what player
saves record, so saves made under an old id will not load into a renamed set.
The open set can be renamed too: a title change is written in place, and an id
change asks about unsaved work, moves the folder and reopens the set from it.

Not yet: editing the contracts themselves (the browser is read-only), backgrounds,
titles, collections, discoveries, combat elements, or campaigns.

## Saving

One Save button writes the open region; the same press also saves the content
library, because a region's NPC and item changes live there. Every write goes
through `scripts/data/SaveIO.gd`, which writes, reads the file back, and reports
failure — a save that did not happen leaves the work dirty and shows a dialog
rather than greying the button out. Content is written 4-space indented and in
authored key order.

Leaving a region with unsaved edits asks first, and lists the rooms, library
entries and configuration it would discard; closing the window offers **Save
and quit** / **Quit without saving** / **Keep editing**. There is no autosave, so
the quit prompt is the safety net.

## Checking your work before the game does

- **Validate** — the editor's own link check (missing exits, one-way links,
  district continuity).
- **Validate Region Policy** — every region against the ruleset's biome /
  region_type / level_band / hazard coverage policy.
- **Validate Content (engine)** — runs the game's own validation
  (`toolkit/editor_validate.py`: schema, references, text templates, stale ids,
  file integrity) and shows its issues. This is the same verdict
  `run_content_checks.py` reaches in CI.

## Keyboard

| Key | Action |
|---|---|
| `Ctrl+Z` / `Ctrl+Y` | undo / redo (graph edits: connections, room create/delete/move, renames, districts, auto-arrange) |
| `Ctrl+F` | search rooms, NPCs and items |
| `F` | recentre the view |
| `Escape` | cancel the current tool, box-select or district preview |
| `Shift`+click | add to the selection |
| drag a room's `+` handle | add a connected room in that direction (the handles show on hover) |

The shortcuts work whatever panel has focus, except while typing in a field or with a dialog open.

Undo does not cover inspector field edits, paste, or the paint and stamp tools,
and the history is cleared when another region is loaded.

## Tests

Eighteen headless checks live in `tests/`, run from the repository root:

```
python run_editor_checks.py                     # finds Godot, runs everything
python run_editor_checks.py --godot <path>      # or name it explicitly
```

They exit non-zero on failure, so they can gate a change the way the Python suite
does, and `.github/workflows/editor-checks.yml` runs them plus the content checks
on every push. `editor_save_safety_smoke.gd` and `editor_session_safety_smoke.gd`
cover saving, quitting and deleting against a throwaway content set under `tmp/`;
`quest_inspector_smoke.gd`, `contract_authoring_smoke.gd`,
`recipe_authoring_smoke.gd` and `dialogue_authoring_smoke.gd` author content
through the real inspectors and then have the *engine's* validator check it;
`content_set_switch_smoke.gd` drives the real `Main.tscn` between two scratch
sets; `engine_validation_smoke.gd` covers that subprocess seam; the rest cover the
region graph, districts and the layout optimiser. Nothing here writes to a
shipped content file.
