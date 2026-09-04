# engine/magic/spell_registry.py
"""
Registry of all available spells in the game, loaded from data files.
"""
import json
import os
from typing import Dict, Optional
from engine.magic.spell import Spell
from engine.utils.logger import Logger

# The registry is now populated at runtime by the loader.
SPELL_REGISTRY: Dict[str, Spell] = {}

def load_spells_from_json(data_root: str) -> dict[str, int]:
    """
    Scans the data/magic directory for all .json files, loads them,
    creates Spell objects, and populates the SPELL_REGISTRY.
    """
    stats = {
        "files_loaded": 0,
        "spells_loaded": 0,
        "overwrites": 0,
        "file_errors": 0,
        "dir_missing": 0,
    }

    if not data_root:
        raise ValueError("Spell loading requires a content-set data root.")
    magic_dir = os.path.join(data_root, "magic")
    if not os.path.isdir(magic_dir):
        stats["dir_missing"] = 1
        Logger.error("SpellRegistry", f"Magic data directory not found at '{magic_dir}'.")
        return stats

    # Loading definitions should be idempotent for each run. Clearing here
    # avoids repeated overwrite noise when definitions are reloaded.
    SPELL_REGISTRY.clear()

    for filename in os.listdir(magic_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(magic_dir, filename)
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    stats["files_loaded"] += 1
                    for spell_id, spell_data in data.items():
                        if spell_id in SPELL_REGISTRY:
                            stats["overwrites"] += 1
                        spell_object = Spell.from_dict(spell_id, spell_data)
                        register_spell(spell_object)
                        stats["spells_loaded"] += 1
            except json.JSONDecodeError:
                stats["file_errors"] += 1
                Logger.error("SpellRegistry", f"Could not decode JSON from '{file_path}'. Check for syntax errors.")
            except Exception as e:
                stats["file_errors"] += 1
                Logger.error("SpellRegistry", f"An unexpected error occurred while loading spells from '{filename}': {e}")
    if stats["overwrites"] > 0:
        Logger.warning(
            "SpellRegistry",
            f"Overwrote {stats['overwrites']} duplicate spell definition(s) while loading {stats['files_loaded']} file(s).",
        )
    return stats

def register_spell(spell: Spell):
    """Adds a spell to the registry."""
    SPELL_REGISTRY[spell.spell_id] = spell

def get_spell(spell_id: str) -> Optional[Spell]:
    """Retrieves a spell definition from the registry."""
    return SPELL_REGISTRY.get(spell_id)

def get_spell_by_name(spell_name: str) -> Optional[Spell]:
    """Finds a spell by its name (case-insensitive)."""
    search_name = spell_name.lower()
    for spell in SPELL_REGISTRY.values():
        if spell.name.lower() == search_name:
            return spell
    return None
