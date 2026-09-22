# Editor save and configuration safety

**Updated 2026-09-22.** Applies to the Ruleset, Manifest, Contract and Combat
Vocabulary dialogs, plus the reference-aware rename/delete and ordinary
library/region save path. This is the first hardening slice of
[batch 6A](../plan/chunks-of-work.md), not the multi-file migration workflow proposed in
the [game-authoring roadmap](../plan/game-authoring-roadmap.md).

**What each dialog can author** — field by field against the engine's schemas — is
recorded in [the coverage ledger](../plan/editor-coverage-ledger.md) §H.2 and pinned by
`server/tests/singles/test_configuration_dialog_coverage.py`: the contract dialog covers
67 of the schema's 69 fields, the combat-vocabulary dialog covers every hazard key the
shipped file uses, and the ruleset dialog covers 7 of the reference ruleset's 23
top-level keys.

## Editing and closing

- Save is enabled after a form change and disabled when that change is reverted.
  Opening a form or saving an unchanged form does not rewrite its file.
- Changing one field retains untouched sections, optional/defaulted values and
  supported nested data. Unsupported collection shapes are refused on load rather
  than quietly shortening the collection on save.
- Invalid numbers, malformed structured payloads, blank IDs and duplicate hazard
  IDs remain problems to repair, not instructions to substitute zero or omit rows.
  Effect payloads use a typed JSON-object field for now; a friendlier structured
  editor remains future work.
- Cancel/window-close on an edited form asks whether to discard. Cancelling that
  prompt keeps the draft. Explicit discard leaves the saved file unchanged.
- Application quit/switch checks include pending configuration. A save failure
  keeps the draft and stops the save-and-leave path. Choosing to switch without
  saving clears the old set's configuration drafts.

## What Save checks and writes

The draft first performs its immediate form checks. `ConfigurationSave.gd` passes
the candidate to `toolkit/configuration_save.py`, which:

1. Compares the source file's SHA-256 with the version loaded by the dialog.
2. Stages a copy of the content set, substitutes the one candidate file, and asks
   `engine.server.content_set.validate_content_set` for the engine's verdict.
3. Refuses engine errors, missing toolchain/validator failures and files changed
   during validation. Warnings do not prevent this save.
4. Writes a verified temporary file and replaces the destination atomically,
   keeping the prior file at `<filename>.bak`. A failed replacement retains the
   original and the visible draft. The backup is the previous revision, not a
   version-history service.

This is **single-file, engine-load validation**. It is not the complete release
gate, runtime playtesting, arbitrary undo, or an atomic transaction spanning the
world, library and configuration. Use Validate Open Set and the release checks
for their broader scopes. Existing blocking errors elsewhere in the staged set
can prevent a configuration save; the returned report names them.

The current service requires Python and the repository's toolkit. Manifest paths
outside the content-set directory and linked files/directories are explicitly
refused. Custom-root authoring and coordinated capability/manifest edits belong to
the next project-lifecycle batch; no file is rewritten to work around that limit.
Validation currently runs synchronously on Save, so very large sets may pause the
dialog. Conflict detection is optimistic, not a collaborative file-lock protocol.

System toggles must still agree with the manifest. Disabling a manifest-declared
capability in the Ruleset dialog alone is rejected; this batch does not silently
rewrite the manifest or delete that system's content. Inherited system values are
shown without materializing overrides during unrelated edits.

## Reference-aware library edits

- Before a library entry is renamed, the editor shows every reference found by
  the engine-shared reverse index, grouped by file and JSON path. It then
  preflights every path on a copy. If even one path is stale, malformed,
  unparseable, or would collide with an existing key, the rename is blocked and
  nothing is changed.
- The repaired rename remains a normal dirty editor change. **Save Changes**
  checkpoints `data/`, writes the affected region/library files, then runs the
  open-set engine validator. An engine error restores the checkpointed files and
  keeps the visible edits dirty, so the author can correct or discard them.
- Delete is intentionally narrower: an entry with indexed referrers cannot be
  deleted yet. The author must rename it or remove the dependencies first. An
  empty index result is described as partial coverage, never as proof that the
  identity is unused.

The current reference index covers item, NPC, ability, room, collection and
recipe references from the same family table used by the validation gate. It does
not yet cover every engine binding, nor does it offer a multi-file refactor
transaction, delete dispositions, external roots, or a combined atomic commit of
configuration and library changes.

## Regression evidence and human retest

`mud-world-editor/tests/configuration_dialog_smoke.gd` exercises actual control
signals, save/reopen, discard, malformed input, tier edits, typed payload parsing,
external conflicts, and the full editor scene's signal/dirty-state integration.
`server/tests/singles/test_configuration_save.py` covers engine refusal, backups,
write failure, external changes and validator failure, plus runner false-positive
and timeout checks. The editor runner now treats `SCRIPT ERROR:` as failure even
when Godot exits zero.
`reference_index_smoke.gd` also proves that a rename preflight is non-mutating,
and that a restored checkpoint can return the library to a visible dirty state.

Human retest on a **copy** of a content set:

1. Open Ruleset; edit its ID, revert it, and check Save returns to disabled.
2. Edit it again, close the dialog, and cancel the discard prompt. Save, reopen,
   and confirm the value persisted. Check the contract browser/library refresh.
3. In Contracts, change a resource label. Confirm stat short labels, generation
   tiers and unrelated fields survive. Add/edit/remove a tier and reopen after a
   valid save. Try a malformed numeric field and confirm nothing is written.
4. In Combat Vocabulary, try a duplicate channel or blank hazard ID. Correct it
   and save; errors must retain the draft. Check long error text and controls fit
   the available screen space.
5. With a configuration edit pending, request application close. Keep editing;
   then try save-and-close. Repeat with a deliberately invalid draft and confirm
   the application does not exit after the failed save.
6. On a copied content set, rename an item used by a recipe or vendor. Review the
   listed paths, save, reopen the recipe/vendor and confirm they now name the new
   item. Try deleting that same item: it should be blocked until those references
   are removed. Introduce an invalid item family, save, and confirm the data file
   is restored while the editor still shows unsaved work.

Visual layout/accessibility and exhaustive edits across every contract/ruleset
field are not certified by these headless checks. The full-scene smoke currently
reports resource-retention warnings at teardown; follow-up cleanup remains open.
