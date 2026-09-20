# Party Lifecycle Contract

## Current Baseline

- World mode gate: party commands are enabled only when `world.mode` resolves to `co_op_party`.
- Party state is player-centered, not transport-centered.
- Runtime exposes party state through `party_state` payloads and includes current party state in transport `hello` payloads.
- Session resume now re-emits `party_state` alongside `session_resumed`, `auth_state`, `server_policy`, and `lock_state`.

## Implemented Commands

- `party status`
- `party list`
- `party invite <player-name>`
- `party join`
- `party decline`
- `party cancel <player-name>`
- `party leave`
- `party leader <player-name>`
- `party disband`

## Implemented Rules

- Invites are required to join.
- Only the current party leader can invite, transfer leadership, or disband.
- Only the current party leader can cancel outstanding invitations.
- A second invite for the same player from the same party is rejected instead of duplicating state.
- When a different leader invites a player who already has a pending invite, the newer invite replaces the older pending invite.
- Joining consumes the pending invite.
- Declining clears the pending invite and notifies the inviting leader when online.
- Cancelling clears the pending invite and notifies the invited player when online.
- Leaving removes only that member.
- If the leader leaves and members remain, leadership transfers to the next remaining member.
- If the last member leaves, the party is removed.
- Offline invites are currently durable for loaded player records: a disconnected player can reconnect later and still `party join` unless the invite was cancelled, replaced, or invalidated.

## Current Payload Shape

`party_state` includes:

- `supported`
- `mode`
- `in_party`
- `party_id`
- `leader_player_id`
- `leader_name`
- `members`
- `pending_invites`
- `outgoing_invites`

## Current Policy Surface

`server_policy.party_policy` includes:

- `enabled`
- `invite_required`
- `leader_controls_membership`
- `decline_supported`
- `cancel_supported`
- `invite_conflict_policy`
- `offline_invites_supported`
- `shared_quest_policy`
- `shared_rewards_policy`
- `loot_policy`

Current config source:

- `feature_profile.raw["party"]`
- supported override keys:
  - `invite_conflict_policy`
  - `offline_invites_supported`
  - `shared_quest_policy`
  - `shared_rewards_policy`
  - `loot_policy`

## Current Runtime Enforcement

- `shared_quest_policy = mirror_all`
  - newly accepted quests are mirrored to current party members,
  - mirrored quests keep per-player `instance_id` values but share a common `party_shared_root_id`,
  - completing the source quest completes mirrored party copies without duplicating the quest reward grant.
- `shared_rewards_policy = split`
  - quest XP and gold are split across current party members with remainder distributed from the front of the recipient list.
- `shared_rewards_policy = leader_claims`
  - quest rewards are routed to the party leader.
- Collection completion rewards now use the same shared reward routing rules as quest rewards.
- Vendor sale proceeds now use the same shared reward routing rules as quest rewards.
- Gambling profit payouts now use the same shared reward routing rules as quest rewards, while stake refunds remain with the acting player.
- Dialogue/topic-script `give_gold` and structured `give_rewards` effects now use the same shared reward routing rules as quest rewards.
- `loot_policy = round_robin`
  - room loot acquired through normal pickup commands rotates across connected party members in the same room.
  - disconnecting a member does not reset the round-robin cursor; when that member reconnects and becomes eligible again, loot fairness resumes from the preserved roster order.
- `loot_policy = leader_discretion`
  - room loot is routed to the party leader when present and eligible.
- `loot_policy = finder_keep`
  - room loot stays with the player who picked it up.
- Scripted `give_item` topic effects now respect party loot routing when they create a tangible item reward.
- Invite conflict semantics are now explicit:
  - `invite_conflict_policy = replace_existing` replaces any older pending invite for that player,
  - the newly inviting leader, the invited player, and the displaced leader all receive deterministic text feedback when online.
- `offline_invites_supported = true`
  - leaders may invite disconnected but already-loaded players,
  - the invite remains pending until it is joined, declined, cancelled, replaced, or invalidated by party teardown.

## Not Yet Implemented

- Mid-quest stage synchronization for mirrored quests
- Shared reward routing beyond current quest/collection/vendor/gambling/combat/dialogue-script coverage (for example other economy grants or scripted currency grants)
- Loot policy enforcement beyond room pickup flows (for example container edge cases, scripted drops, or vendor-like grants)
- Revive/downed-state party rules
- Offline character discovery beyond current loaded player set
- Party-scoped operator diagnostics

## Next Steps

1. Extend shared reward routing to remaining non-quest reward sources such as scripted currency grants and other economy systems.
2. Add broader multi-member reconnect stress tests across TCP and WebSocket transports, including mirrored quest/reward state churn beyond the current two-member presence baseline.
3. Broaden offline invite durability beyond the current loaded-player scope if persistent directory/discovery support is added.
4. Add client UI affordances for party roster, pending invite state, outgoing invites, leader actions, and loot-routing feedback.
