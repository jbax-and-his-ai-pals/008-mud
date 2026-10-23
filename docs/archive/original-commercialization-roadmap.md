# The original commercialization roadmap

Moved out of the README on 2026-10-22. Historical: for current priorities read `ROADMAP.md` and `docs/plan/`.


> **For current priorities, read [`ROADMAP.md`](ROADMAP.md)** (rewritten
> 2026-09-14 after a full engine + content audit; tracks phases P0-P8) and
> [`docs/design/WORLD_DESIGN.md`](docs/design/WORLD_DESIGN.md). Much of what
> this section describes as future phases is already done — a headless,
> server-authoritative core with TCP/WS transports exists
> (`engine/server/`), and the content-set pipeline/editor integration Phase 4
> calls for is largely built (`engine/server/content_set/`,
> `content_sets/fantasy_frontier/`, the synced `mud-world-editor/`). Kept
> below as the original commercialization framing and for the docs it
> still points at usefully (platform architecture, Steam packaging, theme
> packs); treat phase numbering and "current state" as historical, not a
> live plan.

Goal: evolve this singleplayer simulation-first game into a commercial, server-authoritative multiplayer MUD with Godot client UX.

Execution docs live in `docs/roadmap/` (see the supersession notice in
`docs/archive/roadmap-README-superseded.md` before treating anything there as current):
- `docs/archive/roadmap-README-superseded.md`
- `docs/roadmap/phases/`
- `docs/roadmap/adr/`
- `docs/reference/platform-architecture.md`
- `docs/archive/steam-packaging-track.md`
- `docs/reference/theme-pack-spec-v1.md`

Current content-engine development flow:

- Validate Fantasy Frontier: `python toolkit/content_set_validator.py content_sets/fantasy_frontier`
- Launch Fantasy Frontier directly (the default content set):
  - `python server/launch_content_set.py --transport tcp`
  - `python server/launch_content_set.py --transport ws`

Legacy server-fixture operator flow:
- Refresh fixture: `python toolkit/fixture_refresh.py --source content_sets/fantasy_frontier/data --latest-root content_sets/fantasy_frontier/data --fixture-root tmp/content_fixtures --fixture-name fantasy_editor_migrated_latest`
- Launch from latest selected fixture (auto-reads `tmp/content_fixtures/LATEST_REFRESH.json`):
  - `python server/launch_from_latest_fixture.py --transport tcp`
  - `python server/launch_from_latest_fixture.py --transport ws`
- Operator reference: `docs/reference/server-operator-guide.md`

### Guiding Product/Tech Decisions
* Keep simulation logic authoritative on the server.
* Treat the Godot client as a view/controller layer over networked game state.
* Preserve data-driven content pipelines (`content_sets/<set>/data/*.json`) as long as possible to reduce rewrite risk.
* Use existing tests as migration safety rails before replacing systems.

### Current State (What Helps Us)
* Strong domain coverage in tests (`tests/` includes combat, world, AI, economy, quests, persistence).
* Clean command dispatch layer (`engine/commands/command_system.py`) that can become protocol-facing handlers.
* Central world lifecycle (`engine/world/world.py`) and persistence (`engine/world/save_manager.py`) already exist.
* Data definitions are externalized in JSON, which is migration-friendly.

### Phase 0: Product and Architecture Baseline (2-4 weeks)
Deliverables:
* Define commercial target: buy-to-play vs F2P, session model, expected CCU, and platform targets.
* Define networking authority model and anti-cheat stance.
* Write a canonical architecture decision record (ADR) for:
  * Server runtime choice (`Python headless` first, or full GDScript/C# port later).
  * Protocol format (JSON over WebSocket first, versioned messages).
  * Account/auth boundary (guest/local dev now, real auth later).
* Establish KPIs: tick time budget, command latency, reconnect success, crash-free session rate.

Exit gate:
* Signed-off architecture + business constraints + scope for first paid launch.

### Phase 1: Extract Headless Authoritative Server Core (4-8 weeks)
Deliverables:
* Separate simulation engine from Pygame-specific rendering/input concerns.
* Introduce server loop that owns:
  * world updates
  * command processing
  * save/load
  * AI ticks
* Introduce a network session model:
  * `player_id`, connection state, command queue, outbound event stream.
* Add protocol boundary adapters around command input/output.
* Keep existing content files and mechanics unchanged where possible.

Recommended first implementation:
* Keep server in Python to minimize rewrite risk.
* Build thin Godot client that connects and renders text/UI events.

Exit gate:
* Multiple remote clients can connect, issue commands, and observe shared world state.

### Phase 2: Godot Client Foundation (4-6 weeks)
Deliverables:
* Godot project with:
  * login/character select flow
  * command input + history/autocomplete
  * text/event feed
  * panelized UI (inventory, map, quests, status)
* Network client with reconnect and session resume handling.
* Message schema versioning support in client.
* Minimal accessibility baseline (font scaling, color contrast presets, keybind config).

Exit gate:
* Playable vertical slice in Godot client with parity for core text loop (move/look/combat/inventory/save).

### Phase 3: Multiplayer Semantics and Live Ops Core (6-10 weeks)
Deliverables:
* Shared-world rules:
  * room occupancy
  * visibility/broadcast scoping
  * interaction contention rules
* Persistence model upgrades:
  * account-level data
  * character slots
  * migration/version handling for saves
* Operational services:
  * structured logs
  * metrics
  * admin commands
  * crash recovery and backup restore drills
* Abuse/security baseline:
  * input validation
  * rate limits
  * moderation hooks

Exit gate:
* Closed alpha with stable multi-user sessions and durable progression.

### Phase 4: Content Pipeline and Tooling for Scale (ongoing)
Deliverables:
* Content schema validation and CI checks for each content set's `data/` tree.
* World/content editor integration path (`mud-world-editor`) with export contracts.
* Regression harness for command transcripts and deterministic combat/world snapshots.
* Authoring docs for designers (items/spells/regions/quests conventions).

Exit gate:
* New content can be added by non-engineers with low defect rates.

### Phase 5: Commercial Readiness (8-12 weeks)
Deliverables:
* Platform and legal readiness:
  * Terms/Privacy
  * account deletion/export policy
  * telemetry disclosures
* Commerce stack:
  * entitlement checks
  * billing integration
  * fraud and chargeback handling policy
* Launch operations:
  * patching and rollback strategy
  * support workflows
  * incident runbooks and on-call rotation
* QA:
  * load testing
  * soak testing
  * compatibility matrix

Exit gate:
* Release candidate passes technical, operational, and legal go-live checklist.

### Migration Risks to Manage Early
* Tight coupling between loop/UI/simulation in current `GameManager`.
* Tick-rate and deterministic behavior drift once network latency is introduced.
* Save format evolution (`save_format_version`) under live-service constraints.
* Tooling debt for validating JSON content at scale.

### Suggested First Milestone in This Repo
1. Create `/docs/roadmap/` with ADRs and milestone checklists.
2. Add a `server_mode` entry point that runs headless without Pygame rendering.
3. Add a simple socket/WebSocket adapter that forwards commands into `CommandProcessor`.
4. Add an integration test: two simulated clients, one shared world, verified state/events.
```
