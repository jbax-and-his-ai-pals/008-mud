# Godot Test Client Shell

Minimal GUI test client for the PoC MUD server.

## Run

1. Start Fantasy Frontier from the repository root:
```powershell
python server/launch_content_set.py --transport tcp --host 127.0.0.1 --port 8765
```
Alternative WebSocket PoC server:
```powershell
python server/launch_content_set.py --transport ws --host 127.0.0.1 --port 8766
```

2. Open Godot 4.x and import project at:
`client/project.godot`

3. Run scene:
`res://scenes/main.tscn`

4. In client:
- Host: `127.0.0.1`
- Port: `8765` (TCP) or `8766` (WebSocket PoC)
- Transport: select `TCP` or `WebSocket`
- Click `Connect`
- Send commands like `look`, `status`, `go north`
- Test atmosphere rendering with `blighttest`
- Test SVG runtime rendering with `svgtest`

## Accessibility Toggles (Client Capability Flags)

Type these into the command input:
- `a11y motion off` to enable reduced-motion capability.
- `a11y motion on` to disable reduced-motion capability.
- `a11y sr on` to enable screen-reader mode capability.
- `a11y sr off` to disable screen-reader mode capability.

When reduced motion is enabled, `blighttest` is downgraded by the server to non-animated text.
When screen-reader mode is enabled, SVG asset preview falls back to alt text only.

## Theme Pack Commands

Type these into the command input:
- `theme list` to list discovered theme packs in `res://themes`.
- `theme use <theme_id>` to apply a pack at runtime.

Bundled theme IDs:
- `default`
- `fantasy_classic`
- `scifi_frontier`

Theme packs are validated at load-time. Invalid packs are skipped with a log warning.
Supported optional `style_tokens` keys:
- `accent_color` (HTML color)
- `text_color` (HTML color)
- `ui_density` (integer spacing hint)

Supported optional `icon_tokens` keys:
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

## Notes

- This shell currently uses TCP JSON-lines transport for immediate local testing.
- WebSocket server endpoint now exists (`poc_ws_server.py`) using the same envelope contract.
