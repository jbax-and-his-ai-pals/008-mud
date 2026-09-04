import os
import json
from typing import Dict, Any
from engine.utils.logger import Logger

def load_quest_templates(data_dir: str) -> Dict[str, Any]:
    templates = {}
    
    files = ["instances.json", "sagas.json", "quests.json"]
    for filename in files:
        path = os.path.join(data_dir, "quests", filename)
        if not os.path.exists(path): continue
        
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                for q_id, q_data in data.items():
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
            Logger.error("QuestLoader", f"Error loading {path}: {e}")
            
    return templates