# Server Operator Guide (Master-Config-First)

## Goal

Run and manage servers primarily through one master config, with CLI overrides as optional.

## 1. Core Files

1. Master config:
- `C:\python\old\restart\server\config\server_config.json` (or your custom file)

2. Feature profile:
- `C:\python\old\restart\server\data\profiles\*.profile.json`

3. Optional presets/examples:
- `C:\python\old\restart\server\config\server_config.example.json`
- `C:\python\old\restart\server\config\server_config.static_lockeddown.example.json`

## 2. Baseline Config Model

Top-level sections:

1. `server`
- host/port/save file/asset DB.
- required `--content-set` selection; each game package owns its authored data.

2. `websocket`
- WS port.

3. `feature_profile`
- path to profile JSON that controls system modes.

4. `session`
- default capabilities/entitlements.
- `require_character_creation` (when `true`, sessions start without a bound player and must run `char create <name>` first).
- `gm_auth_token`.
- `authz_detail_level` (`full` or `minimal`).

5. `entitlements`
- gate policy for operator and creator actions.

Note:
- Character creation is always client/session-driven. Auto-spawned session players are not supported.

## 3. Launching

Bootstrap config/profile generation (wizard CLI):

```powershell
python C:\python\old\restart\server\setup_wizard_cli.py --preset creator_sandbox --server-name "Builder Lab"
```

TCP server:

```powershell
python C:\python\old\restart\server\poc_server.py --config C:\python\old\restart\server\config\server_config.json
```

TCP server from migrated fixture content:

```powershell
python server/poc_server.py --content-set content_sets/fantasy_frontier
```

WebSocket server:

```powershell
python C:\python\old\restart\server\poc_ws_server.py --config C:\python\old\restart\server\config\server_config.json
```

Launch using latest refreshed fixture selected by `LATEST_REFRESH.json`:

```powershell
python C:\python\old\restart\server\launch_from_latest_fixture.py --transport tcp
python C:\python\old\restart\server\launch_from_latest_fixture.py --transport ws
```

## 4. Feature Modes vs Entitlement Gates

Two layers control behavior:

1. Feature profile modes
- enable/disable/read-only behavior (combat, authoring, weather, world mutation, etc).

2. Entitlement gates
- authorize specific operations (profile apply, world debug, creator authoring, etc).

Rule of thumb:
- Profile says if a system can exist.
- Entitlements say who can use sensitive operations.

## 5. Security/Visibility Defaults

1. Public/shared servers:
- prefer `session.authz_detail_level: "minimal"`.
- require GM token for privileged operations.

2. Internal/dev servers:
- `authz_detail_level: "full"` can help diagnose operator setup.

## 6. GM and Operator Actions

1. GM auth lifecycle:
- `gm auth <token>`
- `gm status`
- `gm deauth`

2. Operator actions are also gated by profile + entitlements.
- If an action is hidden/denied, check:
  - profile mode,
  - GM status,
  - entitlement gate config.

## 7. Recommended Starter Patterns

1. Static narrative world:
- start from `server_config.static_lockeddown.example.json`.

2. Social no-combat world:
- disable combat in profile, keep mutation/authoring as needed.

3. Creator sandbox:
- mutable world + broader entitlements in controlled environment.

## 8. Troubleshooting Checklist

1. Policy mismatch:
- run `server policy` from client and verify profile modes.

2. Operator action denied:
- verify entitlement gate + session entitlements + GM session state.

3. Unexpected content failures:
- run toolkit validators before launch:
  - `data_integrity_validator.py`
  - `reference_integrity_validator.py`

## 9. Next Docs To Add

1. Full config schema reference.
2. Event/protocol reference for client integrators.
3. Backup/restore/migration runbook details.
