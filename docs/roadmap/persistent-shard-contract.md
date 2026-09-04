# Persistent Shard Contract

## Current Baseline

- World mode gate: shard behavior is surfaced when `world.mode` resolves to `persistent_shard`.
- `persistent_shard` is now the default resolved world mode when no explicit `world.mode` is set.
- Runtime/server policy payloads expose shard policy to both TCP and WebSocket clients.
- Transport snapshots now include shard policy fields as part of the stable contract.

## Current Policy Surface

`server_policy.shard_policy` includes:

- `enabled`
- `session_resume_policy`
- `disconnect_timeout_policy`
- `disconnect_timeout_seconds`
- `persistence_scope`
- `late_join_policy`
- `world_clock_policy`
- `background_simulation_policy`
- `operator_locks_required`
- `runtime_state`
- `runtime_message`
- `tick_enabled`
- `gameplay_enabled`
- `character_creation_enabled`
- `new_session_admission_enabled`
- `new_session_admission_reason`
- `diagnostics`

Related feature flag:

- `server_policy.feature_flags.persistent_world`

Current config source:

- `feature_profile.raw["persistent_shard"]`
- fallback alias: `feature_profile.raw["shard"]`

Supported override keys:

- `session_resume_policy`
- `disconnect_timeout_policy`
- `disconnect_timeout_seconds`
- `persistence_scope`
- `late_join_policy`
- `world_clock_policy`
- `background_simulation_policy`
- `operator_locks_required`

## Default Baseline Semantics

- `session_resume_policy = enabled`
  - transport resume is part of the expected shard lifecycle.
- `disconnect_timeout_policy = indefinite`
  - disconnected sessions are expected to be resumable until explicit cleanup policy is introduced.
- `persistence_scope = world_and_players`
  - shard mode assumes both world state and player state matter.
- `late_join_policy = enabled`
  - additional sessions may connect to the running shard.
- `world_clock_policy = always_on`
  - the shard clock conceptually continues independent of a single active viewer.
- `background_simulation_policy = always_on`
  - background world simulation is intended to remain authoritative even when a specific player is not driving it.
- `operator_locks_required = true` unless authoring is globally disabled
  - live world mutation in persistent mode is expected to remain lock-aware by default.

## What Is Implemented Today

- Policy surfacing:
  - TCP `hello` payload includes shard-aware `server_policy`.
  - WebSocket `hello` payload includes shard-aware `server_policy`.
  - resume flows re-emit the same policy bundle after `session_resumed`.
- Profile-driven configuration:
  - shard policy values are resolved centrally in `HeadlessServer.shard_policy_value(...)`.
  - policy payload tests cover both defaults and raw profile overrides.
- Session resume enforcement:
  - `session_resume_policy = disabled` now actively rejects transport resume attempts.
  - `disconnect_timeout_policy = grace_window` now actively rejects resume attempts after the configured `disconnect_timeout_seconds` window has elapsed.
  - disconnect timestamps are tracked per session so reconnect policy is enforced by the authoritative server, not just by transport wrappers.
- Session cleanup automation:
  - expired disconnected shard sessions are now pruned automatically during ordinary new TCP/WS session activity and after failed resume evaluation,
  - player snapshots are persisted before stale session metadata is evicted,
  - party-presence sync events are emitted for still-connected affected party members after shard-session eviction.
- Operator-facing runtime controls:
  - TCP and WebSocket operator surfaces now expose a `Shard` domain with `Status`, `Set Normal`, `Set Drain`, `Set Freeze`, and `Set Maintenance`.
  - `server_policy.shard_policy` now publishes live runtime state and enforcement flags, not just static profile intent.
  - `initial_runtime_state` / `initial_runtime_message` are now bootstrap-only startup defaults; operator mode changes replace them authoritatively for the rest of the runtime.
  - `shard mode drain` blocks new character creation while allowing existing sessions to continue.
  - `shard mode freeze` pauses world ticks and blocks gameplay commands and character creation.
  - `shard mode maintenance` pauses world ticks and blocks gameplay commands and character creation, with optional operator note text.
  - live shard mode changes now fan out to connected TCP/WS sessions with fresh `shard_status` and `server_policy` payloads, plus an operator announcement text for non-issuing sessions.
- Admission baseline:
  - new-participant admission is now enforced for character creation in persistent-shard mode,
  - `late_join_policy = disabled` blocks new character creation once the shard already has active world participants,
  - `drain`, `freeze`, and `maintenance` all surface a shard admission block reason for new entrants,
  - resume flows still remain available under their own shard resume policy so reconnects are not broken by admission gating.
- Shard observability:
  - `server_policy.shard_policy.diagnostics` now publishes live shard runtime/session pressure details.
  - `shard status` now includes the same diagnostics bundle.
  - `audit shard` now emits a structured `audit_result` with shard diagnostics for operator tooling.
  - diagnostics currently include runtime state/message, total/connected/disconnected/resumable session counts, expired grace-window session count, grace-window seconds, maximum disconnected age, and last mode-change metadata.
- Contract stability:
  - transport parity snapshots now treat shard policy as a first-class protocol surface.
- Runtime regression coverage:
  - shard runtime now has a broader multi-session simulation test pass covering `normal -> drain -> freeze -> maintenance -> normal`,
  - that coverage validates existing-session gameplay gating, new-session admission blocking, and tick suppression/resumption through the authoritative headless runtime.

## What This Does Not Yet Guarantee

- World simulation does not yet branch shard-specific tick behavior beyond the shared multiplayer-safe baseline.
- Disconnect timeout now has a first runtime implementation for late-resume rejection and stale session eviction, but not yet for richer operator-visible cleanup workflows.
- Admission/late-join now has a first runtime baseline, but it is still character-creation-centered rather than a full authenticated admission system.
- Persistence scope is exposed, but storage/restore guarantees for locks, transient encounters, and operator mutations still need deeper codification.
- There is now a first dedicated shard observability surface for session/runtime pressure, but not yet for uptime, simulation drift, or deeper maintenance workflow telemetry.

## Next Steps

1. Deepen admission semantics from character-creation gating into a fuller reclaim/auth model for late joins, reconnects, and named-character recovery.
2. Add deeper shard diagnostics and observability for maintenance windows, cleanup visibility, uptime, and simulation state.
3. Define storage guarantees for shard-only concerns such as lock persistence, operator-authored live edits, and world-clock continuity.
4. Expand from the current shard mode-transition simulation into heavier reconnect/resume coverage with multiple concurrent shard sessions and active world updates.
