# Steam Packaging Track

This track runs alongside all phases. Do not leave this to the end.

## Product SKUs (Proposed)

1. `MUD Client` (primary player app on Steam)
2. `MUD Engine + Toolkit` (creator-focused app/distribution)
3. `Sample Worlds` (bundled content or optional DLC-style packs)
4. `Creator SDK` (docs/templates distributed with app install)

## Packaging Milestones

- [ ] Define install layout for client/engine/toolkit/sample packs.
- [ ] Define first-run world/template creation flow.
- [ ] Define mod folder conventions and package manifest format.
- [ ] Define update-safe user content directories.
- [ ] Add build pipeline for Steam depots/branches.
- [ ] Add crash + telemetry opt-in flow and privacy disclosures.
- [x] Define client offline/online mode UX for singleplayer and hosted worlds.

## Steam Readiness Checklist

- [ ] Controller/keyboard UX baseline for toolkit launch flow.
- [x] Controller/keyboard UX baseline for shipped client gameplay loop.
- [x] Offline/online mode behavior documented.
- [ ] Save migration compatibility policy documented.
- [ ] Workshop strategy decided (if used): upload/download/mod version behavior.
- [ ] Support and rollback policy documented.

## Mobile Store Companion Checklist

- [ ] Android store pipeline, signing, and release channel strategy documented.
- [ ] iOS store pipeline, signing, and release channel strategy documented (if in scope).
- [ ] Mobile lifecycle/connectivity UX policy documented.

Evidence:
- Offline/online launcher flow + handoff: [launcher_controller.gd](C:/python/old/restart/client/scripts/ui/launcher_controller.gd)
- Runtime interpretation of launch mode + transport selection: [main_controller.gd](C:/python/old/restart/client/scripts/ui/main_controller.gd)
- Keyboard command UX and remapping baseline: [keybindings_manager.gd](C:/python/old/restart/client/scripts/ui/keybindings_manager.gd)
