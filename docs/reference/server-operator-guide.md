# Server Operator Guide (Master-Config-First)

> **Verified 2026-09-20.** Every command below was run in this checkout. Two of
> them used to fail as written: the wizard requires `--content-set`, and
> `poc_server.py` requires it too, so a bare `--config` launch exits with a
> missing-argument error. What the wizard actually writes is
> `<server-slug>.server_config.json`, not `server_config.json`.

## Goal

Run and manage servers primarily through one master config, with CLI overrides as optional.

## 1. Core Files

1. Master config — **you write it; nothing creates it for you.**
   The wizard (section 3) writes `<server-slug>.server_config.json` into
   `--config-dir` (default `server/config/`). `server/config/server_config.json`
   is only `poc_server.py`'s default *path*, and it does not exist in a fresh
   checkout, so either generate one or pass `--config` explicitly.

2. Feature profile — profiles live **in the content set they describe**:
   - `content_sets/<set>/data/profiles/*.profile.json`
   - `fantasy_frontier` ships five: `static_world`, `locked_static_no_combat`,
     `social_no_combat`, `creative_world`, `mobile_low_fx`.
   - The wizard writes a new one here, named after the server.

3. Optional presets/examples:
- `server/config/server_config.example.json`
- `server/config/server_config.static_lockeddown.example.json`

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

Every command below runs from the repository root with the project interpreter
(`.venv\Scripts\python.exe` after `bootstrap.ps1`; `python` is shorthand).

Bootstrap config + profile generation (wizard CLI). It writes a profile into the
content set and a config into `--config-dir`, and **refuses to overwrite** an
existing file unless you pass `--force`:

```powershell
python server/setup_wizard_cli.py --preset creator_sandbox --server-name "Builder Lab" --content-set content_sets/fantasy_frontier
```

Launch a content set over either transport — the supported entry point, which
also owns `--presentation-mode player|test`:

```powershell
python server/launch_content_set.py --transport tcp --content-set content_sets/fantasy_frontier
python server/launch_content_set.py --transport ws  --content-set content_sets/fantasy_frontier
python server/launch_content_set.py --dry-run        # print the resolved command, start nothing
```

The servers underneath take the same arguments directly:

```powershell
python server/poc_server.py    --content-set content_sets/fantasy_frontier --config server/config/<slug>.server_config.json
python server/poc_ws_server.py --content-set content_sets/fantasy_frontier --config server/config/<slug>.server_config.json
```

`--content-set` is **required** by both servers and accepts a content-set
directory or a manifest path. There is no longer a launcher that picks a fixture
from `LATEST_REFRESH.json`; that file is a log of a past fixture refresh, and
`run_content_checks.py` reads it to find the tree it recorded.

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
- start from `server/config/server_config.static_lockeddown.example.json`.
- the matching shipped profile is `locked_static_no_combat.profile.json`.

2. Social no-combat world:
- ship profile `social_no_combat.profile.json`, or disable combat in your own
  profile and keep mutation/authoring as needed.

3. Creator sandbox:
- mutable world + broader entitlements in controlled environment
  (`--preset creator_sandbox`).

## 8. Troubleshooting Checklist

1. Policy mismatch:
- run `server policy` from client and verify profile modes.

2. Operator action denied:
- verify entitlement gate + session entitlements + GM session state.

3. Unexpected content failures:
- run the one content gate before launch, which runs both validators across every
  set and plays each one:
  - `python run_content_checks.py`
  - individually: `toolkit/data_integrity_validator.py`,
    `toolkit/reference_integrity_validator.py`

## 9. Next Docs To Add

1. Full config schema reference.
2. Event/protocol reference for client integrators.
3. Backup/restore/migration runbook details.
