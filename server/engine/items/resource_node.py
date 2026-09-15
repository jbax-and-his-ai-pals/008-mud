# engine/items/resource_node.py
from typing import List, Optional
import random
from engine.items.item import Item
from engine.config import FORMAT_ERROR, FORMAT_SUCCESS, FORMAT_RESET
from engine.presentation import is_player_mode, show_internals

def _is_public_region(region_id: str) -> bool:
    """Exclude per-player houses and quest instances from world-wide
    gathering hints -- they aren't generally-accessible locations."""
    return not (region_id.startswith("instance_") or region_id.startswith("dynamic_player_house"))

class ResourceNode(Item):
    def __init__(self, obj_id: Optional[str] = None, name: str = "Resource",
                 description: str = "A resource node.", 
                 resource_item_id: str = "item_stone",
                 tool_required: str = "pickaxe",
                 charges: int = 3,
                 **kwargs):
        
        if 'stackable' in kwargs:
            kwargs.pop('stackable')
            
        if 'weight' in kwargs:
            kwargs.pop('weight')

        super().__init__(obj_id, name, description, weight=9999, stackable=False, **kwargs)
        
        self.update_property("can_take", False)
        self.update_property("resource_item_id", resource_item_id)
        self.update_property("tool_required", tool_required)
        self.update_property("charges", charges)
        self.update_property("max_charges", charges)

    def _presentation_context(self, world, player=None) -> dict:
        """Minimal context for resolving the viewer's presentation mode."""
        return {"world": world, "player": player}

    def _tool_display_name(self, tool_req, world) -> str:
        """What this content set calls the tool that matches `tool_required`.

        The first item template whose `tool_type` matches supplies the name, so
        a content set names its own tools. Falling back to the raw value with
        underscores opened out keeps the sentence readable even when the
        requirement names a tool nothing provides -- which is itself worth
        seeing rather than hiding.
        """
        templates = getattr(world, "item_templates", None)
        if isinstance(templates, dict):
            for template in templates.values():
                if not isinstance(template, dict):
                    continue
                properties = template.get("properties")
                if not isinstance(properties, dict):
                    continue
                if str(properties.get("tool_type", "")) != str(tool_req):
                    continue
                name = str(template.get("name", "") or "").strip()
                if name:
                    return name
        return str(tool_req).replace("_", " ")

    def _depleted_message(self, world, player=None) -> str:
        """What a viewer is told when there is nothing left here.

        A player is told the patch is picked clean; a tester also gets the
        exact recovery window. `(recovers in N days)` is engine internals --
        precise, actionable-to-a-tester, and not something a forager in the
        world would know.
        """
        if is_player_mode(self._presentation_context(world, player)):
            return f"You've gathered all you can from the {self.name} for now."
        base_message = f"The {self.name} has been depleted."
        days_left = self.recovery_days_left(world)
        if days_left is not None:
            base_message += f" It should recover in about {days_left} day{'s' if days_left != 1 else ''}."
        return base_message

    def gather(self, player, world) -> str:
        charges = self.available_charges(world)
        respawn_days = int(self.get_property("respawn_days", 0))
        if charges <= 0:
            return self._depleted_message(world, player) + self._alternatives_note(world)

        time_manager = getattr(getattr(world, "game", None), "time_manager", None)
        day_number = self._day_number(world)

        allowed_seasons = self.get_property("seasons", [])
        current_season = str(getattr(time_manager, "time_data", {}).get("season", "")) if time_manager else ""
        if allowed_seasons and current_season not in allowed_seasons:
            return f"The {self.name} offers nothing during this season."
            
        tool_req = self.get_property("tool_required")
        
        has_tool = False
        for item in player.equipment.values():
            if item and item.get_property("tool_type") == tool_req:
                has_tool = True
                break
        if not has_tool:
            for slot in player.inventory.slots:
                if slot.item and slot.item.get_property("tool_type") == tool_req:
                    has_tool = True; break
        
        if not has_tool:
            # A player should read "a foraging knife", not "a foraging_knife":
            # the tool requirement is an authored property value, and the id
            # form of it is engine-internal spelling. Testers keep the exact
            # value so an author can see which tool_type they mistyped.
            if is_player_mode(self._presentation_context(world, player)):
                tool_label = self._tool_display_name(tool_req, world)
            else:
                tool_label = str(tool_req)
            return f"{FORMAT_ERROR}You need a {tool_label} to gather from this. You don't seem to be carrying or wearing one.{FORMAT_RESET}"
            
        from engine.items.item_factory import ItemFactory
        resource_id = self.get_property("resource_item_id")
        selected_yield = None
        yield_table = self.get_property("yield_table", [])
        if isinstance(yield_table, list):
            for candidate in yield_table:
                if isinstance(candidate, dict) and random.random() <= float(candidate.get("chance", 0.0)):
                    resource_id = candidate.get("item_id", resource_id)
                    selected_yield = candidate
                    break
        resource = ItemFactory.create_item_from_template(resource_id, world)
        
        if resource:
            # A node can provide a dependable regional grade while an
            # authored yield-table entry can replace it with a rarer grade.
            # This remains useful for any setting's materials without the
            # engine knowing their genre or lore.
            quality = (
                selected_yield.get("material_quality", self.get_property("material_quality", {}))
                if selected_yield is not None
                else self.get_property("material_quality", {})
            )
            if isinstance(quality, dict):
                raw_score = quality.get("score", 0)
                score = int(raw_score) if isinstance(raw_score, int) and not isinstance(raw_score, bool) else 0
                if score > 0:
                    quality_id = str(quality.get("id", "refined")).strip() or "refined"
                    quality_label = str(quality.get("label", quality_id.replace("_", " ").title())).strip()
                    resource.properties["material_quality"] = quality_id
                    resource.properties["material_quality_label"] = quality_label
                    resource.properties["material_quality_score"] = score
                    resource.properties["material_source_id"] = self.obj_id
                    resource.properties["material_source_label"] = self.name
                    resource.stackable = False
                    resource.update_property("stackable", False)
            can_add, space_message = player.inventory.can_add_item(resource)
            if not can_add:
                return f"{FORMAT_ERROR}You cannot carry the {resource.name}: {space_message}{FORMAT_RESET}"
            added, add_message = player.inventory.add_item(resource)
            if not added:
                return f"{FORMAT_ERROR}You cannot carry the {resource.name}: {add_message}{FORMAT_RESET}"
            remaining = charges - 1
            self.update_property("charges", remaining)
            if remaining <= 0 and respawn_days > 0:
                self.update_property("depleted_day", day_number)
                self.update_property("last_partial_gather_day", None)
            elif remaining > 0 and respawn_days > 0:
                self.update_property("last_partial_gather_day", day_number)
            discovery = ""
            collection_manager = getattr(getattr(world, "game", None), "collection_manager", None)
            if collection_manager is not None:
                discovery = collection_manager.handle_collection_discovery(player, resource)
            discovery_manager = getattr(getattr(world, "game", None), "discovery_manager", None)
            journal_note = discovery_manager.handle_item_discovery(player, resource) if discovery_manager else ""
            quest_manager = getattr(world, "quest_manager", None)
            quest_note = quest_manager.handle_resource_gathered(player, resource.obj_id) if quest_manager else ""
            quality_note = f" ({resource.get_property('material_quality_label')} quality)" if resource.get_property("material_quality_score", 0) else ""
            message = f"{FORMAT_SUCCESS}You gather {resource.name}{quality_note} from the {self.name}.{FORMAT_RESET}"
            # Charge counts are engine internals: a tester needs them, a player
            # should not be counting the world's resets.
            if show_internals(self._presentation_context(world, player)):
                message += f" ({charges - 1} remaining)"
            notes = [note for note in (discovery, journal_note, quest_note) if note]
            return message + "\n" + "\n".join(notes) if notes else message
        
        return "You find nothing useful."

    def _day_number(self, world) -> int:
        time_manager = getattr(getattr(world, "game", None), "time_manager", None)
        return int(getattr(time_manager, "game_time", 0) // 86400) if time_manager else 0

    def available_charges(self, world) -> int:
        """Refresh and return charge state for gathering and inspection alike."""
        charges = int(self.get_property("charges", 0))
        max_charges = int(self.get_property("max_charges", 1))
        respawn_days = int(self.get_property("respawn_days", 0))
        day_number = self._day_number(world)

        if charges <= 0:
            depleted_day = self.get_property("depleted_day")
            if respawn_days > 0 and depleted_day is not None and day_number - int(depleted_day) >= respawn_days:
                charges = max_charges
                self.update_property("charges", charges)
                self.update_property("depleted_day", None)
        elif charges < max_charges and respawn_days > 0:
            # A partial harvest never fully blocks recovery: it slowly
            # trickles back toward max instead of sitting frozen until
            # someone drains it to zero (see ROADMAP.md).
            last_partial_day = self.get_property("last_partial_gather_day")
            if last_partial_day is not None:
                elapsed = day_number - int(last_partial_day)
                gained = elapsed // respawn_days
                if gained > 0:
                    charges = min(max_charges, charges + gained)
                    self.update_property("charges", charges)
                    new_last_day = int(last_partial_day) + gained * respawn_days
                    self.update_property("last_partial_gather_day", None if charges >= max_charges else new_last_day)
        return charges

    def recovery_days_left(self, world) -> Optional[int]:
        """Real remaining time for a currently-depleted, renewable node, or
        None when the node isn't depleted or won't recover on its own."""
        if self.available_charges(world) > 0:
            return None
        respawn_days = int(self.get_property("respawn_days", 0))
        depleted_day = self.get_property("depleted_day")
        if respawn_days <= 0 or depleted_day is None:
            return None
        days_left = respawn_days - (self._day_number(world) - int(depleted_day))
        return days_left if days_left > 0 else None

    def _other_nodes(self, world):
        for region_id, region in getattr(world, "regions", {}).items():
            if not _is_public_region(region_id):
                continue
            for room in region.rooms.values():
                for item in room.items:
                    if isinstance(item, ResourceNode) and item.obj_id != self.obj_id:
                        yield item, room, region

    def find_alternate_sources(self, world) -> List[str]:
        """Other public nodes yielding this exact same resource."""
        resource_id = self.get_property("resource_item_id")
        if not resource_id:
            return []
        seen = set()
        locations = []
        for node, room, region in self._other_nodes(world):
            if node.get_property("resource_item_id") != resource_id:
                continue
            label = f"{node.name} ({room.name})"
            if label not in seen:
                seen.add(label)
                locations.append(label)
        return locations

    def find_substitutes(self, world) -> List[str]:
        """Public nodes yielding an authored substitute resource."""
        substitute_ids = self.get_property("substitute_resource_ids", [])
        if not isinstance(substitute_ids, list) or not substitute_ids:
            return []
        seen = set()
        locations = []
        for node, room, region in self._other_nodes(world):
            node_resource_id = node.get_property("resource_item_id")
            if node_resource_id not in substitute_ids:
                continue
            label = f"{node.name} ({room.name})"
            if label not in seen:
                seen.add(label)
                locations.append(label)
        return locations

    def _alternatives_note(self, world) -> str:
        lines = []
        alternates = self.find_alternate_sources(world)
        if alternates:
            lines.append(f" Also found at: {', '.join(alternates)}.")
        substitutes = self.find_substitutes(world)
        if substitutes:
            lines.append(f" You could gather instead from: {', '.join(substitutes)}.")
        return "".join(lines)
