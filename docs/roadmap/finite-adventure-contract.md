# Finite Adventure Contract

## Purpose

Define the first authoritative runtime contract for short-form, resettable campaign play.

This mode is meant for:
- single-run authored stories,
- explicit ending states,
- replayable proof-of-concept adventures,
- and smaller curated worlds that should not behave like an always-on shard.

## World Mode

- `world.mode = finite_adventure`

Current baseline behavior:
- only the primary session may issue gameplay commands,
- only the primary session may resume the active run session,
- the runtime exposes finite-adventure policy only when this mode is active.

## Run Lifecycle

Current run states:
1. `not_started`
2. `active`
3. `completed`
4. `abandoned`

Current run commands:
1. `adventure status`
2. `adventure list`
3. `adventure summary [text|markdown|json]`
4. `adventure start [campaign_id]`
5. `adventure checkpoint`
6. `adventure restore`
7. `adventure abandon`
8. `adventure reset`
9. `adventure replay`

## Campaign Binding

- Finite adventure uses the existing campaign graph system as authored content.
- A run starts a campaign definition through `CampaignManager.start_campaign(...)`.
- The default campaign is resolved from:
  1. `finite_adventure.default_campaign_id`
  2. the sole available campaign definition when exactly one exists

## Completion Semantics

- A campaign `END` node marks the run `completed`.
- The campaign outcome becomes the run outcome.
- Current baseline completion metadata:
  - `campaign_id`
  - `current_node`
  - `started_at`
  - `completed_at`
  - `outcome`

## Abandon / Reset / Replay

- `adventure checkpoint`
  - currently available when `checkpoint_policy` is not disabled,
  - currently allowed only during an active run,
  - captures a player-scoped snapshot of run state,
  - intentionally does not promise full NPC/world rewind yet.

- `adventure restore`
  - restores the most recent player-scoped checkpoint,
  - reactivates the run from the checkpointed campaign/node,
  - preserves the checkpoint so the player can restore again if needed,
  - intentionally does not promise full dynamic world rewind yet.

- `adventure abandon`
  - terminates the active run,
  - clears active campaign and quest state for the player,
  - marks the run `abandoned`,
  - preserves the latest checkpoint metadata if one exists.

- `adventure reset`
  - allowed only when no run is active,
  - clears finite-adventure quest/campaign state,
  - restores a bounded pre-run world baseline,
  - restores player vitals and bootstrap location,
  - restores authoritative time/weather state to the captured run-start baseline,
  - returns the run to `not_started`.

- `adventure replay`
  - performs reset semantics,
  - then immediately starts the selected/default campaign again,
  - is gated by `finite_adventure.replay_supported`.

## Transport / Policy Surface

When `world.mode = finite_adventure`, `server_policy` includes:
- `adventure_policy.enabled`
- `adventure_policy.default_campaign_id`
- `adventure_policy.replay_supported`
- `adventure_policy.checkpoint_policy`
- `adventure_policy.run_state`

The runtime also emits:
- `finite_adventure_state`
- `finite_adventure_catalog`
- `finite_adventure_summary`
- `finite_adventure_report`

Current `finite_adventure_catalog` baseline includes:
- `enabled`
- `default_campaign_id`
- `campaigns`

Each catalog entry currently includes:
- `campaign_id`
- `name`
- `description`
- `start_node_id`
- `node_count`
- `is_default`

Current `finite_adventure_state` checkpoint metadata includes:
- `checkpoint_policy`
- `checkpoint_available`
- `checkpoint_saved_at`
- `checkpoint_campaign_id`
- `checkpoint_node`
- `last_summary_available`

Current `finite_adventure_summary` baseline includes:
- `summary_version`
- `campaign_id`
- `campaign_name`
- `status`
- `outcome`
- `started_at`
- `completed_at`
- `duration_seconds`
- `final_node`
- `history`
- `resolution_counts`
- `player_name`
- `player_level`
- `player_gold`
- `final_health`
- `max_health`
- `final_mana`
- `max_mana`
- `quest_log_count`
- `completed_quest_count`
- `archived_quest_count`
- `world_mode`
- `report_formats`

Current `finite_adventure_report` baseline includes:
- `available`
- `format`
- `content`
- `file_name_hint`
- `campaign_id`

Current report formats:
- `text`
- `markdown`
- `json`

## Persistence

Player persistence now stores:
- `finite_adventure_state`
- `active_campaigns`
- `completed_campaigns`

Current checkpoint storage is embedded in `finite_adventure_state.checkpoint` and includes:
- checkpoint metadata,
- and a player-scoped serialized snapshot used for restore.

Current run-summary storage is embedded in `finite_adventure_state.last_summary` and survives:
- normal save/load,
- reset,
- replay,
- and post-run review after completion or abandon.

Current bounded world-baseline storage is embedded in `finite_adventure_state.world_baseline` and is used by:
- `adventure reset`
- `adventure replay`

This baseline currently restores:
- room item state,
- room visited flags and mutable room properties,
- region mutable properties,
- non-summoned NPC state,
- dynamic/instance regions,
- quest board state,
- respawn queue state,
- time state,
- weather state,
- world-field / world-effects cell state,
- transient room runtime residue such as temporary environmental effects and hazard tick caches,
- transient player runtime residue such as active effects, cooldowns, summons, minigame/trade/follow state, and combat message buffers.

This means finite-adventure lifecycle state survives normal player save/load flows.

## Current Limits

This is a baseline, not the final contract.

Not yet guaranteed:
- full simulation rewind for every runtime mutation source,
- checkpoint restore of dynamic NPC/world state,
- campaign-pack validation for ending completeness,
- dedicated client UX for endings and post-run review.

## Next Likely Expansions

1. richer checkpoint tiers beyond the current player-only snapshot baseline
2. richer run-summary/report presentation and export formats
3. stricter reset/replay determinism for the remaining world mutation surfaces not covered by the current bounded baseline
4. client affordances for run state, checkpoints, endings, summaries, and replay flow
