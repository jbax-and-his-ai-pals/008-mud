# Track J — Documentation

**Status:** proposed. Written as an evaluation of the documents against the code. Nothing here is implemented; no existing file was modified.

## Assessment

**State.** The lane owns `docs/**` minus `docs/design/`, plus `README.md` and `docs/reference/PLAYER_MANUAL.md` (`docs/plan/work-tracks.md:33,346-351`). It currently holds 53 markdown files, ~83,600 words, plus four `.ps1`-adjacent runner docs and `toolkit/README.md`, `server/mods/README.md`, `content_sets/fantasy_frontier/README.md`. The centre of gravity is by *audience imagined*, not by *state of the code*: there are track files for products that do not exist (`steam-packaging-track.md`, `mobile-track.md`), operator docs for a config file that is not in the repository (`server/config/server_config.json`, only the `.example.json` exists), and player docs for a game whose root README tells you to run a file that is not there. Only three documents were written or revised after the current architecture settled (`work-tracks.md`, `editor-content-source.md`, `handoff-2026-09-18-cross-theme-contracts.md`, all 2026-09-18); most of the rest are dated 2026-05-04 or 2026-09-13.

**Strongest.** `docs/archive/editor-content-source.md` is the best document in the lane and the template the rest should copy: it states a decision with a date, names the code it replaced (`toolkit/editor_export_shim.py`), shows the *evidence* for the decision (a table of canonical-vs-mirror counts, commit ids `67400cd`/`abd3175`), names its guardrails, and every claim checks out — `mud-world-editor/legacy-mirror` and `mud-world-editor/data` do not exist, `mud-world-editor/tests/content_source_check.gd` does. Second is `docs/reference/boot-warning-codes.md`, which is nearly accurate and is the only reference page in the tree. Third is the code itself: `run_content_checks.py`'s docstring, `run_tests.py`'s, `save_format.py`'s, `toolkit/README.md` and `server/mods/README.md` are better documentation than most of `docs/` and cost nothing to keep true.

**Weakest.** The two documents a newcomer reads first are the two most wrong, and both are wrong in the same way — they describe *a different repository*.

1. `README.md` (563 lines) is the entry point and it fails at step one. It says `python main.py`; there is no root `main.py`, and `server/main.py:18` requires `--content-set`. It lists `server/launch_from_latest_fixture.py` as the legacy operator flow; that file does not exist (grep of `server/*.py` finds no such module, and `run_content_checks.py:167` treats the path it would have needed as possibly-absent). It says PyTorch/Transformers are "not needed" because "`_load_model` returns early"; `server/engine/ai/` has been `archive/ai-conversation/` since 2026-09-18 (`work-tracks.md:531`), so the sentence explains an archived file's behaviour rather than the absence of one. Its testing section says `python -m unittest discover tests`; there is no root `tests/` — it is `server/tests/` and the runner is `run_tests.py`. Section "Godot + True MUD Commercialization Roadmap" is a five-phase plan whose Phase 1–4 are largely built, and only the top three lines admit it.
2. `docs/reference/PLAYER_MANUAL.md` is largely verified against content (six backgrounds match `content_sets/fantasy_frontier/data/player/backgrounds.json:5-128` exactly; the four friendship tiers match `rules/ruleset.json:412-427`; `Aurelian Surveyor`/`Aurelian Artificer`/`Hedge Healer`/`Pathfinder` all exist in `data/titles.json`) — but it instructs the player to type `titles`, which is not a registered command. The registered name is `title`, aliases `mytitle`/`wearth` (`server/engine/commands/advancement.py:88-93`); `titles` appears nowhere in `server/` outside the loader's `_load_json(..., "titles")` label. A player following §9 gets `Unknown command: titles`, and the manual lists it twice (`PLAYER_MANUAL.md:429`, and in the quick-reference table at `:621`). A second, softer miss: §11 says "Riverside's alchemist has an **alchemy kit** in the shop and sells empty glass vials". The alchemist (Kaelan, `data/npcs/villagers.json:594-638`) sells vials and potions; the alchemy kit is a free **room item** on the floor of `town:alchemist_interior` (`data/regions/town.json:537-541`). Nothing tells the player to `take alchemy kit`, which is what the alchemy recipes actually need (`crafting_manager.py:64-82`).

**Surprises.**

- **`docs/archive/roadmap-README-superseded.md`'s historical marking is still accurate but no longer sufficient.** Its supersession notice (lines 3–11) is correct and correctly points at `/ROADMAP.md`. What has rotted is the *list*: it marks `phases/`, `next-session.md`, `platform-architecture.md`, `world-editor-track.md`, `content-authoring-and-mod-publishing-guidelines.md`, `accessibility-track.md`, `adr/0000-template.md` as historical and leaves **20 of the 34 files in its own directory unmarked** — including the ones most likely to be mistaken for current: `server-operator-guide.md` (operator-facing, 13 stale absolute paths), `client-track.md`, `mobile-track.md`, `steam-packaging-track.md`, `engine-capability-track.md`, `theme-pack-spec-v1.md`, `editor-content-source.md`, `HANDOFF.md`.
- **`docs/archive/roadmap-README-superseded.md:23` is now factually wrong about `work-tracks.md`.** It says "seven tracks". `work-tracks.md` defines A–K, i.e. ten tracks plus an Archive group (its ownership table, lines 22–35).
- **`docs/plan/track-roadmaps/README.md:76-83` records a correction to `work-tracks.md` that is not in the file.** It states that the table "now says 'the primitives track E composes, wherever they live'" and that the document "states the rule directly: a file has an owner; a concern has an owner; where they disagree the concern wins." `work-tracks.md:25` still reads "the mechanics inside `server/engine/**`", and no such sentence exists. Track B and Track E still appear to own the same tree on the two lines that matter most.
- **The one document that documents the save system is wrong about the save system, in a way that matters.** `docs/reference/save-content-isolation-policy.md:11-14` says every save "carries a `schema_version` field" with a `"1.3"`-style value, and `:35-41` points migrations at `server/engine/server/save_migrations.py`. The engine writes `"save_format_version": SAVE_FORMAT_VERSION` as an **integer** (`server/engine/world/save_manager.py:80`, `save_format.py:32` — currently `4`), migrations live in `MIGRATIONS` inside `save_format.py`, and there is no `save_migrations.py` and no `persistence_migrations/` directory. The document is *right* about the policy (saves are content-set-bound — `save_manager.py:139-144` refuses a mismatched `content_set.id`) and *wrong* about every mechanism it names.
- **Four of the boot warning codes in `docs/reference/boot-warning-codes.md:49-52` do not exist.** The document lists `provider.weather.unresolved`, `provider.weather.not_found`, `provider.world_effects.unresolved`, `provider.world_effects.not_found`. The code emits `weather.provider.not_found`, `weather.provider.missing`, `world_effects.provider.not_found`, `world_effects.provider.missing` (`server/engine/server/headless/world_effects.py:81,90,107,116`). The word order is reversed. This one has teeth: the page is written for operators to paste codes into `startup_diagnostics.fail_on_warning_codes`, and a wrong code there fails silently — the policy simply never fires. The other 15 codes match.
- **There is no GMCP implementation, and there is an Accepted ADR for it plus a Mudlet example pack.** `docs/archive/adr/0002-gmcp-package-contract.md:1-4` is `Status: Accepted`; `docs/archive/mudlet-gmcp-README.md` gives six worked Lua handlers for `Char.Status`, `Room.Nearby`, `Asset.SVG` and so on. A grep of `server/` for `GMCP`/`gmcp`/`Core.Supports`/`Char.Status` returns **zero hits**. The ADR's own rollout notes list "Write Mudlet example scripts" as open (`docs/archive/HANDOFF.md:112`) — so the scripts exist and the protocol does not.
- **The "three gates" exist, are not described anywhere in `docs/`, and CI runs only one of them.** `run_tests.py`, `run_content_checks.py` (10 numbered steps, `run_content_checks.py:10-33`) and `run_editor_checks.py` are each well-documented *in their own docstrings*; `.github/workflows/server-tests.yml` runs unit tests only, `editor-checks.yml` runs the editor suite. Nothing runs `run_content_checks.py` in CI, so the content gates are a local habit. `README.md:36` mentions two of the three; `toolkit/README.md:30` mentions one.
- **No document reads `content_set.manifest.json`'s contract.** The three required data directories (`regions`, `items`, `npcs` — `content_set.py:20`), the eleven capability names (`content_set.py:21`), the required manifest strings (`content_set.py:2405`) and the required `rules/`, `presentation/`, `opening/` files are documented only in a 33-line JSON file and an 8-line list in `content_sets/fantasy_frontier/README.md:21-30` — a list that describes Fantasy Frontier's *contents*, not the shape a new set must satisfy, and whose counts are already wrong (it says 14 region files; `data/regions/` holds 25; it says 16 item files; there are 19).

---

## Document survey

Verdicts are against the code as it stands at `8c2fb0a` plus the uncommitted working tree. `docs/design/**` is Track K's lane and is listed once, by reference, not judged.

| Document | Verdict | Note |
|---|---|---|
| `README.md` | **contradicts code** | `python main.py` (no root `main.py`; `server/main.py:18` needs `--content-set`); `server/launch_from_latest_fixture.py` does not exist; `python -m unittest discover tests` (no root `tests/`); PyTorch note explains an archived module; ~340 lines of Phase 0–5 plan for work largely done. |
| `docs/reference/PLAYER_MANUAL.md` | **contradicts code** | `titles` is not a command (it is `title`, `advancement.py:88`); alchemy kit is a free room item, not shop stock. Everything else spot-checked — backgrounds, tiers, titles, command aliases, board gating — matches. |
| `docs/archive/roadmap-README-superseded.md` | current, incomplete | Supersession notice and "`/ROADMAP.md` wins" are right. "Seven tracks" (`:23`) is wrong (A–K). 20 sibling files left unmarked. |
| `docs/plan/work-tracks.md` | current | The map, and accurate about lanes, the archive, and the retired set. Its own ownership table disagrees with Track B's `May not` block (see Surprises). |
| `docs/plan/track-roadmaps/README.md` | **contradicts code** | Claims two corrections to `work-tracks.md`; neither is present in the file. |
| `docs/archive/editor-content-source.md` | current | Every claim verified, including the two "must stay gone" assertions. |
| `docs/archive/handoff-2026-09-18-cross-theme-contracts.md` | current | The one handoff that names the current initiative; its `py -3.12` invocation matches `run_tests.py`. |
| `docs/archive/deterministic-harness.md` | current | All three artifacts exist; `MUD_UPDATE_SNAPSHOTS` is read at `snapshot_assertions.py:57`. |
| `docs/reference/boot-warning-codes.md` | **contradicts code** | 4 of 19 codes are transposed (see Surprises). Presets section otherwise sound. |
| `docs/reference/save-content-isolation-policy.md` | **contradicts code** | `schema_version`/`"1.3"` → `save_format_version`/int; `save_migrations.py` and `persistence_migrations/` do not exist; `SqliteStore` has no version table (`persistence/sqlite_store.py:38-66`). Policy is right, mechanism is invented. |
| `docs/reference/mud-world-editor-export-contract.md` | **contradicts code** | Describes an export manifest and a one-way sync step retired by `editor-content-source.md`; the editor writes `content_sets/` directly. The `@dig`/`@edit` "live reload" half is real (`poc_server.py:1456-1518`). |
| `docs/archive/mudlet-gmcp-README.md` | **contradicts code** | Zero GMCP implementation in `server/`. Six example handlers for a protocol that does not exist. |
| `docs/reference/onboarding-tutorial-flow.md` | **contradicts code** | No `sample_world` content set, no `guide_npc`, no `tutorial_flags`; `pack_tool.py` has only `validate`/`export` subcommands (`pack_tool.py:168-180`), so `pack_tool.py init --template adventure` cannot run. `world.dispatch_event` exists (`world/world.py:493`) but nothing emits or listens for `tutorial_step`. |
| `docs/reference/support-workflow.md` | **contradicts code** | `python -m unittest discover tests.singles` is not the runner (and not the path); `version` is not a registered command; `server/VERSION` does not exist. The tier model itself is unverifiable but coherent. |
| `docs/reference/launch-checklist.md` | mostly current | Validator names are right; should point at `run_content_checks.py`, which is the actual single entry point. Operational/legal items are aspirational by nature. |
| `docs/reference/content-authoring-and-mod-publishing-guidelines.md` | partly current | The manifest field list matches `plugin_manager.py:48-74` and the mod roots match `run_content_checks.py:100`. But it is **publishing policy, not authoring**: it never shows a template, a region, a quest or a room. |
| `docs/reference/theme-pack-spec-v1.md` | current | Required fields match `pack_tool.py:56`; `docs/design/cross_theme_engine_contracts.md` is the live boundary doc. |
| `docs/reference/server-operator-guide.md` | **contradicts code** | 13 absolute paths on a different machine; `server/data/profiles/` does not exist (profiles live in `content_sets/<set>/data/profiles/`); `launch_from_latest_fixture.py` does not exist. Section 8's `server policy` and section 6's `gm auth` *are* real (`poc_server.py:285,298,404`). |
| `docs/archive/HANDOFF.md` | stale, self-labelled | Says so at line 3, then points at `next-session.md` as "current direction" — which is itself superseded. Its open items (msgpack skip, CI lint, Mudlet scripts) are still open. |
| `docs/archive/next-session.md`, `content-engine-roadmap.md`, `platform-architecture.md`, `archive-2026-09.md`, `phases/*`, `handoff-2026-05-04.md` | superseded, correctly marked | Each carries a supersession banner. `phases/` and the 05-04 handoff additionally carry 34 stale absolute paths. |
| `docs/archive/engine-capability-track.md` | superseded, unmarked | 3 absolute paths; lists 4 world modes, omitting `finite_adventure` (`feature_profile.py:10`). `work-tracks.md:486` claims its capability *targets* are "still the right list" — that claim is now partly false. |
| `docs/archive/client-track.md`, `mobile-track.md`, `accessibility-track.md`, `accessibility-qa-matrix.md`, `steam-packaging-track.md`, `multi-modal-1bit-brief.md`, `server-setup-wizard-track.md`, `server-feature-matrix.md`, `manual-poc-test-checklist.md`, `operator-profile-recipes.md`, `finite-adventure-contract.md`, `party-lifecycle-contract.md`, `persistent-shard-contract.md`, `world-editor-*.md`, `adr/*`, `evidence/*` | superseded or pre-release, mostly unmarked | Product surfaces that have not shipped. The four client/consumer track files carry 19 stale absolute paths between them. `world-editor-evaluation.md` and `world-editor-gap-matrix.md` are current for their own lane. |
| `docs/design/**` (4 files) | Track K | Not surveyed; `cross_theme_engine_contracts.md` and `duration-primitive.md` are the two a new contributor must read, and neither is reachable from `README.md`. |
| `toolkit/README.md`, `server/mods/README.md`, `content_sets/fantasy_frontier/README.md`, `content_sets/fantasy_frontier/data/profiles/README.md` | mostly current | `content_sets/fantasy_frontier/README.md` uses `.\.conda\python.exe` (no `.conda/` in the repo) and undercounts its own files; `toolkit/README.md`'s fixture example writes to `content_sets/fantasy_frontier/data_fixtures` (does not exist; the real root is `server/data_fixtures/`, `run_content_checks.py:156`). |

---

## Stale-path findings

52 lines across 8 markdown files reference `C:/python/old/restart/...`, plus 6 in `server/data_fixtures/LATEST_REFRESH.json`. Every one of the 36 distinct repo paths resolves to a file that **exists in this checkout at the same relative path** — this is a relocated checkout, not deleted code. So the fix is mechanical; the only judgement is what to do with the four documents that are superseded anyway.

| File | Count | Replacement |
|---|---|---|
| `docs/archive/phases/phase-4-ecosystem-hardening.md` | 15 | Relativize to repo root: `toolkit/data_integrity_validator.py`, `toolkit/reference_integrity_validator.py`, `run_content_checks.ps1`, `toolkit/pack_tool.py`, `toolkit/mod_manifest_validator.py`, `server/engine/core/plugin_manager.py`, `server/engine/server/realtime_assets.py`, `server/poc_server.py`, `server/tests/singles/*`, `docs/reference/theme-pack-spec-v1.md`, `docs/reference/content-authoring-and-mod-publishing-guidelines.md`. All exist. |
| `docs/archive/phases/phase-1-headless-server.md` | 11 | Relativize: `server/engine/server/headless_server.py`, `server/engine/server/feature_profile.py`, `server/poc_server.py`, `server/poc_ws_server.py`, `docs/archive/party-lifecycle-contract.md`, `docs/archive/persistent-shard-contract.md`, `server/tests/singles/test_party_lifecycle.py`, `test_party_policy_runtime.py`, `test_tcp_session_resume.py`, `test_ws_session_resume.py`, `test_transport_parity_snapshots.py`. All exist. |
| `docs/archive/phases/phase-0-baseline.md` | 8 | Relativize: `docs/archive/roadmap-README-superseded.md`, `docs/reference/platform-architecture.md` (×3), `docs/archive/engine-capability-track.md`, `docs/archive/finite-adventure-contract.md`, `docs/archive/party-lifecycle-contract.md`, `docs/archive/persistent-shard-contract.md`. All exist. |
| `docs/archive/accessibility-track.md` | 6 | Relativize: `docs/archive/accessibility-qa-matrix.md`, `client/scripts/ui/main_controller.gd` (×5). Both exist. |
| `docs/archive/mobile-track.md` | 4 | Relativize: `client/scenes/main.tscn`, `client/scripts/ui/main_controller.gd` (×3). Both exist. |
| `docs/archive/steam-packaging-track.md` | 3 | Relativize: `client/scripts/ui/launcher_controller.gd`, `client/scripts/ui/main_controller.gd`, `client/scripts/ui/keybindings_manager.gd`. All exist. |
| `docs/archive/engine-capability-track.md` | 3 | Relativize: `docs/archive/party-lifecycle-contract.md`, `docs/archive/persistent-shard-contract.md`, `docs/archive/finite-adventure-contract.md`. All exist. |
| `docs/archive/documentation-track.md` | 2 | Relativize: `docs/archive/documentation-information-architecture.md`, `docs/reference/server-operator-guide.md`. Both exist. |
| `server/data_fixtures/LATEST_REFRESH.json` | 6 | **Not a doc fix — a decision.** This is a machine-generated record of where a fixture was built (`schema` in `run_content_checks.py:150-169`). Its `fixture_selected_target` is what the fixture gates read, and because it points at another machine those gates **skip on every other checkout** — `run_content_checks.py:166-169` prints SKIP and passes. Either regenerate it locally (`toolkit/fixture_refresh.py`) or add a note to the gate docs that a fresh clone reports SKIP here by design. Do not hand-edit the paths: they are a factual record of a past run. |

Two more absolute-path families exist outside `docs/` and are **not** Track J's to change, listed so they are not lost: `docs/reference/server-operator-guide.md:10-17,50,56,68,74-75` uses `C:\python\old\restart\server\...` in backslash form (13 further references, counted separately above because the pattern differs), and `README.md`'s Phase text is prose-only. There are no `C:/python` references in `toolkit/**`, `server/**` or `mud-world-editor/**`.

---

## Proposed roadmap

### 1. `docs/AUTHORING_A_CONTENT_SET.md` — the missing document

**What.** One guide, ~1,200–1,800 words, that takes a person from an empty directory to a booting, gate-green content set, and states the engine/content boundary in the order a reader needs it rather than the order the code has it:

1. **The one idea** (~150 words): content declares, the engine resolves; the engine does not know what a barrel is. Two examples of the same declaration in two themes (`content_sets/fantasy_frontier` spell vs `content_sets/orbital_salvage` ability) so the point is shown, not asserted.
2. **The contract, enumerated from the code** (~400 words): `content_set.manifest.json`'s required strings (`content_set.py:2405`: `id`, `title`, `version`, `manifest_schema_version`, `engine_api_min`, `engine_api_max`); `paths.content_root`/`ruleset`/`presentation`/`opening`; `start`; the eleven capability names (`content_set.py:21`); the three required data directories `regions`, `items`, `npcs` (`content_set.py:20`); and what each capability turns on (`_CAPABILITY_SYSTEMS`, `run_content_checks.py`'s step list).
3. **The walkthrough** (~600 words): manifest → one region with two rooms → one item → one NPC → `rules/ruleset.json` → `presentation/default.json` → `opening/*.json`, each as a small verified JSON fragment, ending in `python server/launch_content_set.py --content-set <path> --dry-run` and then a real launch.
4. **How it gets checked** (~250 words): the three gates, what each one actually runs, and the difference between an error and a warning (`skill_audit` is warnings-only by design, `run_content_checks.py:129-131`).
5. **Adding the second capability** (~250 words): what changes when you declare `crafting`/`quests`/`combat`, and where the failure messages come from.

**Why now.** It is the only missing document that blocks a *person* rather than a feature, it is the document the engine's whole premise implies, and every fact it needs is already in the code and verified — so it can be written today without running ahead of the engine. Without it, "author a content set" means reading `content_set.py` (2,600+ lines) and `run_content_checks.py`.

**Depends on.** Nothing external. It must cite Track D's loader and Track B's contracts as they are, not as planned. If Track D is mid-refactor, cite commit + line and note the volatility.

**Scope.** Medium — one document, but every claim verified by hand.

**Done when.** A contributor with no prior context can follow it to a set that boots under `launch_content_set.py` and passes `run_content_checks.py`; every JSON fragment in the document is a truncation of a file that exists; every path and command in it has been executed once.

**Risk.** Drift the moment Track D changes the loader. Mitigate by keeping the *shapes* in one table with code citations so the diff is local — and by adding it to the doc set that a `content_set.py` change obliges someone to revisit.

### 2. `docs/DOCUMENT_INVENTORY.md` — one index with a verdict per file

**What.** A single table, generated once by hand and then maintained, listing all 53 files under `docs/` with: status (`current` / `superseded` / `contradicts code`), owner track, the last date it was verified against the code, and — for anything not current — one sentence naming what is wrong. It subsumes and corrects `docs/archive/roadmap-README-superseded.md`'s historical list.

**Why now.** The lane's central defect is not that documents are stale; it is that a reader has no way to tell which ones are. `docs/archive/roadmap-README-superseded.md` marks 7 of 34 files; this proposal marks all 53 and gives the verdict from this evaluation as its first draft. It is also the cheapest possible change: no document is rewritten, and every "contradicts code" line is already written in the survey above.

**Depends on.** Nothing. Should be written before items 3–7 so those have somewhere to land.

**Scope.** Small.

**Done when.** Every file under `docs/` appears; every `contradicts code` row names the specific wrong statement and the code that disagrees; the index says which track owns the fix for each row.

**Risk.** An index that is not maintained is a second stale document. Mitigate with one rule: a document may not be added to `docs/` without a row.

### 3. Root `README.md` — cut to something that is true

**What.** Rewrite to ~150 lines: what the project is (one Python engine, four content sets, a Godot client and editor), the verified setup path (`bootstrap.ps1`, `run_tests.py`, `run_content_checks.py`), the three launch forms that exist (`launch_content_set.py`, `poc_server.py --content-set`, `poc_ws_server.py --content-set`), the three gates, and a "where to go next" block pointing at the inventory, the authoring guide, `work-tracks.md` and `/ROADMAP.md`. Move the engine-systems catalogue, the modding examples and the Phase 0–5 commercialization text into `docs/reference/multi-modal-1bit-brief.md` and `content-engine-roadmap.md`, which already carry that framing and are marked historical.

**Why now.** It is line one of the project and it is wrong in the first code block. It is also the file most likely to be read by someone who never opens `docs/`.

**Depends on.** Item 1 (so the "where next" block points somewhere real).

**Scope.** Small–medium.

**Done when.** Every command in the README has been run once from a clean checkout; no sentence refers to a path that does not exist.

**Risk.** Losing the modding examples. Mitigate by moving them, not deleting them — `README.md:305-374` is currently the closest thing to an item/spell/region authoring snippet anywhere in the repo, and item 1 should absorb it.

### 4. `docs/reference/PLAYER_MANUAL.md` — a command-existence audit

**What.** Two passes. (a) Mechanical: extract every backticked token in the manual and every row of §18's table, and check each against `registered_commands` (the registry in `command_system.py:66`); fix the misses. The known miss is `titles` → `title` (`advancement.py:88`). (b) Behavioural: correct §11's alchemy paragraph to say the kit is on the floor of the alchemist's shop and must be taken, and add the one line that makes field alchemy reachable. Then record the manual's verification target *in the manual*: "verified against Fantasy Frontier 0.1.0 at commit X; re-verify with the command in §19."

**Why now.** The manual is the only player-facing document in the lane and its errors are the errors a player acts on. `titles` is a two-character fix with a user-visible effect.

**Depends on.** Nothing.

**Scope.** Small (mechanical pass) + small (behavioural pass).

**Done when.** Every command string in the manual resolves in the running game; the alchemy paragraph matches `data/regions/town.json:537-541`; the manual names its content-set version.

**Risk.** The manual is written as prose, not as a reference, and a heavy-handed audit could flatten it. Keep the voice; fix only what is false.

### 5. `docs/OPERATIONS.md` — replace the operator guide and fold in the runbook

**What.** A single operator document, ~400 lines, built from verified paths: bootstrap and interpreter policy (`bootstrap.ps1`, `.venv`, `run_*.ps1` refusing to fall back to PATH), the config model (`server/config/server_config.json`, which **does not exist in the repo** — only `server_config.example.json` and `server_config.static_lockeddown.example.json` do, and `poc_server.py:1616` defaults to the missing path), the feature-profile modes (`feature_profile.py:10`, all six values including `finite_adventure`), the entitlement/GM layer (`gm auth`/`gm status`/`gm deauth`, `server policy`, `poc_server.py:285-298`), startup diagnostics with the **corrected** warning codes, and a troubleshooting section keyed to what the reader will actually see. Supersedes `docs/reference/server-operator-guide.md` and absorbs §5–8 of `docs/reference/support-workflow.md`.

**Why now.** There is currently no operator document with correct paths, and the two candidates contradict each other about the config layout. This is the highest-value fix after the authoring guide because it is the document that turns "the server won't start" into a diagnosable state.

**Depends on.** Track I for the warning-code list (the four transposed codes are a finding filed against `world_effects.py`'s naming or the doc's — someone must decide which side is canonical before the reference page can be rewritten).

**Scope.** Medium.

**Done when.** Each documented launch command runs; each warning code listed is grep-able in `server/`; the config section states plainly that the master config is generated, not committed.

**Risk.** Documenting an operator layer that `/ROADMAP.md:2269-2271` explicitly says has "no audience yet" and should not be extended. Mitigate by keeping it a *reference for what exists*, not a guide to building on it, and by not expanding the entitlement surface.

### 6. `docs/reference/command-reference.md` — generated, not written

**What.** A single generated page listing every registered command: name, aliases, category, help text, and the capability or ruleset system that gates it. The data is already structured — `command` decorators populate `registered_commands` (`command_system.py:104-128`) — so this is a ~40-line script in `toolkit/` plus its output, regenerated by hand when commands change. It also answers the manual's audit mechanically.

**Why now.** The manual is the only command list and it is prose; `help` is per-session and gated; and `registered_commands` is the engine's actual vocabulary. This is the one reference document in this lane that cannot drift, because it is derived.

**Depends on.** Nothing, though it wants a home in the `run_content_checks`-adjacent habit rather than CI (adding a gate is Track I's call).

**Scope.** Small.

**Done when.** The page lists ≥90 commands with zero hand-written names; the manual's §18 table is checked against it.

**Risk.** It documents debug commands to players. Filter on `category != "debug"`, matching what `help` already does (`command_system.py:274-280`).

### 7. A dated staleness sweep of the tracks and phases

**What.** One pass over the eight files carrying the 52 absolute paths, doing exactly two things: replace each path with its repo-relative equivalent (the table above), and add or correct the one-line status banner at the top. No rewriting.

**Why now.** It is bounded, mechanical, and every replacement target exists in this checkout — verified. It removes the single loudest signal that these documents describe another machine, and a stale absolute path is worse than a stale date because it looks like an instruction.

**Depends on.** Item 2 (so the sweep does not need to re-decide which files are current).

**Scope.** Small.

**Done when.** `grep -r 'C:/python' docs/` returns nothing; each of the eight files opens with a status line consistent with the inventory.

**Risk.** Touching 8 files for cosmetics. Mitigate by doing the banner work at the same time, so each file is edited once.

---

## Explicitly not proposing

- **Rewriting `docs/design/**`.** Track K's lane (`work-tracks.md:374-378`). `cross_theme_engine_contracts.md` and `duration-primitive.md` are flagged in the survey only so Track J's index can link to them.
- **Documenting the duration primitive.** `docs/design/duration-primitive.md:3` says "proposed. Nothing here is implemented." A doc that runs ahead of the engine is a bug report filed against the future (`work-tracks.md:356-358`).
- **Adding a content-neutrality explainer page.** The explanation already exists as `cross_theme_engine_contracts.md` §"Layering rule" §"Contract model", and duplicating it in `docs/` is how two documents start disagreeing. Item 1 should *link* to it and quote the one-line rule.
- **Deleting the superseded files.** Deletion is reversible only through `git log`, they are already correctly bannered in most cases, and `work-tracks.md:492-493` still uses several of them as track detail. The archive directory exists for this reason.
- **A CONTRIBUTING or code-style guide.** No such convention is enforced anywhere in the repo; inventing one adds a document nobody can be held to. The five rules that do exist are in `work-tracks.md` §"Shared zones".
- **Documenting the `@dig`/`@edit` live-authoring protocol as a public surface.** It is real but gated on `creator_sdk.authoring` plus a GM session (`poc_server.py:1537-1549`), and `/ROADMAP.md:2269-2271` says not to extend that layer. The export-contract page should be demoted to a note in the editor lane's docs rather than expanded.
- **A CI job that runs `run_content_checks.py`.** The absence is a real finding — content gates never run in CI (`.github/workflows/server-tests.yml` runs only unittest) — but workflow files are Track C's lane (`work-tracks.md:26`) and gate scope is Track I's. Filed as a finding; not ours to implement.
- **Fixing `work-tracks.md`'s B/E ownership ambiguity myself.** The file is Track K's (`work-tracks.md:377`). Reported as a finding with the two conflicting lines.
- **A troubleshooting guide separate from item 5.** There is no operator runbook today, so a standalone troubleshooting page would be its only content. Fold it into `docs/OPERATIONS.md`; split it later if it outgrows the parent.

---

## Risks

1. **The verified-fact cost is the whole cost.** Every row in the survey needed a file open. Item 1 in particular can only be written honestly by executing each command in it. If this lane is run at conversation speed rather than verification speed, it will produce another `save-content-isolation-policy.md` — confidently detailed, mechanically wrong — which is worse than the gap it fills.
2. **Documentation cannot fix the code it describes.** The `titles` defect is a one-word doc fix on the surface, but the underlying question — should `titles` also be a command? — is Track E's, and the four transposed warning codes are a naming decision that belongs to whoever owns `world_effects.py`. If those findings are filed and not picked up, the manual stays wrong by decision, and this roadmap will look like it failed.
3. **The lane does not own its own acceptance test.** Nothing in CI runs `run_content_checks.py` and nothing checks that documented commands exist. Without item 6 (which makes at least the command vocabulary derived), doc accuracy is a habit with no tripwire.
4. **`README.md` is load-bearing for things that are not documentation.** Its modding snippets and its Phase plan are the only place several ideas are written down. Cut without moving them and the loss is real.
5. **The inventory rots first.** Item 2 is the cheapest and the least likely to be maintained; if it goes stale it becomes evidence that the whole approach does not work.
6. **Snapshot semantics are ambiguous.** The client/runtime tracks describe a Steam/mobile product that has no audience; documenting it (or not) will be second-guessed either way.

---

## Unknowns

1. **Is a "current" statement allowed to be an aspiration?** `docs/archive/roadmap-README-superseded.md:3` marks the phase order historical while `work-tracks.md:492-493` calls the same documents "current as track detail". Which of the two governs when they disagree is not written down anywhere. (Note: this directory was being written concurrently while I read it — the survey records file states as of the reads above, and `docs/archive/roadmap-README-superseded.md` had an uncommitted one-line change of unknown authorship in the working tree.)
2. **Should `titles` exist?** The manual's author expected it; `advancement.py:14-17` documents the opposite decision for `journal`. Only Track E can resolve which side the fix is on.
3. **Are `modern_capsule`, `night_shift` and `orbital_salvage` examples or tests?** It changes whether item 1 points a new author at them. `docs/plan/track-roadmaps/README.md:110` implies `night_shift` is thin and needs contract currency; the design doc calls `orbital_salvage` a proving slice. I could not find a statement of intent for `modern_capsule` at all.
4. **Who owns the 52 stale paths?** They are in files Track J's lane covers, but Track G owns `world-editor-*` and Track K owns the phase ordering. Whether a status-banner correction is a doc edit or a lane violation is unanswered.
5. **Is `docs/` for players, contributors, or maintainers?** `README.md` mixes all three, the manual is player-facing, `docs/reference/` is operator-facing, and `docs/reference/onboarding-tutorial-flow.md` says it is for "the Steam and mobile releases". The lane's own definition ("the reader-facing surface", `work-tracks.md:342`) does not resolve it, and the answer decides whether item 2 should split the tree by audience.
6. **Is the committed `LATEST_REFRESH.json` a bug or a convenience?** `run_content_checks.py:150-155` says its absence "is not a content failure"; the file is present and points at another machine. Whether the right fix is regenerating it, deleting it, or documenting the skip is a Track I decision I could not make from the documents.
7. **What is the correct track count?** `docs/archive/roadmap-README-superseded.md:23` says seven; `work-tracks.md` defines A–K. I can state the file's content but not which number was intended.
8. **Has `docs/reference/PLAYER_MANUAL.md` ever been verified against a running game?** `ROADMAP.md:277,293` record a revision under P1, but nothing states the method, so I cannot tell whether the `titles` line is a regression or has been wrong since it was written.
9. **Does any other document contain a claim I did not open?** I read all 53 files under `docs/` and 5 READMEs outside it. `docs/design/**` (4 files, ~70KB) I did not read beyond `cross_theme_engine_contracts.md`'s first 110 lines, and it is the likeliest place for a claim that contradicts the code.
