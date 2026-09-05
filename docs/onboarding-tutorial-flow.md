# Onboarding and Tutorial Flow

## Purpose

This document defines the first-run creator and player onboarding flows for the Steam and mobile releases.

---

## Player First-Run Flow

### Step 1: World Selection

On first launch, the player is presented with the World Selection screen:
- A list of available worlds (sample packs bundled at install).
- A "Connect to Server" option for hosted/remote worlds.
- Offline single-player mode is the default selection.

### Step 2: New Game / Load Game

- If no save exists: **New Game** is the only option.
- If a save exists: **Continue** is prominently featured; **New Game** is secondary.

### Step 3: In-World Tutorial Sequence

The bundled `sample_world` pack includes a guided tutorial NPC (`guide_npc`) placed in the starting room (`town:town_square`).

Tutorial NPC triggers:
- **First look**: NPC greets the player and offers to explain commands.
- `talk guide` → NPC walks through `look`, `go`, `inventory`, `help`.
- After 3 moves: NPC mentions `help` as a persistent reference.
- After first combat: NPC offers brief combat tips.

Tutorial state is tracked via player flags in the save file:
```json
{ "tutorial_flags": { "greeted": true, "moved": true, "fought": false } }
```

Tutorial NPC will not repeat completed steps on reload.

### Step 4: Creator Mode Introduction (opt-in)

After 10 minutes of play (or via `settings > creator mode`):
- A non-intrusive banner suggests trying the `@dig` command to add a new room.
- Linking to the content authoring docs.
- Creator mode is not forced on players.

---

## Creator First-Run Flow

For users launching the **Engine + Toolkit** SKU:

1. **Template Selection**: Choose a starter pack (blank world, social world, adventure world).
2. **World Initialization**: `toolkit/pack_tool.py init --template adventure` scaffolds the a content-set `data/` folder.
3. **Guided Edit**: The toolkit README walks through editing the first room, NPC, and item via JSON.
4. **Validation**: `run_content_checks.ps1` is run automatically after template generation.
5. **Launch Server**: `python server/poc_server.py` starts the local headless server.
6. **Connect Client**: The Godot client connects to `ws://localhost:9090` by default.

---

## Tutorial Content Hooks (Engine Side)

The engine exposes a lightweight tutorial event hook so packs can customize onboarding:

```python
# In any command handler or world event:
world.dispatch_event("tutorial_step", {
    "player": player,
    "step": "first_move",
})
```

Packs can listen for these events in their plugin `setup(api)` and respond with custom messages or NPC dialogue.

---

## Accessibility Note

The tutorial must be completable at maximum text scale with high-contrast theme enabled. Refer to the accessibility QA matrix (scenario 1) for validation steps.
