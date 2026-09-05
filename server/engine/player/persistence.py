# engine/player/persistence.py

# engine/player/persistence.py
from typing import Dict, Any, TYPE_CHECKING, cast, Optional
from engine.utils.utils import _serialize_item_reference
from engine.items.inventory import Inventory
from engine.items.item_factory import ItemFactory
from engine.core.conversation_history import ConversationHistory
from engine.config import (
    PLAYER_DEFAULT_NAME, PLAYER_BASE_XP_TO_LEVEL, PLAYER_DEFAULT_STATS,
    EQUIPMENT_SLOTS, PLAYER_DEFAULT_MAX_TOTAL_SUMMONS
)

if TYPE_CHECKING:
    from engine.player.core import Player
    from engine.world.world import World

class PlayerPersistenceMixin:
    """
    Mixin class handling serialization for the Player.
    """
    def to_dict(self, world: 'World') -> Dict[str, Any]:
        p = cast('Player', self)
        
        # Serialize superclass (GameObject) data
        data = super().to_dict() # type: ignore
        
        # Add Player-specific data
        data.update({
            "health": p.health,
            "max_health": p.max_health,
            "stats": p.stats,
            "effects": p.active_effects, 
            "is_alive": p.is_alive,
            "current_location": {
                "region_id": p.current_region_id,
                "room_id": p.current_room_id
            },
            "respawn_region_id": p.respawn_region_id,
            "respawn_room_id": p.respawn_room_id,
            "inventory": p.inventory.to_dict(world),
            "equipment": {
                slot: _serialize_item_reference(item, 1, world) 
                for slot, item in p.equipment.items() if item
            },
            "conversation_history": p.conversation.to_dict(),
            "last_talked_to": p.last_talked_to,
            "collections_progress": p.collections_progress,
            "collections_completed": p.collections_completed,
            "follow_target": p.follow_target,
            "reputation": p.reputation,
            "gameplay": {},
        })
        gameplay = data["gameplay"]
        if p.runtime_state.magic is not None:
            gameplay["magic"] = {"mana": p.runtime_state.magic.mana, "max_mana": p.runtime_state.magic.max_mana, "known_spells": list(p.runtime_state.magic.known_spells), "cooldowns": p.runtime_state.magic.cooldowns}
        if p.runtime_state.combat is not None:
            gameplay["combat"] = {"attack_power": p.runtime_state.combat.attack_power, "defense": p.runtime_state.combat.defense}
        if p.runtime_state.progression is not None:
            gameplay["progression"] = {"player_class": p.runtime_state.progression.player_class, "level": p.runtime_state.progression.level, "experience": p.runtime_state.progression.experience, "experience_to_level": p.runtime_state.progression.experience_to_level, "skills": p.runtime_state.progression.skills}
        if p.runtime_state.gold is not None:
            gameplay["economy"] = {"gold": p.runtime_state.gold}
        if p.runtime_state.quests is not None:
            gameplay["quests"] = {"active": p.runtime_state.quests.active, "completed": p.runtime_state.quests.completed, "archived": p.runtime_state.quests.archived, "active_campaigns": p.runtime_state.quests.active_campaigns, "completed_campaigns": p.runtime_state.quests.completed_campaigns, "finite_adventure_state": p.runtime_state.quests.finite_adventure}
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any], world: 'World') -> Optional['Player']:
        """
        Reconstructs a Player object from a dictionary.
        """
        # Import locally to avoid circular dependency
        from engine.player.core import Player

        # Create instance using base init
        player_obj = cls(name=data.get("name", PLAYER_DEFAULT_NAME), world=world) # type: ignore
        
        # Cast to Player to satisfy Pylance about attribute access
        player = cast(Player, player_obj)
        
        # Core GameObject properties
        player.obj_id = data.get("id", "player")
        player.description = data.get("description", "The main character.")
        player.properties = data.get("properties", {})
        player.is_alive = data.get("is_alive", True)

        gameplay = data.get("gameplay")
        if not isinstance(gameplay, dict):
            raise ValueError("Player save requires a gameplay aspect object")
        magic = gameplay.get("magic", {})
        combat = gameplay.get("combat", {})
        progression = gameplay.get("progression", {})
        economy = gameplay.get("economy", {})
        quests = gameplay.get("quests", {})

        # Player Stats & Progression
        player.runtime_state.progression.player_class = progression.get("player_class", "")
        player.runtime_state.gold = economy.get("gold", 0)
        player.runtime_state.progression.level = progression.get("level", 0)
        player.runtime_state.progression.experience = progression.get("experience", 0)
        player.runtime_state.progression.experience_to_level = progression.get("experience_to_level", 0)
        
        player.stats = PLAYER_DEFAULT_STATS.copy()
        player.stats.update(data.get("stats", {}))
        
        # Skills are stored in their canonical structured form.
        raw_skills = progression.get("skills", {})
        if not isinstance(raw_skills, dict) or any(not isinstance(value, dict) for value in raw_skills.values()):
            raise ValueError("Player gameplay.progression.skills must contain structured skill state")
        player.runtime_state.progression.skills = raw_skills

        # Quests & Campaign
        player.runtime_state.quests.active = quests.get("active", {})
        player.runtime_state.quests.completed = quests.get("completed", {})
        player.runtime_state.quests.archived = quests.get("archived", {})
        player.runtime_state.quests.active_campaigns = quests.get("active_campaigns", {})
        player.runtime_state.quests.completed_campaigns = quests.get("completed_campaigns", {})
        player.runtime_state.quests.finite_adventure = quests.get("finite_adventure_state", {})

        # Status Effects
        player.active_effects = data.get("effects", [])
        # Re-apply stat modifiers from active effects
        player.stat_modifiers = {}
        for effect in player.active_effects:
            if effect.get("type") == "stat_mod":
                for stat, value in effect.get("modifiers", {}).items():
                    player.stat_modifiers[stat] = player.stat_modifiers.get(stat, 0) + value

        # Magic
        player.runtime_state.magic.known_spells = set(magic.get("known_spells", []))
        player.runtime_state.magic.cooldowns = magic.get("cooldowns", {})
        player.runtime_state.combat.attack_power = combat.get("attack_power", 0)
        player.runtime_state.combat.defense = combat.get("defense", 0)
        player.max_total_summons = PLAYER_DEFAULT_MAX_TOTAL_SUMMONS

        # Vitals
        player.max_health = data.get("max_health", player.max_health)
        player.health = data.get("health", player.max_health)
        player.runtime_state.magic.max_mana = magic.get("max_mana", 0)
        player.runtime_state.magic.mana = magic.get("mana", player.runtime_state.magic.max_mana)
        
        # Location
        loc = data.get("current_location", {})
        player.current_region_id = loc.get("region_id")
        player.current_room_id = loc.get("room_id")
        player.respawn_region_id = data.get("respawn_region_id", world.content_set.start_region_id)
        player.respawn_room_id = data.get("respawn_room_id", world.content_set.start_room_id)
        
        # Inventory
        inventory_data = data.get("inventory", {})
        player.inventory = Inventory.from_dict(inventory_data, world)
        
        # Equipment
        equipment_data = data.get("equipment", {})
        player.equipment = {slot: None for slot in EQUIPMENT_SLOTS}
        
        for slot, item_ref in equipment_data.items():
            if slot in player.equipment and item_ref and "item_id" in item_ref:
                item_id = item_ref["item_id"]
                overrides = item_ref.get("properties_override", {})
                item = ItemFactory.create_item_from_template(item_id, world, **overrides)
                if item:
                    player.equipment[slot] = item
                else:
                    print(f"Warning: Failed to load equipped item '{item_id}' for slot '{slot}'.")

        # Interaction State
        player.last_talked_to = data.get("last_talked_to")
        if "conversation_history" in data:
            player.conversation = ConversationHistory.from_dict(data["conversation_history"])
        
        player.collections_progress = data.get("collections_progress", {})
        player.collections_completed = data.get("collections_completed", {})
        player.follow_target = data.get("follow_target")
        player.reputation = data.get("reputation", {})

        player.world = world
        normalize = getattr(world, "apply_content_player_defaults", None)
        if callable(normalize):
            normalize(player)
        return player
