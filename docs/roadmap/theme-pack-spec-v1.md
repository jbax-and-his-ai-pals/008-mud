# Theme Pack Spec v1

## Goal

Allow radically different world themes while preserving one runtime.

## Client Runtime Manifest (v0)

Required:
- `theme_id`
- `display_name`
- `pack_spec_version` (currently `"1"`)
- `runtime_api_min` (dotted numeric, for example `"1.0"`)
- `runtime_api_max` (dotted numeric, for example `"1.0"`)

Optional:
- `ui_strings` (dictionary)
- `lexicon` (dictionary)
- `style_tokens` (dictionary)
- `icon_tokens` (dictionary)

## Known `ui_strings` Keys

- `status_title`
- `inventory_title`
- `journal_title`
- `nearby_title`
- `world_state_title`
- `network_title`
- `asset_title`
- `connect_button`
- `disconnect_button`
- `send_button`
- `command_placeholder`

## Known `lexicon` Keys

- `world_field_id`

## Known `style_tokens` Keys

- `accent_color` (HTML color string)
- `text_color` (HTML color string)
- `ui_density` (integer spacing hint)

## Known `icon_tokens` Keys

- `status_effect`
- `hostile_tag`
- `item_prefix`
- `npc_none`
- `item_none`
- `inventory_item_prefix`
- `inventory_none`
- `inventory_empty`
- `quest_active_prefix`
- `quest_completed_prefix`
- `quest_archived_prefix`
- `quest_none`

## Validation Rules

- Packs without `theme_id` or `display_name` are rejected.
- Packs without compatibility fields are rejected by default validator mode.
- `pack_spec_version` must match the supported spec major (`"1"`).
- Runtime compatibility must satisfy `runtime_api_min <= runtime_api_max`.
- Validator runtime API must fall within the pack range.
- `ui_strings`, `lexicon`, and `style_tokens` must be dictionaries when present.
- `ui_strings`, `lexicon`, `style_tokens`, and `icon_tokens` must be dictionaries when present.
- Missing optional fields always fall back to deterministic defaults.

## Initial Sample Packs Target

1. Classic Fantasy
2. Sci-Fi Frontier
3. Cyberpunk District
4. Post-Apocalyptic Settlement
