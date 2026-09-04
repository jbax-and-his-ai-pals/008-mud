# engine/game_object.py
import random
from typing import Dict, Any, List, Optional, Tuple
import uuid
import time
from engine.config import EFFECT_DEFAULT_TICK_INTERVAL, FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS, NPC_DOT_FLAVOR_MESSAGES, MINIMUM_DAMAGE_TAKEN
from engine.config.config_display import SCREEN_HEIGHT, SCREEN_WIDTH

class GameObject:
    def __init__(self, obj_id: Optional[str] = None, name: str = "Unknown",
        description: str = "No description"):
        self.obj_id = obj_id if obj_id else f"{self.__class__.__name__.lower()}_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.description = description
        self.properties: Dict[str, Any] = {}
        self.active_effects: List[Dict[str, Any]] = []
        self.is_alive: bool = True
        self.stats: Dict[str, Any] = {} # MODIFIED: Allow Any for resistances dict
        self.stat_modifiers: Dict[str, int] = {}

    def get_description(self) -> str:
        return f"{self.name}\n\n{self.description}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.__class__.__name__,
            "id": self.obj_id,
            "name": self.name,
            "description": self.description,
            "properties": self.properties,
            "is_alive": self.is_alive
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GameObject':
        obj = cls(
            obj_id=data.get("obj_id") or data.get("id"),
            name=data.get("name", "Unknown"),
            description=data.get("description", "No description")
        )
        obj.properties = data.get("properties", {})
        obj.is_alive = data.get("is_alive", True)
        return obj

    def update_property(self, key: str, value: Any) -> None:
        self.properties[key] = value

    def get_property(self, key: str, default: Any = None) -> Any:
        return self.properties.get(key, default)

    def get_effective_stat(self, stat_name: str) -> int:
        """Calculates a stat by combining the base value with active modifiers."""
        # Handle resistance stats which start with 'resist_'
        if stat_name.startswith("resist_"):
            return self.get_resistance(stat_name.replace("resist_", ""))

        base_stat = self.stats.get(stat_name, 0)
        modifier = self.stat_modifiers.get(stat_name, 0)
        return base_stat + modifier

    def get_resistance(self, damage_type: str) -> int:
        """
        Calculates total resistance for a damage type from innate stats and effects.
        Subclasses (Player) will override this to include equipment.
        Value is a percentage, e.g., 25 means 25% resistance.
        Negative values represent weakness.
        """
        # 1. Innate resistance from stats
        innate_res = self.stats.get("resistances", {}).get(damage_type, 0)

        # 2. Temporary resistance from stat modifiers (buffs/debuffs)
        # Effects that modify resistance will have a stat modifier key like "resist_fire"
        effect_res = self.stat_modifiers.get(f"resist_{damage_type}", 0)

        return innate_res + effect_res

    def has_effect(self, effect_name: str) -> bool:
        """Checks if an effect with a given name is currently active."""
        name_lower = effect_name.lower()
        return any(eff.get("name", "").lower() == name_lower for eff in self.active_effects)

    def has_effect_tag(self, tag: str) -> bool:
        """Checks if any active effect has a specific tag (e.g. 'poison', 'curse')."""
        tag_lower = tag.lower()
        for eff in self.active_effects:
            tags = eff.get("tags", [])
            # Support both list of strings and single string
            if isinstance(tags, list):
                if any(t.lower() == tag_lower for t in tags): return True
            elif isinstance(tags, str):
                if tags.lower() == tag_lower: return True
        return False

    def take_damage(self, amount: int, damage_type: str) -> int:
        if not self.is_alive or amount <= 0: return 0

        # --- 1. Reactive Logic (Hydra / Gimmick Bosses) ---
        # Check if we have specific reactions to this damage type
        reactions = self.properties.get("damage_reactions", {})
        if damage_type in reactions:
            reaction = reactions[damage_type]
            action = reaction.get("action")
            
            if action == "remove_effect_tag":
                tag = reaction.get("tag")
                if tag:
                    removed = self.remove_effects_by_tag(tag)
                    # We could return visual feedback here via a floating text call or separate event
                    # For now, the effect removal logic handles its own messages if called via update,
                    # but immediate removal is silent unless we add text here.
        
        base_reduction = 0
        if damage_type == "physical":
            base_reduction = self.get_effective_stat("defense")
        else:
            base_reduction = self.get_effective_stat("magic_resist")

        damage_after_flat_reduction = max(0, amount - base_reduction)
        if damage_after_flat_reduction == 0: return 0

        resistance_percent = self.get_resistance(damage_type)
        resistance_percent = max(-100, min(100, resistance_percent))
        resistance_multiplier = 1.0 - (resistance_percent / 100.0)
        final_damage = int(damage_after_flat_reduction * resistance_multiplier)
        actual_damage_taken = max(MINIMUM_DAMAGE_TAKEN, final_damage) if final_damage > 0 else 0

        old_health = getattr(self, 'health', 0)
        new_health = max(0, old_health - actual_damage_taken)
        setattr(self, 'health', new_health)

        if new_health <= 0: self.is_alive = False

        # --- VISUAL JUICE (Floating Text) ---
        # Use getattr to safely access 'world' and 'game' without Pylance errors
        world_ref = getattr(self, 'world', None)
        if world_ref:
            game_ref = getattr(world_ref, 'game', None)
            if game_ref and hasattr(game_ref, 'renderer'):
                
                # Calculate Position
                # Default to center screen
                x = SCREEN_WIDTH // 2 + random.randint(-50, 50)
                y = SCREEN_HEIGHT // 2 - 100
                
                # Determine Color
                # We check class name string to avoid circular import of Player class for isinstance check
                is_player = self.__class__.__name__ == "Player"
                color = (255, 50, 50) if is_player else (255, 255, 255)
                
                # Add Text
                game_ref.renderer.add_floating_text(f"-{actual_damage_taken}", x, y, color)

        return int(actual_damage_taken)

    def heal(self, amount: int) -> int:
        return 0

    def apply_effect(self, effect_data: Dict[str, Any], current_time: float) -> Tuple[bool, str]:
        if not self.is_alive: return False, f"{self.name} cannot be affected."
        effect_name = effect_data.get("name", "Unknown Effect")
        
        # Before adding, remove any existing effect with the same name to refresh it
        self.remove_effect(effect_name)

        new_effect_instance = effect_data.copy()
        new_effect_instance["id"] = f"effect_{uuid.uuid4().hex[:8]}"
        new_effect_instance["last_tick_time"] = current_time

        if "base_duration" in new_effect_instance:
            new_effect_instance["duration_remaining"] = new_effect_instance.get("base_duration", 10.0)
        
        # If this is a stat modifier, apply the change immediately
        if new_effect_instance.get("type") == "stat_mod":
            for stat, value in new_effect_instance.get("modifiers", {}).items():
                self.stat_modifiers[stat] = self.stat_modifiers.get(stat, 0) + value

        self.active_effects.append(new_effect_instance)
        return True, ""

    def remove_effect(self, effect_name: str) -> bool:
        effect_to_remove = None
        for eff in self.active_effects:
            if eff.get("name", "").lower() == effect_name.lower():
                effect_to_remove = eff
                break
        
        if not effect_to_remove:
            return False

        if effect_to_remove.get("type") == "stat_mod":
            for stat, value in effect_to_remove.get("modifiers", {}).items():
                self.stat_modifiers[stat] = self.stat_modifiers.get(stat, 0) - value
                if self.stat_modifiers.get(stat) == 0:
                    del self.stat_modifiers[stat]
        
        self.active_effects.remove(effect_to_remove)
        return True

    def remove_effects_by_tag(self, tag: str) -> List[str]:
        """Removes all effects matching a specific tag."""
        removed_names = []
        tag_lower = tag.lower()
        
        # Iterate backwards to safely remove
        for i in range(len(self.active_effects) - 1, -1, -1):
            eff = self.active_effects[i]
            tags = eff.get("tags", [])
            match = False
            if isinstance(tags, list):
                if any(t.lower() == tag_lower for t in tags): match = True
            elif isinstance(tags, str):
                if tags.lower() == tag_lower: match = True
            
            if match:
                self.remove_effect(eff["name"])
                removed_names.append(eff["name"])
                
        return removed_names

    def process_active_effects(self, current_time: float, time_delta: float) -> List[str]:
            from engine.player import Player
            if not self.is_alive:
                if self.active_effects: self.active_effects.clear()
                return []

            expired_effect_names: List[str] = []
            tick_messages: List[str] = []

            # Iterate over a copy as remove_effect will modify the list
            for effect in list(self.active_effects):
                # Handle duration-based effects
                if "duration_remaining" in effect:
                    effect["duration_remaining"] -= time_delta
                    if effect["duration_remaining"] <= 0:
                        effect_name = effect.get("name")
                        if effect_name:
                            expired_effect_names.append(effect_name)
                        else:
                            print(f"process_active_effects() - error parsing effect_name from effect - {effect}.")
                        continue

                # Handle Damage Over Time (DoT)
                if effect.get("type") == "dot":
                    tick_interval = effect.get("tick_interval", EFFECT_DEFAULT_TICK_INTERVAL)
                    if current_time - effect.get("last_tick_time", 0) >= tick_interval:
                        effect["last_tick_time"] = current_time
                        damage = effect.get("damage_per_tick", 0)
                        dmg_type = effect.get("damage_type", "unknown")
                        damage_taken = self.take_damage(damage, dmg_type)
                        if damage_taken > 0:
                            effect_name_fmt = f"{FORMAT_HIGHLIGHT}{effect.get('name', 'effect')}{FORMAT_RESET}"
                            if isinstance(self, Player):
                                message = f"You take {FORMAT_ERROR}{damage_taken}{FORMAT_RESET} {dmg_type} damage from the {effect_name_fmt}."
                            else:
                                message = random.choice(NPC_DOT_FLAVOR_MESSAGES).format(npc_name=self.name, effect_name=effect.get('name', 'effect'))
                            tick_messages.append(message)

                # Handle Heal Over Time (HoT)
                elif effect.get("type") == "hot":
                    tick_interval = effect.get("tick_interval", EFFECT_DEFAULT_TICK_INTERVAL)
                    if current_time - effect.get("last_tick_time", 0) >= tick_interval:
                        effect["last_tick_time"] = current_time
                        heal_amount = effect.get("heal_per_tick", 0)
                        healed_for = self.heal(heal_amount)
                        if healed_for > 0:
                            effect_name_fmt = f"{FORMAT_HIGHLIGHT}{effect.get('name', 'effect')}{FORMAT_RESET}"
                            if isinstance(self, Player):
                                message = f"The {effect_name_fmt} heals you for {FORMAT_SUCCESS}{healed_for}{FORMAT_RESET} health."
                            else:
                                message = f"{self.name} is healed for {FORMAT_SUCCESS}{healed_for}{FORMAT_RESET} health by the {effect_name_fmt}."
                            tick_messages.append(message)

                if not self.is_alive:
                    if isinstance(self, Player):
                        tick_messages.append(f"You succumb to the effects of {effect.get('name', 'the affliction')}!")
                    break

            # Now, process expirations
            if expired_effect_names:
                for name in expired_effect_names:
                    if name:
                        # remove_effect also handles reverting stat mods
                        was_removed = self.remove_effect(name)
                        if was_removed:
                            effect_name_fmt = f"{FORMAT_HIGHLIGHT}{name}{FORMAT_RESET}"
                            if isinstance(self, Player):
                                tick_messages.append(f"The {effect_name_fmt} on you wears off.")
                            else:
                                tick_messages.append(f"The {effect_name_fmt} on {self.name} wears off.")

            if not self.is_alive and self.active_effects:
                # If the character died, clear all remaining effects without reverting stats
                self.active_effects.clear()
                self.stat_modifiers.clear()

            return tick_messages