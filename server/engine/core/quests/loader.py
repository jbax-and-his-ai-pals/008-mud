import os
import json
from typing import Dict, Any
from engine.utils.logger import Logger


def load_quest_templates(data_dir: str) -> Dict[str, Any]:
    """Every quest template in `quests/`, notes excluded.

    A `_`-prefixed key is an authoring note and a non-object value is not a quest,
    so both are skipped. Without that check the note itself was read as a quest:
    `"stages" not in q_data` on a *string* raises `TypeError`, the `except` below
    is outside the loop, and the whole file is abandoned — so one `_comment` in
    `quests.json` silently removed all 22 quests while the file stayed valid JSON
    with valid references.

    A single malformed entry is now skipped and reported rather than costing the
    file, which is the same rule `crafting_manager` learned for recipes.
    """
    templates = {}

    files = ["instances.json", "sagas.json", "quests.json"]
    for filename in files:
        path = os.path.join(data_dir, "quests", filename)
        if not os.path.exists(path): continue

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            Logger.error("QuestLoader", f"Error loading {path}: {e}")
            continue

        if not isinstance(data, dict):
            Logger.error("QuestLoader", f"{path} must contain an object of quest templates.")
            continue

        for q_id, q_data in data.items():
            # An authoring note is not a quest, and neither is a value that is
            # not an object. Both are the loader's business to skip, not to choke
            # on -- see the docstring for what choking on them cost.
            if str(q_id).startswith("_"):
                continue
            if not isinstance(q_data, dict):
                Logger.warning(
                    "QuestLoader",
                    f"Skipping quest '{q_id}' in {filename}: it must be an object, got "
                    f"{type(q_data).__name__}.",
                )
                continue

            try:
                # Normalization
                if "stages" not in q_data:
                    q_data["stages"] = [{
                        "stage_index": 0,
                        "description": q_data.get("description", "Complete the task."),
                        "objective": q_data.get("objective", {}),
                        "turn_in_id": q_data.get("giver_npc_template_id") or "quest_board"
                    }]

                # DEBUG CHECK
                for stage in q_data.get("stages", []):
                    if "spawn_on_entry" in stage:
                        Logger.debug("QuestLoader", f"Loaded spawn_on_entry for quest '{q_id}'")

                templates[q_id] = q_data
            except Exception as e:
                # One unusable quest does not take its file with it.
                Logger.error("QuestLoader", f"Skipping quest '{q_id}' in {filename}: {e}")

    return templates
