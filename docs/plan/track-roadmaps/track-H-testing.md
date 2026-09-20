# Track H — Testing

## Assessment

**State.** The division between the three suites is a directory name and nothing else: `run_tests.py:39` is `SUITES = ("singles", "batch", "current")`, each discovered with `-p "test_*.py"`. `server/tests/TESTING.md` catalogues 34 `tests/singles/*` modules and their method names (22 of 22 sampled names exist) and never mentions the three suites. Measured: `singles/` 474 modules, `batch/` 41 modules / 280 test methods, `current/` one real file (`test_campaign_branching.py`, 3 tests) plus `all_code_tests_part2.py`, which is one comment line. **What batch is for, read rather than assumed:** every file uses `tests/fixtures.py:67` `GameTestBase` — a real `GameManager` over `content_sets/fantasy_frontier`, a real world, `game.process_command` — so it is integration-flavoured. But the set of `engine.*` modules imported by `tests/batch/*.py` and not by `tests/singles/*.py` is **empty**, and only one method name is shared (`test_year_rollover`). Its distinguishing features are that it is frozen (all 41 files from commit `e2c0638`, 2026-09-03; newest touch 2026-09-15, while `current/` has not been touched since that commit and singles has gained hundreds of modules) and that it asserts more loosely: 74 `if <var>:` guards across 27 of 41 batch files against 88 across 65 of 473 singles files. The division is historical; `current` is the clearest case — a staging lane nothing has staged into for two and a half weeks.

**Strongest.** The content-loading failure paths, and one pattern: `server/tests/singles/test_reference_coverage.py:60-68` copies a *real* content set into a temp tree, mutates one reference, runs the real validator **as a subprocess**, and asserts exit 1 plus the offending id — while `TestItDoesNotInventFindings:152-177` asserts the same validator exits 0 when an optional reference is simply absent and when a file carries an authoring `_comment`. A gate proven to fire and proven not to cry wolf; `test_content_playability_check.py:222-259` does the same for playability by breaking a copy of `orbital_salvage`. The command failure boundary is contract-shaped: `test_command_crash_boundary.py` registers a raising handler and asserts the player gets an answer, the session survives, the exception's *text* (a fake secret path) does not leak but its *type* does (`:61-69`), and the operator sees a count (`:107-119`).

**Weakest.** (1) **Gate exit codes are untested where the runner consumes them.** `test_pack_tool_compatibility.py:239-242` drives `main()` in-process; `normalize_content_numbers.py`'s check mode is tested only through `normalize_content_set()` — `main()`'s exit-1 branch (`toolkit/normalize_content_numbers.py:411`) runs nowhere; `content_neutrality_validator.py` has **no test at all**. This is the P0 failure ("`run_content_checks.ps1` now actually runs", ROADMAP.md:151) recurring in test form: the library was proven, the door was not. (2) **Save/load is sampled, not round-tripped.** `test_persistence.py:25-58` saves, wipes, reloads, checks three fields. `test_save_manager_full.py`'s `TestLoad` asserts `assertTrue(success)` after injecting malformed payloads — `test_missing_quest_manager_is_skipped:183-191` and `test_falsy_dynamic_region_entry_is_skipped:113-122` pass unchanged against a `load()` that returned `(True, None, None)` and restored nothing. No test compares whole serialised state across a reload, and **no test loads a save the current writer did not produce**: there is no committed old-save fixture, and of the three `MIGRATIONS` (`save_format.py:92-96`) two are identity functions.

**Surprises.** (1) **Fourteen tracked test modules are 0 bytes** — `git cat-file -s HEAD:<path>` is 0 for every `test_*.py` under `server/tests/singles/` with `Length -eq 0`, including `test_onboarding.py`, `test_launcher_scene.py`, `test_keybindings.py`, `test_crash_recovery.py` and `test_server_panel_payloads.py`, which `docs/archive/HANDOFF.md:29-83` documents as holding 24, 24, 37, 36 and 27 tests respectively; adding `test_client_a11y_presets.py` (15, `:62`) makes the 163 tests that file claims for six empty modules, and `:110` credits `test_msgpack_transport.py` with 8 more. All were created empty in `e2c0638` and never had content in this repository's history. Discovery imports them, counts zero, reports green. (2) Five tests are silently checkout-locked: `test_p4_progression.py:419,428,434,456,475` pass `content_root=r"C:\jbax-and-his-ai-pals\008-mud\content_sets\fantasy_frontier\data"`. (3) `snapshot_assertions.py:57-63` re-records under `MUD_UPDATE_SNAPSHOTS=1` and then compares the file it just wrote to the payload, so the 30 snapshots can be turned green by the change they exist to catch. (4) Of four sets, `night_shift` is booted at runtime by one test file (`test_content_set_crime_vocabulary.py:29`); everything else runs fantasy via `fixtures.py:10`. The single test with the most leverage over this project's defect history is a runner-level falsification harness (item 1): it would have caught the walker with the wrong path, the validator that read an authoring note as an id, the reachability gate that counted exit targets as reachable, and the `pack_tool` CLI that could not start.

## Gate falsifiability audit

| Gate (as the runner invokes it) | Fault-injection test proving it can fire? | What it would take |
|---|---|---|
| `pack_tool.py validate` (themes; starter packs `--strict`) | Yes, in-process: `test_pack_tool_compatibility.py:239-242` drives `main()` with patched argv and asserts nonzero | Nothing |
| `data_integrity_validator.py` (fantasy only) | Yes: `test_root_with_errors_exits_one` | Run it for all four sets (Track I item 4) |
| `mod_manifest_validator.py` | Yes at function level (`:77,:92,:103`); the CLI exit is never driven | One subprocess case |
| `content_set_validator.py` (4 sets) | Yes: broken packages written, messages asserted; `main()`'s `SystemExit(1)` not driven | One CLI case |
| `normalize_content_numbers.py --check` | **No**: `normalize_content_set()` tested, `main()`'s exit-1 path runs nowhere | Scratch set with `3.0` in an int field, `main()` invoked, exit 1 asserted |
| `reference_integrity_validator.py` (4 sets) | Yes, best in class: `test_reference_coverage.py:60-68`, real copy + subprocess + exit 1 | Nothing |
| `stale_reference_audit.py` (4 sets) | Yes: `test_root_with_issues_exits_one` | Nothing |
| `skill_audit.py` (4 sets) | **Cannot fire**: `skill_audit.py:724` returns 0 unconditionally — warning-only by design | Decide whether that stays true, or stop calling it a gate |
| `content_neutrality_validator.py` (fantasy, orbital) | **No test module exists in `server/tests/`** | Fixture is Track I item 5's; the test is H's |
| `content_playability_check.py` (4 sets) | Yes: `test_content_playability_check.py:222-259` breaks a copy of a real set | Nothing |
| Fixture steps on the `LATEST_REFRESH.json` target | Not runnable here: `run_content_checks.py:166` SKIPs, path absent; `test_fixture_refresh.py` proves the tool, not the chain | A committed relative target, one CLI case |
| `genre_coupling_audit.py` | Not run by any runner, no test; `:129,:165` both return 0 | A runner step and a non-zero exit, or retire it |
| `region_policy_validator.py`, `editor_validate.py`, `template_placeholder_validator.py` | Yes on the Python side (`test_region_policy_validator.py:46-102` writes broken regions) | Reachable only through Godot today |
| `run_editor_checks.py` (24 `.gd` smoke scripts) | Unproven — no case deliberately breaks the editor to prove a check goes red | One `.gd` check against a corrupted scratch set |

## Weak tests found

1. `server/tests/batch/test_batch_saga.py:9` `test_saga_flow` — the body is wrapped in `if captain and alchemist:` (`:62`) and every message assertion in `if res:` (`:76,:86,:96`). If the factory returned `None`, or `process_command` returned `None`, the test passes having asserted nothing about the three-stage progression it protects. It also injects its own quest/NPC templates, so it cannot notice those ids drifting in content.
2. `server/tests/singles/test_save_manager_full.py:113-122` (also `:183-191`, `:102-111`) — writes a malformed save, calls `load()`, asserts only `assertTrue(success)`. "The loader survived" is the whole claim; a loader that returned success and restored nothing satisfies it.
3. `server/tests/batch/test_batch_enhancements.py:103-134` — assertions behind `if res:` / `if res2:`, and `test_reputation_impact:46-50` opens with `if not villager: return`. The file's own comment at `:123-127` records that a previous patch target was a silent no-op: the test depended on an unseeded dice roll and passed anyway.
4. `server/tests/singles/test_editor_content_source.py:63-69`, `:117-129` — asserts implementation text: `assertIn('DEFAULT_CONTENT_SET := "../content_sets/fantasy_frontier"', source)` breaks on reformatting while proving nothing about what `DataRoot` resolves; `assertNotIn('"editor"', loader)` passes if the loader starts walking `editor/` by another expression. The file's other three tests assert real content facts.
5. `server/tests/singles/test_content_set_runtime.py:470-476` `test_content_root_is_not_a_runtime_override` — asserts a `TypeError` from an unexpected keyword, which is the signature's shape; the contract it wants ("a content root supplied at runtime has no effect") is untested.

## Proposed roadmap

### 1. Falsify every gate on the runner's own command line

**What.** `server/tests/singles/test_gate_falsification.py`: per gate, copy the real input tree to a scratch dir, inject one named defect, run the **exact argv `run_content_checks.py` uses** as a subprocess, and assert a nonzero exit plus a finding naming file and field. Start where nothing exists — `content_neutrality_validator.py`, then `normalize_content_numbers.py --check`, the `pack_tool`/`mod_manifest`/`content_set_validator` CLI doors, then the fixture steps against a committed relative target.
**Why now.** The same failure shape has recurred in test form: libraries proven, entry points not. This is the single test that would have caught the most historical defects.
**Depends on.** Track I item 5 (gate falsifiability) for the neutrality fixture; Track I item 4 for a published step list.
**Scope.** Medium.
**Done when.** Deleting a gate from the runner, or making one exit 0 unconditionally, fails this module — and each case asserts the finding's text, not just the exit code.
**Risk.** A scratch copy that drifts from the real tree proves nothing; build every case from a real set, as `test_reference_coverage.py:33-38` does.

### 2. Give the empty modules a verdict, and make zero tests impossible

**What.** Delete or restore the fourteen 0-byte modules, correct `HANDOFF.md:29-83`, and make `run_tests.py` print a per-module test count and **exit 1 when a discovered module contributes zero**.
**Why now.** Discovery reports green while counting nothing, and the docs claim 163 tests that do not exist — the gates' failure mode, one layer up.
**Depends on.** Track C item 4 proposes the CI half; land both together or the build reddens on merge.
**Scope.** Small.
**Done when.** `run_tests.py --suite singles` fails on an empty module; the file list and `HANDOFF.md` agree with the tree.
**Risk.** Restoring a file from prose is guesswork; deleting with a recorded reason is honest unless a real checkout exists (`HANDOFF.md` names `C:\python\old\restart`).

> **Partially done (2026-09-19).** The fourteen 0-byte modules and `test.py` have a
> verdict; the `run_tests.py` half is still open.
>
> **Five were implemented**, with the reasons that made them worth keeping rather
> than deleting:
>
> | Module | What it now asserts |
> |---|---|
> | `test_crash_recovery` | A *new* `SaveManager` against a save directory a crash left mid-write: an orphaned temp file is never consulted, the last good save survives a crash during the next write, and the wreckage is not overwritten |
> | `test_launcher_scene` | `launcher_controller.gd`'s `$` node paths against `launcher.tscn`, the `Engine` metadata keys the launcher writes and `main_controller` reads, and `KeybindingsManager.ACTIONS` against `keybindings_default.json` |
> | `test_client_a11y_presets` | Which of the eleven capabilities the server honours (two) and which are client-only (nine), asserted exhaustively so a new server-side consumer cannot pass unnoticed |
> | `test_client_theme_packs` | The three shipped packs against the client's own validator, plus both directions of the `ui_strings`/`icon_tokens` inventory |
> | `test_transport_entry_points_are_importable` | `websockets` is declared in both dependency files and both server entry points import — the check that would have caught the missing dependency |
>
> **Ten were deleted as redundant**, each with a module that already covers the
> subject: `test_keybindings`, `test_onboarding`, `test_poc_accessibility_payload`
> and `test_client_theme_packs`'s sibling concerns → the two client modules above;
> `test_msgpack_transport`, `test_poc_tcp_roundtrip`, `test_poc_ws_server` →
> `test_transport_base`, `test_websocket_transport`, `test_transport_parity_snapshots`;
> `test_server_sqlite_persistence` → `test_sqlite_store`;
> `test_server_panel_payloads` → `test_status_and_room_payload_builders`;
> `test_server_bridge` → `test_websocket_transport`;
> `test_blight_heartbeat` → `test_field_and_fx_debug_commands` and
> `test_field_interaction_helpers`; and `server/test.py`, which was outside the
> `test_*.py` discovery pattern and collected by nothing.
>
> **Still open here.** `run_tests.py` prints no per-module count and exits 0 on an
> empty module, so the class of defect is still reachable — deleting today's
> fifteen does not prevent tomorrow's. `docs/archive/README.md` carries the
> correction to `HANDOFF.md` rather than editing the archived file, following that
> folder's own rule.
>
> **Found while doing it.** `run_editor_checks.py:69` globs `mud-world-editor/tests/*.gd`
> only, so **`client/**/*.gd` is syntax-checked by nothing** — not this gate, not
> the Python suite, not CI. The four client modules above read GDScript as text
> and can catch a contract drift, but a plain syntax error in the client ships
> green. `test_client_theme_packs` alone reads 20+ `.gd` files.

### 3. A save must survive its own reader

**What.** (a) A whole-state round-trip: roll a player forward (level, skills, ledger, titles, quests, a generated inventory instance, equipment, gold, position, housing), compare `to_dict()` before and after a save/load on a fresh server, normalising only documented volatile keys. (b) A committed fixture of each older format (v1/v2/v3 stamps over a real payload) loaded through `SaveManager.load()` rather than `migrate()` alone, asserting what each migration must preserve and that a v3 summon ledger comes back empty and stays empty after a re-save.
**Why now.** Two of three migrations are identity functions and no test has loaded a save the current writer did not produce; Track C item 2 needs the key inventory this enforces.
**Depends on.** Track C owns the write path and refusal semantics (its item 1); H owns the fixture and the test.
**Scope.** Medium.
**Done when.** The round-trip fails if one persisted field is dropped from `to_dict`; the version fixtures fail if `load()` stops calling `migrate()`.
**Risk.** A normalisation list that grows until the comparison is vacuous — keep it to keys the payload marks volatile, and assert its size.

### 4. An acceptance route per shipped set

**What.** Extend `test_content_set_first_ten_minutes.py` (fantasy, modern today) to `night_shift` and `orbital_salvage`: fresh character, one move, one action the set declares, one save/reload — asserting structure and command success, not authored wording.
**Why now.** `night_shift` reaches the suite only through `test_content_set_crime_vocabulary.py`; the content gate boots sets but the suite never asserts they stay playable between content edits.
**Depends on.** Track K's sequencing brings `night_shift` into contract currency (track-roadmaps/README.md:110) — write these after, or they encode ids that change.
**Scope.** Small.
**Done when.** Breaking a set's start room or first NPC fails exactly one test, naming the set.
**Risk.** Prose assertions make cosmetic content edits fail tests.

### 5. The suite must run anywhere the repository is checked out

**What.** Replace the five absolute paths at `test_p4_progression.py:419,428,434,456,475` with `tests/fixtures.py` constants, and add a tripwire over `server/tests/**` that fails on a `[A-Za-z]:\\` or `/home/` literal.
**Why now.** Those five are silently checkout-locked; a moved clone reports failures that are not defects — the interpreter-mismatch lesson repeated.
**Depends on.** Nothing. **Scope.** Small.
**Done when.** The suite passes from a second checkout path; a re-introduced absolute path fails the tripwire.
**Risk.** Low; allow paths under `tmp/`.

### 6. Snapshots must not be able to launder a regression

**What.** Move recording behind an explicit flag that skips the assertion and prints loudly; add a provenance header (source, revision, date) and a test that it matches the payload's shape.
**Why now.** `MUD_UPDATE_SNAPSHOTS=1` rewrites the 30 snapshots and then compares them to what it just wrote, and nothing in CI forbids the variable.
**Depends on.** Nothing. **Scope.** Small.
**Done when.** An update run cannot report those assertions as passing, and a snapshot recorded from a different payload shape is reported.
**Risk.** Re-record churn on legitimate output changes; the header makes that visible rather than silent.

### 7. Assertions must not be optional

**What.** A lint test over `server/tests/**` failing when a test method's only assertions sit inside a conditional that tests a fixture or command result, with an allowlist ratchet seeded from today's 162 sites so the count can fall but not rise.
**Why now.** 74 such guards in batch alone; each is an assertion that may never run, in exactly the place a deleted feature hides.
**Depends on.** Nothing; pairs with item 2. **Scope.** Small.
**Done when.** A new `if npc: self.assert...` fails the lint and the baseline only shrinks.
**Risk.** False positives on legitimate guards (`if os.name == "nt"`) — keep the rule narrow.

## Explicitly not proposing

- **A coverage threshold.** Refused in the deferral ledger (`work-tracks.md:455`); falsifiability is the measurable proxy worth having instead.
- **Deleting `tests/batch` on the strength of the empty batch-only-module set.** That measures imports and method-name overlap, not behaviour; the 280 tests pass and none has been shown wrong. Retiring it is a human judgement. Stop adding to it instead.
- **Rewriting or replacing `tests/current`.** One frozen campaign test; whether a staging lane should exist is a process call (Track K), not testing work.
- **Fixing the save write path so a crash cannot truncate a file.** Track C item 1 owns it; a test here would assert behaviour that does not exist yet.
- **A golden-output test over command responses.** It would freeze prose that Track F and `presentation.variant` deliberately vary.
- **Godot-side test infrastructure for the editor.** `mud-world-editor/**` is Track G's lane; `run_editor_checks.py` already gives it an entry point.
- **Re-recording snapshots to make anything green.** It discards the only cross-transport parity evidence the project has.
- **A fuzz/property layer over the command surface.** No primitive exists for it, and it would find exits and prose, not contracts.

## Risks

- **The harness becomes CI's slowest step.** Every case copies a set (~281 KB for fantasy) and the playability cases boot a world. Share one scratch copy per run and prefer one defect per gate over exhaustive families.
- **Item 2 reddens the build immediately** — fourteen failures on the first run; the file disposition must land in the same commit, and it is a human decision about 163 documented-but-absent tests.
- **Item 4 encodes content about to change** (the `night_shift` work), turning a playability guard into a change-detector for Track F.
- **Item 1 depends on Track I's gate surface.** If I's item 3 changes neutrality's id collection, or I's item 4 widens the runner, the fixtures and step list move under this harness; read the runner's declared steps rather than hard-coding them.
- **Injected defects leaking into the real tree.** Every case must copy first and write only under `tmp/`; a case that mutates content in place poisons every later test in the process.
- **Platform divergence.** Several save tests carry `PermissionError` retry loops for Windows file locks (`test_save_format.py:103-111`); new file-lock fixtures behave differently on the Linux CI job.

## Unknowns

- Whether `tests/current` was ever a staging lane or is simply a fourth folder from the migration; nothing in the tree says, and no file has been added since `e2c0638`.
- Whether the 163 tests `HANDOFF.md` attributes to the empty modules ever existed in the `C:\python\old\restart` checkout it references; in this repository's history those blobs are 0 bytes at every revision.
- Whether the editor checks can be made to fail on purpose. `run_editor_checks.py:69` globs 24 `.gd` scripts from `mud-world-editor/tests/` (`.github/workflows/editor-checks.yml` still says "seventeen"); I read the Python-probe and skip branches of `background_authoring_smoke.gd` but not enough assertion bodies to name one that has gone red.
- Whether the batch suite is behaviourally redundant: it imports no engine module singles does not, but that is not the same as no unique behaviour.
- Relative runtime of the three suites; I did not time them, so I cannot say what bounding the harness is worth. (`server-tests.yml` runs all three under coverage with no threshold; `editor-checks.yml` runs the editor and content checks and never the Python suite, so batch's only consumer is one workflow.)
