# Content Authoring and Mod Publishing Guidelines

## Purpose

This document defines baseline quality and validation expectations for:

- data content inside content-set packages
- theme packs under `client/themes` and `toolkit/starter_packs`
- server mods under `server/mods` and `mods`

It is intended to keep community content stable across runtime updates and safe for distribution.

## 1. Authoring Rules (Data Content)

- Keep all content in UTF-8 JSON files.
- Prefer additive content changes over in-place mutation of shared IDs.
- Treat IDs as stable contracts once published.
- Avoid removing or renaming referenced IDs without migration notes.

Reference checks enforced by gate:

- JSON integrity: `toolkit/data_integrity_validator.py`
- Cross-file references: `toolkit/reference_integrity_validator.py`

### Required Practices

- Region exits must target valid room references.
- `initial_npcs[].template_id` must reference existing NPC templates.
- Item references (`item_id`, `item_template_id`) must resolve.
- Campaign `quest_template_id` and node transitions must resolve.

## 2. Theme Pack Compatibility Contract

Theme packs must include:

- `theme_id`
- `display_name`
- `pack_spec_version`
- `runtime_api_min`
- `runtime_api_max`

Validation entrypoint:

- `toolkit/pack_tool.py validate ...`

Compatibility policy:

- `pack_spec_version` must match supported pack spec major.
- runtime API must satisfy `runtime_api_min <= runtime_api <= runtime_api_max`.
- packs failing validation checks are not shippable.

## 3. Mod Manifest Compatibility Contract

Each mod must provide `manifest.json` with:

- `plugin_id`
- `name`
- `version`
- `manifest_schema_version`
- `engine_api_min`
- `engine_api_max`
- `capabilities` (array)

Allowed capabilities:

- `command_registration`
- `world_modification`
- `server_broadcast`
- `system_provider_registration`

Validation entrypoint:

- `toolkit/mod_manifest_validator.py --roots server/mods mods`

Runtime enforcement:

- Plugin load path validates manifest requirements and capability whitelist before executing `setup(api)`.

## 4. Publishing Workflow (Minimum)

1. Run `powershell -ExecutionPolicy Bypass -File run_content_checks.ps1`.
2. Resolve all `[ERROR]` findings.
3. Review `[WARN]` findings and either fix or document rationale.
4. Include release notes for:
   - new IDs introduced
   - removed/deprecated IDs
   - compatibility range changes
5. Tag content bundle version and manifest version consistently.

## 5. Compatibility and Deprecation Policy

- Stable IDs and contracts are required within a published content set.
- Breaking changes require:
  - explicit deprecation note
  - migration guidance
  - engine version range update in pack/mod manifests
- New runtime API versions should retain prior behavior where possible, and only tighten contracts with clear changelogs.
