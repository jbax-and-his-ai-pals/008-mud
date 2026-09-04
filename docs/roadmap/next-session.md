# Historical Next Session Log

> **Superseded as the active plan.** This file is a detailed implementation log from the earlier platform-first roadmap. The active direction is the [Content Engine Roadmap](content-engine-roadmap.md): establish a content-set package boundary, extract Fantasy Frontier as the reference game, and use a small non-fantasy set to prove the engine abstraction. Retain the material below for implementation history and useful technical notes; do not use its ordering or completion claims to set new priorities.


## Current State

- Transport parity and protocol snapshots are stable for TCP/WS JSON/WS MessagePack.
- Entitlement checks are enforced at:
  - transport/operator envelope boundaries, and
  - core command execution (`HeadlessServer` authz hook).
- Operator catalog derives requirement metadata from command decorators where possible.
- Session authz payload detail level is now config-driven (`full` or `minimal`).
- `server.data_root` + CLI `--data-root` are wired for TCP/WS boot against alternate data trees.
- `world_bootstrap.starter_items` is now config-driven; missing starter templates are warning-only.
- Character creation is client/session-driven by default; sessions must issue `char create <name>` before gameplay commands.
- Transport handshake coverage now explicitly tests character-creation gating on both TCP and WS (`test_transport_character_creation_gate`).
- Command envelope contract is now transport-consistent: `client_capabilities` is optional (defaults to `{}` server-side); when provided, it must be an object.
- Added constructor/policy contract matrix tests across `HeadlessServer`, TCP, and WS (`test_server_constructor_contract_matrix`) to catch drift in entitlement defaults and character-creation policy surfaces.
- Boot warnings now have a structured surface (`boot_warnings_structured`) with code/source/severity/message and dedupe semantics; profile apply uses the same centralized warning reset/seed path as startup.
- `KnowledgeManager` topic-load warnings now flow into structured boot warnings (`content.topics.missing`, `content.topics.load_error`) in headless/server runtime, replacing ad-hoc stdout prints.
- Spell-definition loading is now idempotent per load cycle (registry reset before load) and duplicate spell IDs emit a single summary warning instead of per-ID spam; `definition_load_stats.spell_registry` captures `files_loaded`, `spells_loaded`, and `overwrites`.
- Definition loader now aggregates high-volume template warnings into concise summaries (duplicate IDs, missing required fields) and stores per-domain counts under `definition_load_stats.item_templates` / `definition_load_stats.npc_templates`.
- Fixture refresh flow exists via `toolkit/fixture_refresh.py` with fallback path selection written to `server/data_fixtures/LATEST_REFRESH.json`.
- `server/launch_from_latest_fixture.py` now warns when `fixture_selected_target` differs from `fixture_primary_target`; optional `--strict-primary-alias` enforces hard-fail behavior for stricter boot environments.
- Priority lock: harden server + client + existing fantasy world data before Steam prep, mobile push, or new sample content.
- `_build_nearby_payload` now uses the session player's location directly instead of the legacy single-player `world.current_region_id` accessor (which is always `None` in headless multi-session mode).
- Provider resolution: double-warning bug fixed — when a custom `provider_id` is configured but not found, only the specific "id not found" warning fires, not the generic "no provider installed" one.
- `evict_stale_sessions` is now called in the WS server `finally` block, matching TCP server parity.
- Profile files: `static_world` and `locked_static_no_combat` are differentiated via `_description` fields explaining intended use.
- Client: `test_glyph_001` removed from all defaults in `main_controller.gd` and `main.tscn`; authoring commands now use the current panel state as their asset ID default.
- Test suite: policy regression tests (`test_readonly_policy`, `test_no_combat_policy`, `test_feature_profile`) now create a character in setUp, fixing pre-existing failures caused by missing player context.
- `run_snapshot_checks.ps1` expanded: now includes `test_mod_manifest_validator` and `test_ws_session_resume` in the policy regression stage.
- Added `tests.singles.test_knowledge_manager_warnings` for missing/invalid/valid `topics.json` warning behavior.
- Added operator audit command `audit boot-warnings` (TCP/WS) with entitlement gate `operator.audit.boot_warnings`, returning structured warning counts and code breakdown.
- Definition-load warning seeding now includes normalized content warning codes for spells/items/npcs (`duplicate_ids`, `invalid_*`, `file_errors`, `dir_missing`), not just spell duplicate IDs.
- Startup diagnostics snapshot is now included in both TCP/WS `hello` payloads and `server_policy` operator payloads, including warning code counts, boot warning fail-code policy, and `LATEST_REFRESH.json` marker metadata when present.
- Config now supports strict boot warning policy via `startup_diagnostics.fail_on_warning_codes`; if any listed code is present at boot, server startup fails fast.
- Added warning code reference doc with production presets: `docs/reference/boot-warning-codes.md`.
- Godot client shell now consumes `startup_diagnostics` and `audit_result` events, surfaces boot-warning audit summaries in-log, and annotates server policy warnings with diagnostics counts.
- Godot client shell now has a dedicated `Startup Diagnostics` panel section (summary + detail) populated from TCP/WS hello and server-policy payloads.
- Godot client shell now has a first usable finite-adventure control/report surface:
  - a dedicated `Adventure` panel renders run state, summary state, and latest report artifact,
  - quick actions now cover `adventure start`, `status`, `abandon`, `checkpoint`, `restore`, `reset`, `replay`, and summary export requests (`text|markdown|json`),
  - the shell now understands `finite_adventure_catalog` and can discover authored campaigns instead of relying only on remembered IDs,
  - the adventure row now includes a campaign picker plus a manual refresh/list action,
  - a lightweight campaign-id override field now allows non-default `adventure start <campaign_id>` flows from the shell,
  - the adventure panel now surfaces selected campaign detail and a first active-objective view derived from live quest payloads,
  - finite-adventure lifecycle commands now also emit fresh `quests` payloads so objective/journal state updates immediately on start, restore, abandon, reset, and replay,
  - run-state, checkpoint, summary, and report updates now emit clearer client-log cues during manual testing,
  - report preview formatting now renders markdown/json exports in a code-style block for easier manual inspection during playtests.
- Added transport diagnostics parity test coverage: `tests.singles.test_transport_startup_diagnostics_parity` validates hello contract fields for both TCP and WS.
- WS session-resume lifecycle is hardened: successful `resume_session` now re-emits `auth_state`, `server_policy`, and `lock_state` for the resumed session so client context is refreshed immediately.
- TCP session-resume parity is now implemented with the same contract as WS (`session_resumed` + `auth_state` + `server_policy` + `lock_state`) and ephemeral-session cleanup.
- Multi-session location hardening pass applied to debug/authoring command handlers:
  - `spawnstation`, `spawn`, and `testrefactor` now resolve room/region from the invoking session `player` context instead of global `world.current_*`.
  - Added regression coverage in `tests.singles.test_debug_command_location_context`.
- Debug world command hardening now extends to `teleport`, `genregion`, `close portal`, and `census`:
  - these commands now operate on invoking session player context (no direct writes to `world.player` / global cursor assumptions).
  - added two-session regression coverage in `tests.singles.test_debug_world_location_context`.
- Gambling follow-up command hardening now covers multi-session execution:
  - `hit`, `stand`, and `guess` now use the invoking session `player` from command context instead of legacy `world.player`,
  - regression coverage added in `tests.singles.test_gambling_session_context`.
- Room-context command hardening now reaches more interaction flows:
  - explicit world helpers now resolve NPCs/items from a provided session player location instead of the legacy global room cursor,
  - `rules`, `bet`, `trade`, `repair`, `repaircost`, `talk`/`ask` target resolution, `follow`, `guide`, `look`, `attack`, spell target resolution, `open`/`close`/`put`, `gather`, `pull`/`pick`, `use`, `give`, `get ... from <container>`, and movement commands now use session-player room context,
  - session-scoped read paths now also apply to `refresh`, `skills`, `weather`, and shared room-description rendering,
  - world-layer helpers (`look`, `change_room`, `attempt_pick_lock_direction`, `get_current_room*`, `find_*_in_room`) now accept explicit players so callers stop inheriting the legacy singleton by accident,
  - crafting station discovery is now player-aware and the region spawner now considers all active player regions instead of only the legacy active cursor region,
  - helper/presentation systems now follow the same trend: AI ambient context gathering uses resolved player-aware room helpers, panel-content hostile/friendly lists now use explicit player room context, and single-player auto-travel now routes movement through the same explicit player-aware world API,
  - persistence/UI cleanup continued: save-load recovery now validates and repairs the loaded player's location directly instead of relying on no-op global cursor setters, renderer/inventory overlay plumbing now falls back to `world.resolve_reference_player()` instead of hard-requiring `world.player`, and minimap rendering now does the same when no explicit player is passed,
  - world bootstrap/spawn plumbing is cleaner: `initialize_new_world()` now records canonical bootstrap start location, session-side character creation uses that bootstrap start for both spawn and respawn defaults, and spawner fallback activation now uses resolved loaded-player context instead of the legacy singleton binding,
  - NPC/runtime helper cleanup now reaches deeper into the simulation layer: world exposes shared `get_player_by_id` / `get_players_in_room` / `get_viewer_for_npc` helpers, summoned-minion owner resolution no longer depends on `world.player`, minion follow/assist logic now resolves the true owner from loaded players, and NPC movement/combat visibility checks now require both matching region and room instead of room ID alone,
  - multiplayer NPC AI is now less “single-viewer” and more truly room-aware: proactive hostile scans consider all co-located players, healer support logic can heal other players in the room instead of only the passed viewer, summon kill credit routes to the actual owner even if another player is the current viewer, and support-action text routing now uses the same shared NPC viewer helper,
  - added a broader tick-level multiplayer simulation slice in `tests.singles.test_multiplayer_simulation_ticks` so hostile targeting, healer support, and summon kill credit are now validated through `world.update()` itself instead of only direct helper calls,
  - regression coverage added in `tests.singles.test_command_room_context`.
- Quest/runtime de-globalization now has a first real pass:
  - `QuestManager.ensure_initial_quests`, `replenish_board`, and `check_quest_completion` now accept/resolve explicit players instead of requiring the legacy singleton player,
  - clear-region auto-completion checks now iterate tracked players in headless/multi-session runtime,
  - `World.update()` now runs quest auto-completion checks per loaded player,
  - instance/quest/description fallback helpers now consistently delegate to `world.resolve_reference_player()` instead of mixing direct `world.player` and ad-hoc loaded-player fallbacks,
  - regression coverage added in `tests.singles.test_quest_session_context`.
- World-mode policy baseline is now wired:
  - `FeatureProfile` supports canonical world modes via `world.mode` (`single_player_story`, `co_op_party`, `persistent_shard`, `readonly_archive`) and resolves a default mode when unset.
  - Server policy payload now publishes `profile_modes.world`.
  - Runtime command routing now enforces a first-pass `single_player_story` policy: only the primary session can issue gameplay commands.
  - `readonly_archive` now enforces static runtime semantics: mutating commands are blocked by world-mode policy and tick-driven world/time/effects updates are suppressed.
  - `finite_adventure` now has a first runtime baseline:
    - only the primary session may drive the run,
    - `adventure status|summary [text|markdown|json]|start|checkpoint|restore|abandon|reset|replay` are implemented server-side,
    - campaign start/end now update persisted finite-adventure run metadata,
    - a first checkpoint baseline now exists:
      - checkpoints are player-scoped serialized snapshots,
      - restore reactivates the run from checkpointed campaign/node state,
      - checkpoint metadata is exposed in `finite_adventure_state`,
      - reset/replay clear checkpoint state while abandon preserves it,
    - reset/replay determinism is now stronger:
      - a bounded `world_baseline` is captured at run start,
      - `adventure reset` and `adventure replay` restore room items, room visited/mutable room properties, region properties, non-summoned NPCs, dynamic regions, quest board state, respawn queue state, time/weather state, and world-field cell state from that baseline,
      - reset/replay also clear transient room/player runtime residue such as temporary environmental effects, hazard tick caches, player active effects, cooldowns, summons, and minigame/trade/follow state,
      - checkpoint restore is still intentionally player-scoped and does not yet claim dynamic world rewind,
    - a first run-summary baseline now exists:
      - completion and abandon flows persist `last_summary`,
      - `finite_adventure_summary` is emitted as a dedicated runtime payload,
      - `finite_adventure_report` now emits export-oriented text/markdown/json report artifacts,
      - summary baseline now includes campaign name/id, status, outcome, duration, final node, node-resolution history, and player/end-state metadata,
      - reset/replay preserve the last summary for post-run review,
    - `server_policy.adventure_policy` now exposes default campaign, replay support, checkpoint policy, and current run state when this mode is active,
    - regression coverage added in `tests.singles.test_finite_adventure_runtime`.
  - `persistent_shard` policy is now a first-class transport contract surface:
    - TCP/WS `server_policy` payloads publish `feature_flags.persistent_world`,
    - `server_policy.shard_policy` now exposes `session_resume_policy`, `disconnect_timeout_policy`, `persistence_scope`, `late_join_policy`, `world_clock_policy`, `background_simulation_policy`, and `operator_locks_required`,
    - `server_policy.shard_policy` now also exposes live runtime state via `runtime_state`, `runtime_message`, `tick_enabled`, `gameplay_enabled`, and `character_creation_enabled`,
    - shard-policy defaults and raw-profile overrides are now covered in `tests.singles.test_server_policy_payload`,
    - shard resume policy now has first real runtime enforcement:
      - `session_resume_policy = disabled` rejects TCP/WS resume attempts,
      - `disconnect_timeout_policy = grace_window` rejects late resume attempts after `disconnect_timeout_seconds`,
      - disconnect timestamps are tracked per session so the authoritative server owns the decision,
      - expired disconnected shard sessions are now pruned automatically during ordinary new TCP/WS session activity and after failed resume attempts, with player snapshots persisted before eviction,
    - shard operator controls now exist across TCP/WS:
      - `shard status`,
      - `shard mode normal`,
      - `shard mode drain [note]`,
      - `shard mode freeze [note]`,
      - `shard mode maintenance [note]`,
      - `drain` blocks new character creation,
      - `freeze` blocks gameplay and pauses shard ticks,
      - `maintenance` blocks gameplay and character creation and pauses shard ticks,
      - startup `initial_runtime_state` / `initial_runtime_message` are now treated as bootstrap-only defaults rather than permanent overrides, so operator mode changes remain authoritative at runtime,
      - successful shard mode changes now broadcast fresh `shard_status` + `server_policy` updates to connected sessions and send a human-readable announcement to non-issuing sessions,
    - shard observability now has a first dedicated surface:
      - `server_policy.shard_policy.diagnostics` publishes live session/runtime pressure,
      - `shard status` now includes those diagnostics directly,
      - `audit shard` now emits a structured `audit_result`,
      - diagnostics include connected/disconnected/resumable session counts, expired grace-window count, grace-window seconds, max disconnected age, and last mode-change metadata,
    - shard admission now has a first runtime baseline:
      - `server_policy.shard_policy` exposes `new_session_admission_enabled` and `new_session_admission_reason`,
      - `late_join_policy = disabled` now blocks new character creation once a shard already has participants,
      - `drain`, `freeze`, and `maintenance` now also surface admission blocking for new entrants while preserving reconnect/resume paths,
    - shard runtime now has a broader multi-session simulation regression pass:
      - `tests.singles.test_persistent_shard_runtime_simulation` validates `normal -> drain -> freeze -> maintenance -> normal`,
      - existing sessions remain playable during `drain`,
      - new sessions are blocked during `drain` / `maintenance`,
      - world-effect tick probes stop during `freeze` / `maintenance` and resume after returning to `normal`,
    - shard reconnect stress coverage is now broader across both TCP and WS:
      - mixed-age disconnected-session pruning is covered,
      - sequential resume churn under a live connected observer is covered,
      - shard diagnostics counts are asserted across prune/resume/disconnect transitions,
    - TCP/WS resume regression coverage now includes shard resume-disabled and grace-window-expired cases,
      - transport parity snapshots have been refreshed so shard policy is now part of the stable JSON/WS/MessagePack contract.
  - Coverage added in `tests.singles.test_feature_profile` and `tests.singles.test_server_policy_payload`.
- Added resume lifecycle coverage in `tests.singles.test_ws_session_resume` for:
  - unknown session resume rejection,
  - ephemeral-session cleanup,
  - rate-limiter cleanup,
  - character-creation gate preservation after resume,
  - gameplay allowance after resume when a character already exists.
- Added TCP lifecycle coverage in `tests.singles.test_tcp_session_resume` for:
  - unknown resume rejection,
  - session rebinding + state-bundle emission,
  - character-creation gate preservation after resume,
  - gameplay allowance after resume when character exists.
- Added co-op party baseline runtime support:
  - player-centered party state in `HeadlessServer`,
  - `party status|invite|join|leave|leader|disband` command handling gated by `co_op_party`,
  - `party_state` payloads exposed in transport hello and resume bundles,
  - policy payload now advertises `party_supported` and baseline `party_policy`,
  - regression coverage added in `tests.singles.test_party_lifecycle`.
- Party policy surface is now config-aware:
  - `party decline` and `party cancel <player-name>` are implemented,
  - `party_state` now includes `outgoing_invites`,
  - `server_policy.party_policy` now exposes `shared_quest_policy`, `shared_rewards_policy`, and `loot_policy` from profile raw config.
- Session presence is now transport-driven instead of session-existence-driven:
  - `Session.connected` is authoritative for online party roster state,
  - TCP/WS connect, disconnect, and resume paths mark session presence explicitly,
  - party roster presence now resyncs to connected party members when a member disconnects or resumes.
- Party runtime policy baseline now exists:
  - `shared_quest_policy = mirror_all` mirrors newly accepted quests across current party members and syncs mirrored completion,
  - `shared_rewards_policy = split|leader_claims` is enforced for quest, collection, vendor-sale, gambling-profit, combat kill, and dialogue-script reward routing,
  - `loot_policy = round_robin|leader_discretion|finder_keep` is enforced for room pickup flows and scripted `give_item` topic grants,
  - regression coverage added in `tests.singles.test_party_policy_runtime`.
- Party reconnect/runtime hardening now has deeper coverage:
  - TCP and WS transport tests both cover party presence updates across disconnect and resume,
  - round-robin loot cursor continuity is covered across disconnect/reconnect so temporary offline members do not reset party loot fairness.
- Dialogue/content scripting can now issue reward effects with feedback:
  - `KnowledgeManager` supports `give_gold` and structured `give_rewards` dialogue effects,
  - headless/party runtime routes those effects through party reward policy when applicable,
  - regression coverage added in `tests.singles.test_knowledge_scripted_rewards`.
- Party invite lifecycle is now more explicit:
  - duplicate invites from the same party are rejected,
  - competing invites use deterministic replacement semantics,
  - offline invites are durable for currently loaded players and can be disabled by profile policy,
  - regression coverage added in `tests.singles.test_party_lifecycle`.

## Goals For The Next Build Pass

1. Fixture + Content Hardening
- Run fixture refresh and use `LATEST_REFRESH.json` selected path when primary replacement is locked.
- Run stale reference audit command and resolve any reported missing template refs.
- `audit stale-refs` operator command is now implemented for TCP/WS transports with entitlement gating (`operator.audit.stale_refs`) and structured `audit_result` events.
- Current status: `server/data` and the currently selected refreshed fixture path are clean (`0` stale-ref errors). The legacy primary alias folder can still contain stale refs when replacement is denied by filesystem locks; treat `fixture_selected_target` as authoritative for runtime.

2. World Editor Path Reinforcement
- Keep editor export on latest canonical migration path (no compatibility alias mapping).
- Continue tightening migration hydration and validation coverage.

3. Documentation Spine
- Keep handoff docs current with runnable commands and selected fixture path behavior.

4. Omni-Engine Capability Baseline
- Priority note: `persistent_shard` is now considered sufficiently established for current product goals and is no longer a primary build lane. Keep it regression-safe, but prefer work that improves the default server/client/content experience.
- Continue deepening the finite-adventure contract:
  - richer checkpoint tiers beyond the current player-only restore baseline,
  - richer ending-state/reporting/export artifacts beyond the current text/markdown/json baseline,
  - tighter reset/replay determinism for the remaining mutation surfaces outside the current bounded world baseline such as other long-lived simulation/plugin state that is not yet snapshotted,
  - client affordances beyond the current shell baseline for run state, checkpoints, endings, summaries, and replay flow.
- Continue broad server robustness work that benefits every world mode:
  - finish sweeping remaining direct scripted/economy reward and currency grant paths into shared routing/policy helpers where appropriate,
  - continue multiplayer-safe de-globalization in any remaining low-traffic debug/UI/world helpers,
  - keep transport/runtime parity and diagnostics stable while deeper features land.
- Extend party baseline with shared-state policy:
  - extend current quest/collection/vendor/gambling/combat/dialogue-script/scripted-item routing to the remaining economy and scripted currency grant paths,
  - broaden offline invite durability beyond loaded-player scope if persistent player discovery is introduced,
  - add broader party-specific multi-member transport/runtime reconnect stress tests beyond current presence-sync baseline.
- Shift emphasis back toward player-facing proof-of-concept quality:
  - tighten client UX around character creation, diagnostics, and core play loops,
  - keep hardening the existing fantasy content path so manual playtesting can focus on real gameplay instead of setup or state drift,
  - reinforce world-editor and server-config workflows so non-live-authoring builders have a first-class path.
- Add acceptance-test skeletons for finite-adventure flows in `server/tests/singles`.

## Validation Checklist

- `cd server && python .\run_snapshot_checks.ps1`
- `python -m unittest tests.singles.test_transport_parity_snapshots tests.singles.test_server_config_resolution -v`
- `python -m unittest tests.singles.test_launch_from_latest_fixture -v`
- `python -m unittest tests.singles.test_transport_character_creation_gate -v`
- `python -m unittest tests.singles.test_server_constructor_contract_matrix tests.singles.test_server_protocol tests.singles.test_transport_character_creation_gate -v`
- `python -m unittest tests.singles.test_poc_policy_commands tests.singles.test_fixture_boot_smoke -v`
- `python -m unittest tests.singles.test_server_config_resolution tests.singles.test_headless_entitlement_policy_wiring -v`
- `python -m unittest tests.singles.test_transport_startup_diagnostics_parity tests.singles.test_poc_policy_commands tests.singles.test_server_policy_payload -v`
- Headless Godot parse:
  - `Godot_v4.6-stable_win64_console.exe --headless --path C:\python\old\restart\client --quit`

## Deliverables

- First canonical content cleanup pass driven by stale-reference audit results.
- Confirmed fixture refresh + boot smoke using selected target from `LATEST_REFRESH.json`.
- Updated handoff docs for next contributor/session.
- Initial capability-contract docs for world modes, finite-adventure lifecycle, and party lifecycle.
- Initial shard operator/runtime contract doc: `docs/roadmap/persistent-shard-contract.md`.
- Initial finite-adventure runtime contract doc: `docs/roadmap/finite-adventure-contract.md`.

## Known Remaining Issues (Not Yet Fixed)

- `_build_nearby_payload` and key debug spawn paths now use session player location directly, and the broader world/quest/instance/panel/save-manager fallback path is much healthier than before. However, some legacy singleton assumptions can still remain in less-traveled world/debug/UI helpers, so full multi-session correctness still needs continued audit coverage.
- `mobile_low_fx` profile: `combat: enabled` + `world_mutation: readonly` is semantically odd (players can fight but not pick up items). Either intentional for a "spectator combat" mode or an oversight — needs a comment or fix.
- `social_no_combat` profile: `world_field` has `mode: custom` but no `provider_id`. Asymmetric with `world_effects` entry. Document or add the matching provider ID.
- Entitlement policy is now injectable in `HeadlessServer`, but policy shape drift between transport config and headless test fixtures remains a risk area; keep contract tests for both constructors when policy schema evolves.
