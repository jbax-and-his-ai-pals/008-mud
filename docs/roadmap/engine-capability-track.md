# Engine Capability Track

## Purpose

Drive the runtime toward a flexible omni-engine that can power:

- finite single-player adventures,
- cooperative party-based adventures,
- persistent multi-session worlds,
- and curated smaller worlds with explicit ending states.

## Capability Targets

1. Pack and module lifecycle
- Versioned world/system pack manifests with dependency resolution.
- Strict validation + migration tooling for content/schema evolution.
- Stable compatibility policy for engine API, protocol, and pack versions.

2. World mode presets
- First-class runtime modes:
  - `single_player_story`
  - `co_op_party`
  - `persistent_shard`
  - `readonly_archive`
- Mode policies gate mutation, combat, respawn, and authoring.
- Current contract references:
  - [Party Lifecycle Contract](C:/python/old/restart/docs/roadmap/party-lifecycle-contract.md)
  - [Persistent Shard Contract](C:/python/old/restart/docs/roadmap/persistent-shard-contract.md)

3. Finite-adventure framework
- Campaign graph as a core runtime primitive.
- Canonical ending states (victory/failure/abandon/timeout).
- End-of-run artifacts (summary, timeline, seed/profile metadata).
- Deterministic reset/replay path for authored short-form worlds.
- Current contract reference:
  - [Finite Adventure Contract](C:/python/old/restart/docs/roadmap/finite-adventure-contract.md)

4. Party and group contract
- Party lifecycle: invite, join, leave, leader transfer, disband.
- Shared state policies: quest sync, reward split, loot ownership, revive rules.
- Session resilience: reconnect/rebind semantics for group play.
- Snapshot tests for co-op correctness under disconnect/reconnect stress.

5. Runtime observability and ops
- Standardized diagnostics surface in startup + policy payloads.
- Tick/command/world-effect instrumentation and threshold alerts.
- Operator-facing dashboards and runbooks for profile/provider incidents.

6. Protocol and client contract
- Versioned server event schema with compatibility windows.
- Transport parity guarantees across TCP/WS/MessagePack.
- Graceful degradation rules when feature payloads are unsupported by client.

## Success Criteria

- New worlds can be authored as either finite campaigns or persistent shards without engine fork.
- Party play is deterministic and policy-aware under reconnect and profile changes.
- Pack upgrades and runtime upgrades are validated pre-boot with clear migration paths.
- Operators can diagnose and recover from configuration/provider failures quickly.
