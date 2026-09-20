# Client Track (Shipped Player App)

This track defines the player-facing client milestones for Steam release, with desktop-first delivery and mobile-variant compatibility.

## Slice 1: Text-First Playable Loop

- [x] Connect/login/session bootstrap flow.
- [x] Command input, history, and response log.
- [x] Basic room view and navigation UX.
- [x] Error and disconnect handling.
- [x] Server `world_state` event rendering in client shell (generic world-field summary panel).

Exit:
- [ ] Player can complete a full text-loop session from start to save/quit.

## Slice 2: Core Gameplay Panels

- [x] Status panel (HP/mana/effects).
- [x] Inventory/equipment panel.
- [x] Quest/journal panel.
- [x] Nearby entities/interactions panel.
- [x] RichTextLabel + RichTextEffect path for server-driven atmospheric glyph effects.

Exit:
- [ ] Core fantasy sample is fully playable from client without debug commands.

## Slice 3: Session and Network Resilience

- [x] Reconnect and session resume.
- [x] Protocol version negotiation.
- [x] Graceful degraded-mode behavior for feature mismatch.
- [x] Client-side telemetry for network failures.

Exit:
- [ ] Client survives transient disconnects and reports actionable diagnostics.

## Slice 4: Theme-Agnostic Presentation

- [x] Theme-aware text/icon/style overrides from pack metadata.
- [x] Runtime switching between sample themes.
- [x] Ensure no fantasy-only hardcoded terms in shared UI.
- [ ] Ensure 1-bit style enforcement path for authored SVG and runtime sprites.

Exit:
- [ ] Same client binary works across all sample themes with pack-driven presentation.

## Slice 5: Steam UX and Polish

- [x] Launcher/start flow for offline vs online worlds.
      → `client/scenes/launcher.tscn` + `launcher_controller.gd`; Engine.set_meta handoff; main_controller reads on _ready()
- [x] Input accessibility baseline (keyboard/controller remap, scaling).
      → `KeybindingsManager` node; `keybindings_default.json`; history nav (Up/Down); `keybind` in-game commands
- [x] High-contrast and low-vision presets integrated into settings.
      → `a11y preset high_contrast / low_vision / screen_reader / reduced_motion / default`
- [x] Color-independent status signaling across critical UI states.
      → `[DEAD]` / `[CRIT]` / `[OOM]` text markers in status vitals label
- [x] First-run onboarding for players.
      → Semi-transparent overlay with tips panel; `user://onboarding_complete` marker; `onboarding show/dismiss`
- [x] Crash recovery flow and support links.
      → `user://session_alive.json` marker; `CrashRecoveryController` with Reconnect / Start Fresh dialog; window-close intercepted via NOTIFICATION_WM_CLOSE_REQUEST

Exit:
- [ ] Client meets Steam-facing UX baseline for release candidate.

## Slice 6: Mobile Variant Integration

- [x] Share protocol and gameplay client core with desktop build.
- [x] Mobile-specific layout and touch interaction profile.
- [x] Suspend/resume/reconnect behavior implemented.
- [x] Mobile performance/battery profile validated.

Exit:
- [x] Mobile variant is playable and stable with the same runtime contracts as desktop.
