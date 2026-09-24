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

def load_spells_from_json(content_root: str) -> dict[str, int]:
    """
    Scans the content set's ability definitions and registers them.

    The directory is content's to name. `abilities/` is what a set that does not
    call them spells uses; `magic/` is kept because that is what the first
    content set named it, and renaming a directory to satisfy an engine
    preference is exactly the coupling this avoids.
    """
    stats = {
        "files_loaded": 0,
        "spells_loaded": 0,
        "overwrites": 0,
        "file_errors": 0,
        "dir_missing": 0,
    }

    if not content_root:
        raise ValueError("Spell loading requires a content-set data root.")
    magic_dir = ""
    for candidate in ("abilities", "magic"):
        path = os.path.join(content_root, candidate)
        if os.path.isdir(path):
            magic_dir = path
            break
    if not magic_dir:
        stats["dir_missing"] = 1
        Logger.error(
            "SpellRegistry",
            "No ability definitions found: expected 'abilities' or 'magic' under '%s'." % content_root,
        )
        return stats

    # Loading definitions should be idempotent for each run. Clearing here
    # avoids repeated overwrite noise when definitions are reloaded.
    SPELL_REGISTRY.clear()

    for filename in os.listdir(magic_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(magic_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                stats["file_errors"] += 1
                Logger.error("SpellRegistry", f"Could not decode JSON from '{file_path}'. Check for syntax errors.")
                continue
            if not isinstance(data, dict):
                stats["file_errors"] += 1
                Logger.error("SpellRegistry", f"'{filename}' must be an object of ability id -> ability.")
                continue
            stats["files_loaded"] += 1
            # Each ability is built on its own: one the engine refuses used to stop
            # every later ability in the same file from registering. `_` keys are
            # annotations, as everywhere else in content.
            for spell_id, spell_data in data.items():
                if str(spell_id).startswith("_"):
                    continue
                try:
                    spell_object = Spell.from_dict(spell_id, spell_data)
                except Exception as e:
                    stats["file_errors"] += 1
                    Logger.error("SpellRegistry", f"Ability '{spell_id}' in '{filename}' was not loaded: {e}")
                    continue
                if spell_id in SPELL_REGISTRY:
                    stats["overwrites"] += 1
                register_spell(spell_object)
                stats["spells_loaded"] += 1
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
