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

Twenty codes, which is the complete set `fail_on_warning_codes` accepts.

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
- `weather.provider.not_found`
- `weather.provider.missing`
- `world_effects.provider.not_found`
- `world_effects.provider.missing`
- `runtime.command.failed`

Two of these are not boot-time literals and are still accepted: the
`content.topics.*` pair comes from `KnowledgeManager._emit_warning` when
`topics.json` is unreadable or absent, and `runtime.command.failed` is emitted
while the server runs, once a command has failed repeatedly. Everything else is a
`code=` at the point the warning is raised.

Note the shape: `weather.provider.not_found`, not `provider.weather.not_found`.
Four codes on this page had the two halves transposed until 2026-09-19.

Every code above is emitted by the engine. The server checks the list at boot —
see **Typos are refused** below.

## Typos are refused

`fail_on_warning_codes` is matched by exact string, so a misspelled code appears
in no warning and the policy simply never fires — the config looks strict and is
not. Until 2026-09-19 four codes on this page were transposed
(`provider.weather.unresolved` for `weather.provider.not_found` and so on) and a
fifth (`runtime.command.failed`) was missing, which is exactly that failure, and
it was invisible because a wrong code produces no output at all.

The server therefore checks the list before it checks the warnings. A code that is
not one of the twenty above **aborts startup**, naming the offending entry:

```
Boot aborted by warning policy. Unknown warning code(s): provider.weather.not_found.
See docs/reference/boot-warning-codes.md for the codes this server emits.
```

This is deliberate: a fail-on list is a safety setting, and one that cannot fire is
worse than none, because it is trusted. `KNOWN_BOOT_WARNING_CODES` in
`engine/server/headless/boot_warnings.py` is the authority, and
`server/tests/singles/test_boot_warning_codes.py` fails if this page, that
constant, and the codes the engine actually emits ever disagree.

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
