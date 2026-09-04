# Phase 4: Ecosystem Hardening

## Goal

Harden runtime, toolkit, and mod ecosystem for scale, safety, and community growth.

## Checklist

- [x] Add schema validators for `data/*.json`.
- [x] Add schema validators for YAML component templates and SVG asset payloads.
- [x] Add CI checks for content integrity and references.
- [x] Define editor export contracts for `mud-world-editor`.
- [x] Implement live authoring lock model (`@dig`/`@edit` collision prevention).
- [x] Add GM-level runtime toggles for major systems (for example blight/permadeath).
- [x] Add deterministic regression harness for commands and combat snapshots.
- [x] Add multiplayer semantics hardening (occupancy, conflict, scoped events).
- [x] Add abuse safeguards (rate limiting, input guards, moderation hooks).
- [x] Document content authoring and mod publishing guidelines.
- [x] Add compatibility policy for engine API vs pack/mod versions.
- [ ] Add mandatory pack dependency solver checks in CI for sample + operator profiles.
- [ ] Add finite-adventure validation suite (ending-state integrity, reset/replay safety).
- [ ] Add party-contract regression suite (shared quest/reward/loot ownership + reconnect continuity).
- [ ] Add observability dashboards/runbooks for world-mode and provider-policy incidents.

Evidence:
- Data JSON integrity validator CLI: [data_integrity_validator.py](C:/python/old/restart/toolkit/data_integrity_validator.py)
- Cross-file reference integrity validator CLI: [reference_integrity_validator.py](C:/python/old/restart/toolkit/reference_integrity_validator.py)
- Data validator tests: [test_data_integrity_validator.py](C:/python/old/restart/server/tests/singles/test_data_integrity_validator.py)
- Reference validator tests: [test_reference_integrity_validator.py](C:/python/old/restart/server/tests/singles/test_reference_integrity_validator.py)
- Single content gate script for CI/local preflight: [run_content_checks.ps1](C:/python/old/restart/run_content_checks.ps1)
- Pack compatibility enforcement and runtime API range validation: [pack_tool.py](C:/python/old/restart/toolkit/pack_tool.py)
- Pack compatibility regression tests: [test_pack_tool_compatibility.py](C:/python/old/restart/server/tests/singles/test_pack_tool_compatibility.py)
- Mod manifest compatibility validator: [mod_manifest_validator.py](C:/python/old/restart/toolkit/mod_manifest_validator.py)
- Plugin loader manifest enforcement: [plugin_manager.py](C:/python/old/restart/server/engine/core/plugin_manager.py)
- Mod compatibility regression tests: [test_mod_manifest_validator.py](C:/python/old/restart/server/tests/singles/test_mod_manifest_validator.py)
- Pack compatibility contract spec: [theme-pack-spec-v1.md](C:/python/old/restart/docs/roadmap/theme-pack-spec-v1.md)
- Content/mod publishing guidance: [content-authoring-and-mod-publishing-guidelines.md](C:/python/old/restart/docs/roadmap/content-authoring-and-mod-publishing-guidelines.md)
- Live authoring lock model protocol and shell commands: [poc_server.py](C:/python/old/restart/server/poc_server.py)
- Lock/update payload handling and collision checks: [realtime_assets.py](C:/python/old/restart/server/engine/server/realtime_assets.py)
- Lock + authoring regression coverage: [test_authoring_shell_commands.py](C:/python/old/restart/server/tests/singles/test_authoring_shell_commands.py)

## Exit Gate

- [ ] Community creators and operators can publish and run packs safely across finite, co-op, and persistent modes with stable compatibility guarantees.
