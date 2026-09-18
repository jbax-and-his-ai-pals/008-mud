# Handoff: cross-theme contracts and generated items

**Use this as the starting brief for the next conversation.** The active
product roadmap remains [`/ROADMAP.md`](../../ROADMAP.md); the design and
delivery detail for this new initiative is in
[`docs/design/cross_theme_engine_contracts.md`](../design/cross_theme_engine_contracts.md).

## Decision reached

The engine must separate authored templates, generic capabilities/contracts,
and persistent generated instances. Fantasy magic, weapons, armour, gems, and
crafting are implementations of base systems, not base systems themselves.
A minimal sci-fi content set will be the abstraction test.

## Current implementation state

- `server/engine/items/gem_generator.py` is a working **provisional** first
  family generator. It rolls intrinsic template rarity, size, and quality;
  chest loot and resource gathering use it.
- `mud-world-editor` now has a **Gems** library tab. It edits Gem templates,
  exposes rarity/base economics plus size/quality tendency, and creates new
  Gem templates. Those tendency controls are honored by `GemGenerator`.
- The canonical Fantasy Frontier content set already has roughly fifty Gem
  templates. The editor's old local mirror was incomplete; its local
  `data/items/gems.json` now carries 38 rarity-tagged entries, but a full
  canonical editor/content-set synchronization remains a separate migration.
- The focused tests pass:

  ```powershell
  py -3.12 run_tests.py --target tests.singles.test_gem_generator --target tests.singles.test_chest_loot_generator
  ```

- Godot syntax boot passes with:

  ```powershell
  & 'C:\Users\baxte\Downloads\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe' --headless --path 'C:\jbax-and-his-ai-pals\008-mud\mud-world-editor' --quit-after 2
  ```

  It still prints the pre-existing ObjectDB/resource cleanup warnings at exit;
  there are no script errors.

## Recommended first implementation slice

1. Audit concrete genre/type checks in combat, items, magic, and crafting.
2. Write the smallest versioned contract registry/schema and validator.
3. Add characterization tests for current Fantasy behavior.
4. Refactor one attack source, one defense source, and one ability through the
   new adapters before broad conversion.
5. Extract `GemGenerator`'s common roll/instance mechanics into the shared
   generated-item resolver; preserve compatibility properties during migration.
6. Only then author the tiny sci-fi proof content set and its smoke journey.

## Working-tree caution

The worktree intentionally contains substantial uncommitted editor, district,
Content Library, magic-group, spawner, gem-generator, and test work from this
conversation. Preserve unrelated edits; do not reset, checkout, or bulk-copy
the content trees without first comparing canonical `content_sets/` data to
the editor mirror.
