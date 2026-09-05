# engine/items/affix_data.py
"""
Procedural item affix (prefix/suffix) data, loaded from the selected content
package. Content sets provide their own via <content_root>/items/affixes.json
(see content_sets/fantasy_frontier/data/items/affixes.json for a worked
example); a content set that omits the file simply rolls no affixes.
"""
import json
import os

# Allowed Types: "Weapon", "Armor", "Jewelry" (Neck/Ring implied by slot), "All"
PREFIXES: dict = {}
SUFFIXES: dict = {}

# Text used when LootGenerator merges stat modifiers into a generated
# equip_effect with no named buff. "{item_name}" is substituted at use time.
GENERATED_EFFECT_TEXT: dict = {
    "effect_name_pattern": "{item_name}",
    "description_suffix": "",
}


def configure_item_affixes(content_root: str) -> None:
    """Load procedural affix definitions from the selected content package."""
    path = os.path.join(content_root, "items", "affixes.json")
    data: dict = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as file:
            parsed = json.load(file)
        if isinstance(parsed, dict):
            data = parsed
    PREFIXES.clear(); PREFIXES.update(data.get("prefixes", {}))
    SUFFIXES.clear(); SUFFIXES.update(data.get("suffixes", {}))
    GENERATED_EFFECT_TEXT["effect_name_pattern"] = data.get("generated_effect_name_pattern", "{item_name}")
    GENERATED_EFFECT_TEXT["description_suffix"] = data.get("generated_description_suffix", "")
