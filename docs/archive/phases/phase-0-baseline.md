# Phase 0: Platform Definition

## Goal

Define the platform contract: engine boundaries, toolkit scope, modding model, and Steam product shape.

## Checklist

- [x] Define product SKU strategy (engine/toolkit/sample packs).
- [ ] Define target platforms and minimum hardware profile.
- [x] Define runtime API boundary vs content boundary.
- [x] Define modding levels (data, script, total conversion).
- [ ] Write ADR: engine runtime and protocol versioning.
- [ ] Write ADR: modding safety and capability model.
- [ ] Define KPI dashboard (tick budget, command latency, crash-free sessions).
- [x] Define first four sample theme targets.
- [x] Define world mode contract (`single_player_story`, `co_op_party`, `persistent_shard`, `readonly_archive`).
- [x] Define finite-adventure lifecycle contract (start, checkpoint, ending states, reset/replay).
- [ ] Write ADR: party/group synchronization and reconnect semantics.
- [ ] Write ADR: pack compatibility windows and migration guarantees.

Evidence:
- Product SKU strategy: [README.md](C:/python/old/restart/docs/roadmap/README.md)
- Runtime/content boundaries: [platform-architecture.md](C:/python/old/restart/docs/roadmap/platform-architecture.md)
- Modding levels: [platform-architecture.md](C:/python/old/restart/docs/roadmap/platform-architecture.md)
- First four sample themes: [platform-architecture.md](C:/python/old/restart/docs/roadmap/platform-architecture.md)
- World mode baseline contract: [engine-capability-track.md](C:/python/old/restart/docs/roadmap/engine-capability-track.md)
- Finite-adventure runtime contract: [finite-adventure-contract.md](C:/python/old/restart/docs/roadmap/finite-adventure-contract.md)
- Party runtime contract: [party-lifecycle-contract.md](C:/python/old/restart/docs/roadmap/party-lifecycle-contract.md)
- Persistent shard contract: [persistent-shard-contract.md](C:/python/old/restart/docs/roadmap/persistent-shard-contract.md)

## Exit Gate

- [ ] Platform scope and architecture are signed off across engine, toolkit, modding, and Steam tracks.
