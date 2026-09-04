# Mudlet GMCP Examples

This directory contains example Lua scripts for Mudlet to interact with the server's GMCP packages. 

In Mudlet, when the server sends a GMCP package (e.g., `Char.Status {"level": 5}`), Mudlet automatically decodes the JSON and stores it in the global `gmcp` table (e.g., `gmcp.Char.Status.level`). Mudlet also raises a system event named after the package (e.g., `"gmcp.Char.Status"`).

To use these examples in Mudlet, create a new **Script**, set the **Registered Event Handlers** to the corresponding GMCP event, and paste the Lua code.

## 1. Negotiating Packages (`Core.Supports.Set`)

Mudlet automatically sends its supported modules on connect. You can add our custom packages to this list so the server knows it's allowed to send them.

**Event Handler:** `sysConnectionEvent`

```lua
-- Script Name: SendGMCP_Supports
-- Triggers on: sysConnectionEvent

local packages = {
    "Core 1",
    "Comm.Text 1",
    "Char.Status 1",
    "Char.Inventory 1",
    "Room.Nearby 1",
    "Quest.Journal 1",
    "Asset.SVG 1",
    "Asset.Lock.StateDelta 1"
}

-- Send the Core.Supports.Set package to the server
sendGMCP("Core.Supports.Set " .. yajl.to_string(packages))
cecho("\n<cyan>[GMCP] Declared supported packages to server.\n")
```

## 2. Handling Character Status (`Char.Status`)

**Event Handler:** `gmcp.Char.Status`

```lua
-- Script Name: Handle_Char_Status
-- Triggers on: gmcp.Char.Status

local status = gmcp.Char.Status

-- Example payload: {"level": 5, "experience": 1200, "health": {"current": 45, "max": 50}, "name": "Player"}
local hp_curr = status.health and status.health.current or 0
local hp_max = status.health and status.health.max or 0

cecho(string.format("\n<green>[Status Update] %s (Level %d) - HP: %d/%d\n", 
    status.name or "Unknown",
    status.level or 0,
    hp_curr,
    hp_max
))
```

## 3. Handling Room Info (`Room.Nearby`)

**Event Handler:** `gmcp.Room.Nearby`

```lua
-- Script Name: Handle_Room_Nearby
-- Triggers on: gmcp.Room.Nearby

local room = gmcp.Room.Nearby

if room.location then
    cecho(string.format("\n<yellow>[Room] You are in %s / %s\n", 
        room.location.region_name or "Unknown Region",
        room.location.room_name or "Unknown Room"
    ))
end

if room.exits and #room.exits > 0 then
    cecho("<yellow>[Room] Exits: " .. table.concat(room.exits, ", ") .. "\n")
end
```

## 4. Handling Text Effects (`Comm.Text`)

The server may send atmospheric effects along with text.

**Event Handler:** `gmcp.Comm.Text`

```lua
-- Script Name: Handle_Comm_Text
-- Triggers on: gmcp.Comm.Text

local comm = gmcp.Comm.Text

if type(comm) == "string" then
    -- Simple text payload
    cecho("\n<white>" .. comm .. "\n")
elseif type(comm) == "table" and comm.text then
    -- Rich text payload with fx
    if comm.fx and comm.fx.blight and comm.fx.blight > 0 then
        -- Blight effect (dark magenta)
        cecho("\n<magenta>[BLIGHT] " .. comm.text .. "\n")
    else
        -- Normal output
        cecho("\n<white>" .. comm.text .. "\n")
    end
end
```

## 5. Handling SVG Assets (`Asset.SVG`)

While Mudlet cannot easily render SVG directly in the main text console without creating a user window/Geyser element, we can log the asset receipt.

**Event Handler:** `gmcp.Asset.SVG`

```lua
-- Script Name: Handle_Asset_SVG
-- Triggers on: gmcp.Asset.SVG

local asset = gmcp.Asset.SVG

cecho(string.format("\n<cyan>[Asset] Received SVG asset '%s' (Revision: %d, Size: %d bytes)\n", 
    asset.asset_id or "unknown",
    asset.revision or 0,
    asset.byte_length or 0
))

-- To view the raw SVG:
-- echo(asset.svg)
```

## 6. Requesting an Asset Lock (`Asset.Lock.Acquired`)

To acquire a lock on an asset for editing, you send `Asset.Lock.State` with a request. However, game commands are just plain text strings. For lock acquisition, the client sends a `lock acquire` command over the normal socket, and the server replies via GMCP.

**Event Handler:** `gmcp.Asset.Lock.Acquired`

```lua
-- Script Name: Handle_Lock_Acquired
-- Triggers on: gmcp.Asset.Lock.Acquired

local lock = gmcp.Asset.Lock.Acquired

cecho(string.format("\n<green>[Lock] Acquired lock on asset '%s'. Expires at timestamp %f.\n", 
    lock.asset_id, 
    lock.expires_at
))
```
