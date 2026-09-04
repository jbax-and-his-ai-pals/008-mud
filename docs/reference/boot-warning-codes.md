# Boot Warning Codes

This document defines structured boot warning codes emitted by the server and how to use strict startup policy.

## Purpose

- Boot warnings provide machine-readable startup diagnostics.
- Codes are exposed via:
  - `hello.payload.startup_diagnostics`
  - `server_policy.payload.startup_diagnostics`
  - `audit boot-warnings` operator command (`audit_result` event)
- Strict policy can fail startup when disallowed codes are present.

## Config

Set fail-fast policy in server config:

```json
{
  "startup_diagnostics": {
    "fail_on_warning_codes": [
      "content.spells.dir_missing",
      "content.items.file_errors"
    ]
  }
}
```

When any listed code appears at boot, startup aborts with:
`Boot aborted by warning policy. Disallowed warning code(s): ...`

## Current Codes

- `profile.mode.invalid`
- `profile.mods.disabled`
- `content.topics.missing`
- `content.topics.load_error`
- `content.spells.duplicate_ids`
- `content.spells.file_errors`
- `content.spells.dir_missing`
- `content.items.duplicate_ids`
- `content.items.invalid_missing_required`
- `content.items.file_errors`
- `content.items.dir_missing`
- `content.npcs.duplicate_ids`
- `content.npcs.invalid_missing_name`
- `content.npcs.file_errors`
- `content.npcs.dir_missing`
- `provider.weather.unresolved`
- `provider.weather.not_found`
- `provider.world_effects.unresolved`
- `provider.world_effects.not_found`

## Recommended Presets

- Dev/local:
  - `[]` (observe warnings, do not fail)
- CI content validation:
  - `["content.spells.dir_missing","content.items.dir_missing","content.npcs.dir_missing","content.spells.file_errors","content.items.file_errors","content.npcs.file_errors"]`
- Production hard fail:
  - CI list plus `content.topics.load_error`

## Notes

- Duplicate/invalid content warnings are non-fatal by default; include them in fail list only if your pipeline treats warnings as release blockers.
- Keep fail-on lists small and explicit to avoid blocking non-critical operator scenarios.
