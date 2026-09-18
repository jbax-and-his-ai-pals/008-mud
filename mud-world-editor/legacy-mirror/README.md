# Legacy mirror — not read by anything

This directory used to be the world editor's data. It is **retired**: the editor
now reads and writes the real content set
(`content_sets/fantasy_frontier/`), the same files the game server loads. See
[`docs/roadmap/editor-content-source.md`](../../docs/roadmap/editor-content-source.md).

Nothing in the repository reads this tree. It is kept for one reason: two files
in it carry authoring that has not been reconciled with the content set, and
deleting them would destroy work that is not recorded anywhere else.

## What was already recovered

Migrated into the content set, by script, before this tree was retired:

| From here | To | Script |
|---|---|---|
| `regions/*.json` `_editor_pos`, `_editor_exit_layout` (12 regions, 193 rooms) | `content_sets/fantasy_frontier/editor/regions/*.editor.json` | `toolkit/migrate_editor_state.py` |
| `world_layout.json`, `magic_groups.json`, `templates/` | `content_sets/fantasy_frontier/editor/` | `toolkit/migrate_editor_state.py` |
| gem `rarity` (28 gems) + 10 gems that existed only here | `content_sets/fantasy_frontier/data/items/gems.json` | `toolkit/merge_editor_gems.py` |
| town district authoring (5 districts, kind/shape/seed, membership) | `content_sets/fantasy_frontier/data/regions/town.json` | `toolkit/port_town_districts.py` |

## What still needs a decision

**`regions/town.json`** — this copy is a *fork*, not a stale duplicate. Compared
with the content set's `town.json`:

- 38 of its 46 shared rooms were rewritten (shorter descriptions, some different
  exits, different NPC instance ids, `properties._district_id` tags);
- it is missing 8 rooms the content set has, including `community_garden`, where
  the opening commission sends the player;
- its district authoring has been ported (above), so the districts themselves are
  no longer a reason to keep it.

The content set's `town.json` is what the game plays and what the tests exercise,
so adopting this copy wholesale would delete content. **Which prose and which
exits win is an editorial decision.** Compare the two files directly:

```powershell
git show HEAD:mud-world-editor/legacy-mirror/regions/town.json > tmp/mirror_town.json
python -c "import json; a=json.load(open('tmp/mirror_town.json')); b=json.load(open('content_sets/fantasy_frontier/data/regions/town.json')); print(sorted(set(a['rooms'])-set(b['rooms'])), sorted(set(b['rooms'])-set(a['rooms'])))"
```

**`regions/dynamic_themes.json`** — same rooms on both sides, differing fields.
Small enough to diff by hand; the content set's copy is the one in play.

When both are settled, delete this directory:

```powershell
git rm -r mud-world-editor/legacy-mirror
```
