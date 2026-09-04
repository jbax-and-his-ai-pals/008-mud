# Server Setup Wizard Track

## Goal

Ship a guided, low-friction path for users to create and run a server without hand-editing JSON.

## Scope

- Can be standalone or integrated into a broader creator toolkit UI.
- Must output valid server config/profile files compatible with headless runtime.
- Must support "safe defaults" and "advanced mode".

## Checklist

- [ ] Define wizard IA and step flow:
  - server identity and network,
  - world style/profile choice,
  - system toggles (combat/weather/world mutation/authoring),
  - access control (GM token, entitlement detail mode),
  - persistence and backup defaults.
- [ ] Add config generation contract (schema + round-trip validation).
- [ ] Add "preview effective policy" panel before final apply.
- [ ] Add desktop client path to launch/connect to the created server.
- [ ] Add validation/error UX with actionable fixes.
- [ ] Add non-interactive export/import path for automation and CI.
- [ ] Add tests for generated-config correctness against resolver behavior.

## Exit Gate

- [ ] A new user can stand up a server and connect a client in under 10 minutes without editing raw config files.
