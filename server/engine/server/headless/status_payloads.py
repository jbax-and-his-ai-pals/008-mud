# engine/server/headless/status_payloads.py
"""StatusPayloadsMixin: extracted from HeadlessServer (see headless_server.py) as part
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
from engine.contracts.resources import (
    ability_resource_id,
    ability_resource_label,
    ability_resource_short,
)
from engine.crafting.crafting_manager import CraftingManager
from engine.crafting.recipe import Recipe
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

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from engine.server.headless_server import HeadlessServer
    from engine.server.headless.models import Session, Party


class StatusPayloadsMixin:
    def _is_status_command(self, text: str) -> bool:
        normalized = text.strip().lower()
        return normalized in {"status", "stat", "st"}

    def _is_combat_command(self, text: str) -> bool:
        """Whether a command should refresh the live encounter presentation."""
        parts = text.strip().lower().split()
        return bool(parts) and parts[0] in {"attack", "kill", "fight", "cast", "combat", "cstat", "fightstatus", "flee", "retreat"}

    def _build_combat_payload(self, session_id: str) -> Dict[str, Any]:
        """Return a small UI-ready encounter snapshot from authoritative state."""
        player = self.get_player_for_session(session_id)
        if not player or player.runtime_state.combat is None:
            return {"active": False, "targets": [], "recent_actions": [], "suggested_actions": ["look", "nearby"]}

        combat = player.runtime_state.combat
        targets: List[Dict[str, Any]] = []
        for target in sorted(list(combat.targets), key=lambda value: str(getattr(value, "name", ""))):
            if not bool(getattr(target, "is_alive", False)):
                continue
            if getattr(target, "current_region_id", None) != player.current_region_id or getattr(target, "current_room_id", None) != player.current_room_id:
                continue
            targets.append({
                "name": str(getattr(target, "name", "Unknown target")),
                "health": int(getattr(target, "health", 0)),
                "max_health": int(getattr(target, "max_health", 0)),
                "current_target": target is combat.target,
            })

        active = bool(combat.in_combat and targets)
        suggested_actions: List[str] = []
        if active:
            current = next((target for target in targets if target["current_target"]), targets[0])
            suggested_actions.append(f"attack {current['name']}")
            suggested_actions.extend(["status", "flee"])
        else:
            suggested_actions.extend(["look", "nearby"])
        return {
            "active": active,
            "targets": targets,
            "recent_actions": [str(message) for message in getattr(player, "combat_messages", [])[-3:]],
            "suggested_actions": suggested_actions,
        }

    def _build_status_payload(self, session_id: str) -> Dict[str, Any]:
        player = self.get_player_for_session(session_id)
        if not player:
            payload = {
                "name": "Unknown",
                "health": {"current": 0, "max": 0},
                "alive": False,
                "effects": [],
            }
            if self.world.uses_abilities():
                payload["ability_resource"] = self._ability_resource_payload(None)
            return payload

        effect_names: List[str] = []
        for effect in getattr(player, "active_effects", []):
            # active_effects entries are plain dicts (see GameObject.apply_effect),
            # not objects, so the name must be read via mapping access.
            effect_name = effect.get("name") if isinstance(effect, dict) else getattr(effect, "name", None)
            if effect_name:
                effect_names.append(str(effect_name))
            else:
                effect_names.append(str(effect))

        payload = {
            "name": str(getattr(player, "name", "Player")),
            "health": {
                "current": int(getattr(player, "health", 0)),
                "max": int(getattr(player, "max_health", 0)),
            },
            "alive": bool(getattr(player, "is_alive", False)),
            "effects": effect_names,
        }
        if self.world.uses_progression() and player.runtime_state.progression is not None:
            payload["level"] = int(player.runtime_state.progression.level)
            payload["experience"] = int(player.runtime_state.progression.experience)
        if self.world.uses_abilities() and player.runtime_state.magic is not None:
            payload["ability_resource"] = self._ability_resource_payload(player)
        return payload

    def _ability_resource_payload(self, player: Optional[Any]) -> Dict[str, Any]:
        """The pool an ability spends, named by the content set.

        One payload key for every content set, and the *name* travels in it: a
        client that hardcoded "mana" would show the wrong word to a game whose
        abilities draw on charge, and the field list alone cannot say what the
        pool is called.
        """
        state = getattr(getattr(player, "runtime_state", None), "magic", None) if player else None
        return {
            "id": ability_resource_id(self.world),
            "label": ability_resource_label(self.world),
            "short": ability_resource_short(self.world),
            "current": int(getattr(state, "mana", 0) or 0),
            "max": int(getattr(state, "max_mana", 0) or 0),
        }

    def _is_inventory_command(self, text: str) -> bool:
        normalized = text.strip().lower()
        return normalized in {"inventory", "inv", "i"}

    def _is_crafting_command(self, text: str) -> bool:
        parts = text.strip().lower().split()
        return bool(parts) and parts[0] in {"recipes", "craftlist", "craft", "make", "salvage", "breakdown", "scrap", "attach", "install", "detach"}

    def _is_attachment_command(self, text: str) -> bool:
        parts = text.strip().lower().split()
        return bool(parts) and parts[0] in {"attach", "install", "detach"}

    def _is_collection_command(self, text: str) -> bool:
        """Identify actions that inspect or can change collection progress."""
        parts = text.strip().lower().split()
        return bool(parts) and parts[0] in {"collection", "collections", "turnin", "donate", "deposit", "gather", "mine", "forage", "harvest", "take", "get", "pickup"}

    def _is_discovery_command(self, text: str) -> bool:
        """Actions that inspect or can add a player discovery."""
        parts = text.strip().lower().split()
        return bool(parts) and parts[0] in {"discoveries", "discovery", "catalogue", "catalog", "gather", "mine", "forage", "harvest", "take", "get", "pickup", "craft", "make"}

    def _is_relationship_command(self, text: str) -> bool:
        parts = text.strip().lower().split()
        return bool(parts) and parts[0] in {"relationship", "bond", "friendship", "relationships", "bonds", "friends", "give", "fulfill"}

    def _build_relationships_payload(self, session_id: str) -> Dict[str, Any]:
        from engine.social.relationships import next_relationship_milestone, relationship_key, relationship_tier
        player = self.get_player_for_session(session_id)
        if not player:
            return {"relationships": []}
        npcs = {relationship_key(npc): npc for npc in self.world.npcs.values()}
        entries = []
        for key, score in sorted(player.npc_relationships.items(), key=lambda entry: (-int(entry[1]), entry[0])):
            npc = npcs.get(key)
            milestone = next_relationship_milestone(player, npc, int(score)) if npc else None
            entries.append({
                "npc_id": key,
                "name": str(getattr(npc, "name", key.replace("_", " ").title())),
                "score": int(score),
                "tier": relationship_tier(int(score), self.world),
                "next_milestone": int(milestone["min"]) if milestone else None,
            })
        return {"relationships": entries}

    def _build_discoveries_payload(self, session_id: str) -> Dict[str, Any]:
        player = self.get_player_for_session(session_id)
        manager = getattr(getattr(self.world, "game", None), "discovery_manager", None)
        if not player or manager is None:
            return {"discoveries": []}
        entries: List[Dict[str, Any]] = []
        for discovery_id, definition in sorted(manager.discoveries.items()):
            if discovery_id not in player.discoveries or not isinstance(definition, dict):
                continue
            progress = player.discoveries.get(discovery_id, {})
            entries.append({
                "discovery_id": discovery_id,
                "name": str(definition.get("name", discovery_id)),
                "description": str(definition.get("description", "")),
                "unlocked_day": int(progress.get("day", 0)) if isinstance(progress, dict) else 0,
            })
        return {"discoveries": entries, "total_authored": len(manager.discoveries)}

    def _build_collections_payload(self, session_id: str) -> Dict[str, Any]:
        """Return a content-neutral ledger view for active item collections."""
        player = self.get_player_for_session(session_id)
        manager = getattr(getattr(self.world, "game", None), "collection_manager", None)
        if not player or manager is None:
            return {"collections": []}
        collections: List[Dict[str, Any]] = []
        for collection_id, definition in sorted(manager.collections.items()):
            if not isinstance(definition, dict):
                continue
            turned_in = set(player.collections_progress.get(collection_id, []))
            items: List[Dict[str, Any]] = []
            for item_id in definition.get("items", []):
                template = self.world.item_templates.get(item_id, {})
                items.append({
                    "item_id": str(item_id),
                    "name": str(template.get("name", item_id)),
                    "turned_in": item_id in turned_in,
                    "in_inventory": player.inventory.count_item(item_id) > 0,
                })
            collections.append({
                "collection_id": str(collection_id),
                "name": str(definition.get("name", collection_id)),
                "description": str(definition.get("description", "")),
                "discovered": collection_id in player.collections_progress,
                "completed": bool(player.collections_completed.get(collection_id, False)),
                "turned_in_count": len(turned_in),
                "required_count": len(items),
                "items": items,
            })
        return {"collections": collections}

    def _build_crafting_payload(self, session_id: str) -> Dict[str, Any]:
        player = self.get_player_for_session(session_id)
        manager = self.crafting_manager
        if not player or manager is None:
            return {"stations": [], "recipes": []}
        stations = sorted(manager.get_nearby_stations(player))
        recipes: List[Dict[str, Any]] = []
        for recipe_id, recipe in sorted(manager.recipes.items()):
            ingredients: List[Dict[str, Any]] = []
            for ingredient in recipe.ingredients:
                options = Recipe.ingredient_options(ingredient)
                # An ingredient may reference a family or a capability instead
                # of a template. `item_id` stays whatever the primary option
                # names (empty for a rule reference), and `reference` tells a
                # client which kind of thing it is.
                item_id = str(ingredient.get("item_id", "") or "")
                template = self.world.item_templates.get(item_id, {})
                ingredients.append({
                    "item_id": item_id,
                    "reference": Recipe.reference_label(ingredient),
                    "name": Recipe.describe_reference(ingredient, self.world),
                    "have": int(manager.count_ingredient(player, ingredient)),
                    "need": max(1, int(ingredient.get("quantity", 1))),
                    "quality_contributes": ingredient.get("quality_contributes", True) is not False,
                    "min_material_quality": Recipe.minimum_quality(ingredient),
                    "acceptable": [
                        {
                            "item_id": str(option.get("item_id", "") or ""),
                            "reference": Recipe.reference_label(option),
                            "name": Recipe.describe_reference(option, self.world),
                            "quality_penalty": int(option.get("quality_penalty", 0) or 0),
                        }
                        for option in options
                    ],
                    "template_name": str(template.get("name", item_id)) if item_id else "",
                })
            craftable, blocker = manager.can_craft(player, recipe)
            result = self.world.item_templates.get(recipe.result_item_id, {})
            craft_count = int(getattr(player, "recipe_craft_counts", {}).get(recipe_id, 0))
            milestone = recipe.familiarity_milestone(craft_count)
            quality_preview = manager.quality_preview(player, recipe)
            material_quality_score = int(quality_preview["material_quality_score"])
            quality_tier = quality_preview["tier"]
            recipes.append({
                "recipe_id": recipe_id,
                "name": str(recipe.name),
                "description": str(recipe.description),
                "station": str(recipe.station_required or "handcraft"),
                "station_display": str(recipe.station_display),
                "craftable": bool(craftable),
                "blocker": str(blocker),
                "result": {"item_id": str(recipe.result_item_id), "name": str(result.get("name", recipe.result_item_id)), "quantity": int(recipe.result_quantity)},
                "ingredients": ingredients,
                "craft_count": craft_count,
                "familiarity_label": str(milestone.get("label", "Unpracticed")) if milestone else "Unpracticed",
                "quality_label": str(quality_tier.get("label", "Standard")) if quality_tier else "Standard",
                "material_quality_score": material_quality_score,
                "quality_contributors": quality_preview["contributors"],
                "next_quality_tier": quality_preview["next_tier"],
            })
        return {"stations": stations, "recipes": recipes}

    def _build_inventory_payload(self, session_id: str) -> Dict[str, Any]:
        player = self.get_player_for_session(session_id)
        if not player or not hasattr(player, "inventory"):
            return {
                "items": [],
                "equipped": [],
                "slots_used": 0,
                "slots_max": 0,
                "total_weight": 0.0,
                "max_weight": 0.0,
            }

        inventory = player.inventory
        items: List[Dict[str, Any]] = []
        for idx, slot in enumerate(inventory.slots):
            if not slot.item:
                continue
            item_weight = float(getattr(slot.item, "weight", 0.0))
            attachments = slot.item.get_property("attachments", [])
            attachment_names = [
                str(entry.get("name", entry.get("item_id", "attachment")))
                for entry in attachments
                if isinstance(entry, dict)
            ] if isinstance(attachments, list) else []
            items.append(
                {
                    "slot_index": idx,
                    "item_id": str(getattr(slot.item, "obj_id", "unknown")),
                    "name": str(getattr(slot.item, "name", "Unknown Item")),
                    "quantity": int(getattr(slot, "quantity", 1)),
                    "stackable": bool(getattr(slot.item, "stackable", False)),
                    "weight_each": item_weight,
                    "weight_total": item_weight * int(getattr(slot, "quantity", 1)),
                    "attachments": attachment_names,
                }
            )

        equipped: List[Dict[str, Any]] = []
        for slot_name, item in player.equipment.items():
            if item is None:
                continue
            attachments = item.get_property("attachments", [])
            attachment_names = [
                str(entry.get("name", entry.get("item_id", "attachment")))
                for entry in attachments
                if isinstance(entry, dict)
            ] if isinstance(attachments, list) else []
            equipped.append({
                "slot": str(slot_name),
                "item_id": str(getattr(item, "obj_id", "unknown")),
                "name": str(getattr(item, "name", "Unknown Item")),
                "attachments": attachment_names,
            })

        return {
            "items": items,
            "equipped": equipped,
            "slots_used": len(items),
            "slots_max": int(getattr(inventory, "max_slots", len(inventory.slots))),
            "total_weight": float(inventory.get_total_weight()),
            "max_weight": float(getattr(inventory, "max_weight", 0.0)),
        }

    def _is_quest_command(self, text: str) -> bool:
        parts = text.strip().lower().split()
        if not parts:
            return False
        return parts[0] in {"journal", "quests", "log", "j"}

    def _build_quests_payload(self, session_id: str) -> Dict[str, Any]:
        player = self.get_player_for_session(session_id)
        if not player or player.runtime_state.quests is None:
            return {"active": [], "completed": [], "archived": []}

        active_items = self._normalize_quest_entries(player.runtime_state.quests.active, include_states={"active", "ready_to_complete"})
        completed_items = self._normalize_quest_entries(player.runtime_state.quests.completed, include_states=None)
        archived_items = self._normalize_quest_entries(player.runtime_state.quests.archived, include_states=None)
        return {
            "active": active_items,
            "completed": completed_items,
            "archived": archived_items,
        }

    def _quest_state_signature(self, player: Any) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        if player is None or player.runtime_state.quests is None:
            return ((), (), ())
        active_ids = tuple(sorted(str(key) for key in player.runtime_state.quests.active.keys()))
        completed_ids = tuple(sorted(str(key) for key in player.runtime_state.quests.completed.keys()))
        archived_ids = tuple(sorted(str(key) for key in player.runtime_state.quests.archived.keys()))
        return (active_ids, completed_ids, archived_ids)

    def _is_nearby_command(self, text: str) -> bool:
        normalized = text.strip().lower()
        if normalized in {"nearby", "scan", "who"}:
            return True
        parts = normalized.split()
        if not parts:
            return False
        # Nearby payloads are used by the client room panel. Emit them for both
        # explicit observation commands and movement commands so navigation updates
        # the UI without requiring a follow-up "look".
        if parts[0] in {"look", "l", "go", "north", "south", "east", "west", "up", "down", "n", "s", "e", "w", "u", "d"}:
            return True
        return False

    def _build_nearby_payload(self, session_id: str) -> Dict[str, Any]:
        player = self.get_player_for_session(session_id)
        # Use the session player's location when available so that each session
        # sees its own room rather than a process-global accessor
        # (world.current_region_id is backed by world.player which is None in
        # headless multi-session mode).
        if player:
            region_id = str(getattr(player, "current_region_id", "") or "")
            room_id = str(getattr(player, "current_room_id", "") or "")
        else:
            region_id = str(self.world.current_region_id or "")
            room_id = str(self.world.current_room_id or "")

        region = self.world.get_region(region_id) if region_id else None
        room = region.get_room(room_id) if region and room_id else None
        if not room:
            return {
                "location": {"region_id": "", "region_name": "Unknown", "room_id": "", "room_name": "Unknown"},
                "exits": [],
                "npcs": [],
                "items": [],
                "interactions": [],
            }

        exits = sorted([str(direction) for direction in room.exits.keys()])
        room_npcs = list(self.world.get_npcs_in_room(region_id, room_id))
        npcs = sorted(
            [
                {
                    "npc_id": str(getattr(npc, "obj_id", "unknown")),
                    "name": str(getattr(npc, "name", "Unknown NPC")),
                    "faction": str(getattr(npc, "faction", "unknown")),
                    "hostile": (
                        self.feature_profile.combat_mode != "disabled"
                        and str(getattr(npc, "faction", "")) == "hostile"
                    ),
                }
                for npc in room_npcs
            ],
            key=lambda n: str(n.get("name", "")),
        )
        # Prefer named/authored NPCs over content's generic randomized-name
        # filler (e.g. ambient wandering villagers) when picking who gets a
        # "talk" suggestion, so a room full of decorative extras doesn't crowd
        # out the NPC a new player actually needs to notice.
        def _is_generic_filler(npc: Any) -> bool:
            template = self.world.npc_templates.get(getattr(npc, "template_id", None), {})
            return bool(template.get("properties", {}).get("randomize_name"))

        interaction_npc_names = [
            str(getattr(npc, "name", "npc"))
            for npc in sorted(room_npcs, key=lambda npc: (_is_generic_filler(npc), str(getattr(npc, "name", ""))))
        ]
        items = sorted(
            [
                {
                    "item_id": str(getattr(item, "obj_id", "unknown")),
                    "name": str(getattr(item, "name", "Unknown Item")),
                    # Item ``can_take`` is the authoritative gameplay rule.
                    # Do not advertise structural puzzle objects as pickups just
                    # because they do not expose an obsolete ``portable`` field.
                    "portable": bool(item.get_property("can_take", True)),
                }
                for item in self.world.get_items_in_room(region_id, room_id)
            ],
            key=lambda i: str(i.get("name", "")),
        )

        interactions: List[str] = []
        for direction in exits[:4]:
            interactions.append(f"go {direction}")
        for npc_name in interaction_npc_names[:3]:
            interactions.append(f"talk {npc_name}")
        for item in items[:3]:
            if item.get("portable", True):
                interactions.append(f"take {item.get('name', 'item')}")

        return {
            "location": {
                "region_id": region_id,
                "region_name": str(getattr(region, "name", "Unknown Region")),
                "room_id": room_id,
                "room_name": str(getattr(room, "name", "Unknown Room")),
            },
            "exits": exits,
            "npcs": npcs,
            "items": items,
            "interactions": interactions,
        }

    def _normalize_quest_entries(self, quest_map: Any, include_states: Optional[set[str]]) -> List[Dict[str, Any]]:
        if not isinstance(quest_map, dict):
            return []
        entries: List[Dict[str, Any]] = []
        for quest_id, raw in quest_map.items():
            if not isinstance(raw, dict):
                continue
            state = str(raw.get("state", "unknown"))
            if include_states is not None and state not in include_states:
                continue
            entries.append(
                {
                    "quest_id": str(quest_id),
                    "title": str(raw.get("title", "Unnamed Quest")),
                    "state": state,
                    "current_stage_index": int(raw.get("current_stage_index", 0)),
                    "objective": self._quest_objective_payload(raw),
                }
            )
        entries.sort(key=lambda q: q.get("title", ""))
        return entries

    def _deliver_item_display_name(self, objective: Dict[str, Any]) -> str:
        """Name a deliver objective's item without falling back to a bare,
        tautological noun ("the delivery") or a raw internal template id."""
        authored_name = str(objective.get("item_to_deliver_name", "")).strip()
        if authored_name:
            return authored_name
        template_id = str(objective.get("item_template_id", "")).strip()
        if template_id:
            template = ItemFactory.get_template(template_id, self.world)
            if template:
                name = str(template.get("name", "")).strip()
                if name:
                    return name
        return "the item"

    def _quest_objective_payload(self, quest: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize the current quest stage for compact journal presentation."""
        stages = quest.get("stages", [])
        stage_index = int(quest.get("current_stage_index", 0))
        stage: Dict[str, Any] = {}
        if isinstance(stages, list) and 0 <= stage_index < len(stages) and isinstance(stages[stage_index], dict):
            stage = stages[stage_index]

        raw_objective = stage.get("objective")
        alternatives = stage.get("objectives_any", [])
        routes: List[Dict[str, Any]] = []
        if isinstance(raw_objective, dict):
            routes.append(raw_objective)
        if isinstance(alternatives, list):
            routes.extend(route for route in alternatives if isinstance(route, dict))
        # Older producers placed objective fields directly on a stage. Keep the
        # payload adapter backward compatible while new authored stages use
        # ``objective`` or ``objectives_any``.
        objective = routes[0] if routes else stage

        kind = str(objective.get("type", "objective"))
        description = str(stage.get("description", "")).strip() or "Complete the objective."
        location_hint = str(objective.get("location_hint", objective.get("location", ""))).strip()
        destination = str(objective.get("recipient_name", stage.get("turn_in_id", ""))).strip()
        progress_current: Optional[int] = None
        progress_required: Optional[int] = None

        if kind == "kill":
            progress_current = int(objective.get("current_quantity", 0))
            progress_required = int(objective.get("required_quantity", 0))
            target = str(objective.get("target_name_plural", objective.get("target_name", "enemies")))
            description = f"Defeat {target}."
        elif kind == "fetch":
            progress_current = int(objective.get("current_quantity", 0))
            progress_required = int(objective.get("required_quantity", 0))
            target = str(objective.get("item_name_plural", objective.get("item_name", "items")))
            description = f"Gather {target}."
        elif kind == "deliver":
            target = self._deliver_item_display_name(objective)
            recipient = str(objective.get("recipient_name", destination or "the recipient"))
            description = f"Deliver {target} to {recipient}."
            destination = recipient
            location_hint = str(objective.get("recipient_location_description", location_hint)).strip()
        elif kind == "group_kill":
            targets = objective.get("targets", {})
            if isinstance(targets, dict):
                progress_current = sum(int(item.get("current", 0)) for item in targets.values() if isinstance(item, dict))
                progress_required = sum(int(item.get("required", 0)) for item in targets.values() if isinstance(item, dict))
            description = str(stage.get("description", "")).strip() or "Defeat the marked enemies."

        route_summaries = []
        for route in routes:
            if route.get("type") == "deliver":
                route_summaries.append("Deliver %s to %s." % (self._deliver_item_display_name(route), route.get("recipient_name", "the recipient")))
            else:
                route_summaries.append(str(route.get("description", route.get("type", "Complete the objective"))))
        return {
            "kind": kind,
            "summary": description,
            "progress_current": progress_current,
            "progress_required": progress_required,
            "destination": destination,
            "location_hint": location_hint,
            "ready_to_turn_in": str(quest.get("state", "")) == "ready_to_complete",
            "alternatives": route_summaries,
        }

    def _is_combat_adjacent_message(self, message: Any) -> bool:
        if str(self.feature_profile.combat_mode).strip().lower() != "disabled":
            return False
        normalized = str(message).strip().lower()
        if normalized == "":
            return False
        # This base set matches the engine's own generated combat text
        # (combat_system.py's literal templates), so it's not itself
        # content-coupled -- but a content set's custom spell/attack
        # flavor text may use different vocabulary entirely, so it can
        # extend the filter via ruleset "combat.additional_combat_message_tokens"
        # (mirrors additional_blocked_command_names on the command side).
        combat_tokens = (
            "attacks",
            "hits",
            "misses",
            "critical hit",
            "combat",
            "damage",
            "bleed",
            "kills",
            "defeated",
            "slain",
            "you are dead",
            "you died",
        ) + tuple(
            str(t).strip().lower()
            for t in self.world.ruleset_section("combat").get("additional_combat_message_tokens", [])
        )
        return any(token in normalized for token in combat_tokens if token)
