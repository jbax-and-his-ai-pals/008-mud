# Handoff Notes

> Status: This file is legacy context from an earlier slice-based checkpoint and is not the primary source of truth.
> Use `docs/roadmap/next-session.md` and `docs/roadmap/README.md` for current direction and priorities.

## Current Position

| Track | Slice | Status |
|---|---|---|
| Client | Slice 4: Theme-Agnostic Presentation | **One item open** (1-bit SVG enforcement) |
| Client | Slice 5: Steam UX and Polish | **Complete** (all 6 items checked) |
| Client | Slice 6: Mobile Variant | Not started |
| Server/Protocol | Follow-ons | 3 items open (msgpack, CI lint, Mudlet scripts) |

Recommended next focus: **close out Slice 4** (1-bit SVG enforcement), then evaluate whether
the Slice 5 exit criterion is satisfied before moving to Slice 6 or server follow-ons.

---

## Completed This Session

### Slice 5 items (all six delivered)

**Launcher / start flow**
- `client/scenes/launcher.tscn` — new boot scene: title, "Play Offline", "Connect Online" reveal
- `client/scripts/ui/launcher_controller.gd` — packs `launch_host / launch_port / launch_mode / launch_auto_connect` into `Engine.set_meta()` then calls `change_scene_to_file("res://scenes/main.tscn")`
- `client/project.godot` — `run/main_scene` changed to `launcher.tscn`
- `main_controller._apply_launch_config()` — drains meta keys, forces WebSocket transport, auto-connects
- Contract tests: `tests/singles/test_launcher_scene.py` (24 tests)

**Keyboard / controller remap baseline**
- `client/data/keybindings_default.json` — 5 actions: `mud_history_prev/next`, `mud_scroll_up/down`, `mud_focus_input`
- `client/scripts/ui/keybindings_manager.gd` (`class_name KeybindingsManager`) — load/save/reset, `is_key_for_action()`, 22-key `KEY_NAME_MAP`, persists to `user://keybindings.json`
- `client/scenes/main.tscn` — `KeybindingsManager` node added
- `main_controller._input()` — routes all 5 actions through manager
- Command history: `_push_history()` / `_history_navigate()`, `HISTORY_MAX_SIZE=100`, Up/Down browse
- In-game commands: `keybind list`, `keybind set <action> <key>`, `keybind reset [action]`
- Contract tests: `tests/singles/test_keybindings.py` (37 tests)

**First-run onboarding**
- `client/scripts/ui/onboarding_controller.gd` (`class_name OnboardingController`) — `show_if_first_run()` / `show_panel()` / `dismiss()` / `is_complete()`; marker: `user://onboarding_complete`
- `client/scenes/main.tscn` — `OnboardingOverlay` subtree (semi-transparent backdrop + centred panel with tips and dismiss button)
- Tips cover: look/go/status/inventory, history nav, scroll keys, theme/a11y/keybind commands, how to re-show
- In-game commands: `onboarding show`, `onboarding dismiss`
- Contract tests: `tests/singles/test_onboarding.py` (24 tests)

**Crash recovery**
- `client/scripts/ui/crash_recovery_controller.gd` (`class_name CrashRecoveryController`) — writes/reads/clears `user://session_alive.json`; emits `restore_requested(host, port, session_id, transport)` and `dismissed`
- `client/scenes/main.tscn` — `CrashRecoveryOverlay` subtree (Backdrop + DetailLabel + RestoreButton + FreshButton)
- Marker written on connect, session_id updated on hello, cleared on disconnect / goodbye / window close
- `main_controller._notification(NOTIFICATION_WM_CLOSE_REQUEST)` intercepts window X; `set_auto_accept_quit(false)` in `_ready()`
- `_on_crash_recovery_restore()` fills host/port/transport/session and calls `_on_connect_pressed()`
- Crash recovery shown before onboarding; onboarding deferred until recovery is dismissed
- Contract tests: `tests/singles/test_crash_recovery.py` (36 tests)

### Earlier in this session (carried from prior context)

- Panel payload contract tests: `tests/singles/test_server_panel_payloads.py` (27 tests)
- Theme panel smoke tests: `TestThemePanelSmoke` in `test_client_theme_packs.py`
- A11y presets: `A11Y_PRESETS` const, `a11y preset <name>` / `a11y list` commands
- Color-independent critical status: `[DEAD]` / `[CRIT]` / `[OOM]` text markers in status vitals label
- Contract tests: `tests/singles/test_client_a11y_presets.py` (15 tests)

---

## Test Suite State

All Python contract tests pass (144 tests across relevant test files).

```
python -m unittest tests.singles.test_crash_recovery \
                   tests.singles.test_onboarding \
                   tests.singles.test_keybindings \
                   tests.singles.test_launcher_scene \
                   tests.singles.test_client_a11y_presets \
                   tests.singles.test_client_theme_packs -v
```

Previous regression sets still green:
```
python -m unittest tests.singles.test_poc_ws_server -v
python -m unittest tests.singles.test_server_panel_payloads -v
python -m unittest tests.singles.test_msgpack_transport -v
```

---

## Known Environment Issue

Godot headless parse/check is unstable in this environment and can crash with
`Failed to open user://logs/...` / signal `11`. All tests are pure-Python contract
tests that parse GDScript source and `.tscn` files via regex. No Godot runtime is
invoked by any test.

---

## Open Items

### Slice 4 — one item remaining
- `[ ]` Ensure 1-bit style enforcement path for authored SVG and runtime sprites.
  - Likely lives in `svg_runtime_renderer.gd` + a validation helper
  - Should reject (or warn on) SVG payloads that contain non-1-bit colours
  - Needs a Python contract test that verifies the validation logic is present

### Slice 5 exit criterion
- `[ ]` Client meets Steam-facing UX baseline for release candidate.
  - All implementation items are green; this is a review/sign-off gate, not more code

### Server / Protocol follow-ons
- `[ ]` Install `msgpack` and activate currently skipped msgpack transport tests (8 tests in `test_msgpack_transport.py` decorated with `@skipUnless(MSGPACK_AVAILABLE)`)
- `[ ]` Add CI lint/assertion to prevent unmapped `Core.Event` in production traces
- `[ ]` Write Mudlet example scripts for GMCP packages (per ADR 0002 rollout notes)

### Slice 6 — not started
- Mobile variant integration (share core, touch layout, suspend/resume)

---

## Key File Map

| Purpose | Path |
|---|---|
| Boot scene | `client/scenes/launcher.tscn` |
| Launcher controller | `client/scripts/ui/launcher_controller.gd` |
| Main game scene | `client/scenes/main.tscn` |
| Main controller | `client/scripts/ui/main_controller.gd` |
| Keybindings manager | `client/scripts/ui/keybindings_manager.gd` |
| Default keybindings | `client/data/keybindings_default.json` |
| Onboarding controller | `client/scripts/ui/onboarding_controller.gd` |
| Crash recovery controller | `client/scripts/ui/crash_recovery_controller.gd` |
| Theme packs | `client/themes/*.json` |
| Client roadmap | `docs/roadmap/client-track.md` |
| Next-session checklist | `docs/roadmap/next-session.md` |
| Theme pack spec | `docs/roadmap/theme-pack-spec-v1.md` |
| GMCP contract ADR | `docs/roadmap/adr/0002-gmcp-package-contract.md` |
