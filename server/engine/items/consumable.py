# engine/items/consumable.py
import time
from typing import Optional
from engine.config import FORMAT_ERROR, FORMAT_RESET, FORMAT_SUCCESS
from engine.items.item import Item

class Consumable(Item):
    def __init__(self, obj_id: Optional[str] = None, name: str = "Unknown Consumable",
                 description: str = "No description", weight: float = 0.5,
                 value: int = 5, uses: int = 1, effect_value: int = 10,
                 effect_type: str = "heal", **kwargs):
        
        # Prevent duplicate stackable arg error
        if 'stackable' in kwargs:
            kwargs.pop('stackable')
            
        super().__init__(
            obj_id=obj_id, name=name, description=description, weight=weight,
            value=value, stackable=(uses==1),
            uses=uses, max_uses=uses, effect_value=effect_value, effect_type=effect_type,
            **kwargs
        )
        self.update_property("stackable", (uses == 1))
    
    def use(self, user, **kwargs) -> str:
        current_uses = self.get_property("uses")
        if current_uses <= 0:
            return f"The {self.name} has already been used up."

        consumed = True
        message = f"You use the {self.name}."

        effect_type = self.get_property("effect_type")
        effect_value = self.get_property("effect_value")

        if effect_type == "heal":
            if hasattr(user, "heal"):
                healed_amount = user.heal(effect_value)
                if healed_amount > 0:
                    message = f"You consume the {self.name} and regain {healed_amount} health."
                else:
                    message = f"You consume the {self.name}, but feel no different."
            else:
                message = f"You consume the {self.name}, but it has no effect."

        elif effect_type == "mana_restore":
            if hasattr(user, "restore_mana"):
                restored_amount = user.restore_mana(effect_value)
                if restored_amount > 0:
                    message = f"You consume the {self.name} and regain {restored_amount} mana."
                else:
                    message = f"You consume the {self.name}, but your mana is already full."
            else:
                message = f"You consume the {self.name}, but it has no effect."

        elif effect_type == "learn_spell":
            spell_id_to_learn = self.get_property("spell_to_learn")
            if not spell_id_to_learn:
                message = f"The {self.name} seems inert or misconfigured."
            elif not hasattr(user, "learn_spell"):
                message = f"You try to learn from the {self.name}, but cannot."
            else:
                learned, learn_message = user.learn_spell(spell_id_to_learn)
                if learned:
                    message = f"{FORMAT_SUCCESS}{learn_message}{FORMAT_RESET}"
                else:
                    message = f"{FORMAT_ERROR}{learn_message}{FORMAT_RESET}"
                    consumed = False

        elif effect_type == "apply_dot":
            dot_name = self.get_property("dot_name")
            dot_duration = self.get_property("dot_duration")
            dot_damage_per_tick = self.get_property("dot_damage_per_tick")
            dot_tick_interval = self.get_property("dot_tick_interval")
            dot_damage_type = self.get_property("dot_damage_type")

            if not all([dot_name, dot_duration, dot_damage_per_tick, dot_tick_interval, dot_damage_type]):
                message = f"The {self.name} seems improperly configured."
            else:
                target = user
                if hasattr(target, 'apply_effect'):
                    dot_data = {
                        "type": "dot", "name": dot_name, "base_duration": dot_duration,
                        "damage_per_tick": dot_damage_per_tick, "tick_interval": dot_tick_interval,
                        "damage_type": dot_damage_type, "source_id": getattr(user, 'obj_id', None)
                    }
                    success, _ = target.apply_effect(dot_data, time.time())
                    if success:
                        message = f"You feel a sickly sensation as you use the {self.name}."
                    else:
                        message = f"You use the {self.name}, but nothing seems to happen."
                else:
                    message = f"You can't seem to apply the effect of {self.name}."
        
        if consumed:
            self.update_property("uses", current_uses - 1)

        new_uses = self.get_property("uses")
        max_uses = self.get_property("max_uses", 1)
        if max_uses > 1 and new_uses > 0:
            message += f" ({new_uses}/{max_uses} uses remaining)."
        elif new_uses <= 0 and consumed:
            message += f" The {self.name} is used up."

        return message

    def examine(self) -> str:
        base_desc = super().examine()
        if self.properties.get("max_uses", 1) > 1:
            return f"{base_desc}\n\nUses remaining: {self.properties.get('uses', 0)}/{self.properties.get('max_uses', 1)}"
        return base_desc