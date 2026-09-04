# Mobile Track (Client Variant)

This track defines the mobile client variant strategy (same core client, mobile-specific UX/runtime constraints).

## Strategy

- Prefer one shared client codebase with platform abstractions.
- Maintain desktop and mobile variants from the same protocol/runtime contracts.
- Avoid engine forks for mobile-specific behavior.

## Slice M1: Mobile UX Foundation

- [x] Touch-first command and interaction model.
- [x] Adaptive layout for phone and tablet form factors.
- [ ] Virtual keyboard flow for command-heavy gameplay.
- [x] Mobile-friendly navigation/panel model (fewer simultaneous panes).
- [x] Large-text and high-contrast presets for low-vision use.

Exit:
- [ ] Core text gameplay loop is comfortable on a phone-size screen.

## Slice M2: Platform Behavior

- [x] Suspend/resume lifecycle handling.
- [x] Network reconnect after app backgrounding.
- [x] Offline-safe local mode behavior (if enabled by product design).
- [x] Device-specific input/accessibility baselines.

Exit:
- [ ] Mobile session survives common lifecycle transitions without player state loss.

## Slice M3: Performance and Battery

- [x] Frame/update cadence profiles for battery efficiency.
- [x] Reduced background work and telemetry batching.
- [x] Memory budget targets by device tier.
- [ ] Startup and reconnect timing targets.

Exit:
- [ ] Mobile performance/battery budgets met on target test devices.

Evidence:
- Touch controls + D-Pad + quick actions scene: [main.tscn](C:/python/old/restart/client/scenes/main.tscn)
- Mobile/desktop platform gating and shared core: [main_controller.gd](C:/python/old/restart/client/scripts/ui/main_controller.gd)
- Suspend/resume + reconnect behavior: [main_controller.gd](C:/python/old/restart/client/scripts/ui/main_controller.gd)
- Mobile a11y baseline usage in-client: [main_controller.gd](C:/python/old/restart/client/scripts/ui/main_controller.gd)

## Slice M4: Store Compliance and Release

- [ ] Android packaging/signing/distribution pipeline.
- [ ] iOS packaging/signing/distribution pipeline (if in scope).
- [ ] Privacy/permissions disclosures aligned to platform policy.
- [ ] Crash reporting and support pathway in-client.

Exit:
- [ ] Release candidate passes platform store submission checks.
