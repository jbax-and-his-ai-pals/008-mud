# Engine change recipes

Every engine feature is a chain: the engine reads it, the validator refuses bad values, the editor can author it, a test
pins it and the docs say it. Each recipe below lists that chain for one kind of change, in order, so nothing is
found by running the gates and reading what failed. The general rule behind all of them is in `ROADMAP.md`: **all
functionality lives in the engine; a game is content only.**

Run `python check.py --quick` after each step (what the change can affect, found from `git diff`) and `python check.py`
before you commit (all four gates at once, about a minute). The checks that notice a missed step are named in brackets.

## Add an effect (a conversation, trigger, scene or quest may run it)

1. `server/engine/dialogue/effects.py`: add the name to `KNOWN_EFFECTS`; its value's shape to `EFFECT_SHAPES`; its
   author-facing label, hint, value kind and (`refs`) the identifier bucket its ids are checked against to
   `EFFECT_EDITOR`; the `_apply_<name>_effect` function; and a step in `apply_effects` (order matters: message first,
   state changes, `teleport` last). [`test_effect_shapes.py`]
2. A reference that is not an id in a bucket (the way `play_scene` names a scene) is checked in
   `server/engine/server/content_set/effects_conditions.py::_check_effect_block`.
3. `python toolkit/sync_editor_vocabulary.py` writes the editor's `DialogueSchema.gd` tables from step 1.
   [`test_editor_vocabulary_sync.py`, `schema_parity_smoke.gd`]
4. Update the pinned count in `test_engine_vocabulary_dump.py` (`effect_keys`).
5. Tests: the effect applied (and refused when malformed), a falsified journey if it changes play, a restart test if it
   changes state that is saved.
6. Docs: `docs/reference/AUTHORING_A_CONTENT_SET.md`; a row in `docs/plan/editor-coverage-ledger.md`.

## Add a condition kind

1. `server/engine/conditions.py`: add the kind to `CONDITION_SPECS` (label, fields, `refs`, note) and its branch in
   the evaluator.
2. `python toolkit/sync_editor_vocabulary.py`.
3. Update the pinned count in `test_engine_vocabulary_dump.py` (`condition_kinds`).
4. Tests: true and false cases, and a validator refusal for a bad reference. Docs and a ledger row as above.

## Add a trigger event

1. `server/engine/world/triggers.py`: add the event to `TRIGGER_EVENTS` and its allowed keys, a `fire_<event>` method,
   and the call where it happens in the engine (`pickup_drop.py` for `item_taken`, the death path for `npc_killed`).
2. Validator: `content_set/triggers_dialogue.py::_validate_triggers`.
3. Editor: `TriggerSchema.gd` (`EVENTS`), `TriggerInspector.gd` (the fields it takes).
   [`trigger_authoring_smoke.gd`, `test_kill_triggers.py` pin the event list]
4. Vocabulary dump and parity: `toolkit/engine_vocabulary_dump.py`, `schema_parity_smoke.gd`.
5. Tests, docs and a ledger row.

## Add an NPC property

1. Read it where it acts (`server/engine/npcs/`). A property nothing reads is deleted, not added.
2. Validator: `content_set/npcs.py` (`_npc_property_errors`, the near-miss warnings). Whether the editor offers it is
   `NPCVocabulary.gd` and `NPCInspector.gd`. [`npc_*_smoke.gd`, `test_story_fixture.py` if a story uses it]
3. Tests, docs, a ledger row.

## Add a ruleset key

1. The reader in the engine; the check in `content_set/ruleset.py::_validate_simple_ruleset_sections` (or the section's
   own validator).
2. Editor: `RulesetDraft.gd` and the section in `scripts/ui/modals/`; `schema_parity_smoke.gd` compares the vocabulary.
3. Tests, docs, a ledger row.

## Add a kind of content (a new `data/<folder>/`, the way `scenes` was added)

Engine: a loader (`world/`), a `_validate_<kind>` in `content_set/`, the id bucket in `identifiers.py`, the vocabulary
dump, and `toolkit/reference_index.py` (a reference family, or a `NOT_INDEXED` note saying why not).
Editor: `DataRoot.gd` (folder), `DatabaseManager.gd` (load, save, ids, add), `ContentLibraryDialog.gd` (list and
inspector), `Main.gd` (the add-new defaults), an inspector, a schema file and `schema_parity_smoke.gd`.
[`content_round_trip_smoke.gd` fails if the editor does not write the files back byte for byte.]

## Change a shipped story

Engine tests never name a shipped story; they use `tests.fixtures.STORY_FIXTURE` (a frozen copy). Only tests *about*
a shipped set name it (`test_adaptation_slices.py`, `test_ff4_opening.py`, ...), and `toolkit/adaptation_walkthroughs/`
plays each from start to finish.

* Read or change a value: `python toolkit/content_edit.py get|set|append|delete <set> <file> <path> [json]`.
* Put hand-written JSON into the editor's form: `python toolkit/format_content.py --apply`.
* Play it and read what the player reads: `python toolkit/play_script.py <set> "wait 30" "take crystal" where`.
* Names in a story are its own: no names from the game it is adapted from (a basic spell that is a common word is
  the one exception).

## Make a test fast, or order-independent

* Tests that load a content set share a per-run cache (`engine.server.content_set.enable_load_cache`, turned on by
  `server/tests/__init__.py`); a set that has not changed on disk is not read again.
* `python run_tests.py --shuffle` runs the modules and the tests in a random order; a failure there is a test that
  depends on what ran before it. `--shuffle-seed N` repeats it.
* Anything a test registers globally (commands, plugins) is removed in `addCleanup`.
