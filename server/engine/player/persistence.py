# engine/player/persistence.py

# engine/player/persistence.py
from typing import Dict, Any, TYPE_CHECKING, cast, Optional
from engine.utils.utils import _serialize_item_reference
from engine.items.inventory import Inventory
from engine.items.item_factory import ItemFactory
from engine.core.conversation_history import ConversationHistory
from engine.player.aspects import ProgressionState
from engine.world.save_format import take_stale_summons_flag
from engine.config import (
    PLAYER_DEFAULT_NAME, PLAYER_BASE_XP_TO_LEVEL, PLAYER_DEFAULT_STATS,
    EQUIPMENT_SLOTS, PLAYER_DEFAULT_MAX_TOTAL_SUMMONS
)

if TYPE_CHECKING:
    from engine.player.core import Player
    from engine.world.world import World


def _serialize_summons(magic: Any) -> Optional[Dict[str, list]]:
    """The player's summon ledger, or None when there is nothing to record.

    A map of ability id to the instance ids it summoned. It is written down so a
    save taken mid-game is honest about what the player had out, and *read back*
    only while those instances still exist -- see `NPC.to_dict` for why a summon
    cannot survive a save.
    """
    if magic is None or not getattr(magic, "summons", None):
        return None
    out: Dict[str, list] = {}
    for ability_id, instance_ids in magic.summons.items():
        cleaned = [str(entry) for entry in instance_ids if isinstance(entry, str) and entry]
        if cleaned:
            out[str(ability_id)] = cleaned
    return out or None


def _read_summons(player: 'Player', raw: Any, stale: bool) -> Dict[str, list]:
    """The summon ledger a save declared, minus entries that cannot be true.

    `stale` comes from the save-format migration that knows this file predates
    summon serialisation at all.
    """
    if stale or not isinstance(raw, dict):
        return {}
    restored: Dict[str, list] = {}
    for ability_id, instance_ids in raw.items():
        if not isinstance(ability_id, str) or not isinstance(instance_ids, list):
            continue
        cleaned = [str(entry) for entry in instance_ids if isinstance(entry, str) and entry]
        if cleaned:
            restored[ability_id] = cleaned
    return restored

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
            # P5: markers a conversation set and another conversation reads.
            "flags": getattr(p, "flags", None) or {},
            "collections_progress": p.collections_progress,
            "collections_completed": p.collections_completed,
            "discoveries": p.discoveries,
            "recipe_craft_counts": p.recipe_craft_counts,
            "known_recipe_ids": list(p.known_recipe_ids),
            # P4 progression spine. Sorted so two saves of the same state are
            # byte-identical, which keeps save-comparison tests meaningful.
            "advancement_entries": sorted(getattr(p, "advancement_entries", None) or []),
            "earned_titles": sorted(getattr(p, "earned_titles", None) or []),
            "active_title": getattr(p, "active_title", "") or "",
            "background_id": getattr(p, "background_id", "") or "",
            "follow_target": p.follow_target,
            "reputation": p.reputation,
            "npc_relationships": p.npc_relationships,
            "npc_gift_days": p.npc_gift_days,
            "vendor_orders_completed": p.vendor_orders_completed,
            "relationship_milestones_completed": p.relationship_milestones_completed,
            "jailed_until": p.jailed_until,
            "confiscated_inventory": p.confiscated_inventory.to_dict(world) if p.confiscated_inventory else None,
            "total_theft_value": p.total_theft_value,
            "discovered_concealed_pick_trick": p.discovered_concealed_pick_trick,
            "gameplay": {},
        })
        gameplay = data["gameplay"]
        if p.runtime_state.magic is not None:
            gameplay["magic"] = {"mana": p.runtime_state.magic.mana, "max_mana": p.runtime_state.magic.max_mana, "known_spells": list(p.runtime_state.magic.known_spells), "cooldowns": p.runtime_state.magic.cooldowns}
            summons = _serialize_summons(p.runtime_state.magic)
            if summons is not None:
                gameplay["magic"]["summons"] = summons
        if p.runtime_state.combat is not None:
            gameplay["combat"] = {"attack_power": p.runtime_state.combat.attack_power, "defense": p.runtime_state.combat.defense}
        if p.runtime_state.progression is not None:
            gameplay["progression"] = {"player_class": p.runtime_state.progression.player_class, "level": p.runtime_state.progression.level, "experience": p.runtime_state.progression.experience, "experience_to_level": p.runtime_state.progression.experience_to_level, "skills": p.runtime_state.progression.skills}
        if p.runtime_state.gold is not None:
            gameplay["economy"] = {"gold": p.runtime_state.gold}
        if p.runtime_state.quests is not None:
            gameplay["quests"] = {"active": p.runtime_state.quests.active, "completed": p.runtime_state.quests.completed, "archived": p.runtime_state.quests.archived, "repeatable_available_at": p.runtime_state.quests.repeatable_available_at, "active_campaigns": p.runtime_state.quests.active_campaigns, "completed_campaigns": p.runtime_state.quests.completed_campaigns, "finite_adventure_state": p.runtime_state.quests.finite_adventure}
        if p.runtime_state.work is not None:
            # Absolute timestamps, so what a save records is *when the job ends*
            # rather than how much was left. A job left running while the player
            # was logged out is therefore still correct on the way back in, and a
            # restart neither resets nor extends it.
            gameplay["work"] = {
                "jobs": [dict(job) for job in p.runtime_state.work.jobs if isinstance(job, dict)]
            }
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
        work = gameplay.get("work", {})

        # Which aspects this game presents was decided when the world was built,
        # and a save can predate that decision in either direction: written by a
        # build that had abilities, read by a content set that does not -- or the
        # reverse. The reader needs *somewhere to put* every field below, and
        # `normalize` is entitled to null an aspect the world does not present,
        # so it runs on both sides of the read: once to guarantee a container,
        # once to leave the player in the state the world actually asked for.
        #
        # A save that arrives without one of these objects is a save from a build
        # that had the aspect and a reader that does not; the container is made
        # here and nulled again by the closing normalize if this world has no use
        # for it.
        from engine.player.aspects import (
            CombatState, MagicState, PlayerGameAspects, ProgressionState, QuestState, WorkState,
        )

        player.runtime_state.magic = player.runtime_state.magic or MagicState()
        player.runtime_state.combat = player.runtime_state.combat or CombatState()
        player.runtime_state.progression = player.runtime_state.progression or ProgressionState()
        player.runtime_state.quests = player.runtime_state.quests or QuestState()
        player.runtime_state.work = player.runtime_state.work or WorkState()
        if player.runtime_state.gold is None:
            player.runtime_state.gold = 0

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
        raw_repeatable_available_at = quests.get("repeatable_available_at", {})
        if not isinstance(raw_repeatable_available_at, dict):
            raise ValueError("Player gameplay.quests.repeatable_available_at must be an object")
        player.runtime_state.quests.repeatable_available_at = {
            str(template_id): float(available_at)
            for template_id, available_at in raw_repeatable_available_at.items()
            if isinstance(template_id, str) and isinstance(available_at, (int, float))
        }
        player.runtime_state.quests.active_campaigns = quests.get("active_campaigns", {})
        player.runtime_state.quests.completed_campaigns = quests.get("completed_campaigns", {})
        player.runtime_state.quests.finite_adventure = quests.get("finite_adventure_state", {})

        # Timed jobs. A job that cannot be read as a timer is dropped rather than
        # refused: the shape is four fields and a save that lost one of them has
        # lost that job, while refusing the whole save would lose the character.
        # An *empty* list and a missing section are the same thing here, which is
        # why nothing distinguishes them below.
        jobs = work.get("jobs", []) if isinstance(work, dict) else []
        player.runtime_state.work.jobs = [
            dict(job) for job in jobs
            if isinstance(job, dict)
            and isinstance(job.get("ends_at"), (int, float))
            and not isinstance(job.get("ends_at"), bool)
            and str(job.get("work", "")).strip()
        ]

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
        # The summon ledger is *held*, not applied: its instance ids only mean
        # something once the NPCs they name have been restored, and a reader
        # that is not `SaveManager` may never restore them at all. See
        # `settle_pending_summons`.
        player.runtime_state.magic.summons = {}
        player._pending_summons = _read_summons(player, magic.get("summons"), take_stale_summons_flag(data))
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
        player.discoveries = data.get("discoveries", {})
        # P5 conversation flags. Tolerant of saves written before they existed.
        raw_flags = data.get("flags", {})
        player.flags = dict(raw_flags) if isinstance(raw_flags, dict) else {}
        raw_recipe_counts = data.get("recipe_craft_counts", {})
        player.recipe_craft_counts = {
            str(recipe_id): max(0, int(count))
            for recipe_id, count in raw_recipe_counts.items()
            if isinstance(recipe_id, str) and isinstance(count, int) and not isinstance(count, bool)
        } if isinstance(raw_recipe_counts, dict) else {}
        raw_known_recipes = data.get("known_recipe_ids", [])
        player.known_recipe_ids = {
            str(recipe_id) for recipe_id in raw_known_recipes if isinstance(recipe_id, str)
        } if isinstance(raw_known_recipes, list) else set()

        # P4 progression spine. Absent in saves written before these existed, so
        # every read is tolerant of a missing key and an empty ledger.
        raw_entries = data.get("advancement_entries", [])
        player.advancement_entries = {
            str(entry) for entry in raw_entries if isinstance(entry, str)
        } if isinstance(raw_entries, list) else set()
        raw_titles = data.get("earned_titles", [])
        player.earned_titles = {
            str(title) for title in raw_titles if isinstance(title, str)
        } if isinstance(raw_titles, list) else set()
        player.active_title = str(data.get("active_title", "") or "")
        player.background_id = str(data.get("background_id", "") or "")
        player.follow_target = data.get("follow_target")
        player.reputation = data.get("reputation", {})
        player.npc_relationships = data.get("npc_relationships", {})
        player.npc_gift_days = data.get("npc_gift_days", {})
        player.vendor_orders_completed = data.get("vendor_orders_completed", {})
        player.relationship_milestones_completed = data.get("relationship_milestones_completed", {})
        player.jailed_until = data.get("jailed_until")
        player.total_theft_value = data.get("total_theft_value", 0)
        player.discovered_concealed_pick_trick = data.get("discovered_concealed_pick_trick", False)
        confiscated_data = data.get("confiscated_inventory")
        player.confiscated_inventory = Inventory.from_dict(confiscated_data, world) if confiscated_data else None

        player.world = world
        # The closing normalize is the other half of the pair above: the save's
        # state has been read into containers that were guaranteed to exist, and
        # this is what leaves the player in the shape *this* world asked for --
        # an aspect the content set does not present is nulled again here, having
        # served its purpose as somewhere to read into.
        normalize = getattr(world, "apply_content_player_defaults", None)
        if callable(normalize):
            normalize(player)
        return player

    def settle_pending_summons(self) -> None:
        """Adopt the summon ledger a save declared, now that the NPCs exist.

        Called by `SaveManager` after it has restored NPCs, because the ledger's
        instance ids are a statement about NPCs and a load is the only moment
        they can be checked. An entry whose instance is not there is dropped
        rather than kept as a dangling id that a later `despawn` would search for
        and never find.
        """
        pending = getattr(self, "_pending_summons", None)
        self._pending_summons = None
        magic = getattr(self.runtime_state, "magic", None)
        if magic is None or not isinstance(pending, dict):
            return
        known = set(getattr(self.world, "npcs", {}) or {}) if self.world is not None else set()
        magic.summons = {
            ability_id: [instance for instance in instances if instance in known]
            for ability_id, instances in pending.items()
        }
        magic.summons = {ability_id: instances for ability_id, instances in magic.summons.items() if instances}
