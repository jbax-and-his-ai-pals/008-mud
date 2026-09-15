# engine/items/consumable.py
import time
from typing import Optional
from engine.items.item import Item

class Consumable(Item):
    def __init__(self, obj_id: Optional[str] = None, name: str = "Unknown Consumable",
                 description: str = "No description", weight: float = 0.5,
                 value: int = 5, uses: int = 1, effect_value: int = 10,
                 effect_type: str = "heal", **kwargs):
        
        # Templates (e.g. unique learn-spell scrolls) may explicitly declare
        # stackable=False even though uses==1 -- honor that override instead
        # of silently discarding it, otherwise every uses==1 consumable is
        # forced stackable and distinct procedurally-generated instances
        # (each with different properties, like a scroll's spell_to_learn)
        # collapse into a single inventory stack.
        explicit_stackable = kwargs.pop('stackable', None)
        is_stackable = explicit_stackable if explicit_stackable is not None else (uses == 1)

        super().__init__(
            obj_id=obj_id, name=name, description=description, weight=weight,
            value=value, stackable=is_stackable,
            uses=uses, max_uses=uses, effect_value=effect_value, effect_type=effect_type,
            **kwargs
        )
        self.update_property("stackable", is_stackable)
    
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
                # Left unformatted, like every other branch here -- use_handler
                # already wraps the returned message in FORMAT_HIGHLIGHT, so
                # adding FORMAT_SUCCESS/FORMAT_ERROR here doubles up the tags
                # (e.g. "[[GREEN]][[RED]]...[[/]][[/]]").
                message = learn_message
                if not learned:
                    consumed = False

        elif effect_type == "learn_recipe":
            recipe_id_to_learn = self.get_property("recipe_to_learn")
            if not recipe_id_to_learn:
                message = f"The {self.name} seems inert or misconfigured."
            elif not hasattr(user, "learn_recipe"):
                message = f"You try to learn from the {self.name}, but cannot."
            else:
                learned, learn_message = user.learn_recipe(recipe_id_to_learn)
                message = learn_message
                if not learned:
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
                    target_world = getattr(target, "world", None)
                    success, _ = target.apply_effect(dot_data, target_world.clock.now() if target_world else time.time())
                    if success:
                        message = f"You feel a sickly sensation as you use the {self.name}."
                    else:
                        message = f"You use the {self.name}, but nothing seems to happen."
                else:
                    message = f"You can't seem to apply the effect of {self.name}."

        elif effect_type == "apply_effect":
            # Keep temporary consumable effects content-authored.  The same
            # status-effect representation powers spells and equipment, so a
            # tonic can grant resist_poison without a one-off item class or a
            # second expiry system.
            effect_data = self.get_property("effect_data")
            if (
                not isinstance(effect_data, dict)
                or not isinstance(effect_data.get("name"), str)
                or not effect_data["name"].strip()
                or not isinstance(effect_data.get("type"), str)
                or not effect_data["type"].strip()
            ):
                consumed = False
                message = f"The {self.name} seems improperly configured."
            elif not hasattr(user, "apply_effect"):
                consumed = False
                message = f"You can't seem to apply the effect of the {self.name}."
            else:
                target_world = getattr(user, "world", None)
                current_time = target_world.clock.now() if target_world else time.time()
                success, _ = user.apply_effect(effect_data, current_time)
                if success:
                    message = f"You consume the {self.name}. {effect_data['name']} takes hold."
                else:
                    consumed = False
                    message = f"You use the {self.name}, but nothing seems to happen."

        elif effect_type == "cleanse":
            # Antidotes are deliberately data-driven too.  use already
            # supplies a target for "use <item> on <name>"; otherwise a
            # draught treats its user.
            effect_tags = self.get_property("effect_tags")
            target = kwargs.get("target") or user
            if (
                not isinstance(effect_tags, list)
                or not effect_tags
                or any(not isinstance(tag, str) or not tag.strip() for tag in effect_tags)
            ):
                consumed = False
                message = f"The {self.name} seems improperly configured."
            elif not hasattr(target, "remove_effects_by_tag"):
                consumed = False
                message = f"The {self.name} cannot be applied to that target."
            else:
                removed = []
                for tag in effect_tags:
                    removed.extend(target.remove_effects_by_tag(tag))
                if removed:
                    message = f"You use the {self.name} and cleanse {getattr(target, 'name', 'the target')} of {len(removed)} affliction(s)."
                else:
                    message = f"You use the {self.name}, but find no matching affliction."

        elif effect_type == "target_damage":
            # A consumable can be used on an NPC in the room, which gives
            # authored flasks and similar throwables a real targeted action
            # while preserving the normal "use <item> on <target>" grammar.
            target = kwargs.get("target")
            damage_amount = self.get_property("damage_amount")
            damage_type = self.get_property("damage_type")
            if target is None:
                consumed = False
                message = f"Use the {self.name} on whom?"
            elif (
                isinstance(damage_amount, bool)
                or not isinstance(damage_amount, (int, float))
                or damage_amount <= 0
                or not isinstance(damage_type, str)
                or not damage_type.strip()
            ):
                consumed = False
                message = f"The {self.name} seems improperly configured."
            elif not hasattr(target, "take_damage"):
                consumed = False
                message = f"The {self.name} cannot harm that target."
            else:
                damage_taken = target.take_damage(int(damage_amount), damage_type)
                target_name = getattr(target, "name", "the target")
                if damage_taken > 0:
                    message = f"You hurl the {self.name} at {target_name}, dealing {damage_taken} {damage_type} damage."
                else:
                    message = f"You hurl the {self.name} at {target_name}, but it does no damage."
        
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
