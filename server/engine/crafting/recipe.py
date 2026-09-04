# engine/crafting/recipe.py
from typing import List, Dict, Any

class Recipe:
    def __init__(self, recipe_id: str, data: Dict[str, Any]):
        self.recipe_id = recipe_id
        self.name = data.get("name", "Unknown Recipe")
        self.description = data.get("description", "Creates an item.")
        
        # The template ID of the item created
        self.result_item_id = data.get("result_item_id")
        self.result_quantity = data.get("result_quantity", 1)
        
        # "anvil", "alchemy_table", "campfire", or None (handcrafting)
        self.station_required = data.get("station_required")
        
        # List of dicts: {"item_id":Str, "quantity":Int}
        self.ingredients: List[Dict[str, Any]] = data.get("ingredients", [])
        
    @property
    def station_display(self) -> str:
        if not self.station_required:
            return "Handcrafting"
        return self.station_required.replace("_", " ").title()