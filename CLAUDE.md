# Working in this repository

A Python MUD engine (`server/engine/`), content sets that are data only (`content_sets/`), a Godot world editor
(`mud-world-editor/`) and a Godot client (`client/`). **All functionality lives in the engine; a game is content
only.** Details and decisions: `ROADMAP.md`, `docs/README.md`.

## Commands (repo root)

Use the project interpreter, not bare `python`: `.venv/Scripts/python.exe` (Windows; `bootstrap.ps1` creates it) or
`.venv/bin/python`.

| | |
|---|---|
| `python check.py` | all four gates at once (unit, content, editor, client), about a minute |
| `python check.py --quick` | only what `git diff` can affect, plus the content gate; for iterating |
| `python run_tests.py --modules tests.singles.test_x` | specific unit-test modules (sharded; `--shuffle` hunts order dependence) |
| `python run_editor_checks.py --only trigger` | editor (Godot) checks whose file name contains the word |
| `python toolkit/play_script.py <set> "wait 30" "take crystal" where` | play a content set and read what the player reads (`--debug` for a test session: `checkpoint <name>`, `scene skip`, `level`, `tp`...) |
| `python toolkit/content_edit.py get\|set\|append\|delete <set> <file> <path> [json]` | change content JSON in the editor's form |
| `python toolkit/format_content.py --apply` | put hand-written content into the editor's form (the round-trip gate is byte-exact) |
| `python toolkit/sync_editor_vocabulary.py` | regenerate the editor's dialogue tables after changing a condition kind or effect |

Set `MUD_LOG_LEVEL=WARNING` to silence engine chatter when running scripts.

## Before you change the engine

`docs/reference/ENGINE_CHANGE_RECIPES.md` lists, per kind of change (an effect, a condition, a trigger event, an NPC
property, a ruleset key, a new kind of content), every file in the chain: engine reader, validator, editor, vocabulary,
tests, docs. A feature is done when all four gates pass, a test pins it (falsified against the parent where it
matters), the editor can author it and the docs and `docs/plan/editor-coverage-ledger.md` say so.

## Rules

* **Stage by explicit path** (`git add path ...`), never `git add -A` or `.`: untracked scratch sets live in the tree.
  End commit messages with the `Co-Authored-By` line the session gives you.
* **Never edit** `content_sets/fantasy_frontier_test/**`, `mud-world-editor/scripts/data/RegionManager.gd` or
  `mud-world-editor/tests/room_item_placement_smoke.gd` (`check.py --staged` refuses them). A validator error that
  set trips becomes a warning, not an edit to the set.
* **Engine tests never name a shipped story.** They use `tests.fixtures.STORY_FIXTURE`; only tests about a shipped set
  (`test_adaptation_slices.py`, `test_ff4_opening.py`) name `ff4_slice` / `zelda_slice`.
* A story uses its own names, not the names of the game it adapts (a basic spell that is a common word excepted).
* Line endings are LF (`.gitattributes`). Content JSON has no trailing newline (the editor's form).
* A test that registers anything global (commands, plugins) removes it in `addCleanup`; tests share a content-set load
  cache, so a set that changes on disk is re-read and one that does not is not.

## Windows shell notes

The Bash tool is Git Bash; heredocs mangle backslashes, apostrophes and tabs. Write a patch script with the file-write
tool and run it with the project interpreter rather than piping Python through a heredoc. Scratch files go in the
session's scratchpad, not the repo.

## Where things are

`server/engine/server/content_set/` (the validator, one module per domain) · `server/engine/dialogue/effects.py` and
`server/engine/conditions.py` (the vocabularies, defined once) · `server/engine/world/` (world, triggers, scenes,
factions) · `server/tests/` (`singles`, `batch`, `current`; `sets/story_fixture` is a frozen copy of the ff4 slice) ·
`toolkit/` (validators and authoring tools) · `docs/plan/` (what is next), `docs/reference/` (how it works),
`docs/design/` (why).
