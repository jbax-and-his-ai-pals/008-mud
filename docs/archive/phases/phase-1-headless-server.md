# Phase 1: Runtime Foundation

## Goal

Establish a production-grade, headless, authoritative runtime that any client can consume.

## Checklist

- [x] Create initial headless runtime shell (`engine/server/headless_server.py`).
- [x] Add basic session abstraction.
- [x] Add structured command/event output.
- [x] Add initial integration tests for single and dual sessions.
- [x] Introduce explicit player-session mapping contract for future multi-character support.
- [x] Remove remaining hard dependencies on UI objects in command/system paths.
- [x] Introduce explicit server tick configuration and deterministic test mode.
- [x] Add transport adapter boundary (WebSocket-ready interface, in-process first).
- [x] Establish Godot bridge baseline transport (WebSocket + JSON envelope first).
- [x] Define binary transport roadmap (MessagePack or Protobuf) for rich-client scale.
- [x] Add legacy protocol adapter plan (Telnet + GMCP translation).
- [x] Add command authz hooks (session capability checks).
- [x] Add persistence smoke tests for headless mode.
- [x] Add protocol schema docs and versioned event envelope.
- [x] Implement resource-to-SQLite serialization path for core entity/resource updates.
- [x] Add explicit world-mode policy routing in runtime command/tick layers.
- [ ] Add finite-adventure state machine support in authoritative runtime.
- [x] Add party lifecycle primitives (invite/join/leave/leadership/disband).
- [x] Add party-aware reconnect/session-resume contract tests.

Evidence:
- World-mode baseline enforcement and policy helpers: [headless_server.py](C:/python/old/restart/server/engine/server/headless_server.py)
- Profile world-mode resolution: [feature_profile.py](C:/python/old/restart/server/engine/server/feature_profile.py)
- TCP policy payload contract: [poc_server.py](C:/python/old/restart/server/poc_server.py)
- WebSocket policy/resume parity: [poc_ws_server.py](C:/python/old/restart/server/poc_ws_server.py)
- Party lifecycle contract: [party-lifecycle-contract.md](C:/python/old/restart/docs/roadmap/party-lifecycle-contract.md)
- Persistent shard contract: [persistent-shard-contract.md](C:/python/old/restart/docs/roadmap/persistent-shard-contract.md)
- Party lifecycle coverage: [test_party_lifecycle.py](C:/python/old/restart/server/tests/singles/test_party_lifecycle.py)
- Party runtime policy coverage: [test_party_policy_runtime.py](C:/python/old/restart/server/tests/singles/test_party_policy_runtime.py)
- TCP resume coverage: [test_tcp_session_resume.py](C:/python/old/restart/server/tests/singles/test_tcp_session_resume.py)
- WebSocket resume coverage: [test_ws_session_resume.py](C:/python/old/restart/server/tests/singles/test_ws_session_resume.py)
- Transport parity snapshots: [test_transport_parity_snapshots.py](C:/python/old/restart/server/tests/singles/test_transport_parity_snapshots.py)

## Exit Gate

- [ ] Runtime is client-agnostic, deterministic under test mode, stable for external transport integration, and supports world-mode-aware authoritative execution across story, co-op, shard, and finite-adventure paths.
