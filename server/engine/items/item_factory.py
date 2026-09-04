# engine/items/item_factory.py
import inspect
import json
import os
import random
import copy
from typing import TYPE_CHECKING, Any, Dict, Optional, Type

from engine.items.gem import Gem
from engine.items.interactive import Interactive
from engine.items.item import Item
from engine.items.weapon import Weapon
from engine.items.armor import Armor
from engine.items.consumable import Consumable
from engine.items.container import Container
from engine.items.key import Key
from engine.items.treasure import Treasure
from engine.items.junk import Junk
from engine.items.lockpick import Lockpick
from engine.items.resource_node import ResourceNode
from engine.magic.spell_registry import SPELL_REGISTRY
from engine.utils.logger import Logger

if TYPE_CHECKING:
    from engine.world.world import World

ITEM_CLASS_MAP: Dict[str, Type[Item]] = {
     "Item": Item,
     "Weapon": Weapon,
     "Armor": Armor,
     "Consumable": Consumable,
     "Container": Container,
     "Key": Key,
     "Treasure": Treasure,
     "Junk": Junk,
     "Gem": Gem,
     "Lockpick": Lockpick,
     "ResourceNode": ResourceNode,
     "Interactive": Interactive,
}
    
class ItemFactory:
    """Factory class for creating items from templates or data."""

    @staticmethod
    def create_random_loot(template_id: str, world: 'World', level: int = 1) -> Optional['Item']:
        from engine.items.loot_generator import LootGenerator
        return LootGenerator.generate_loot(template_id, world, level)

    @staticmethod
    def create_item(item_type: str, **kwargs) -> Optional['Item']:
        cls = ITEM_CLASS_MAP.get(item_type)
        if not cls:
            Logger.warning("ItemFactory", f"Unknown item type '{item_type}' requested in create_item. Trying base Item.")
            cls = ITEM_CLASS_MAP.get("Item")

        if not cls:
             return None
        try:
            sig = inspect.signature(cls.__init__)
            valid_params = set(sig.parameters.keys())
            has_kwargs = any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())
            
            valid_kwargs = {}
            extra_properties = {}
            
            for k, v in kwargs.items():
                if k in valid_params or k == 'obj_id': 
                    valid_kwargs[k] = v
                elif has_kwargs: 
                    valid_kwargs[k] = v
                elif k not in ['name', 'description', 'weight', 'value', 'stackable', 'type']: 
                    extra_properties[k] = v
            
            item = cls(**valid_kwargs)
            for key, value in extra_properties.items(): 
                item.update_property(key, value)
            return item
        except Exception as e:
            Logger.error("ItemFactory", f"Error creating item type '{item_type}' with args {kwargs}: {e}")
            return None

    @staticmethod
    def _get_item_class(item_type_name: str) -> Optional[Type['Item']]:
        return ITEM_CLASS_MAP.get(item_type_name)

    @staticmethod
    def from_dict(data: Dict[str, Any], world: Optional['World'] = None) -> Optional['Item']:
        item_id = data.get("obj_id", data.get("id"))
        if item_id and world:
             overrides = data.get("properties_override", data.get("properties", {}))
             for key in ["name", "description", "weight", "value", "stackable"]:
                  if key in data: overrides[key] = data[key]
             item = ItemFactory.create_item_from_template(item_id, world, **overrides)
             if item: return item

        item_type_name = data.get("type", "Item")
        item_class = ITEM_CLASS_MAP.get(item_type_name)
        if not item_class:
             item_class = ITEM_CLASS_MAP.get("Item")
        
        if not item_class: return None
        
        try:
            if issubclass(item_class, Container): return item_class.from_dict(data, world)
            else: return item_class.from_dict(data)
        except Exception as e:
             Logger.error("ItemFactory", f"Error creating item type '{item_type_name}' from dict: {e}")
             return None

    @staticmethod
    def get_template(item_id: str, world: Optional['World'] = None) -> Optional[Dict[str, Any]]:
         if world and hasattr(world, 'item_templates'):
              return world.item_templates.get(item_id)
         return None

    @staticmethod
    def create_item_from_template(item_id: str, world: 'World', **overrides) -> Optional['Item']:
        if not world or not hasattr(world, 'item_templates'): return None
        template = world.item_templates.get(item_id)
        if not template:
            if item_id.startswith("item_scroll_") and "item_scroll_random" in world.item_templates:
                 template = world.item_templates.get("item_scroll_random")
                 
            if not template:
                Logger.error("ItemFactory", f"Item template '{item_id}' not found.")
                return None

        template_props = template.get("properties", {})
        if template_props.get("is_procedural", False):
            proc_type = template_props.get("procedural_type")
            new_template = copy.deepcopy(template)
            
            if proc_type == "random_spell_scroll":
                if overrides.get("spell_to_learn"):
                     pass
                else:
                    possible_spells = [s for s in SPELL_REGISTRY.values() if s.level_required > 0 and s.mana_cost > 0]
                    if possible_spells:
                        chosen_spell = random.choice(possible_spells)
                        new_template['name'] = f"Scroll of {chosen_spell.name}"
                        new_template['description'] = f"A scroll inscribed with the runes for the '{chosen_spell.name}' spell."
                        new_template['value'] = chosen_spell.level_required * 50 + 50
                        new_template['properties']['spell_to_learn'] = chosen_spell.spell_id
                        
                        if 'name' not in overrides: overrides['name'] = new_template['name']
                        if 'description' not in overrides: overrides['description'] = new_template['description']
                        if 'value' not in overrides: overrides['value'] = new_template['value']
                        if 'spell_to_learn' not in overrides: overrides['spell_to_learn'] = chosen_spell.spell_id
                        
            if 'is_procedural' in new_template['properties']:
                del new_template['properties']['is_procedural']
            if 'procedural_type' in new_template['properties']:
                del new_template['properties']['procedural_type']
                
            template = new_template

        item_type_name = template.get("type", "Item")
        item_class = ITEM_CLASS_MAP.get(item_type_name)

        if item_class is None:
            return None

        try:
            creation_args = template.copy()
            creation_args["obj_id"] = item_id
            
            template_properties = creation_args.pop("properties", {})
            
            if "properties_override" in overrides:
                 overrides.update(overrides.pop("properties_override"))

            creation_args.update(overrides)
            creation_args["world"] = world 

            sig = inspect.signature(item_class.__init__)
            valid_params = set(sig.parameters.keys())
            has_kwargs = any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())
            
            if has_kwargs:
                init_args = creation_args
            else:
                init_args = {k: v for k, v in creation_args.items() if k in valid_params or k == 'obj_id'}

            if 'equip_slot' in valid_params:
                if 'equip_slot' in overrides:
                    init_args['equip_slot'] = overrides['equip_slot']
                elif 'equip_slot' in template_properties:
                    init_args['equip_slot'] = template_properties['equip_slot']
            
            item = item_class(**init_args)

            if not hasattr(item, 'properties'): item.properties = {}
            
            for key, value in template_properties.items():
                 if key in overrides: continue
                 if key == 'equip_slot' and 'equip_slot' in init_args: continue
                 item.properties[key] = value

            if not has_kwargs:
                 for key, value in overrides.items():
                      if key not in valid_params and key != 'obj_id' and key != 'world':
                           item.properties[key] = value
            
            item.weight = getattr(item, 'weight', 0.0)
            item.value = getattr(item, 'value', 0)
            item.stackable = getattr(item, 'stackable', False)
            
            item.update_property("weight", item.weight)
            item.update_property("value", item.value)
            item.update_property("stackable", item.stackable)
            
            return item

        except Exception as e:
            Logger.error("ItemFactory", f"Error creating item '{item_id}': {e}")
            return None