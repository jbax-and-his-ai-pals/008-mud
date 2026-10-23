# Contributing

Thanks for looking. The short version: **the engine holds all functionality; a game is content only.**

## Setup

Python 3.12. `powershell -ExecutionPolicy Bypass -File bootstrap.ps1` on Windows, or create `.venv` and
`pip install -r server/requirements.lock`. Use the project interpreter, not a bare `python`. The Godot
editor and client checks need Godot 4 on your machine (`check.py` finds it).

## Before you open a pull request

```bash
python check.py          # all four gates: unit, content, editor, client (about two minutes)
python check.py --quick  # while iterating: only what your diff can affect
```

A feature is done when all four gates pass, a test pins it (ideally one that fails without the change),
and the editor can author it, with the docs and `docs/plan/editor-coverage-ledger.md` saying so.
`docs/reference/ENGINE_CHANGE_RECIPES.md` lists every file in the chain for each kind of change
(an effect, a condition, a trigger event, an NPC property, a ruleset key, a new kind of content).

## Rules of the road

* Stage by explicit path; never `git add -A`.
* Engine tests use `tests.fixtures.STORY_FIXTURE`, never a shipped story. Only tests about a shipped set name it.
* A story uses its own names, not the names of the game it adapts.
* Never edit `content_sets/fantasy_frontier_test/**`; a validator error that set trips becomes a warning.
* Line endings are LF. Content JSON has no trailing newline (the editor's form): run
  `python toolkit/format_content.py --apply` after hand-writing content.

## Making a game rather than changing the engine

Start with `docs/reference/AUTHORING_A_CONTENT_SET.md`, and play `dq1_slice` or `zelda1` with
`python toolkit/play_script.py <set> ...` to see what a player reads.
