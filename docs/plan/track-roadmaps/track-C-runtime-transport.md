# Track C - Runtime & Transport

**Status:** proposed. An evaluation of the process, not the game. Nothing here is implemented.

## Assessment

**State.** Four rings. `server/poc_server.py` (1695 lines) is the hub: config resolution, the
operator/GM ladder, policy payloads, entitlements, the session-writer map. `poc_ws_server.py` (815)
wraps it, holding a `JsonLineMudServer` as `self.core` (poc_ws_server.py:39). `engine/server/headless/**`
(10 modules, ~3.6k lines) holds session, world and tick logic; `engine/server/transport/` is 115 lines
total. Persistence is two stacks that never meet: the JSON save stack (`save_manager.py` 250,
`save_format.py` 152, `player/persistence.py` 340) and an sqlite store (201) nothing reads.

**Strongest.** `save_format.py`: one version, one meaning; a future-stamped file refused rather than
half-read; every version gap recorded even when the migration is a no-op; and `test_save_format.py:44-51`
pins that shape so a bump without an entry fails. The transport parity snapshots (646 lines) and
`run_tests.py`'s refusal to run without its three dependencies (exit 2, not 40 phantom failures) are the
other two pieces behaving like adults.

**Weakest.** The write path. `save_manager.py:94-95` is `os.makedirs`, `open(save_path, 'w')`,
`json.dump(..., default=str)`. Verified:

1. **Truncate in place.** `os.replace`, `mkstemp`, `NamedTemporaryFile`, `fsync`, `shutil.copy`, `.bak`:
   zero hits in `server/`. The one copy of a character is truncated the moment `save` runs, so a kill, a
   full disk or an exception mid-dump leaves partial JSON in its place.
2. **`default=str` hides it.** A value the encoder cannot represent is stringified instead of failing the
   save, so "World state saved" does not mean the file reloads as the same types - the int-to-float
   incident's shape, one layer down.
3. **Nothing is written until a player types `save`** (`commands/system.py:39-51`). No autosave, no
   save-to-JSON at shutdown: the shutdown flush (`headless/lifecycle.py:74-81`) writes to `SqliteStore`,
   which `poc_server.py:54` builds with `db_path=":memory:"` and discards at exit.

The irreversible chain: `save_handler` defaults to `game.current_save_file` (`system.py:45`), and a
failed `load` neither clears that name nor changes game state (`system.py:65-90`). So load a corrupt
save - the world is silently replaced by a fresh one (`save_manager.py:228` catches everything and calls
`initialize_new_world()`) - then type `save`, and the unreadable file is overwritten by a brand-new
adventurer. The old character is gone and nothing says which file to look at.

Migrations have no end-to-end test: `test_save_manager_full.py` never mentions `save_format_version` or
`migrate`, and the one test covering the v3-to-v4 flag (`test_save_format.py:212`) sets
`STALE_SUMMONS_KEY` by hand and calls `Player.from_dict` directly, bypassing both `migrate()` and
`SaveManager.load()`. That a real v1/v2/v3 file loads through the real reader is untested.

**Surprises.**

- **Not two servers, but one duplicated ladder.** 1580 vs 773 non-blank non-comment lines; 395 identical
  (constructor pass-through, `main()`, broadcast/cleanup helpers). The WS class defines 11 functions of
  its own, one of them `_handle_websocket_client` (poc_ws_server.py:119-692) - a **575-line single
  method** mirroring the ladder inlined at poc_server.py:1050-1395 (GM auth, server policy, profile
  list/apply, world-effects, three audits, shard mode, authoring translation). Both call
  `execute_command_envelope` (poc_server.py:1395, poc_ws_server.py:665). Command execution is shared;
  routing is not, and the parity test drives the WS handler with a fake websocket, never `websockets.serve`.
- **The world clock only runs while someone is logged in.** `poc_server.py:780` claims the background tick
  advances the world "even while clients are idle"; lines 790-791 `continue` when nothing is connected, and
  `TimeManager.update(dt)` accumulates dt (0.1s per tick, time_manager.py:69-84) rather than reading the
  clock, so time neither advances nor catches up. `WallClock.advance` is a no-op (clock.py:35). Day, season
  and `respawn_days` are frozen with zero clients.
- **A persistence subsystem is write-only.** `SqliteStore.load_entity`, `list_entities`,
  `load_world_cells` (sqlite_store.py:172-215) have no callers anywhere in the repo - not `server/`, not
  `toolkit/`, not `mud-world-editor/`. `test_server_sqlite_persistence.py` is 0 bytes.
- **Five 0-byte test modules** (`test_msgpack_transport`, `test_poc_ws_server`, `test_server_bridge`,
  `test_server_panel_payloads`, `test_server_sqlite_persistence`) plus `server/test.py`. They import
  cleanly, contribute nothing, and CI cannot tell them from real files.
- **`websockets` is in no requirements file**, so `poc_ws_server.py:92` raises at startup in the pinned dev
  and CI environment; nothing tests that entry point.
- **Three content-check steps can never fail on CI.** `data_fixtures/LATEST_REFRESH.json` records
  `fixture_selected_target` as `C:\python\old\restart\...`, so `run_content_checks.py:166-177` prints SKIP
  and line 184 prints "All content checks passed." (Track I's file - reported, not proposed.)
- **NPC `properties` are never persisted** (`npc.py:236-246` writes no `properties`;
  `npc_factory.py:195-197` refills them from the template), so `is_escort_target` / `escort_quest_id`
  (`core/quests/manager.py:528-529`) and summon flags evaporate on load. NPC *inventory* does persist
  (`test_vendor_stock_persistence.py:44`), which is why this stayed hidden.

## Proposed roadmap

### 1. Make the save survive a crash, and stop a failed load from being overwritten

**What.** Write `.tmp`, flush and `fsync`, `os.replace` onto the target, keep the previous file as `.bak`.
In `SaveManager.load`, return a distinct refusal for a bad version, a content-set mismatch or unreadable
JSON, and clear `game.current_save_file` so the next `save` needs an explicit name.
**Why now.** The only irreversible defect in the lane, holding the only copy of a character.
**Depends on.** Nothing; Track H for the falsification test.
**Scope.** small.
**Done when.** A save whose `json.dump` raises (monkeypatched) leaves the previous file byte-identical
with the `.bak` present, and loading a deliberately corrupted file then running `save` with no argument
leaves those bytes unchanged and says why.
**Risk.** `os.replace` on Windows fails while another handle holds the target - the suite already retries
`PermissionError` on save files (`test_save_format.py:103-111`). Green on Linux, broken locally, is the
likely failure; verify on Windows.

### 2. Declare which save keys are restored, and make a dishonest key fail

**What.** In `save_format.py`, declare keys that round-trip, keys that are metadata by design, and keys
deliberately dropped, and check what the save wrote against them. First catch: `NPC.to_dict` writes no
`properties`, so persisted and restored sets silently differ.
**Why now.** The summon ledger needed a migration and a held-then-dropped flag to stay honest, found by
accident. This is the cheap way to stop `default=str` being lethal.
**Depends on.** Track H to falsify it. Track E owns `npcs/`; the `properties` gap is a handoff.
**Scope.** small.
**Done when.** Removing a key from the "restored" set makes the check name that key and fail, and it has
been shown failing on the NPC `properties` gap before the gap is closed.
**Risk.** Hand-maintained names become a second reader that disagrees with the first (Track I's stated
failure mode). Keep it as names checked against observed behaviour.

### 3. Decide whether world time passes with nobody connected

**What.** Either advance the shared clock by wall-clock delta when the tick loop finds no connected
session, or declare in the contract that world time is play-time and fix the docstrings at
`poc_server.py:780` and `poc_ws_server.py:66`.
**Why now.** The next primitive is world-anchored time evaluated on read against absolute numbers, and
the clock producing them freezes when the server is idle. Decide before `work` lands, not after.
**Depends on.** Track K - a design call, not a mechanics one.
**Scope.** small.
**Done when.** A test advances a simulated zero-session gap and asserts the world day moved, or the
docstrings and the duration doc plainly say it does not.
**Risk.** Advancing offline changes `respawn_days` and `jailed_until` for existing saves and can flip a
season between sessions - content feel, wanting K's sign-off.

### 4. Point CI at the real runner, add a Windows job, fail on an empty test module

**What.** Run `python run_tests.py --suite all` in `server-tests.yml` instead of hand-rolled
`coverage run` steps; add a `windows-latest` job on the same command; fail the job when a file matching
`tests/**/test_*.py` contains no `def test_`.
**Why now.** CI is Linux-only while the dev path is Windows (`LOCALAPPDATA` save roots, `.ps1` runners,
that permission retry loop), and five empty modules pass silently today.
**Depends on.** Nothing; Track H may prefer the empty-module rule inside `run_tests.py`.
**Scope.** small.
**Done when.** Emptying a test module fails the job, a Windows job exists and passes, and both workflows
gate on the same command.
**Risk.** Doubles CI wall time; keep the Windows job to the server suites.

### 5. Finish or delete the sqlite persistence half

**What.** The entity and world-cell tables are written, never read. Either wire a real restore (session
resume across a restart, using the `db_path` the entry points already accept) or delete that half.
**Why now.** `LifecycleMixin.shutdown()` persists every active session before closing and flushes an
in-memory database. That is 200 lines of reassurance with no reader, and it is what a future session-resume
feature will assume works.
**Depends on.** Track K if the answer is delete. `RealtimeAssetService` uses its own tables, unaffected.
**Scope.** medium to wire, small to delete.
**Done when.** Either a test stops the server and restores a player from the sqlite file, or
`load_entity`/`list_entities`/`load_world_cells` and the empty test module are gone.
**Risk.** Deleting a path someone is mid-way through using - check `git log` for intent. Wiring it is a
behaviour change, not a config flip, since both entry points pass `:memory:`.

### 6. Extract the command ladder so there is one of it

**What.** Move the pre-route ladder into one transport-agnostic router returning "handled, with these
events" or "not mine, run the command". Both handlers read one list.
**Why now.** Nine inline branches are mirrored by the same nine in a 575-line method; a rule added to one
side only is a silent behavioural difference between transports that the parity tests cannot see.
**Depends on.** The parity snapshots green before and after, unchanged.
**Scope.** medium.
**Done when.** A tenth pre-route rule needs one file; `git diff --stat` on the two entry points is
net-negative for duplicate lines; `test_transport_parity_snapshots.py` and `test_poc_policy_commands.py`
pass untouched.
**Risk.** A 575-line extraction with no static checking - one branch behind the snapshots, or not at all.

### 7. Sweep the junk drawer, and pin what the entry points need

**What.** (a) Pin `websockets` in `requirements*` and warn at boot when the WS transport is chosen without
it, instead of raising at `poc_ws_server.py:92`. (b) Add a strict config read: `load_server_config` returns
`{}` for a missing file *and* for one that exists but is malformed (`server_config.py:33-41`), so a typo'd
JSON boots on defaults. Keep the tolerant function (pinned by `test_server_config_full.py:22-27`) and add
one that tells "absent" from "unparseable" and says which. (c) Move the root scripts to `server/tools/`:
delete `test.py` (0 bytes); keep `run_playtest_lab.py` and `setup_wizard_cli.py` (documented at
`docs/reference/server-operator-guide.md:50`); fold `run_coverage.ps1` and `run_snapshot_checks.ps1` into one local
runner - every module the latter names is under `tests/singles`, which CI already runs in full, so it is
convenience, not a gate.
**Why now.** The lane boundary is invisible where a newcomer looks first, and `work-tracks.md:514-517`
already flags it.
**Depends on.** Nothing.
**Scope.** small.
**Done when.** `git ls-files server` at the root lists only the entry points and `requirements*`;
`python -m unittest discover -s tests/singles` still passes; a malformed config is reported at startup.
**Risk.** Low, except that moving scripts breaks muscle memory and any doc naming a path - grep the docs
first and keep one obvious path working.

## Explicitly not proposing

- **Fixing `run_content_checks.py`'s always-SKIP fixture steps** - Track I owns that runner; reported above.
- **Persisting NPC `properties`** - Track E owns `npcs/`; item 2 exists to make the gap fail loudly.
- **What `work` means, or which content gets a timer** - Track D's and Track K's.
- **A third transport, an HTTP admin API, or leaving JSON saves** - the JSON save's problem is durability,
  not format.
- **A performance or load track** - `work-tracks.md:501-503` already deferred it until a content set has
  enough timers to matter; adding one now invents the workload.
- **A coverage threshold** - the empty test modules are the finding; item 4 gates those.
- **Rewriting the WS handler beyond the ladder** - payloads and command execution are already shared, so a
  broader rewrite is regression surface with no contract behind it.

## Risks

- **Item 1 on Windows.** Defender and file locks are why the save tests already retry `PermissionError`.
- **Item 2 becoming a second reader.** A manifest nobody regenerates agrees with itself; it is only worth
  having if a test proves it can fail.
- **Item 3 changing existing saves.** Advance-on-idle silently alters `respawn_days`, `jailed_until` and
  seasons for characters written before it.
- **Item 4 green by omission.** A Windows job running a subset becomes the decoration it was meant to
  remove; `run_tests.py` must be the single entry point in both workflows.
- **Item 6 half-finished.** A large unverified refactor of the busiest method in the lane is the likeliest
  item to stall, and a half-extracted ladder is worse than the duplication.
- **Sequencing.** Items 1 and 2 touch the same files as each other and as any Track D change to `world/`.

## Unknowns

- **I could not run any gate.** This interpreter is Python 3.14.7 with none of `yaml`, `pygame`, `msgpack`,
  `websockets` or `coverage`, so `run_tests.py` would exit 2. Every claim above is read from code,
  including the crash-during-save behaviour, inferred from the absence of any atomic-write primitive plus
  the single truncating `open`.
- Does anything in `content_sets/**` or `mud-world-editor/` write to a save directory? A second writer
  would change item 1's design.
- Was the sqlite half built for a planned feature or abandoned? `git log` would say; I did not check.
- Is `db_path=":memory:"` at `poc_server.py:54` deliberate? The class accepts `--asset-db` for assets but
  exposes no knob for the entity database.
- What should happen when a save's `content_set.id` is empty? The guard at `save_manager.py:141` only fires
  on a truthy id; validating the id itself is Track D's.
- How much of the ~4180 singles exercises the save stack end to end? Several save tests are named after
  systems, so I could not size real coverage without running the suite.
