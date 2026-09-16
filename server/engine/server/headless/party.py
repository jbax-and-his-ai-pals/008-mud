# engine/server/headless/party.py
"""PartyMixin: extracted from HeadlessServer (see headless_server.py) as part
of the P8 file-splitting pass -- a pure move, no behavior change. Composed
back into HeadlessServer alongside the other headless/* mixins.
"""
from __future__ import annotations

import copy
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import re

import engine.commands  # noqa: F401 - force command module registration
from engine.commands.command_system import CommandProcessor
from engine.core.clock import Clock, SimulatedClock, WallClock
from engine.core.advancement import AdvancementManager
from engine.core.backgrounds import BackgroundManager
from engine.core.collection_manager import CollectionManager
from engine.core.discovery_manager import DiscoveryManager
from engine.core.knowledge_manager import KnowledgeManager
from engine.core.titles import TitleManager
from engine.core.plugin_manager import PluginManager
from engine.dialogue.manager import DialogueManager
from engine.core.time_manager import TimeManager
from engine.core.weather_manager import WeatherManager
from engine.crafting.crafting_manager import CraftingManager
from engine.server.protocol import build_server_event, validate_client_command_envelope
from engine.server.persistence import SqliteStore
from engine.server.world_effects_heartbeat import WorldEffectsHeartbeat
from engine.server.feature_profile import FeatureProfile
from engine.server.entitlement import EntitlementGuard
from engine.server.content_set import ContentSetDefinition, load_content_set
from engine.server.system_providers import (
    BuiltinWeatherProvider,
    BuiltinWorldEffectsProvider,
    CustomWeatherProvider,
    CustomWorldEffectsProvider,
    DisabledWeatherProvider,
    DisabledWorldEffectsProvider,
)
from engine.world.world import World
from engine.world.region import Region
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai import initialize_npc_schedules
from engine.utils.utils import _serialize_item_reference
from engine.server.headless.models import Party  # constructed at runtime below

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from engine.server.headless_server import HeadlessServer
    from engine.server.headless.models import Session


class PartyMixin:
    def build_party_state_payload(self, session_id: str) -> Dict[str, Any]:
        session = self.sessions.get(session_id)
        mode = self.feature_profile.resolved_world_mode()
        if session is None:
            return {
                "supported": mode == "co_op_party",
                "mode": mode,
                "in_party": False,
                "party_id": "",
                "leader_player_id": "",
                "leader_name": "",
                "members": [],
                "pending_invites": [],
                "outgoing_invites": [],
            }

        player_id = str(session.player_id)
        party = self._party_for_player_id(player_id)
        pending_party_id = self.pending_party_invites.get(player_id, "")
        pending_invites: List[Dict[str, Any]] = []
        if pending_party_id and pending_party_id in self.parties:
            inviter_party = self.parties[pending_party_id]
            pending_invites.append(
                {
                    "party_id": inviter_party.party_id,
                    "leader_player_id": inviter_party.leader_player_id,
                    "leader_name": self._display_name_for_player_id(inviter_party.leader_player_id),
                }
            )
        outgoing_invites: List[Dict[str, Any]] = []
        if party is not None and party.leader_player_id == player_id:
            for invited_player_id in self._pending_invitees_for_party(party.party_id):
                outgoing_invites.append(
                    {
                        "player_id": invited_player_id,
                        "name": self._display_name_for_player_id(invited_player_id),
                    }
                )

        if party is None:
            return {
                "supported": mode == "co_op_party",
                "mode": mode,
                "in_party": False,
                "party_id": "",
                "leader_player_id": "",
                "leader_name": "",
                "members": [],
                "pending_invites": pending_invites,
                "outgoing_invites": outgoing_invites,
            }

        members: List[Dict[str, Any]] = []
        for member_player_id in party.member_player_ids:
            online_session = self._find_online_session_by_player_id(member_player_id)
            members.append(
                {
                    "player_id": member_player_id,
                    "name": self._display_name_for_player_id(member_player_id),
                    "is_leader": member_player_id == party.leader_player_id,
                    "online": online_session is not None,
                    "session_id": getattr(online_session, "session_id", ""),
                }
            )

        return {
            "supported": mode == "co_op_party",
            "mode": mode,
            "in_party": True,
            "party_id": party.party_id,
            "leader_player_id": party.leader_player_id,
            "leader_name": self._display_name_for_player_id(party.leader_player_id),
            "members": members,
            "pending_invites": pending_invites,
            "outgoing_invites": outgoing_invites,
        }

    def _party_for_player_id(self, player_id: str) -> Party | None:
        party_id = self.player_party_membership.get(str(player_id), "")
        if party_id == "":
            return None
        return self.parties.get(party_id)

    def party_policy_value(self, key: str, default: Any = None) -> Any:
        raw = getattr(self.feature_profile, "raw", {})
        if not isinstance(raw, dict):
            return default
        party_node = raw.get("party", {})
        if not isinstance(party_node, dict):
            return default
        return party_node.get(key, default)

    def party_invite_conflict_policy(self) -> str:
        return str(self.party_policy_value("invite_conflict_policy", "replace_existing")).strip().lower() or "replace_existing"

    def party_offline_invites_supported(self) -> bool:
        raw_value = self.party_policy_value("offline_invites_supported", True)
        if isinstance(raw_value, str):
            return raw_value.strip().lower() not in {"0", "false", "no", "off", "disabled"}
        return bool(raw_value)

    def _party_impacted_player_ids(self, player_id: str) -> List[str]:
        impacted_player_ids: List[str] = [str(player_id)]
        party = self._party_for_player_id(str(player_id))
        if party is not None:
            impacted_player_ids.extend(list(party.member_player_ids))

        pending_party_id = self.pending_party_invites.get(str(player_id), "")
        if pending_party_id:
            pending_party = self.parties.get(pending_party_id)
            if pending_party is not None:
                impacted_player_ids.extend(list(pending_party.member_player_ids))

        for invited_player_id in self._pending_invitees_for_party(self.player_party_membership.get(str(player_id), "")):
            impacted_player_ids.append(invited_player_id)
        return list(sorted(set(impacted_player_ids)))

    def party_member_player_ids(self, player_id: str) -> List[str]:
        party = self._party_for_player_id(player_id)
        if party is None:
            return [str(player_id)]
        return list(party.member_player_ids)

    def party_member_players(
        self,
        player_id: str,
        *,
        require_same_location_as: Any | None = None,
        require_connected: bool = False,
    ) -> List[Any]:
        players: List[Any] = []
        for member_id in self.party_member_player_ids(player_id):
            member = self.world.players.get(member_id)
            if member is None:
                continue
            if require_same_location_as is not None:
                if (
                    getattr(member, "current_region_id", None) != getattr(require_same_location_as, "current_region_id", None)
                    or getattr(member, "current_room_id", None) != getattr(require_same_location_as, "current_room_id", None)
                ):
                    continue
            if require_connected and self._find_online_session_by_player_id(member_id) is None:
                continue
            players.append(member)
        return players

    def distribute_party_loot(self, actor: Any, item: Any) -> tuple[Any, str]:
        actor_id = str(getattr(actor, "obj_id", ""))
        if self.feature_profile.resolved_world_mode() != "co_op_party":
            return actor, ""
        party = self._party_for_player_id(actor_id)
        if party is None:
            return actor, ""

        policy = str(self.party_policy_value("loot_policy", "round_robin")).strip().lower()
        eligible = self.party_member_players(
            actor_id,
            require_same_location_as=actor,
            require_connected=True,
        )
        if not eligible:
            return actor, ""

        recipient = actor
        if policy == "leader_discretion":
            leader = self.world.players.get(party.leader_player_id)
            if leader is not None and leader in eligible:
                recipient = leader
        elif policy == "finder_keep":
            recipient = actor
        else:
            full_roster: List[Any] = []
            for member_player_id in party.member_player_ids:
                member = self.world.players.get(member_player_id)
                if member is not None:
                    full_roster.append(member)
            if not full_roster:
                full_roster = list(eligible)
            eligible_ids = {str(getattr(player, "obj_id", "")) for player in eligible}
            cursor = self.party_loot_cursors.get(party.party_id, 0)
            recipient = actor
            selected_index = None
            for offset in range(len(full_roster)):
                index = (cursor + offset) % len(full_roster)
                candidate = full_roster[index]
                if str(getattr(candidate, "obj_id", "")) in eligible_ids:
                    recipient = candidate
                    selected_index = index
                    break
            if selected_index is None:
                recipient = actor
                selected_index = cursor % len(full_roster)
            self.party_loot_cursors[party.party_id] = (selected_index + 1) % len(full_roster)

        can_add, _msg = recipient.inventory.can_add_item(item)
        if not can_add:
            actor_can_add, _actor_msg = actor.inventory.can_add_item(item)
            if actor_can_add:
                recipient = actor
            else:
                return actor, ""

        if getattr(recipient, "obj_id", "") == getattr(actor, "obj_id", ""):
            return actor, ""
        return recipient, f"Loot policy routed {item.name} to {recipient.name}."

    def _reward_recipient_players(self, actor: Any) -> List[Any]:
        actor_id = str(getattr(actor, "obj_id", ""))
        if self.feature_profile.resolved_world_mode() != "co_op_party":
            return [actor]
        party = self._party_for_player_id(actor_id)
        if party is None:
            return [actor]

        policy = str(self.party_policy_value("shared_rewards_policy", "split")).strip().lower()
        if policy == "leader_claims":
            leader = self.world.players.get(party.leader_player_id)
            return [leader] if leader is not None else [actor]

        recipients = self.party_member_players(actor_id)
        return recipients or [actor]

    def party_reward_routing_active(self, actor: Any) -> bool:
        actor_id = str(getattr(actor, "obj_id", ""))
        if actor_id == "":
            return False
        if self.feature_profile.resolved_world_mode() != "co_op_party":
            return False
        return self._party_for_player_id(actor_id) is not None

    def _split_int_amount(self, total: int, count: int) -> List[int]:
        if count <= 0:
            return []
        base = total // count
        remainder = total % count
        values = [base for _ in range(count)]
        for index in range(remainder):
            values[index] += 1
        return values

    def grant_party_rewards(self, actor: Any, rewards: Dict[str, Any]) -> str:
        recipients = self._reward_recipient_players(actor)
        if not recipients:
            recipients = [actor]

        msgs: List[str] = []
        xp_total = int(rewards.get("xp", 0) or 0)
        gold_total = int(rewards.get("gold", 0) or 0)

        if xp_total > 0:
            for recipient, amount in zip(recipients, self._split_int_amount(xp_total, len(recipients))):
                if amount <= 0 or recipient.runtime_state.progression is None:
                    continue
                recipient.gain_experience(amount)
                msgs.append(f"{recipient.name} +{amount} XP")

        if gold_total > 0 and self.world.ruleset_system_enabled("economy"):
            currency = self.world.currency_name().capitalize()
            for recipient, amount in zip(recipients, self._split_int_amount(gold_total, len(recipients))):
                if amount <= 0 or recipient.runtime_state.gold is None:
                    continue
                recipient.runtime_state.gold += amount
                msgs.append(f"{recipient.name} +{amount} {currency}")

        item_rewards = rewards.get("items", [])
        if isinstance(item_rewards, list):
            from engine.items.item_factory import ItemFactory

            for item_data in item_rewards:
                item_id = str(item_data.get("item_id", "")).strip()
                quantity = int(item_data.get("quantity", 1) or 1)
                if item_id == "" or quantity <= 0:
                    continue
                for _ in range(quantity):
                    item = ItemFactory.create_item_from_template(item_id, self.world)
                    if item is None:
                        continue
                    recipient, _note = self.distribute_party_loot(actor, item)
                    recipient.inventory.add_item(item, 1)
                    msgs.append(f"{recipient.name} received {item.name}")

        generated_item_data = rewards.get("generated_item_data")
        if isinstance(generated_item_data, dict):
            from engine.items.item_factory import ItemFactory

            item = ItemFactory.from_dict(generated_item_data, actor.world)
            if item is not None:
                recipient, _note = self.distribute_party_loot(actor, item)
                recipient.inventory.add_item(item)
                msgs.append(f"{recipient.name} received {item.name}")

        relationship_rewards = rewards.get("relationships", [])
        if isinstance(relationship_rewards, list):
            from engine.social.relationships import relationship_key

            for reward in relationship_rewards:
                if not isinstance(reward, dict):
                    continue
                template_id = str(reward.get("npc_template_id", "")).strip()
                try:
                    amount = int(reward.get("amount", 0))
                except (TypeError, ValueError):
                    continue
                npc = next(
                    (candidate for candidate in self.world.npcs.values() if getattr(candidate, "template_id", None) == template_id),
                    None,
                )
                if npc is None or amount == 0:
                    continue
                key = relationship_key(npc)
                for recipient in recipients:
                    old_score = int(recipient.npc_relationships.get(key, 0))
                    recipient.npc_relationships[key] = max(0, min(100, old_score + amount))
                    signed_amount = f"+{amount}" if amount > 0 else str(amount)
                    msgs.append(f"{recipient.name} {signed_amount} relationship with {npc.name}")

        if not msgs:
            return ""
        return "Rewards: " + ", ".join(msgs)

    def grant_party_gold(self, actor: Any, amount: int) -> str:
        total = int(amount or 0)
        if total <= 0 or not self.world.ruleset_system_enabled("economy"):
            return ""
        recipients = self._reward_recipient_players(actor)
        if not recipients:
            recipients = [actor]

        msgs: List[str] = []
        currency = self.world.currency_name().capitalize()
        for recipient, share in zip(recipients, self._split_int_amount(total, len(recipients))):
            if share <= 0 or recipient.runtime_state.gold is None:
                continue
            recipient.runtime_state.gold += share
            msgs.append(f"{recipient.name} +{share} {currency}")
        return ", ".join(msgs)

    def _ensure_party_for_leader(self, leader_player_id: str) -> Party:
        existing = self._party_for_player_id(leader_player_id)
        if existing is not None:
            return existing
        party = Party(
            party_id="party_" + uuid.uuid4().hex[:10],
            leader_player_id=leader_player_id,
            member_player_ids=[leader_player_id],
        )
        self.parties[party.party_id] = party
        self.player_party_membership[leader_player_id] = party.party_id
        return party

    def _party_sync_events_for_player_ids(self, player_ids: List[str]) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        seen_session_ids: set[str] = set()
        for session in self.sessions.values():
            if not getattr(session, "connected", False):
                continue
            if session.player_id not in player_ids:
                continue
            if session.session_id in seen_session_ids:
                continue
            seen_session_ids.add(session.session_id)
            events.append(
                self._event(
                    "party_state",
                    session.session_id,
                    self.build_party_state_payload(session.session_id),
                )
            )
        return events

    def build_party_presence_sync_events_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        session = self.sessions.get(session_id)
        if session is None:
            return []
        return self._party_sync_events_for_player_ids(self._party_impacted_player_ids(str(session.player_id)))

    def mirror_party_quest_acceptance(self, actor: Any, new_quest_ids: List[str]) -> List[Dict[str, Any]]:
        if self.feature_profile.resolved_world_mode() != "co_op_party":
            return []
        if str(self.party_policy_value("shared_quest_policy", "leader_driven")).strip().lower() != "mirror_all":
            return []

        actor_id = str(getattr(actor, "obj_id", ""))
        party = self._party_for_player_id(actor_id)
        if party is None:
            return []

        events: List[Dict[str, Any]] = []
        for quest_id in new_quest_ids:
            quest_data = actor.runtime_state.quests.active.get(quest_id)
            if not isinstance(quest_data, dict):
                continue

            root_id = str(quest_data.get("party_shared_root_id", quest_id)).strip() or quest_id
            quest_data["party_shared_root_id"] = root_id
            quest_data["party_shared_party_id"] = party.party_id
            quest_data["party_shared_owner_player_id"] = actor_id

            for member_id in party.member_player_ids:
                if member_id == actor_id:
                    continue
                member = self.world.players.get(member_id)
                if member is None:
                    continue
                already_present = any(
                    str(existing.get("party_shared_root_id", "")) == root_id
                    for existing in (member.runtime_state.quests.active.values() if member.runtime_state.quests is not None else [])
                    if isinstance(existing, dict)
                )
                if already_present:
                    continue
                mirrored = copy.deepcopy(quest_data)
                mirrored["instance_id"] = f"{root_id}_{member_id[-4:]}"
                member.runtime_state.quests.active[mirrored["instance_id"]] = mirrored
                target_session = self._find_online_session_by_player_id(member_id)
                if target_session is not None:
                    events.append(self._event("text", target_session.session_id, f"Party quest shared: {mirrored.get('title', 'Quest')}"))
                    events.append(self._event("quests", target_session.session_id, self._build_quests_payload(target_session.session_id)))
        return events

    def sync_party_quest_completion(self, actor: Any, completed_quest_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.feature_profile.resolved_world_mode() != "co_op_party":
            return []
        if str(self.party_policy_value("shared_quest_policy", "leader_driven")).strip().lower() != "mirror_all":
            return []

        actor_id = str(getattr(actor, "obj_id", ""))
        party = self._party_for_player_id(actor_id)
        if party is None:
            return []
        root_id = str(completed_quest_data.get("party_shared_root_id", completed_quest_data.get("instance_id", ""))).strip()
        if root_id == "":
            return []

        events: List[Dict[str, Any]] = []
        for member_id in party.member_player_ids:
            if member_id == actor_id:
                continue
            member = self.world.players.get(member_id)
            if member is None:
                continue
            mirrored_id = ""
            for candidate_id, candidate_data in (member.runtime_state.quests.active.items() if member.runtime_state.quests is not None else []):
                if not isinstance(candidate_data, dict):
                    continue
                if str(candidate_data.get("party_shared_root_id", "")) == root_id:
                    mirrored_id = candidate_id
                    break
            if mirrored_id == "":
                continue
            mirrored = member.runtime_state.quests.active.pop(mirrored_id)
            mirrored["state"] = "completed"
            member.runtime_state.quests.completed[mirrored_id] = mirrored
            target_session = self._find_online_session_by_player_id(member_id)
            if target_session is not None:
                events.append(self._event("text", target_session.session_id, f"Party quest completed: {mirrored.get('title', 'Quest')}"))
                events.append(self._event("quests", target_session.session_id, self._build_quests_payload(target_session.session_id)))
        return events

    def _pending_invitees_for_party(self, party_id: str) -> List[str]:
        invited: List[str] = []
        for player_id, invited_party_id in self.pending_party_invites.items():
            if invited_party_id == party_id:
                invited.append(str(player_id))
        return sorted(set(invited))

    def _try_handle_party_command(self, session_id: str, text: str) -> tuple[bool, List[Dict[str, Any]]]:
        normalized = str(text).strip()
        lowered = normalized.lower()
        if not lowered.startswith("party"):
            return False, []
        if self.feature_profile.resolved_world_mode() != "co_op_party":
            return True, [self._event("text", session_id, "Party commands are enabled only in world mode 'co_op_party'.")]

        session = self.sessions.get(session_id)
        if session is None:
            return True, [self._event("text", session_id, "Unknown session.")]

        player = self.get_player_for_session(session_id)
        if player is None:
            return True, [self._event("text", session_id, "Create a character before using party commands.")]

        player_id = str(session.player_id)
        parts = normalized.split()
        action = parts[1].lower() if len(parts) >= 2 else "status"
        party = self._party_for_player_id(player_id)
        events: List[Dict[str, Any]] = []

        if action in {"status", "list"}:
            events.append(self._event("party_state", session_id, self.build_party_state_payload(session_id)))
            if party is None:
                events.append(self._event("text", session_id, "You are not currently in a party."))
            else:
                events.append(
                    self._event(
                        "text",
                        session_id,
                        "Party members: %s"
                        % ", ".join(self._display_name_for_player_id(member_id) for member_id in party.member_player_ids),
                    )
                )
            return True, events

        if action == "invite":
            if len(parts) < 3:
                return True, [self._event("text", session_id, "Usage: party invite <player-name>")]
            target_name = normalized.split(None, 2)[2]
            target_player_id, error = self._find_player_id_by_name(target_name)
            if error:
                return True, [self._event("text", session_id, error)]
            if target_player_id == player_id:
                return True, [self._event("text", session_id, "You cannot invite yourself.")]
            target_session = self._find_online_session_by_player_id(target_player_id)
            if target_session is None and not self.party_offline_invites_supported():
                return True, [self._event("text", session_id, "Offline party invites are disabled by server policy.")]
            target_party = self._party_for_player_id(target_player_id)
            if target_party is not None:
                return True, [self._event("text", session_id, "That player is already in a party.")]
            party = self._ensure_party_for_leader(player_id)
            if party.leader_player_id != player_id:
                return True, [self._event("text", session_id, "Only the party leader can invite players.")]
            existing_invite_party_id = self.pending_party_invites.get(target_player_id, "")
            if existing_invite_party_id == party.party_id:
                return True, [self._event("text", session_id, f"{self._display_name_for_player_id(target_player_id)} already has a pending invite from your party.")]
            prior_party = self.parties.get(existing_invite_party_id) if existing_invite_party_id else None
            self.pending_party_invites[target_player_id] = party.party_id
            actor_name = self._display_name_for_player_id(player_id)
            target_name_display = self._display_name_for_player_id(target_player_id)
            if prior_party is not None and prior_party.party_id != party.party_id:
                prior_leader_name = self._display_name_for_player_id(prior_party.leader_player_id)
                events.append(
                    self._event(
                        "text",
                        session_id,
                        f"Invited {target_name_display} to the party. Replaced their pending invite from {prior_leader_name}.",
                    )
                )
            else:
                events.append(self._event("text", session_id, f"Invited {target_name_display} to the party."))
            if target_session is not None:
                if prior_party is not None and prior_party.party_id != party.party_id:
                    prior_leader_name = self._display_name_for_player_id(prior_party.leader_player_id)
                    events.append(
                        self._event(
                            "text",
                            target_session.session_id,
                            f"{actor_name} invited you to join their party, replacing your pending invite from {prior_leader_name}. Use: party join",
                        )
                    )
                else:
                    events.append(self._event("text", target_session.session_id, f"{actor_name} invited you to join their party. Use: party join"))
            if prior_party is not None and prior_party.party_id != party.party_id:
                prior_leader_session = self._find_online_session_by_player_id(prior_party.leader_player_id)
                if prior_leader_session is not None and prior_leader_session.session_id != session_id:
                    events.append(
                        self._event(
                            "text",
                            prior_leader_session.session_id,
                            f"Your pending invite for {target_name_display} was replaced by {actor_name}'s party invite.",
                        )
                    )
            sync_player_ids = list(set(party.member_player_ids + [target_player_id]))
            if prior_party is not None and prior_party.party_id != party.party_id:
                sync_player_ids.extend(prior_party.member_player_ids)
            events.extend(self._party_sync_events_for_player_ids(sync_player_ids))
            return True, events

        if action == "decline":
            pending_party_id = self.pending_party_invites.get(player_id, "")
            if pending_party_id == "":
                return True, [self._event("text", session_id, "You do not have a pending party invite.")]
            pending_party = self.parties.get(pending_party_id)
            self.pending_party_invites.pop(player_id, None)
            events.append(self._event("text", session_id, "Party invite declined."))
            if pending_party is not None:
                leader_session = self._find_online_session_by_player_id(pending_party.leader_player_id)
                if leader_session is not None:
                    events.append(
                        self._event(
                            "text",
                            leader_session.session_id,
                            f"{self._display_name_for_player_id(player_id)} declined your party invite.",
                        )
                    )
                sync_player_ids = list(set(pending_party.member_player_ids + [player_id]))
                events.extend(self._party_sync_events_for_player_ids(sync_player_ids))
            else:
                events.extend(self._party_sync_events_for_player_ids([player_id]))
            return True, events

        if action == "cancel":
            if len(parts) < 3:
                return True, [self._event("text", session_id, "Usage: party cancel <player-name>")]
            if party is None:
                return True, [self._event("text", session_id, "You are not currently in a party.")]
            if party.leader_player_id != player_id:
                return True, [self._event("text", session_id, "Only the current party leader can cancel invitations.")]
            target_name = normalized.split(None, 2)[2]
            target_player_id, error = self._find_player_id_by_name(target_name)
            if error:
                return True, [self._event("text", session_id, error)]
            if self.pending_party_invites.get(target_player_id, "") != party.party_id:
                return True, [self._event("text", session_id, "That player does not have a pending invite from your party.")]
            self.pending_party_invites.pop(target_player_id, None)
            events.append(
                self._event(
                    "text",
                    session_id,
                    f"Cancelled invite for {self._display_name_for_player_id(target_player_id)}.",
                )
            )
            target_session = self._find_online_session_by_player_id(target_player_id)
            if target_session is not None:
                events.append(
                    self._event(
                        "text",
                        target_session.session_id,
                        f"{self._display_name_for_player_id(player_id)} cancelled your party invite.",
                    )
                )
            sync_player_ids = list(set(party.member_player_ids + [target_player_id]))
            events.extend(self._party_sync_events_for_player_ids(sync_player_ids))
            return True, events

        if action == "join":
            pending_party_id = self.pending_party_invites.get(player_id, "")
            if pending_party_id == "":
                return True, [self._event("text", session_id, "You do not have a pending party invite.")]
            if party is not None:
                return True, [self._event("text", session_id, "Leave your current party before joining another one.")]
            invited_party = self.parties.get(pending_party_id)
            if invited_party is None:
                self.pending_party_invites.pop(player_id, None)
                return True, [self._event("text", session_id, "That party invite is no longer valid.")]
            invited_party.member_player_ids.append(player_id)
            self.player_party_membership[player_id] = invited_party.party_id
            self.pending_party_invites.pop(player_id, None)
            leader_name = self._display_name_for_player_id(invited_party.leader_player_id)
            events.append(self._event("text", session_id, f"You joined {leader_name}'s party."))
            leader_session = self._find_online_session_by_player_id(invited_party.leader_player_id)
            if leader_session is not None:
                events.append(self._event("text", leader_session.session_id, f"{self._display_name_for_player_id(player_id)} joined your party."))
            events.extend(self._party_sync_events_for_player_ids(list(invited_party.member_player_ids)))
            return True, events

        if action == "leave":
            if party is None:
                return True, [self._event("text", session_id, "You are not currently in a party.")]
            prior_members = list(party.member_player_ids)
            party.member_player_ids = [member_id for member_id in party.member_player_ids if member_id != player_id]
            self.player_party_membership.pop(player_id, None)
            self.pending_party_invites.pop(player_id, None)
            if not party.member_player_ids:
                self.parties.pop(party.party_id, None)
            elif party.leader_player_id == player_id:
                party.leader_player_id = party.member_player_ids[0]
            events.append(self._event("text", session_id, "You left the party."))
            if party is not None and party.party_id in self.parties:
                leader_session = self._find_online_session_by_player_id(party.leader_player_id)
                if leader_session is not None and leader_session.session_id != session_id:
                    events.append(self._event("text", leader_session.session_id, f"{self._display_name_for_player_id(player_id)} left the party."))
            events.extend(self._party_sync_events_for_player_ids(prior_members))
            return True, events

        if action == "leader":
            if len(parts) < 3:
                return True, [self._event("text", session_id, "Usage: party leader <player-name>")]
            if party is None:
                return True, [self._event("text", session_id, "You are not currently in a party.")]
            if party.leader_player_id != player_id:
                return True, [self._event("text", session_id, "Only the current party leader can transfer leadership.")]
            target_name = normalized.split(None, 2)[2]
            target_player_id, error = self._find_player_id_by_name(target_name)
            if error:
                return True, [self._event("text", session_id, error)]
            if target_player_id not in party.member_player_ids:
                return True, [self._event("text", session_id, "That player is not in your party.")]
            party.leader_player_id = target_player_id
            events.append(self._event("text", session_id, f"Party leadership transferred to {self._display_name_for_player_id(target_player_id)}."))
            events.extend(self._party_sync_events_for_player_ids(list(party.member_player_ids)))
            return True, events

        if action == "disband":
            if party is None:
                return True, [self._event("text", session_id, "You are not currently in a party.")]
            if party.leader_player_id != player_id:
                return True, [self._event("text", session_id, "Only the current party leader can disband the party.")]
            member_ids = list(party.member_player_ids)
            for member_id in member_ids:
                self.player_party_membership.pop(member_id, None)
                self.pending_party_invites.pop(member_id, None)
            self.parties.pop(party.party_id, None)
            for member_id, invited_party_id in list(self.pending_party_invites.items()):
                if invited_party_id == party.party_id:
                    self.pending_party_invites.pop(member_id, None)
            events.append(self._event("text", session_id, "Party disbanded."))
            events.extend(self._party_sync_events_for_player_ids(member_ids))
            return True, events

        return True, [self._event("text", session_id, "Unknown party command. Use: party status|invite|join|decline|cancel|leave|leader|disband")]
