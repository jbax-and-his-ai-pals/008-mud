# Mud World Editor Export Contract

## Overview
This document defines the schema and export contract required for external tools like `mud-world-editor` to interoperate with the server's data ingestion pipeline.

## Contract 1: JSON Asset Manifest
The editor must output a single, deterministic `.zip` or directory structure with an accompanying `manifest.json`. 

### `manifest.json`
```json
{
  "version": "1.0",
  "author": "Editor",
  "content": {
    "regions": ["data/regions/"],
    "npcs": ["data/npcs/"],
    "items": ["data/items/"],
    "svg": ["assets/svg/"]
  }
}
```

## Contract 2: YAML/JSON strict typing
All exported components must adhere to the data validators defined in `toolkit/data_integrity_validator.py`.
The server strictly requires:
- `obj_id` keys to be globally unique within a domain.
- Required keys for regions (`name`, `rooms`).
- Required keys for NPCs (`health`, `max_health`, `level`, `stats`).
- Required keys for Items (`name`, `description`, `properties`).

## Contract 3: SVG Strict Outlines
Any SVG assets included must be structurally flat (`<svg>` -> `<path>`), avoiding arbitrary XML namespaces or `<script>` tags, which are blocked by the data payload guard.

## Live Reload
The server supports live reloading via the `@dig` and `@edit` pipeline. An external editor can write directly to the selected content-set `data/` folder in local-dev mode, and the `data_integrity_validator.py` can be used as a pre-commit/pre-export validation hook by the editor.
